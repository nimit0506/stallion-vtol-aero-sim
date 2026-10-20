"""
Export the aircraft wall (face pressure + wall shear + face geometry) of the solved cases to .npz, so the
forces can be split by region in numpy (..\box_effect\box_effect.py). This copy: the no-box case only.

  ..\\.venv\\Scripts\\python.exe export_wall.py         -> results\\wall_nobox_aoa{0,4}.npz
"""
from pathlib import Path

import numpy as np
import ansys.fluent.core as pf
from ansys.fluent.core.fields.field_data.requests import (ScalarFieldDataRequest, SurfaceDataType,
                                                          SurfaceFieldDataRequest)

HERE = Path(__file__).resolve().parent
CASES = {"nobox": HERE / "results"}                  # name -> solved case folder
ANGLES = (0, 4)                       # the converged ones; 8 deg is an unconverged last iterate
# per-face pressure (gauge, Pa) and wall shear stress (Pa): together they give the force on each face
FIELDS = ("pressure", "x-wall-shear", "y-wall-shear", "z-wall-shear")


def area_vectors(verts, conn):
    """Newell area vector of every polygon face (orientation as Fluent stores it)."""
    out = np.zeros((len(conn), 3))
    for k, f in enumerate(conn):
        p = verts[f]; q = np.roll(p, -1, axis=0)
        out[k] = 0.5 * np.cross(p, q).sum(0)
    return out


def main():
    s = pf.launch_fluent(mode="solver", precision="double", dimension=3, processor_count=4,
                         ui_mode="no_gui", cwd=str(HERE / "results"), start_timeout=300)
    try:
        for name, res in CASES.items():
            geo = None                                   # face geometry, read once per case
            for i, a in enumerate(ANGLES):
                if i == 0:                               # first angle: case (mesh) + data
                    s.settings.file.read_case_data(file_name=str(res / f"aoa_{a}.cas.h5"))
                else:                                    # same mesh: only swap the data
                    s.settings.file.read_data(file_name=str(res / f"aoa_{a}.dat.h5"))
                walls = list(s.settings.setup.boundary_conditions.wall.keys())   # just "aircraft"
                fd = s.fields.field_data
                if geo is None:
                    # face vertices + connectivity -> area vectors; centroids for moments and regions
                    sd = fd.get_field_data(SurfaceFieldDataRequest(
                        surfaces=walls, data_types=[SurfaceDataType.Vertices, SurfaceDataType.FacesConnectivity,
                                                    SurfaceDataType.FacesCentroid]))
                    geo = {}
                    for w in walls:
                        d = sd[w]
                        geo[w] = (np.asarray(d.face_centroids).reshape(-1, 3),
                                  area_vectors(np.asarray(d.vertices).reshape(-1, 3), d.connectivity))
                    print(name, {w: len(g[0]) for w, g in geo.items()}, flush=True)
                # one .npz per case and angle: <zone>__centroid, <zone>__area, <zone>__<field>
                out = {}
                for w in walls:
                    out[f"{w}__centroid"], out[f"{w}__area"] = geo[w]
                    for fld in FIELDS:
                        # node_value=False: face (cell) values, matching the face centroids/areas
                        v = fd.get_field_data(ScalarFieldDataRequest(field_name=fld, surfaces=[w], node_value=False))
                        out[f"{w}__{fld}"] = np.asarray(v[w])
                np.savez(HERE / "results" / f"wall_{name}_aoa{a}.npz", **out)
                print("wrote", name, a, flush=True)
    finally:
        s.exit()                                         # free the Student licence


if __name__ == "__main__":
    main()
