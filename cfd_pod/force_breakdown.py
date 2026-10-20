"""
Split lift / drag / pitching moment of the pod and clean CFD by region of the aircraft skin.

  ..\\.venv\\Scripts\\python.exe force_breakdown.py      (after export_wall.py)

The totals are checked against Fluent's own CL/CD/Cm in forces.csv before anything is split.
Regions (CFD frame, m): box = everything below the belly under the fuselage; boom fronts = the
front ends of the motor booms (tilt motors in the equipped model); the rest = wing, fuselage, tail.
"Interference" = how much the forces on the unchanged parts change between the clean and pod runs.
"""
import csv
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8-sig"))
REF = CFG["reference"]
S, C, RC = REF["area_m2"], REF["length_m"], np.array(REF["moment_center_m"])   # same values Fluent used
Q = 0.5 * CFG["flight"]["density_kg_m3"] * CFG["flight"]["speed_m_s"] ** 2      # dynamic pressure, Pa
RES = {"pod": HERE / "results", "clean": HERE.parent / "cfd_clean" / "results"}


def regions(c):
    """Boolean masks over the wall faces (by face centroid c, m)."""
    x, y, z = c.T
    box = (z < -0.003) & (np.abs(x) < 0.06) & (y > -0.40) & (y < -0.17)   # below the belly, under the fuselage
    boom = (np.abs(x) > 0.26) & (np.abs(x) < 0.37) & (y > -0.17)          # boom ends ahead of the wing
    return {"box": box, "boom fronts": boom & ~box, "rest": ~box & ~boom}


def coeffs(F, M, a):
    """Force F (N) and moment M (N m, about RC) -> CL, CD, Cm at angle a (deg). Cm is about +x (nose-up +)."""
    a = math.radians(a)
    drag = np.array([0, -math.cos(a), math.sin(a)])      # along the free stream (air comes from +y, below)
    lift = np.array([0, math.sin(a), math.cos(a)])       # perpendicular to it, upward
    return F @ lift / (Q * S), F @ drag / (Q * S), M[..., 0] / (Q * S * C)


def load(case, a):
    """Face centroids, area vectors, pressure and wall-shear vectors of one exported case/angle."""
    d = np.load(HERE / "results" / f"wall_{case}_aoa{a}.npz")     # export_wall.py writes both here
    c, A = d["aircraft__centroid"], d["aircraft__area"]
    p = d["aircraft__pressure"]
    tau = np.column_stack([d[f"aircraft__{k}-wall-shear"] for k in "xyz"])
    return c, A, p, tau


def main():
    # Fluent's own totals, for the check
    ref = {}
    for case, res in RES.items():
        with open(res / "forces.csv", newline="") as fh:
            for r in csv.DictReader(fh):
                ref[(case, float(r["aoa_deg"]))] = (float(r["CL"]), float(r["CD"]), float(r["Cm"]))

    # sign conventions: pick the one that reproduces Fluent's totals (checked on every case/angle)
    best = None
    for sp in (1, -1):
        for st in (1, -1):
            err = 0
            for case in RES:
                for a in (0, 4):
                    c, A, p, tau = load(case, a)
                    # face force = pressure x area vector + shear stress x face area
                    F = sp * p[:, None] * A + st * tau * np.linalg.norm(A, axis=1)[:, None]
                    M = np.cross(c - RC, F).sum(0)               # moment about the reference point
                    cl, cd, cm = coeffs(F.sum(0), M, a)
                    err += sum(abs(u - v) for u, v in zip((cl, cd, cm), ref[(case, float(a))]))
            if best is None or err < best[0]:
                best = (err, sp, st)
    _, sp, st = best

    # split: sum the face forces (and their moments) over each region's faces
    out = {}
    for a in (0, 4):
        row = {}
        for case in RES:
            c, A, p, tau = load(case, a)
            Fp = sp * p[:, None] * A                                   # pressure force per face
            Fv = st * tau * np.linalg.norm(A, axis=1)[:, None]         # viscous (friction) force per face
            tot = coeffs((Fp + Fv).sum(0), np.cross(c - RC, Fp + Fv).sum(0), a)
            reg = {}
            for name, m in regions(c).items():
                F = (Fp + Fv)[m]
                cl, cd, cm = coeffs(F.sum(0), np.cross(c[m] - RC, F).sum(0), a)
                _, cdp, _ = coeffs(Fp[m].sum(0), np.zeros(3), a)       # pressure part of the drag only
                reg[name] = {"CL": cl, "CD": cd, "CD_pressure": cdp, "Cm": cm, "drag_N": cd * Q * S,
                             "lift_N": cl * Q * S, "area_cm2": np.linalg.norm(A[m], axis=1).sum() * 1e4}
            row[case] = {"check_vs_fluent": {"CL": [tot[0], ref[(case, float(a))][0]],
                                             "CD": [tot[1], ref[(case, float(a))][1]],
                                             "Cm": [tot[2], ref[(case, float(a))][2]]},
                         "regions": reg}
        out[f"{a}deg"] = row

    (HERE / "results" / "force_breakdown.json").write_text(json.dumps(out, indent=2))
    # printed summary: totals vs Fluent first (must match), then each region
    for a, row in out.items():
        print(f"\n=== AoA {a} ===")
        for case, r in row.items():
            ch = r["check_vs_fluent"]
            print(f"{case:5s} totals vs Fluent: CL {ch['CL'][0]:.4f}/{ch['CL'][1]:.4f}  CD {ch['CD'][0]:.5f}/"
                  f"{ch['CD'][1]:.5f}  Cm {ch['Cm'][0]:.4f}/{ch['Cm'][1]:.4f}")
            for n, g in r["regions"].items():
                print(f"   {n:12s} drag {g['drag_N']:6.3f} N (pressure {g['CD_pressure']/g['CD']*100 if g['CD'] else 0:4.0f}%)"
                      f"  lift {g['lift_N']:7.3f} N  Cm {g['Cm']:+.4f}  area {g['area_cm2']:7.0f} cm2")
    print("sign convention: pressure", sp, "shear", st)


if __name__ == "__main__":
    main()
