"""
Step 0 (pod variant) - GLB -> raw STL in the pipeline's frame.

The GLB (trimesh export, glTF Y-up, metres) holds 96 separate CAD parts: skins, internal
electronics, servos, carbon spars, and the pod. Here they are only merged and rotated into the frame
01_prep_stl.py expects (nose +Y, up +Z, span X), then written as binary STL in mm. All repair
happens in 01_prep_stl.py (the shrink-wrap drops the internal parts: the outside air can't reach them).

  ..\\.venv\\Scripts\\python.exe 00_import_glb.py [--input path.glb]
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pyvista as pv
import vtk

HERE = Path(__file__).resolve().parent
DEFAULT_IN = HERE.parent / "geometry" / "source" / "stallion_v2_equipped_with_pod.glb"


def read_glb(path):
    """Every mesh in the GLB's scene as a triangulated PolyData (node transforms already applied by VTK)."""
    r = vtk.vtkGLTFReader()
    r.SetFileName(str(path))
    r.Update()
    parts = []

    def walk(b):
        """The reader returns nested multiblocks (scene -> nodes -> primitives): collect the leaves."""
        for i in range(b.n_blocks):
            blk = b[i]
            if isinstance(blk, pv.MultiBlock):
                walk(blk)
            elif blk is not None:
                parts.append(blk.extract_surface().triangulate())
    walk(pv.wrap(r.GetOutput()))
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_IN))
    ap.add_argument("--output", default=str(HERE / "input" / "stallion_pod_raw.stl"))
    args = ap.parse_args()

    parts = read_glb(args.input)
    m = pv.merge(parts)                       # one polydata; parts still overlap (the wrap fixes that)
    # glTF Y-up -> pipeline frame: x stays (span), y' = -z (nose +Y), z' = y (up +Z)
    p = m.points.copy()
    m.points = np.column_stack([p[:, 0], -p[:, 2], p[:, 1]]) * 1000.0   # metres -> mm
    Path(args.output).parent.mkdir(exist_ok=True)
    m.save(args.output, binary=True)
    # quick sanity print: part count and the overall size in metres
    b = np.asarray(m.bounds).reshape(3, 2) / 1000.0
    info = {"input": args.input, "parts": len(parts), "facets": int(m.n_cells),
            "bounds_m": b.round(4).tolist()}
    print(json.dumps(info, indent=2))
    print(f"Wrote {args.output} (mm)")


if __name__ == "__main__":
    main()
