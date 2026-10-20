"""
Move the payload box (VIAL POD) forward to fix the CG, for 0.8 and 1.2 mm walls, and render it.

  ..\\.venv\\Scripts\\python.exe fix_cg.py [--target-sm 10] [--pod-mm 120]

For each wall thickness it writes two GLBs to cg_fix\\:
  *_pod.glb          box (+ its hatch) moved forward --pod-mm and raised to touch the belly again
  *_pod_batt.glb     the same, plus the battery moved forward just enough to reach --target-sm
then reruns the CG on each, checks clearances and renders the result to cg_fix\\renders\\.
The box is ~40-50 g, so on its own it moves the CG only a little; the battery (700 g) does the rest.
The neutral point is the CFD one (box at its original place).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pyvista as pv

import cg
import move_parts as mp

HERE = Path(__file__).resolve().parent
OUT = HERE / "cg_fix"
POD, BATT = "VIAL POD", "BATTERY -"
POD_RAISE_MM = 1.4          # box top is 1.5 mm below the belly after the move: raise it back into contact


def evaluate(js, buf, wall, tmp):
    """Run the CG model on a (modified) glTF layout: write it to a temporary GLB and read it back."""
    mp.save_glb(tmp, js, buf)
    a = argparse.Namespace(wall_mm=wall, infill=0.2, rho=0.54, payload_g=0.0)
    parts = cg.read_parts(tmp)
    items = cg.build_items(parts, a)
    return cg.analyse(parts, items, a), items


def render(meshes0, meshes, moved, cgs, np_y, path, view, title):
    """meshes0 = original layout (ghost of moved parts), meshes = new layout."""
    p = pv.Plotter(off_screen=True, window_size=(1920, 1080))
    p.set_background("#1E2023")
    # moved parts solid + a faint wireframe where they used to be; fuselage see-through
    for i, (nm, m) in meshes.items():
        if i in moved:
            col = "#FF8A3D" if nm.startswith(POD) else "#4DA3FF"
            p.add_mesh(m, color=col, smooth_shading=True)
            p.add_mesh(meshes0[i][1], color=col, style="wireframe", opacity=0.25, line_width=1)
        elif nm.startswith(BATT):
            p.add_mesh(m, color="#4DA3FF", smooth_shading=True)
        elif nm.startswith(("FUS ", "NOSE", "HATCH", "FRONT REINF")):
            p.add_mesh(m, color="#C9CDD2", opacity=0.22 if view == "side" else 0.55, smooth_shading=True)
        else:
            p.add_mesh(m, color="#9AA0A6", smooth_shading=True)
    # CG / NP markers (mm)
    marks = cgs + [("neutral point", np.array([0, np_y, cgs[0][1][2]]), "#FF4D4D")]
    offs = [np.array([40 + 45 * k, 0, 45 + 28 * k]) for k in range(len(cgs))] + [np.array([-60, 0, -70])]
    for (label, xyz, col), o in zip(marks, offs):     # the CGs are mm apart: labels on leader lines
        p.add_mesh(pv.Sphere(radius=3.5, center=xyz), color=col)
        p.add_mesh(pv.Line(xyz, xyz + o), color=col, line_width=2)
    p.add_point_labels(np.array([m[1] + o for m, o in zip(marks, offs)]), [m[0] for m in marks],
                       font_size=20, text_color="white", shape_color="#2B2E33", shape_opacity=0.85,
                       always_visible=True, show_points=False)
    p.add_text(title, position="upper_left", font_size=16, color="white")
    # cameras in mm, CFD frame: side = from +x (right), bottom = from below, iso = front-right-below
    if view == "side":
        p.camera_position = [(900, -200, 60), (0, -200, 40), (0, 0, 1)]; p.camera.parallel_projection = True
        p.camera.parallel_scale = 190
    elif view == "bottom":
        p.camera_position = [(0, -230, -900), (0, -230, 0), (0, 1, 0)]; p.camera.parallel_projection = True
        p.camera.parallel_scale = 260
    else:
        p.camera_position = [(520, 260, -330), (0, -230, 10), (0, 0, 1)]; p.camera.view_angle = 30
    p.screenshot(path); p.close()


def margin_chart(rows, np_y, mac_le, c, path):
    """Number line in % MAC: neutral point, the 5-15 % static-margin band, and each layout's CG."""
    import matplotlib
    matplotlib.use("Agg")                        # no window, just the PNG
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(16, 4.2), dpi=120)
    fig.patch.set_facecolor("#1E2023"); ax.set_facecolor("#1E2023")
    pct = lambda y: (mac_le - y) / c * 100       # y (m, forward +) -> % MAC behind the leading edge
    npp = pct(np_y)
    ax.axvline(npp, color="#FF4D4D", lw=2); ax.text(npp, 2.75, "neutral point", color="#FF4D4D", ha="center")
    ax.axvspan(npp - 15, npp - 5, color="#3DDC84", alpha=0.12)
    ax.text(npp - 10, 2.75, "5-15 % static margin", color="#3DDC84", ha="center")
    for k, (wall, cases) in enumerate(rows):     # one row of dots per wall thickness
        yk = 1.8 - k * 1.1
        ax.text(pct(-0.270) + 0.2, yk, f"{wall} mm walls", color="white", va="center", fontsize=12)
        for (lab, y, sm), col in zip(cases, ("#9AA0A6", "#FF8A3D", "#4DA3FF")):
            ax.plot(pct(y), yk, "o", ms=13, color=col)
            ax.annotate(f"{lab}\nSM {sm:.1f} %", (pct(y), yk), (0, 14 if col != "#FF8A3D" else -34),
                        textcoords="offset points", ha="center", color=col, fontsize=10)
    ax.set_xlim(pct(-0.270), npp + 2); ax.set_ylim(0, 3.1); ax.set_yticks([])
    ax.set_xlabel("CG position, % MAC from the leading edge", color="white")
    ax.tick_params(colors="white"); [s.set_color("#55595F") for s in ax.spines.values()]
    fig.tight_layout(); fig.savefig(path, facecolor=fig.get_facecolor()); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", type=Path, default=mp.GLB)
    ap.add_argument("--target-sm", type=float, default=10.0, help="static margin to reach, % MAC")
    ap.add_argument("--pod-mm", type=float, default=120.0,
                    help="box travel forward; 120 keeps its mount pad on the flat part of the belly")
    args = ap.parse_args()
    (OUT / "renders").mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_tmp.glb"                       # scratch GLB for evaluate()
    cfg = json.loads((cg.POD / "config.json").read_text(encoding="utf-8-sig"))
    c = cfg["reference"]["length_m"]             # mean aerodynamic chord, m
    mac_le = -0.2356                             # y of the MAC leading edge, m

    js0, buf = mp.load_glb(args.glb)             # original layout (the BIN chunk is never changed)
    meshes0 = mp.part_meshes(js0, buf)
    summary, chart = {}, []
    for wall in (0.8, 1.2):
        tag = f"w{str(wall).replace('.', '')}"   # w08 / w12 in file names
        base, _ = evaluate(js0, buf, wall, tmp)
        np_y = base["aero"]["neutral_point_y_m"]

        # 1) box only (json round trip = deep copy of the scene description)
        js1 = json.loads(json.dumps(js0))
        moved1 = mp.apply_moves(js1, [(POD, np.array([0, args.pod_mm, POD_RAISE_MM]))])
        r1, _ = evaluate(js1, buf, wall, tmp)

        # 2) box + battery, battery shift solved for the target margin (CG is linear in the shift)
        M = r1["mass_g"]["total"]
        y_target = np_y + args.target_sm / 100 * c          # CG position that gives the target margin
        # moving mass m by d moves the CG by m*d/M  ->  d = (CG shift needed) * M / m, rounded up to 1 mm
        d_batt = max(0.0, math.ceil((y_target - r1["cg_m"][1]) * M / cg.COMPONENTS[BATT] * 1000))
        # the belly curves up toward the nose: lift the battery (spacer on the pad) until it clears FUS 1
        for lift in range(0, 21, 2):
            js2 = json.loads(json.dumps(js1))
            moved2 = moved1 | mp.apply_moves(js2, [(BATT, np.array([0, d_batt, lift]))])
            m2 = mp.part_meshes(js2, buf)
            bi = next(i for i in moved2 if m2[i][0].startswith(BATT))
            # any triangle contact with a part whose bounding box overlaps the battery's (pad excluded)?
            if not any(mp._contacts(m2[bi][1], o) for j, (nm, o) in m2.items()
                       if j not in moved2 and not nm.startswith("BATTERY PAD")
                       and np.all(np.array(o.bounds[1::2]) >= np.array(m2[bi][1].bounds[0::2]))
                       and np.all(np.array(o.bounds[0::2]) <= np.array(m2[bi][1].bounds[1::2]))):
                break
        else:
            raise SystemExit(f"{wall} mm: battery +{d_batt} mm does not fit even lifted 20 mm")
        r2, _ = evaluate(js2, buf, wall, tmp)

        # write both layouts, then report gaps/contacts of every moved part
        f1, f2 = OUT / f"stallion_pod_{tag}_pod.glb", OUT / f"stallion_pod_{tag}_pod_batt.glb"
        mp.save_glb(f1, js1, buf); mp.save_glb(f2, js2, buf)
        meshes2 = mp.part_meshes(js2, buf)
        clr = mp.clearance(meshes2, moved2)
        mp.print_clearance(f"{wall} mm walls, clearance after the move:", clr)

        # CG markers for the renders (mm)
        cgs = [("CG original", np.array(base["cg_m"]) * 1000, "#9AA0A6"),
               ("CG box moved", np.array(r1["cg_m"]) * 1000, "#FF8A3D"),
               ("CG box + battery", np.array(r2["cg_m"]) * 1000, "#4DA3FF")]
        ttl = (f"{wall} mm walls | box +{args.pod_mm:g} mm, battery +{d_batt:g} mm fwd" + (f" +{lift} mm up" if lift else "") + " | "
               f"SM {base['aero']['static_margin_pct_mac']}% -> {r1['aero']['static_margin_pct_mac']}% "
               f"-> {r2['aero']['static_margin_pct_mac']}%")
        for view in ("side", "bottom", "iso"):
            render(meshes0, meshes2, moved2, cgs, np_y * 1000, str(OUT / "renders" / f"{tag}_{view}.png"), view, ttl)
        chart.append((wall, [("original", base["cg_m"][1], base["aero"]["static_margin_pct_mac"]),
                             ("box moved", r1["cg_m"][1], r1["aero"]["static_margin_pct_mac"]),
                             ("box + battery", r2["cg_m"][1], r2["aero"]["static_margin_pct_mac"])]))
        summary[f"{wall} mm walls"] = {
            "box_move_mm": [0, args.pod_mm, POD_RAISE_MM], "battery_move_mm": [0, d_batt, lift],
            "original": base, "box_only": r1, "box_and_battery": r2,
            "clearance_after": [{"moved": a, "other": b, "contacts": n, "gap_mm": round(g, 1)} for a, b, n, g in clr],
            "files": [f1.name, f2.name]}
        print(f"{wall} mm: mass {base['mass_g']['total']} g | SM {base['aero']['static_margin_pct_mac']} -> "
              f"{r1['aero']['static_margin_pct_mac']} (box) -> {r2['aero']['static_margin_pct_mac']} "
              f"(box + battery {d_batt:g} mm fwd, {lift} mm up) | hover tail share {base['hover']['tail_motor_share_pct']} -> "
              f"{r2['hover']['tail_motor_share_pct']} %")
    # the neutral point is aerodynamic, so it is the same for both wall thicknesses
    margin_chart(chart, summary["0.8 mm walls"]["original"]["aero"]["neutral_point_y_m"], mac_le, c,
                 OUT / "renders" / "cg_vs_np.png")
    tmp.unlink(missing_ok=True)
    (OUT / "cg_fix_report.json").write_text(json.dumps(summary, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
