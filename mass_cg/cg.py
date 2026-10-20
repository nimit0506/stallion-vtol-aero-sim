"""
Centre of gravity of the pod-equipped Stallion from the GLB, plus static margin from the CFD
and the hover thrust split between the three motors.

  ..\\.venv\\Scripts\\python.exe cg.py [--wall-mm 0.8] [--infill 0.2] [--rho 0.54] [--payload-g 0]

Frame = CFD frame: x span (+right), y forward (nose +Y), z up. Metres.
Printed parts: LW-PLA, walls (wall-mm, solid) at the part's surface + infill fraction of the rest.
Components: catalogue masses placed at their CAD part; items not in the CAD (ESC, power board,
capacitor, wiring) are placed at the flight controller.
"""
import argparse
import csv
import json
import struct
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
GLB = HERE.parent / "geometry" / "source" / "stallion_v2_equipped_with_pod.glb"
POD = HERE.parent / "cfd_pod"               # CFD case: config.json (reference values) + results/forces.csv

# catalogue masses (g) for parts that exist in the CAD, matched by name prefix
COMPONENTS = {
    "BATTERY -": 700.0,                     # 4S 8000 mAh class pack (CAD label); not "BATTERY PAD"
    "MOTOR LEFT": 49.0, "MOTOR RIGHT": 49.0, "MOTOR TAIL": 49.0,   # EMAX ECO II 2807
    "TILT SERVO": 13.4,                     # TowerPro MG90D
    "V-TAIL SERVO": 12.0, "AILERON SERVO": 12.0,   # EMAX ES08MA II
    "RX -": 19.0,                           # FlySky FS-iA10B
    "FC -": 8.0,                            # Kakute F405-Wing Mini
    "USB EXT": 3.0,
    "LOCK SPRING": 1.0,
}
PROP_G = 7.0                                 # per motor, added at the motor
AT_FC_G = {"4-in-1 ESC": 12.0, "power board": 6.0, "capacitor C1": 4.0, "wiring, XT60, Y-cables": 35.0}
CARBON_RHO = 1.55                            # g/cm3, pultruded carbon tube


def read_parts(glb=GLB):
    """Volume (cm3), surface area (cm2), volume centroid and area centroid (m, CFD frame) of every
    mesh node in the GLB, read straight from the binary (keeps the CAD part names)."""
    # GLB = 12-byte header, then a JSON chunk (scene description) and a BIN chunk (vertex data)
    with open(glb, "rb") as f:
        f.read(12)
        clen, _ = struct.unpack("<II", f.read(8)); js = json.loads(f.read(clen))
        blen, _ = struct.unpack("<II", f.read(8)); buf = f.read(blen)
    CT = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}   # glTF component types
    NC = {"SCALAR": 1, "VEC3": 3}                                               # values per element

    def acc(i):
        """glTF accessor i as an (count, n) numpy view into the BIN chunk."""
        a = js["accessors"][i]; bv = js["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(buf, CT[a["componentType"]], a["count"] * NC[a["type"]], off).reshape(a["count"], -1)

    def mat(n):
        """Local 4x4 transform of a node (glTF stores matrices column-major, hence .T)."""
        if "matrix" in n:
            return np.array(n["matrix"]).reshape(4, 4).T
        M = np.eye(4)
        if "translation" in n: M[:3, 3] = n["translation"]
        return M   # trimesh export: matrix or translation only

    # world transform of every node = parent transforms chained down the scene tree
    world = {}
    def visit(i, P):
        M = P @ mat(js["nodes"][i]); world[i] = M
        for c in js["nodes"][i].get("children", []): visit(c, M)
    for r in js["scenes"][js.get("scene", 0)]["nodes"]: visit(r, np.eye(4))

    parts = []
    for i, n in enumerate(js["nodes"]):
        if "mesh" not in n: continue
        V = A = 0.0; cV = np.zeros(3); cA = np.zeros(3)     # volume, area and their first moments
        for p in js["meshes"][n["mesh"]]["primitives"]:
            v = acc(p["attributes"]["POSITION"]).astype(float)
            M = world.get(i, np.eye(4)); v = v @ M[:3, :3].T + M[:3, 3]
            v = np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])          # glTF Y-up -> CFD frame
            f = acc(p["indices"]).reshape(-1, 3).astype(int)
            a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
            # volume of a closed mesh = sum of signed tetrahedra (origin, a, b, c); each tet's
            # centroid is (0 + a + b + c) / 4, so the volume-weighted sum gives the volume centroid
            vol = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0         # signed tets to origin
            V += vol.sum(); cV += (vol[:, None] * (a + b + c) / 4.0).sum(0)
            # triangle areas and centroids -> surface area and area centroid (where the walls sit)
            ar = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
            A += ar.sum(); cA += (ar[:, None] * (a + b + c) / 3.0).sum(0)
        parts.append({"name": n.get("name", ""), "V": abs(V) * 1e6, "A": A * 1e4,   # m3 -> cm3, m2 -> cm2
                      "cV": cV / V if V else cA / A, "cA": cA / A})
    return parts


def build_items(parts, args):
    """(label, group, mass g, position m) for every mass in the aircraft."""
    items = []
    fc_pos = None
    for p in parts:
        nm = p["name"]
        comp = next((k for k in COMPONENTS if nm.startswith(k)), None)   # catalogue part?
        if nm.startswith("CARBON"):                  # carbon tubes: solid volume x carbon density
            items.append((nm, "carbon", p["V"] * CARBON_RHO, p["cV"]))
        elif comp:                                   # bought component: catalogue mass at its CAD centroid
            items.append((nm, "component", COMPONENTS[comp], p["cV"]))
            if comp.startswith("MOTOR"):
                items.append((nm.split(" -")[0] + " prop", "component", PROP_G, p["cV"]))
            if comp == "FC -":
                fc_pos = p["cV"]                     # anchor for the parts that aren't in the CAD
        else:                                        # printed LW-PLA
            t = args.wall_mm / 10.0                  # wall thickness, cm
            shell = min(p["A"] * t, p["V"])          # solid perimeter walls (cm3), never more than the part
            infill = args.infill * (p["V"] - shell)  # the rest of the volume at the infill fraction
            items.append((nm, "printed", shell * args.rho, p["cA"]))          # walls sit on the surface
            items.append((nm + " (infill)", "printed", infill * args.rho, p["cV"]))
        if nm.startswith("VIAL POD - direct") and args.payload_g:
            items.append(("pod payload", "payload", args.payload_g, p["cV"]))
    for k, m in AT_FC_G.items():
        items.append((k + " (placed at FC)", "component", m, fc_pos))
    return items


def analyse(parts, items, args):
    """Total mass and CG, static margin and trim from the pod CFD, and the hover thrust split."""
    m = np.array([i[2] for i in items]); P = np.array([i[3] for i in items])
    M = m.sum(); cg = (m[:, None] * P).sum(0) / M      # CG = mass-weighted mean position
    groups = {}                                         # mass per group: printed / carbon / component
    for _, g, mi, _ in items:
        groups[g] = groups.get(g, 0) + mi

    # --- static margin from the CFD (converged angles 0 and 4 deg) -------------------
    # dCm/dCL about the reference point: the neutral point is where that slope would be zero
    cfg = json.loads((POD / "config.json").read_text(encoding="utf-8-sig"))
    ref = cfg["reference"]; c = ref["length_m"]; y_ref = ref["moment_center_m"][1]
    with open(POD / "results" / "forces.csv", newline="") as fh:
        F = {float(r["aoa_deg"]): r for r in csv.DictReader(fh)}
    cl0, cl4 = float(F[0]["CL"]), float(F[4]["CL"])
    cm0, cm4 = float(F[0]["Cm"]), float(F[4]["Cm"])
    dcm = (cm4 - cm0) / (cl4 - cl0)
    y_np = y_ref + c * dcm                       # neutral point (forward = +y)
    sm = (cg[1] - y_np) / c                      # static margin, fraction of MAC (+ = CG ahead of NP = stable)
    # pitching moment about the CG (lift acts through the reference point's moment model)
    cm_cg = {a: float(F[a]["Cm"]) - float(F[a]["CL"]) * (cg[1] - y_ref) / c for a in (0.0, 4.0)}
    # CL where Cm about the CG = 0 (linear between 0 and 4 deg)
    k = (cm_cg[4.0] - cm_cg[0.0]) / (cl4 - cl0)
    cl_trim = cl0 - cm_cg[0.0] / k

    # --- hover thrust split ----------------------------------------------------------
    # moment balance about the pitch axis: front pair and tail motor must share the weight so that
    # their resultant passes through the CG -> tail share = distance CG-to-front / front-to-tail
    mot = {p["name"].split(" -")[0]: p["cV"] for p in parts if p["name"].startswith("MOTOR ")}
    yl, yr, yt = mot["MOTOR LEFT"][1], mot["MOTOR RIGHT"][1], mot["MOTOR TAIL"][1]
    y_front = 0.5 * (yl + yr)
    tail_frac = (y_front - cg[1]) / (y_front - yt)
    xl, xr = mot["MOTOR LEFT"][0], mot["MOTOR RIGHT"][0]
    right_share = (cg[0] - xl) / (xr - xl)       # of the front pair (tail motor on centreline)

    W = M / 1000 * 9.81                          # weight, N
    out = {
        "settings": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "mass_g": {k: round(v) for k, v in groups.items()} | {"total": round(M)},
        "cg_m": np.round(cg, 4).tolist(),
        "aero": {"reference_point_y_m": y_ref, "mac_m": c, "dCm_dCL": round(dcm, 4),
                 "neutral_point_y_m": round(y_np, 4), "static_margin_pct_mac": round(sm * 100, 1),
                 "cm_about_cg": {f"{a:g}deg": round(v, 4) for a, v in cm_cg.items()},
                 "trim_CL_as_built": round(cl_trim, 3)},
        "cruise_CL_needed_20ms": round(W / (245.0 * ref["area_m2"]), 3),   # 245 Pa = dynamic pressure at 20 m/s
        "hover": {"motor_y_m": {"front pair": round(y_front, 4), "tail": round(yt, 4)},
                  "tail_motor_share_pct": round(tail_frac * 100, 1),
                  "each_front_motor_pct": round((1 - tail_frac) * 50, 1),
                  "right_front_vs_left_pct": round(right_share * 100, 1)},
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", type=Path, default=GLB)
    ap.add_argument("--wall-mm", type=float, default=0.8)
    ap.add_argument("--infill", type=float, default=0.2)
    ap.add_argument("--rho", type=float, default=0.54, help="LW-PLA printed density g/cm3")
    ap.add_argument("--payload-g", type=float, default=0.0, help="payload in the pod")
    ap.add_argument("--report", type=Path, default=HERE / "cg_report.json")
    args = ap.parse_args()

    parts = read_parts(args.glb)
    items = build_items(parts, args)
    out = analyse(parts, items, args)
    out["settings"]["glb"] = str(args.glb); out["settings"]["report"] = str(args.report)
    args.report.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    # the 12 heaviest items: what actually sets the CG
    heavy = sorted(items, key=lambda i: -i[2])[:12]
    print("\nheaviest items:")
    for nm, g, mi, pos in heavy:
        print(f"  {nm[:44]:44s} {mi:7.1f} g   y={pos[1]:+.3f} z={pos[2]:+.3f}")
    np.save(HERE / "cg_items.npy", np.array([(i[2], *i[3]) for i in items]))   # (mass, x, y, z) for plots


if __name__ == "__main__":
    main()
