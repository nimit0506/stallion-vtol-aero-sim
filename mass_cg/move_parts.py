"""
Move parts of the GLB and write a new GLB (the original is never touched), with a clearance check.

  ..\\.venv\\Scripts\\python.exe move_parts.py --move "VIAL POD=0,120,1.5" --out ..\\moved.glb
  ..\\.venv\\Scripts\\python.exe move_parts.py --move "VIAL POD=0,120,0" --move "BATTERY -=0,10,0" --out x.glb

--move "NAME PREFIX=dx,dy,dz": millimetres in the CFD frame (x span +right, y forward, z up). Every node
whose name starts with the prefix gets that offset (added to any translation it already has).
The GLB is glTF Y-up, so the offset is stored as glTF translation (dx, dz, -dy) / 1000.

The clearance check runs the moved parts against every other part whose box comes within 10 mm.
It reports triangle contacts (exact) and the smallest vertex-to-surface gap, before and after the move.
"""
import argparse
import json
import struct
from pathlib import Path

import numpy as np
import pyvista as pv
import vtk

HERE = Path(__file__).resolve().parent
GLB = HERE.parent / "geometry" / "source" / "stallion_v2_equipped_with_pod.glb"
CT = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}   # glTF component types
NC = {"SCALAR": 1, "VEC3": 3}                                               # values per element


def load_glb(path):
    """(scene JSON as dict, BIN chunk bytes). GLB = 12-byte header, JSON chunk, BIN chunk."""
    with open(path, "rb") as f:
        f.read(12)                                # magic 'glTF', version, total length
        clen, _ = struct.unpack("<II", f.read(8)); js = json.loads(f.read(clen))
        blen, _ = struct.unpack("<II", f.read(8)); buf = f.read(blen)
    return js, buf


def save_glb(path, js, buf):
    """Write a GLB from the (edited) JSON and the untouched BIN chunk."""
    j = json.dumps(js, separators=(",", ":")).encode()
    j += b" " * (-len(j) % 4)                     # JSON chunk padded with spaces
    b = buf + b"\0" * (-len(buf) % 4)             # BIN chunk padded with zeros (4-byte alignment)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(j) + 8 + len(b)))   # 'glTF', v2, length
        f.write(struct.pack("<II", len(j), 0x4E4F534A)); f.write(j)                  # 'JSON' chunk
        f.write(struct.pack("<II", len(b), 0x004E4942)); f.write(b)                  # 'BIN' chunk


def parse_move(s):
    """'NAME PREFIX=dx,dy,dz' -> (prefix, offset array in mm). rsplit: names may contain '='."""
    name, xyz = s.rsplit("=", 1)
    return name, np.array([float(t) for t in xyz.split(",")])


def apply_moves(js, moves):
    """moves: list of (prefix, offset mm CFD). Returns the node indices that moved."""
    moved = set()
    for prefix, d in moves:
        hit = [i for i, n in enumerate(js["nodes"]) if n.get("name", "").startswith(prefix)]
        if not hit:
            raise SystemExit(f"no part name starts with {prefix!r}")
        for i in hit:
            n = js["nodes"][i]
            # this GLB's nodes carry no transform (geometry is baked in world coordinates); refuse
            # anything else rather than silently composing transforms wrongly
            if "matrix" in n or "rotation" in n or "scale" in n:
                raise SystemExit(f"{n['name']}: node has a matrix/rotation/scale, not handled")
            t = np.array(n.get("translation", [0.0, 0.0, 0.0]))
            # CFD (x, y, z) mm -> glTF (x, z, -y) m, added to any earlier move
            n["translation"] = (t + np.array([d[0], d[2], -d[1]]) / 1000.0).tolist()
            moved.add(i)
    return moved


def part_meshes(js, buf):
    """{node index: (name, PolyData in mm, CFD frame)} with node translations applied (root nodes only)."""
    def acc(i):
        """glTF accessor i as an (count, n) numpy view into the BIN chunk."""
        a = js["accessors"][i]; bv = js["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(buf, CT[a["componentType"]], a["count"] * NC[a["type"]], off).reshape(a["count"], -1)

    out = {}
    for i, n in enumerate(js["nodes"]):
        if "mesh" not in n: continue
        pts, fcs, k = [], [], 0                   # k = vertex offset when a mesh has several primitives
        for p in js["meshes"][n["mesh"]]["primitives"]:
            v = acc(p["attributes"]["POSITION"]).astype(float) + np.array(n.get("translation", [0, 0, 0]))
            pts.append(np.column_stack([v[:, 0], -v[:, 2], v[:, 1]]) * 1000.0)   # glTF m -> CFD frame mm
            fcs.append(acc(p["indices"]).reshape(-1, 3).astype(np.int64) + k); k += len(v)
        f = np.vstack(fcs)
        # VTK face array: [3, a, b, c, 3, a, b, c, ...]
        out[i] = (n.get("name", ""), pv.PolyData(np.vstack(pts), np.column_stack([np.full(len(f), 3), f]).ravel()))
    return out


def _contacts(a, b):
    """Number of intersecting triangle pairs between meshes a and b (0 = no touching or overlap)."""
    c = vtk.vtkCollisionDetectionFilter()
    c.SetInputData(0, a); c.SetInputData(1, b)
    c.SetTransform(0, vtk.vtkTransform()); c.SetTransform(1, vtk.vtkTransform())   # identity: test as is
    c.SetCollisionModeToAllContacts(); c.Update()
    return c.GetNumberOfContacts()


def _gap(a, b):
    """smallest vertex-to-surface distance either way (mm)."""
    best = np.inf
    for src, dst in ((a, b), (b, a)):             # both ways: a coarse mesh's vertices can miss the other
        d = vtk.vtkImplicitPolyDataDistance(); d.SetInput(dst)
        best = min(best, min(abs(d.EvaluateFunction(p)) for p in src.points))
    return best


def clearance(meshes, moved, margin=10.0):
    """[(moved part, other part, contacts, gap mm)] for parts whose bounding boxes come within margin."""
    rows = []
    for i in sorted(moved):
        na, a = meshes[i]
        lo, hi = np.array(a.bounds[0::2]) - margin, np.array(a.bounds[1::2]) + margin   # grown box
        for j, (nb, b) in meshes.items():
            if j in moved: continue               # parts moved together don't count against each other
            blo, bhi = np.array(b.bounds[0::2]), np.array(b.bounds[1::2])
            if np.any(bhi < lo) or np.any(blo > hi): continue   # boxes apart: can't be close
            rows.append((na, nb, _contacts(a, b), _gap(a, b)))
    return rows


def print_clearance(title, rows):
    """One line per nearby pair: contacts, or the gap in mm."""
    print(title)
    if not rows:
        print("  nothing within 10 mm")
    for na, nb, c, g in rows:
        state = f"TOUCH/OVERLAP ({c} contacts)" if c else f"gap {g:5.1f} mm"
        print(f"  {na[:34]:34s} vs {nb[:34]:34s} {state}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", type=Path, default=GLB)
    ap.add_argument("--move", action="append", required=True, help='"NAME PREFIX=dx,dy,dz" mm, CFD frame')
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.resolve() == args.glb.resolve():
        raise SystemExit("--out must differ from the input GLB")

    js, buf = load_glb(args.glb)
    moves = [parse_move(s) for s in args.move]
    before = part_meshes(js, buf)                 # layout before (for comparison)
    moved = apply_moves(js, moves)                # edits js in place
    after = part_meshes(js, buf)
    print_clearance("clearance BEFORE the move:", clearance(before, moved))
    print_clearance("clearance AFTER the move:", clearance(after, moved))
    save_glb(args.out, js, buf)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
