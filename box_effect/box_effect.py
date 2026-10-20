"""
What the payload box (VIAL POD) does to the aircraft: CG, lift, drag, pitching moment, centre of pressure,
neutral point, surface pressure (Cp), and the combined static margin.

  ..\\.venv\\Scripts\\python.exe box_effect.py

Inputs (all produced by the same pipeline, same mesh settings and reference values):
  ..\\cfd_pod\\results      equipped aircraft WITH the box          (forces.csv, wall_pod_aoa{0,4}.npz)
  ..\\cfd_nobox\\results    the same GLB with only the 2 box parts removed (forces.csv, wall_nobox_aoa{0,4}.npz)
  ..\\mass_cg\\cg.py         mass model (0.8 and 1.2 mm LW-PLA walls, 20 % infill)
Outputs: box_effect.json and figures\\*.png
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.tri import Triangulation
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "mass_cg"))
import cg  # noqa: E402

CASES = {"box": ROOT / "cfd_pod" / "results", "nobox": ROOT / "cfd_nobox" / "results"}
WALL = {"box": "wall_pod_aoa{}.npz", "nobox": "wall_nobox_aoa{}.npz"}
LABEL = {"box": "with box", "nobox": "without box"}
COL = {"box": "#FF8A3D", "nobox": "#4DA3FF"}
CFG = json.loads((ROOT / "cfd_pod" / "config.json").read_text(encoding="utf-8-sig"))
S, C = CFG["reference"]["area_m2"], CFG["reference"]["length_m"]
RC = np.array(CFG["reference"]["moment_center_m"]); Y_REF = RC[1]
Q = 0.5 * CFG["flight"]["density_kg_m3"] * CFG["flight"]["speed_m_s"] ** 2
MAC_LE = -0.2356                                    # wing MAC leading edge, y (m)
FIG = HERE / "figures"

BG, PANEL, INK, MUTED, GRID = "#1E2023", "#1E2023", "#E8EAED", "#9AA0A6", "#33373D"
CP_MAP = LinearSegmentedColormap.from_list("cp", ["#2B6CB0", "#7FB2E5", "#8A8F96", "#F2A36B", "#C8501E"])
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": PANEL, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "font.size": 12,
                     "axes.titlesize": 14, "axes.titleweight": "bold", "legend.frameon": False})


# ----------------------------------------------------------------------------------------------- data
def forces(case):
    """forces.csv of a case as {aoa: {CL, CD, Cm, status}}."""
    with open(CASES[case] / "forces.csv", newline="") as fh:
        return {float(r["aoa_deg"]): {k: float(r[k]) for k in ("CL", "CD", "Cm")} | {"status": r["status"]}
                for r in csv.DictReader(fh)}


def wall(case, a):
    """Face centroids (m), outward area vectors (m2), pressure (Pa) and wall shear (Pa) from export_wall.py."""
    d = np.load(CASES[case] / WALL[case].format(a))
    c, A, p = d["aircraft__centroid"], d["aircraft__area"], d["aircraft__pressure"]
    tau = np.column_stack([d[f"aircraft__{k}-wall-shear"] for k in "xyz"])
    if np.einsum("ij,ij->", c - c.mean(0), A) < 0:   # make A point out of the aircraft (divergence theorem)
        A = -A
    return c, A, p, tau


def coeffs(F, M, a):
    """Total force F (N) and moment M (N m about the reference point) -> CL, CD, Cm at angle a (deg)."""
    a = math.radians(a)
    lift = np.array([0, math.sin(a), math.cos(a)]); drag = np.array([0, -math.cos(a), math.sin(a)])
    return F @ lift / (Q * S), F @ drag / (Q * S), M[0] / (Q * S * C)


def face_forces(c, A, p, tau, a, ref):
    """Pick the pressure / shear sign that reproduces Fluent's totals; return per-face forces."""
    best = None
    for sp in (1, -1):
        for st in (1, -1):
            F = sp * p[:, None] * A + st * tau * np.linalg.norm(A, axis=1)[:, None]
            cl, cd, cm = coeffs(F.sum(0), np.cross(c - RC, F).sum(0), a)
            err = abs(cl - ref["CL"]) + abs(cd - ref["CD"]) + abs(cm - ref["Cm"])
            if best is None or err < best[0]:
                best = (err, F, (cl, cd, cm))
    return best[1], best[2]


def regions(c):
    x, y, z = c.T
    box = (z < -0.003) & (np.abs(x) < 0.06) & (y > -0.40) & (y < -0.17)
    boom = (np.abs(x) > 0.26) & (np.abs(x) < 0.37) & (y > -0.17)
    tail = (y < -0.56) & ~boom
    wing = (np.abs(x) > 0.148) & ~boom & ~tail
    fus = ~box & ~boom & ~tail & ~wing
    return {"box": box, "fuselage": fus, "wing": wing, "V-tail + tail boom": tail, "motor booms (front)": boom}


# ------------------------------------------------------------------------------------------- analysis
def aero_summary(F):
    """Per case: coefficients and centre of pressure per angle, lift slope, dCm/dCL, neutral point, Cm at zero lift."""
    out = {}
    for case, f in F.items():
        cl0, cl4, cm0, cm4 = f[0]["CL"], f[4]["CL"], f[0]["Cm"], f[4]["Cm"]
        # stability slope from the two converged angles; the neutral point is where it would be zero
        dcm = (cm4 - cm0) / (cl4 - cl0)
        # centre of pressure: the point the total lift acts through, y_cp = y_ref + c * Cm / CL
        # (it moves with angle; the neutral point does not, which is why stability uses the NP)
        out[case] = {
            "per_aoa": {f"{a:g}": {"CL": r["CL"], "CD": r["CD"], "Cm": r["Cm"], "L/D": r["CL"] / r["CD"],
                                   "centre_of_pressure_y_m": Y_REF + C * r["Cm"] / r["CL"],
                                   "centre_of_pressure_pct_mac": (MAC_LE - (Y_REF + C * r["Cm"] / r["CL"])) / C * 100,
                                   "status": r["status"]} for a, r in f.items()},
            "CL_alpha_per_deg": (cl4 - cl0) / 4, "dCm_dCL": dcm,
            "neutral_point_y_m": Y_REF + C * dcm, "neutral_point_pct_mac": (MAC_LE - (Y_REF + C * dcm)) / C * 100,
            "Cm0_at_CL0": cm0 - dcm * cl0,
        }
    return out


def cruise(f, mass_g):
    """20 m/s level flight: CL needed, AoA and CD by linear interpolation between 0 and 4 deg."""
    cl = mass_g / 1000 * 9.81 / (Q * S)                  # level flight: lift = weight
    t = (cl - f[0]["CL"]) / (f[4]["CL"] - f[0]["CL"])    # where that CL falls between 0 and 4 deg
    cd = f[0]["CD"] + t * (f[4]["CD"] - f[0]["CD"])
    return {"CL": cl, "aoa_deg": 4 * t, "CD": cd, "drag_N": cd * Q * S, "L/D": cl / cd,
            "power_W_at_20ms": cd * Q * S * CFG["flight"]["speed_m_s"]}


def mass_cases():
    """Mass and CG with and without the box (box parts dropped by name), for 0.8 and 1.2 mm walls."""
    parts0 = cg.read_parts()
    out = {}
    for w in (0.8, 1.2):
        a = argparse.Namespace(wall_mm=w, infill=0.2, rho=0.54, payload_g=0.0)
        out[w] = {}
        for case, parts in (("box", parts0), ("nobox", [p for p in parts0 if not p["name"].startswith("VIAL POD")])):
            it = cg.build_items(parts, a)
            o = cg.analyse(parts, it, a)
            box_g = sum(i[2] for i in it if i[0].startswith("VIAL POD"))
            out[w][case] = {"mass_g": o["mass_g"]["total"], "cg_m": o["cg_m"], "box_g": round(box_g, 1),
                            "hover_tail_pct": o["hover"]["tail_motor_share_pct"]}
    return out


def stability(mass, aero, F):
    """Static margin and trim using each case's OWN mass and OWN aerodynamics."""
    out = {}
    for w, m in mass.items():
        out[f"{w} mm"] = {}
        for case in ("box", "nobox"):
            y_cg = m[case]["cg_m"][1]; a = aero[case]
            sm = (y_cg - a["neutral_point_y_m"]) / C * 100      # + = CG ahead of NP = stable
            f = F[case]
            # move the moment reference from y_ref to the CG: Cm_cg = Cm_ref - CL * (y_cg - y_ref) / c
            cmcg = {k: f[k]["Cm"] - f[k]["CL"] * (y_cg - Y_REF) / C for k in (0.0, 4.0)}
            k = (cmcg[4.0] - cmcg[0.0]) / (f[4]["CL"] - f[0]["CL"])   # dCm_cg/dCL = -static margin
            # trim CL: where Cm about the CG is zero (no elevator deflection), linear in CL
            cr = cruise(f, m[case]["mass_g"])
            out[f"{w} mm"][case] = {
                "mass_g": m[case]["mass_g"], "cg_y_m": y_cg, "cg_z_m": m[case]["cg_m"][2],
                "cg_pct_mac": (MAC_LE - y_cg) / C * 100, "neutral_point_pct_mac": a["neutral_point_pct_mac"],
                # near-neutral (|SM| < 1 %) the slope k ~ 0 and the trim CL blows up: report none
                "static_margin_pct": sm, "trim_CL": f[0]["CL"] - cmcg[0.0] / k if abs(sm) >= 1.0 else None,
                "Cm_about_cg_at_cruise": cmcg[0.0] + k * (cr["CL"] - f[0]["CL"]), "cruise": cr,
                "hover_tail_motor_pct": m[case]["hover_tail_pct"]}
    return out


def breakdown(F):
    """Lift, drag and Cm of each surface region, both cases, at 0 and 4 deg (with a check against Fluent's totals)."""
    out = {}
    for a in (0, 4):
        out[f"{a}deg"] = {}
        for case in ("box", "nobox"):
            c, A, p, tau = wall(case, a)
            Ff, tot = face_forces(c, A, p, tau, a, F[case][a])
            r = {}
            for name, msk in regions(c).items():
                cl, cd, cm = coeffs(Ff[msk].sum(0), np.cross(c[msk] - RC, Ff[msk]).sum(0), a)
                r[name] = {"CL": cl, "CD": cd, "Cm": cm, "lift_N": cl * Q * S, "drag_N": cd * Q * S}
            out[f"{a}deg"][case] = {"regions": r, "totals_check": {"from_faces": tot, "fluent": F[case][a]}}
    return out


# -------------------------------------------------------------------------------------------- figures
def fig_coefficients(F):
    """CL, CD, Cm and L/D against angle, with box vs without."""
    fig, axs = plt.subplots(1, 4, figsize=(19, 5.2))
    for case, f in F.items():
        a = np.array(sorted(f)); conv = np.array(["NOT" not in f[k]["status"] for k in a])
        for ax, key in zip(axs, ("CL", "CD", "Cm", "LD")):
            v = np.array([f[k]["CL"] / f[k]["CD"] if key == "LD" else f[k][key] for k in a])
            ax.plot(a, v, color=COL[case], lw=2, label=LABEL[case])
            ax.plot(a[conv], v[conv], "o", ms=9, color=COL[case], mec=BG, mew=2)
            ax.plot(a[~conv], v[~conv], "o", ms=9, mfc=BG, color=COL[case], mew=2)
    for ax, t in zip(axs, ("Lift coefficient CL", "Drag coefficient CD", "Pitching moment Cm (about ref.)",
                           "Lift / drag")):
        ax.set_title(t, loc="left"); ax.set_xlabel("angle of attack (deg)"); ax.set_xticks([0, 4, 8])
    axs[0].legend(loc="upper left")
    fig.text(0.01, 0.01, "Hollow marker = 8 deg did not converge (mean of last 200 iterations).", color=MUTED,
             fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(FIG / "coefficients.png", dpi=110); plt.close(fig)


def fig_breakdown(B):
    """Bar charts: change in lift and drag per region at 4 deg (box's own force + interference)."""
    names = ["box", "fuselage", "wing", "V-tail + tail boom", "motor booms (front)"]
    fig, axs = plt.subplots(1, 2, figsize=(16, 4.3))
    for ax, key, ttl in ((axs[0], "lift_N", "Change in lift by region, 4 deg (N)"),
                         (axs[1], "drag_N", "Change in drag by region, 4 deg (N)")):
        r = B["4deg"]
        d = [r["box"]["regions"][n][key] - r["nobox"]["regions"][n][key] for n in names]
        y = np.arange(len(names))[::-1]
        ax.barh(y, d, height=0.55, color=[COL["box"] if n == "box" else "#8A8F96" for n in names])
        for yi, v in zip(y, d):
            ax.text(v + (0.02 if v >= 0 else -0.02), yi, f"{v:+.2f}", va="center",
                    ha="left" if v >= 0 else "right", color=INK, fontsize=12)
        ax.axvline(0, color=MUTED, lw=1); ax.set_yticks(y, ["box itself"] + names[1:])
        ax.set_title(ttl, loc="left"); ax.grid(axis="y", visible=False)
        lim = max(abs(min(d)), abs(max(d)), 1e-3) * 1.45; ax.set_xlim(-lim, lim)   # symmetric about zero
    fig.text(0.01, 0.01, "with box minus without box. Grey bars = interference: the box changes the flow over "
             "parts that did not change.", color=MUTED, fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(FIG / "breakdown_4deg.png", dpi=110); plt.close(fig)


def underside(case, a):
    """Downward-facing faces of the front of the aircraft and their Cp (= gauge pressure / q)."""
    c, A, p, tau = wall(case, a)
    n = A / np.linalg.norm(A, axis=1)[:, None]
    m = (n[:, 2] < -0.25) & (np.abs(c[:, 0]) < 0.36) & (c[:, 1] > -0.62) & (c[:, 1] < 0.08)
    return c[m], p[m] / Q


def tri(c, maxedge=0.014):
    """Plan-view triangulation of face centroids, seen from below; long edges masked so gaps stay empty."""
    t = Triangulation(-c[:, 0], c[:, 1])           # seen from below: x mirrored
    tr = t.triangles; P = np.column_stack([t.x, t.y])
    e = np.max([np.linalg.norm(P[tr[:, i]] - P[tr[:, (i + 1) % 3]], axis=1) for i in range(3)], axis=0)
    t.set_mask(e > maxedge); return t


def fig_cp_maps(a):
    """Underside Cp with box, without box, and the difference on the faces both meshes share."""
    cb, pb = underside("box", a); cn, pn = underside("nobox", a)
    fig, axs = plt.subplots(1, 3, figsize=(19, 8.2))
    norm = TwoSlopeNorm(vmin=-0.8, vcenter=0, vmax=0.8)
    for ax, (c, p, ttl) in zip(axs[:2], ((cb, pb, "Cp underside, with box"), (cn, pn, "Cp underside, without box"))):
        im = ax.tripcolor(tri(c), p, cmap=CP_MAP, norm=norm, shading="gouraud")
        ax.set_title(f"{ttl}, {a} deg", loc="left")
    fig.colorbar(im, ax=axs[:2], shrink=0.75, pad=0.02, label="Cp  (blue = suction, orange = pressure)")
    # difference on the faces both meshes share (box faces excluded)
    keep = ~regions(cb)["box"]
    # the two meshes differ, so pair each face with the nearest face of the other case (within 6 mm)
    d, j = cKDTree(cn).query(cb[keep])
    ok = d < 0.006
    cd = cb[keep][ok]; dp = pb[keep][ok] - pn[j[ok]]
    im2 = axs[2].tripcolor(tri(cd), dp, cmap=CP_MAP, norm=TwoSlopeNorm(vmin=-0.3, vcenter=0, vmax=0.3),
                           shading="gouraud")
    axs[2].set_title(f"Cp change (with - without), {a} deg", loc="left")
    fig.colorbar(im2, ax=axs[2], shrink=0.75, pad=0.02, label="delta Cp")
    for ax in axs:
        # dashed outline of the box footprint (x +-37 mm, y -364..-204 mm) to orient the eye
        ax.plot([-0.037, 0.037, 0.037, -0.037, -0.037], [-0.364, -0.364, -0.204, -0.204, -0.364],
                "--", color=INK, lw=1, alpha=0.7)
        ax.set_aspect("equal"); ax.grid(False); ax.set_xlim(-0.36, 0.36); ax.set_ylim(-0.62, 0.08)
        ax.set_xlabel("span (m), seen from below"); ax.set_ylabel("nose  <-  y (m)")
    fig.savefig(FIG / f"cp_underside_{a}deg.png", dpi=110, bbox_inches="tight"); plt.close(fig)


def fig_belly(a):
    """Cp along the bottom centreline (belly) with and without the box."""
    fig, ax = plt.subplots(figsize=(16, 5.6))
    for case in ("nobox", "box"):
        c, A, p, tau = wall(case, a)
        n = A / np.linalg.norm(A, axis=1)[:, None]
        m = (np.abs(c[:, 0]) < 0.012) & (n[:, 2] < -0.3) & (c[:, 1] > -0.62) & (c[:, 1] < 0.07)
        bx = regions(c)["box"]
        # in the no-box run the "box" region holds only the bare mount lugs
        sub = "box underside" if case == "box" else "mount lugs (no box)"
        for msk, ls, lab in ((m & ~bx, "-", f"belly, {LABEL[case]}"), (m & bx, ":", sub)):
            if not msk.any(): continue
            o = np.argsort(c[msk, 1]); yv = c[msk, 1][o]; cp = (p[msk] / Q)[o]
            k = max(1, len(yv) // 120)                 # light smoothing: running mean over neighbours
            cp = np.convolve(cp, np.ones(k) / k, mode="same")
            # break the line where there is no surface (e.g. the belly hidden above the box)
            gap = np.where(np.diff(yv) > 0.01)[0] + 1
            yv, cp = np.insert(yv, gap, np.nan), np.insert(cp, gap, np.nan)
            ax.plot(yv, cp, ls, lw=2, color=COL[case], label=lab)
    ax.axvspan(-0.364, -0.204, color=COL["box"], alpha=0.08)
    ax.text(-0.284, ax.get_ylim()[1] * 0.9, "box", ha="center", color=COL["box"])
    ax.invert_yaxis(); ax.set_xlabel("y (m)   tail  <-  ->  nose"); ax.set_ylabel("Cp (suction up)")
    ax.set_title(f"Pressure along the bottom centreline, {a} deg", loc="left"); ax.legend(loc="lower right")
    fig.tight_layout(); fig.savefig(FIG / f"belly_cp_{a}deg.png", dpi=110); plt.close(fig)


def fig_span(a, F):
    """Spanwise lift distribution (wing + fuselage) with and without the box."""
    fig, ax = plt.subplots(figsize=(16, 5.6))
    bins = np.linspace(-0.68, 0.68, 69); mid = 0.5 * (bins[1:] + bins[:-1])
    for case in ("nobox", "box"):
        c, A, p, tau = wall(case, a)
        Ff, _ = face_forces(c, A, p, tau, a, F[case][a])
        ar = math.radians(a); lift = Ff @ np.array([0, math.sin(ar), math.cos(ar)])   # lift per face, N
        keep = c[:, 1] > -0.56                       # wing + fuselage (tail excluded)
        # sum the face lift in 20 mm spanwise strips, divide by strip width -> N per metre of span
        L, _ = np.histogram(c[keep, 0], bins, weights=lift[keep])
        ax.plot(mid, L / np.diff(bins), lw=2, color=COL[case], label=LABEL[case])
    ax.set_xlabel("span x (m)"); ax.set_ylabel("lift per metre of span (N/m)")
    ax.set_title(f"Spanwise lift (wing + fuselage), {a} deg", loc="left"); ax.legend(loc="upper right")
    fig.tight_layout(); fig.savefig(FIG / f"span_lift_{a}deg.png", dpi=110); plt.close(fig)


def fig_stability(st):
    """CG and neutral point in % MAC for each wall thickness, with and without the box."""
    fig, ax = plt.subplots(figsize=(16, 3.6))
    rows = list(st.items())
    for k, (w, d) in enumerate(rows):
        yk = 1.0 - k * 0.55
        ax.text(23.6, yk + 0.2, f"{w} walls", color=INK, fontsize=13, weight="bold")
        for j, case in enumerate(("nobox", "box")):
            yy = yk - j * 0.2; r = d[case]
            ax.plot([r["cg_pct_mac"], r["neutral_point_pct_mac"]], [yy, yy], color=COL[case], lw=2, alpha=0.5)
            ax.plot(r["cg_pct_mac"], yy, "o", ms=11, color=COL[case], mec=BG, mew=2)
            ax.plot(r["neutral_point_pct_mac"], yy, "D", ms=10, color=COL[case], mec=BG, mew=2)
            # label right of whichever marker is further aft (CG can sit behind the NP = unstable)
            ax.text(max(r["neutral_point_pct_mac"], r["cg_pct_mac"]) + 0.35, yy, f"{LABEL[case]}: SM {r['static_margin_pct']:.1f} %",
                    va="center", color=INK, fontsize=11)
    ax.set_xlim(23.5, 47); ax.set_ylim(0.1, 1.32); ax.set_yticks([])
    ax.set_xlabel("position, % MAC from the wing leading edge    (circle = CG, diamond = neutral point)")
    ax.set_title("Static margin = gap between CG and neutral point", loc="left")
    fig.tight_layout(); fig.savefig(FIG / "static_margin.png", dpi=110); plt.close(fig)


# ----------------------------------------------------------------------------------------------- main
def main():
    """Run every analysis, write box_effect.json and the figures, print a summary."""
    FIG.mkdir(parents=True, exist_ok=True)
    F = {k: forces(k) for k in CASES}
    aero = aero_summary(F)
    mass = mass_cases()
    st = stability(mass, aero, F)
    B = breakdown(F)
    out = {"aero": aero, "mass": {f"{w} mm": v for w, v in mass.items()}, "stability": st, "breakdown": B}
    (HERE / "box_effect.json").write_text(json.dumps(out, indent=2, default=float))

    fig_coefficients(F); fig_breakdown(B); fig_stability(st)
    for a in (0, 4):
        fig_cp_maps(a); fig_belly(a); fig_span(a, F)

    print("AERO (with box | without box | delta)")
    for a in ("0", "4", "8"):
        b, n = aero["box"]["per_aoa"][a], aero["nobox"]["per_aoa"][a]
        print(f" {a} deg  CL {b['CL']:.4f} | {n['CL']:.4f} | {b['CL']-n['CL']:+.4f}   CD {b['CD']:.4f} | {n['CD']:.4f} | "
              f"{b['CD']-n['CD']:+.4f}   Cm {b['Cm']:+.4f} | {n['Cm']:+.4f} | {b['Cm']-n['Cm']:+.4f}   L/D {b['L/D']:.2f} | "
              f"{n['L/D']:.2f}   CP {b['centre_of_pressure_pct_mac']:.1f} | {n['centre_of_pressure_pct_mac']:.1f} %MAC")
    for case in ("box", "nobox"):
        a = aero[case]
        print(f" {case:6s} CLa {a['CL_alpha_per_deg']:.4f}/deg  dCm/dCL {a['dCm_dCL']:+.4f}  NP {a['neutral_point_pct_mac']:.1f} %MAC"
              f"  Cm0 {a['Cm0_at_CL0']:+.4f}")
    print("CHECK face sums vs Fluent:", {f"{a}/{c}": [round(v, 4) for v in B[a][c]["totals_check"]["from_faces"]]
                                         for a in B for c in B[a]})
    for w, d in st.items():
        for case, r in d.items():
            print(f" {w} {case:6s} mass {r['mass_g']} g  CG {r['cg_pct_mac']:.1f} %MAC  NP {r['neutral_point_pct_mac']:.1f}"
                  f"  SM {r['static_margin_pct']:.1f} %  cruise AoA {r['cruise']['aoa_deg']:.2f}  drag {r['cruise']['drag_N']:.2f} N"
                  f"  L/D {r['cruise']['L/D']:.1f}  P {r['cruise']['power_W_at_20ms']:.1f} W  trim CL "
                  + (f"{r['trim_CL']:.2f}" if r["trim_CL"] is not None else "n/a (near neutral)"))
    for a in B:
        print(a, {n: (round(B[a]["box"]["regions"][n]["lift_N"] - B[a]["nobox"]["regions"][n]["lift_N"], 3),
                      round(B[a]["box"]["regions"][n]["drag_N"] - B[a]["nobox"]["regions"][n]["drag_N"], 3),
                      round(B[a]["box"]["regions"][n]["Cm"] - B[a]["nobox"]["regions"][n]["Cm"], 4))
                  for n in B[a]["box"]["regions"]})


if __name__ == "__main__":
    main()
