"""
Deck: the Stallion VTOL WITH and WITHOUT the payload box, every aerodynamic metric of both CFD runs.

  ..\\.venv\\Scripts\\python.exe make_ppt_box.py      -> ..\\presentations\\Stallion_box_vs_nobox_CFD.pptx

Reads (run box_effect.py first):
  box_effect.json, figures\\*.png                          (this folder, from box_effect.py)
  ..\\cfd_pod\\  and  ..\\cfd_nobox\\                     results\\forces.csv, results\\aoa_*_forces.out,
                                                         logs\\mesh_log.txt, renders\\*.png
  ..\\mass_cg\\box_renders\\{with,without}_box.png          (render_box.py)
Both CFD runs use the same GLB, mesh settings, solver and reference values; the only difference is
that the two VIAL POD parts (box + its hatch) were removed for the no-box run.
"""
import csv
import json
import re
from pathlib import Path

import numpy as np
from pptx import Presentation
from pptx.chart.data import XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "presentations" / "Stallion_box_vs_nobox_CFD.pptx"
CASE = {"box": ROOT / "cfd_pod", "nobox": ROOT / "cfd_nobox"}     # CFD case folders
FIG = HERE / "figures"

# colours: same dark theme as the other decks; orange = with box, blue = without box
BG, PANEL, HEAD = RGBColor(0x1E, 0x20, 0x23), RGBColor(0x2A, 0x2D, 0x31), RGBColor(0x3A, 0x3E, 0x43)
TEXT, MUTED, AXIS, GRID = RGBColor(0xF2, 0xF2, 0xF2), RGBColor(0xA8, 0xAE, 0xB5), RGBColor(0x55, 0x5A, 0x60), RGBColor(0x3A, 0x3E, 0x43)
COL = {"box": RGBColor(0xFF, 0x8A, 0x3D), "nobox": RGBColor(0x4D, 0xA3, 0xFF)}
LABEL = {"box": "With box", "nobox": "Without box"}
FONT = "Calibri"
W, H = Inches(13.333), Inches(7.5)

# ---------------------------------------------------------------- data
R = json.loads((HERE / "box_effect.json").read_text())                 # everything box_effect.py computed
CFG = json.loads((CASE["box"] / "config.json").read_text(encoding="utf-8-sig"))
V = CFG["flight"]["speed_m_s"]
REFV = CFG["reference"]


def forces(case):
    """forces.csv of a case as {aoa: row dict}."""
    with open(CASE[case] / "results" / "forces.csv", newline="") as fh:
        return {float(r["aoa_deg"]): r for r in csv.DictReader(fh)}


def history(case, a):
    """(iteration, CL, CD, Cm) rows of one angle's force history; iterations restart at 1 per angle."""
    rows = [[float(x) for x in l.split()] for l in (CASE[case] / "results" / f"aoa_{a:g}_forces.out").read_text().splitlines()
            if len(l.split()) == 4 and l.split()[0].isdigit()]
    h = np.array(rows)
    h[:, 0] -= h[0, 0] - 1                       # the files count cumulatively over the angles
    return h


def cells(case):
    """Cell count from the mesher's log."""
    return int(re.findall(r"Total cells : (\d+)", (CASE[case] / "logs" / "mesh_log.txt").read_text(errors="ignore"))[-1])


F = {c: forces(c) for c in CASE}
ANGLES = sorted(F["box"])
HIST = {(c, a): history(c, a) for c in CASE for a in ANGLES}
CELLS = {c: cells(c) for c in CASE}
f = lambda c, a, k: float(F[c][a][k])           # one number from forces.csv


def spread(c, a, col, n=50):
    """(max - min) / |mean| of a coefficient over the last n iterations, %: how settled it is."""
    x = HIST[(c, a)][-n:, col]
    return (x.max() - x.min()) / abs(x.mean()) * 100


def pct(new, old):
    """Percentage change old -> new."""
    return (new - old) / abs(old) * 100


# ---------------------------------------------------------------- slide helpers
def new_slide(prs, notes=None):
    """Blank dark slide; notes go into the speaker notes."""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid(); s.background.fill.fore_color.rgb = BG
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def text(slide, x, y, w, h, runs, size=16, color=TEXT, bold=False, align=PP_ALIGN.LEFT):
    """Text box. runs: str, or list of paragraphs; a paragraph is a str or a list of (text, {size, bold, color})."""
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(runs if isinstance(runs, list) else [runs]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align; p.space_after = Pt(6)
        for t, o in ([(para, {})] if isinstance(para, str) else para):
            r = p.add_run(); r.text = t
            ft = r.font
            ft.name, ft.size, ft.bold = FONT, Pt(o.get("size", size)), o.get("bold", bold)
            ft.color.rgb = o.get("color", color)
    return tb


def title(slide, t, sub=None):
    """Slide title (and optional grey subtitle) in the fixed top-left position."""
    text(slide, Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.7), t, size=32, bold=True)
    if sub:
        text(slide, Inches(0.6), Inches(1.02), Inches(12.1), Inches(0.4), sub, size=15, color=MUTED)


def image(slide, path, x, y, w=None, h=None, caption=None):
    """Picture with an optional centred caption below it."""
    pic = slide.shapes.add_picture(str(path), x, y, w, h)
    if caption:
        text(slide, x, pic.top + pic.height + Inches(0.05), pic.width, Inches(0.3), caption,
             size=12, color=MUTED, align=PP_ALIGN.CENTER)
    return pic


def panel(slide, x, y, w, h):
    """Flat rounded card."""
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.adjustments[0] = 0.06
    sh.fill.solid(); sh.fill.fore_color.rgb = PANEL
    sh.line.fill.background(); sh.shadow.inherit = False
    return sh


def table(slide, rows, x, y, widths, row_h=Inches(0.4), size=13, color_fn=None):
    """Dark table, row 0 = header. color_fn(row, col, value) -> RGBColor or None recolours a cell's text."""
    t = slide.shapes.add_table(len(rows), len(rows[0]), x, y, sum(widths), row_h * len(rows)).table
    for c, wd in enumerate(widths):
        t.columns[c].width = wd
    for r, row in enumerate(rows):
        t.rows[r].height = row_h
        for c, val in enumerate(row):
            cell = t.cell(r, c)
            cell.fill.solid(); cell.fill.fore_color.rgb = HEAD if r == 0 else PANEL
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.text = str(val) or " "                      # empty cells have no run to style
            ft = cell.text_frame.paragraphs[0].runs[0].font
            ft.name, ft.size, ft.bold = FONT, Pt(size), r == 0
            ft.color.rgb = (color_fn(r, c, str(val)) if color_fn and r else None) or TEXT
    return t


def case_color(r, c, v):
    """Colour the case-name column by case."""
    return COL["box"] if v == LABEL["box"] else COL["nobox"] if v == LABEL["nobox"] else None


def stat(slide, x, y, w, value, label, color):
    """Big-number card."""
    panel(slide, x, y, w, Inches(1.65))
    text(slide, x + Inches(0.22), y + Inches(0.15), w - Inches(0.44), Inches(0.8), value, size=38, bold=True, color=color)
    text(slide, x + Inches(0.22), y + Inches(0.95), w - Inches(0.44), Inches(0.65), label, size=13, color=MUTED)


def history_chart(slide, x, y, w, h, ttl, col, fmt):
    """Native XY chart: one coefficient against iteration, both cases, 0 and 4 deg (8 deg has its own scale)."""
    cd = XyChartData()
    order = []
    for a in ANGLES[:2]:
        for c in ("nobox", "box"):
            s = cd.add_series(f"{LABEL[c]}, {a:g}°"); order.append((c, a))
            for row in HIST[(c, a)]:
                s.add_data_point(row[0], row[col])
    ch = slide.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER_LINES_NO_MARKERS, x, y, w, h, cd).chart
    ch.has_title = True; ch.chart_title.text_frame.text = ttl
    tf = ch.chart_title.text_frame.paragraphs[0].runs[0].font
    tf.size, tf.bold, tf.color.rgb, tf.name = Pt(14), True, TEXT, FONT
    ch.has_legend = True; ch.legend.position = XL_LEGEND_POSITION.BOTTOM; ch.legend.include_in_layout = False
    ch.legend.font.size, ch.legend.font.color.rgb, ch.legend.font.name = Pt(10), MUTED, FONT
    for ax in (ch.category_axis, ch.value_axis):
        ax.tick_labels.font.size, ax.tick_labels.font.color.rgb, ax.tick_labels.font.name = Pt(10), MUTED, FONT
        ax.format.line.color.rgb = AXIS
    ch.value_axis.has_major_gridlines = True
    ch.value_axis.major_gridlines.format.line.color.rgb = GRID
    ch.category_axis.has_major_gridlines = False
    ch.value_axis.tick_labels.number_format = fmt; ch.value_axis.tick_labels.number_format_is_linked = False
    for s, (c, a) in zip(ch.series, order):
        s.smooth = False
        s.format.line.color.rgb = COL[c]
        s.format.line.width = Pt(2.0 if a else 1.25)      # 4 deg thick, 0 deg thin
        s.marker.style = XL_MARKER_STYLE.NONE
    return ch


def fmt_cm(v):
    """Cm with 4 decimals, no '-0.0000'."""
    return f"{v + 0.0:+.4f}".replace("-0.0000", "0.0000")


# ---------------------------------------------------------------- deck
prs = Presentation()
prs.slide_width, prs.slide_height = W, H
A = R["aero"]; ST = R["stability"]; B = R["breakdown"]; MS = R["mass"]
BOXREN = ROOT / "mass_cg" / "box_renders"

# 1 title ----------------------------------------------------------------
s = new_slide(prs, "Two CFD runs of the same aircraft. The only geometric difference is the payload box under the "
                   "fuselage (VIAL POD and its hatch).")
image(s, BOXREN / "with_box.png", Inches(0.0), Inches(1.95), w=Inches(6.6))       # renders carry their own labels
image(s, BOXREN / "without_box.png", Inches(6.73), Inches(1.95), w=Inches(6.6))
text(s, Inches(0.6), Inches(0.45), Inches(12.1), Inches(1.4),
     [[("Stallion VTOL  ·  payload box", {"size": 20, "color": MUTED})],
      [("With vs without the box: aerodynamic comparison", {"size": 36, "bold": True})]])
text(s, Inches(0.6), Inches(6.0), Inches(12.1), Inches(1.0),
     [f"Ansys Fluent 2026 R1 Student · steady RANS, k-ω SST · {V:g} m/s · angle of attack "
      f"{', '.join(f'{a:g}' for a in ANGLES)}°",
      [("Every metric on the following slides comes from these two runs (plus the mass model for CG / static margin).",
        {"size": 13, "color": MUTED})]], size=16)

# 2 what was compared ---------------------------------------------------------
m = CFG["mesh"]
s = new_slide(prs, "Both runs went through the identical pipeline: GLB import, sealed shrink-wrap, the same mesh "
                   "sizing, solver and convergence rule, and the same reference area, chord and moment centre. "
                   "So any difference in the results is caused by the box.")
title(s, "Test setup: one change only", "Same GLB, pipeline, mesh settings, solver and reference values")
rows = [("", "With box", "Without box"),
        ("Geometry", "stallion_v2_equipped_with_pod.glb (96 parts)", "same GLB, 2 box parts removed (94 parts)"),
        ("Mesh", f"poly-hexcore, {CELLS['box']:,} cells", f"poly-hexcore, {CELLS['nobox']:,} cells"),
        ("Surface size / prisms", f"{m['min_size_mm']:g}–{m['aircraft_max_size_mm']:g} mm, {m['boundary_layers']} layers, "
                                  f"first {m['bl_first_height_mm']} mm", "identical"),
        ("Flow", f"{V:g} m/s, ρ {CFG['flight']['density_kg_m3']} kg/m³, steady, incompressible", "identical"),
        ("Model", "pressure-based coupled, k-ω SST", "identical"),
        ("Angles", f"{', '.join(f'{a:g}' for a in ANGLES)}° (free-stream tilted, one mesh)", "identical"),
        ("Reference", f"S {REFV['area_m2']} m², c {REFV['length_m']} m, moment centre y {REFV['moment_center_m'][1]} m",
         "identical")]
table(s, rows, Inches(0.6), Inches(1.65), [Inches(2.3), Inches(5.0), Inches(4.8)], row_h=Inches(0.52), size=13,
      color_fn=lambda r, c, v: COL["box"] if c == 1 and r < 3 else COL["nobox"] if c == 2 and r < 3 else None)
text(s, Inches(0.6), Inches(6.05), Inches(12.1), Inches(1.0),
     ["Convergence rule (both): CL and CD change < 0.2 % per 50 iterations, 150–600 iterations per angle. "
      "Cm positive nose-up. Centre of pressure and neutral point are given in % of the mean aerodynamic chord "
      f"(MAC {REFV['length_m'] * 1000:.0f} mm) behind its leading edge."], size=13, color=MUTED)

# 2b summary of findings -------------------------------------------------------------
# neutral-point shift split by region: NP % MAC = const - 100 * dCm/dCL, and dCm/dCL is a sum over regions
dcl = {c: f(c, 4.0, "CL") - f(c, 0.0, "CL") for c in CASE}
NP_SHIFT = {n: -100 * ((B["4deg"]["box"]["regions"][n]["Cm"] - B["0deg"]["box"]["regions"][n]["Cm"]) / dcl["box"]
                       - (B["4deg"]["nobox"]["regions"][n]["Cm"] - B["0deg"]["nobox"]["regions"][n]["Cm"]) / dcl["nobox"])
            for n in B["4deg"]["box"]["regions"]}
d_np = A["box"]["neutral_point_pct_mac"] - A["nobox"]["neutral_point_pct_mac"]
s8, s12 = ST["0.8 mm"], ST["1.2 mm"]
cr8 = (s8["nobox"]["cruise"], s8["box"]["cruise"])
s = new_slide(prs, "Summary of the comparison; every number is from the slides that follow.")
title(s, "Summary", "What the payload box does to the aircraft")
find = [
    ("Drag", f"CD +{f('box',0,'CD') - f('nobox',0,'CD'):.4f} at 0° (+{pct(f('box',0,'CD'), f('nobox',0,'CD')):.0f} %) and "
             f"+{f('box',4,'CD') - f('nobox',4,'CD'):.4f} at 4° (+{pct(f('box',4,'CD'), f('nobox',4,'CD')):.0f} %). In cruise "
             f"(0.8 mm walls) drag goes {cr8[0]['drag_N']:.2f} → {cr8[1]['drag_N']:.2f} N (+{pct(cr8[1]['drag_N'], cr8[0]['drag_N']):.0f} %), "
             f"+{cr8[1]['power_W_at_20ms'] - cr8[0]['power_W_at_20ms']:.1f} W of drag power; best L/D {f('nobox',4,'L_over_D'):.2f} → "
             f"{f('box',4,'L_over_D'):.2f}."),
    ("Lift", f"CL within ±{max(abs(pct(f('box',a,'CL'), f('nobox',a,'CL'))) for a in ANGLES[:2]):.0f} % at 0° and 4°. The box "
             f"itself pushes down ({B['4deg']['box']['regions']['box']['lift_N'] - B['4deg']['nobox']['regions']['box']['lift_N']:+.2f} N "
             f"at 4°); lift slope {A['nobox']['CL_alpha_per_deg']:.4f} → {A['box']['CL_alpha_per_deg']:.4f} per degree."),
    ("Pitch / CP", f"The box adds a nose-up moment at 0° (Cm {fmt_cm(f('box',0,'Cm') - f('nobox',0,'Cm'))}) and moves the "
                   f"neutral point aft by {d_np:.1f} % MAC ({A['nobox']['neutral_point_pct_mac']:.1f} → "
                   f"{A['box']['neutral_point_pct_mac']:.1f} %), mostly through the V-tail "
                   f"({NP_SHIFT['V-tail + tail boom']:+.1f} % of it): the box changes the flow reaching the tail."),
    ("Stability", f"So removing the box costs static margin: {s8['box']['static_margin_pct']:.1f} → {s8['nobox']['static_margin_pct']:.1f} % "
                  f"(0.8 mm walls) and {s12['box']['static_margin_pct']:.1f} → {s12['nobox']['static_margin_pct']:.1f} % (1.2 mm, "
                  f"{'unstable' if s12['nobox']['static_margin_pct'] < 0 else 'marginal'}). Flying without the box needs the CG "
                  f"about {d_np / 100 * REFV['length_m'] * 1000:.0f} mm further forward to keep the same margin."),
    ("Mass", f"The box weighs {MS['0.8 mm']['box']['box_g']:.0f} g (0.8 mm) / {MS['1.2 mm']['box']['box_g']:.0f} g (1.2 mm) and sits "
             "close to the CG, so its mass moves the CG by under 0.5 mm: its effect is aerodynamic, not mass."),
]
y = Inches(1.6)
for k, v in find:
    text(s, Inches(0.6), y, Inches(1.9), Inches(0.9), k, size=17, bold=True, color=COL["box"])
    text(s, Inches(2.55), y, Inches(10.2), Inches(1.0), v, size=15)
    y += Inches(1.02)

# 3 full results table ----------------------------------------------------------
s = new_slide(prs, "All force results of both runs. Δ = with box minus without box.")
title(s, "Results: all angles, both configurations", f"Whole aircraft at {V:g} m/s")
hdr = ("AoA", "Configuration", "CL", "CD", "Cm", "L/D", "Lift N", "Drag N", "CP % MAC", "Iterations", "Status")
rows = [hdr]
for a in ANGLES:
    for c in ("nobox", "box"):
        pa = A[c]["per_aoa"][f"{a:g}"]
        rows.append((f"{a:g}°", LABEL[c], f"{f(c,a,'CL'):.4f}", f"{f(c,a,'CD'):.5f}", fmt_cm(f(c, a, 'Cm')),
                     f"{f(c,a,'L_over_D'):.2f}", f"{f(c,a,'lift_N'):.2f}", f"{f(c,a,'drag_N'):.3f}",
                     f"{pa['centre_of_pressure_pct_mac']:.1f}", F[c][a]["iterations"],
                     "converged" if F[c][a]["status"] == "converged" else "not conv. (mean)"))
    rows.append(("", "Δ (box)", f"{f('box',a,'CL') - f('nobox',a,'CL'):+.4f}", f"{f('box',a,'CD') - f('nobox',a,'CD'):+.5f}",
                 fmt_cm(f('box', a, 'Cm') - f('nobox', a, 'Cm')), f"{f('box',a,'L_over_D') - f('nobox',a,'L_over_D'):+.2f}",
                 f"{f('box',a,'lift_N') - f('nobox',a,'lift_N'):+.2f}", f"{f('box',a,'drag_N') - f('nobox',a,'drag_N'):+.3f}",
                 f"{A['box']['per_aoa'][f'{a:g}']['centre_of_pressure_pct_mac'] - A['nobox']['per_aoa'][f'{a:g}']['centre_of_pressure_pct_mac']:+.1f}",
                 "", ""))
table(s, rows, Inches(0.45), Inches(1.5), [Inches(w) for w in (0.6, 1.5, 0.95, 1.05, 1.0, 0.85, 0.95, 1.0, 1.15, 1.05, 2.3)],
      row_h=Inches(0.42), size=12,
      color_fn=lambda r, c, v: case_color(r, c, v) or (MUTED if rows[r][1] == "Δ (box)" else None)
      or (COL["box"] if "not" in v else None))
text(s, Inches(0.6), Inches(5.9), Inches(12.1), Inches(1.2),
     ["CP = centre of pressure (where the total lift acts), % MAC behind the wing's MAC leading edge.",
      "8° did not converge in either run (forces oscillate); its rows are the mean of the last 200 iterations, "
      "so treat the 8° differences with care."], size=12, color=MUTED)

# 4 headline numbers ------------------------------------------------------------
a = 4.0
s = new_slide(prs, "Headline changes at 4°, the converged angle nearest to cruise.")
title(s, "What the box changes (4°)", f"With box vs without box, {V:g} m/s")
cards = [(f"{pct(f('box',a,'CD'), f('nobox',a,'CD')):+.1f} %", f"drag coefficient\n{f('nobox',a,'CD'):.4f} → {f('box',a,'CD'):.4f}", COL["box"]),
         (f"{f('box',a,'drag_N') - f('nobox',a,'drag_N'):+.2f} N", f"drag at {V:g} m/s\n{f('nobox',a,'drag_N'):.2f} → {f('box',a,'drag_N'):.2f} N", COL["box"]),
         (f"{pct(f('box',a,'L_over_D'), f('nobox',a,'L_over_D')):+.1f} %", f"lift-to-drag\n{f('nobox',a,'L_over_D'):.2f} → {f('box',a,'L_over_D'):.2f}", COL["box"]),
         (f"{pct(f('box',a,'CL'), f('nobox',a,'CL')):+.1f} %", f"lift coefficient\n{f('nobox',a,'CL'):.4f} → {f('box',a,'CL'):.4f}", COL["nobox"])]
cw = Inches(2.85)
for i, (val, lab, col) in enumerate(cards):
    stat(s, Inches(0.6) + i * (cw + Inches(0.23)), Inches(1.6), cw, val, lab, col)
sb, sn = ST["0.8 mm"]["box"], ST["0.8 mm"]["nobox"]
cards2 = [(fmt_cm(f('box', a, 'Cm') - f('nobox', a, 'Cm')), "pitching moment Cm\n(about the reference point)", MUTED),
          (f"{A['box']['neutral_point_pct_mac'] - A['nobox']['neutral_point_pct_mac']:+.1f} pts",
           f"neutral point shift, % MAC\n{A['nobox']['neutral_point_pct_mac']:.1f} → {A['box']['neutral_point_pct_mac']:.1f} % MAC", MUTED),
          (f"{sb['static_margin_pct'] - sn['static_margin_pct']:+.1f} pts", f"static margin (0.8 mm walls)\n"
           f"{sn['static_margin_pct']:.1f} → {sb['static_margin_pct']:.1f} % MAC", MUTED),
          (f"{sb['cruise']['power_W_at_20ms'] - sn['cruise']['power_W_at_20ms']:+.1f} W",
           f"cruise power to overcome drag\n{sn['cruise']['power_W_at_20ms']:.1f} → {sb['cruise']['power_W_at_20ms']:.1f} W (0.8 mm)", MUTED)]
for i, (val, lab, col) in enumerate(cards2):
    stat(s, Inches(0.6) + i * (cw + Inches(0.23)), Inches(3.5), cw, val, lab, col)
text(s, Inches(0.6), Inches(5.45), Inches(12.1), Inches(1.6),
     ["Power = drag × speed at 20 m/s (aerodynamic power, before propeller and motor losses).",
      "Static margin uses each configuration's own mass and CG with its own CFD neutral point."], size=13, color=MUTED)

# 5 coefficient curves ------------------------------------------------------------
s = new_slide(prs, "CL, CD, Cm and L/D against angle of attack for both configurations.")
title(s, "Coefficients vs angle of attack", "Hollow marker: 8° did not converge (time average)")
image(s, FIG / "coefficients.png", Inches(0.45), Inches(1.6), w=Inches(12.4))

# 6 centre of pressure / neutral point --------------------------------------------
s = new_slide(prs, "Centre of pressure moves with angle; the neutral point is the fixed point used for stability. "
                   "Both from the CFD moments about the same reference point.")
title(s, "Centre of pressure, neutral point and pitch stability", "From the CFD moments (0° and 4°, converged)")
rows = [("Metric", "Without box", "With box", "Δ")]
def addrow(lbl, kb, kn, fmt_, scale=1.0):
    """One table row comparing a value of both cases."""
    vb, vn = kb * scale, kn * scale
    rows.append((lbl, fmt_.format(vn), fmt_.format(vb), ("{:+" + fmt_[2:]).format(vb - vn)))
for a in ANGLES:
    addrow(f"Centre of pressure at {a:g}°, % MAC", A["box"]["per_aoa"][f"{a:g}"]["centre_of_pressure_pct_mac"],
           A["nobox"]["per_aoa"][f"{a:g}"]["centre_of_pressure_pct_mac"], "{:.1f}")
addrow("Neutral point, % MAC", A["box"]["neutral_point_pct_mac"], A["nobox"]["neutral_point_pct_mac"], "{:.1f}")
addrow("dCm/dCL (about ref. point)", A["box"]["dCm_dCL"], A["nobox"]["dCm_dCL"], "{:.4f}")
addrow("Lift-curve slope CLα, per deg", A["box"]["CL_alpha_per_deg"], A["nobox"]["CL_alpha_per_deg"], "{:.4f}")
addrow("Cm at zero lift (Cm0)", A["box"]["Cm0_at_CL0"], A["nobox"]["Cm0_at_CL0"], "{:.4f}")
table(s, rows, Inches(0.6), Inches(1.6), [Inches(3.5), Inches(1.5), Inches(1.5), Inches(1.3)], row_h=Inches(0.48), size=14)
# right: where the neutral-point shift comes from (exact split, regions sum to the total)
rows2 = [("Region", "NP shift, % MAC")] + [("box itself" if n == "box" else n, f"{v:+.1f}") for n, v in NP_SHIFT.items()] \
        + [("total", f"{sum(NP_SHIFT.values()):+.1f}")]
table(s, rows2, Inches(8.75), Inches(1.6), [Inches(2.35), Inches(1.6)], row_h=Inches(0.48), size=13)
text(s, Inches(8.75), Inches(1.6) + Inches(0.48) * len(rows2) + Inches(0.1), Inches(3.95), Inches(1.0),
     "Positive = aft = more stable. Each region's share of the change in dCm/dCL between the two runs.",
     size=11, color=MUTED)
text(s, Inches(0.6), Inches(5.65), Inches(12.1), Inches(1.4),
     ["Centre of pressure = y_ref + c·Cm/CL. At low lift it sits far from the wing (a small CL divides the moment), "
      "so compare its change, not its value. 8° values are time averages of an unconverged run.",
      "Neutral point = y_ref + c·dCm/dCL from the 0° and 4° runs; a CG ahead of it is statically stable."], size=12, color=MUTED)

# 7 static margin with mass ---------------------------------------------------------
s = new_slide(prs, "Combines the mass model (CG) with each configuration's own CFD (neutral point).")
title(s, "Static margin and trim, with mass", "Each configuration with its own mass, CG and CFD neutral point")
image(s, FIG / "static_margin.png", Inches(0.45), Inches(1.45), w=Inches(12.4))
rows = [("Walls", "Configuration", "Mass g", "CG % MAC", "NP % MAC", "Static margin", "Trim CL*", "Cm about CG (cruise)", "Hover tail motor")]
for w, d in ST.items():
    for c in ("nobox", "box"):
        r = d[c]
        rows.append((w, LABEL[c], f"{r['mass_g']:,}", f"{r['cg_pct_mac']:.1f}", f"{r['neutral_point_pct_mac']:.1f}",
                     f"{r['static_margin_pct']:.1f} %",
                     f"{r['trim_CL']:.2f}" if r["trim_CL"] is not None else "n/a (neutral)", fmt_cm(r["Cm_about_cg_at_cruise"]),
                     f"{r['hover_tail_motor_pct']:.1f} %"))
table(s, rows, Inches(0.6), Inches(4.95), [Inches(w) for w in (0.9, 1.5, 1.0, 1.15, 1.15, 1.45, 1.0, 2.25, 1.75)],
      row_h=Inches(0.4), size=12, color_fn=case_color)
text(s, Inches(0.6), Inches(7.05), Inches(12.1), Inches(0.3),
     "* Trim CL = lift coefficient where the moment about the CG is zero with neutral elevators (straight-line fit "
     "of 0° and 4°); above ~1.0 it means the aircraft needs up-elevator to fly at cruise.", size=10, color=MUTED)

# 8 cruise performance ----------------------------------------------------------------
s = new_slide(prs, "Level flight at 20 m/s: lift = weight. AoA and CD interpolated linearly between the 0° and 4° runs.")
title(s, f"Cruise at {V:g} m/s", "Lift = weight; angle and drag interpolated between the converged 0° and 4° runs")
rows = [("Walls", "Configuration", "Mass g", "CL needed", "Angle of attack", "CD", "Drag N", "L/D", "Drag power W")]
for w, d in ST.items():
    for c in ("nobox", "box"):
        r = d[c]; cr = r["cruise"]
        rows.append((w, LABEL[c], f"{r['mass_g']:,}", f"{cr['CL']:.3f}", f"{cr['aoa_deg']:.2f}°", f"{cr['CD']:.4f}",
                     f"{cr['drag_N']:.2f}", f"{cr['L/D']:.2f}", f"{cr['power_W_at_20ms']:.1f}"))
table(s, rows, Inches(0.6), Inches(1.65), [Inches(w) for w in (1.0, 1.7, 1.1, 1.25, 1.6, 1.15, 1.15, 1.0, 1.6)],
      row_h=Inches(0.5), size=14, color_fn=case_color)
d8 = ST["0.8 mm"]; d12 = ST["1.2 mm"]
text(s, Inches(0.6), Inches(4.4), Inches(12.1), Inches(2.6),
     [[("Range / endurance: ", {"bold": True, "color": COL["box"]}),
       (f"at a fixed cruise speed the battery energy per km scales with drag, so the box costs about "
        f"{pct(d8['box']['cruise']['drag_N'], d8['nobox']['cruise']['drag_N']):.0f} % (0.8 mm walls) / "
        f"{pct(d12['box']['cruise']['drag_N'], d12['nobox']['cruise']['drag_N']):.0f} % (1.2 mm walls) more energy per km, "
        "i.e. roughly that much less range in fixed-wing flight.", {})],
      [("Weight: ", {"bold": True}),
       (f"the box itself is only {MS['0.8 mm']['box']['box_g']:.0f} g / {MS['1.2 mm']['box']['box_g']:.0f} g, so almost "
        "all of the penalty is aerodynamic drag, not weight.", {})],
      [("Drag power excludes propeller and motor efficiency; the electrical power is higher by 1/(η_prop·η_motor).",
        {"size": 12, "color": MUTED})]], size=15)

# 9 where it comes from --------------------------------------------------------------
s = new_slide(prs, "Forces summed over regions of the aircraft surface. The box's own force plus the change it causes "
                   "on the other parts (interference) add up to the total difference.")
title(s, "Where the difference comes from", "Force on each surface region: with box minus without box")
image(s, FIG / "breakdown_4deg.png", Inches(0.45), Inches(1.45), w=Inches(12.4))
regs = list(B["4deg"]["box"]["regions"])
rows = [("AoA", "Quantity") + tuple("box itself" if n == "box" else n for n in regs) + ("total",)]
for akey in ("0deg", "4deg"):
    for q, lab, fm in (("lift_N", "Δ lift N", "{:+.3f}"), ("drag_N", "Δ drag N", "{:+.3f}"), ("Cm", "Δ Cm", "{:+.4f}")):
        dv = [B[akey]["box"]["regions"][n][q] - B[akey]["nobox"]["regions"][n][q] for n in regs]
        rows.append((akey.replace("deg", "°"), lab) + tuple(fm.format(v) for v in dv) + (fm.format(sum(dv)),))
table(s, rows, Inches(0.45), Inches(4.85), [Inches(w) for w in (0.6, 1.0, 1.55, 1.45, 1.35, 1.8, 2.05, 1.55)],
      row_h=Inches(0.3), size=11)

# 10 Cp maps -------------------------------------------------------------------------
for akey in (4, 0):
    s = new_slide(prs, f"Underside pressure coefficient at {akey}°, seen from below. Right panel: change caused by the box "
                       "on the surfaces both runs share (box surfaces left out).")
    title(s, f"Surface pressure (Cp) underneath, {akey}°", "Blue = suction, orange = pressure; right: with box minus without box")
    image(s, FIG / f"cp_underside_{akey}deg.png", Inches(0.45), Inches(1.45), w=Inches(12.4))
    text(s, Inches(0.6), Inches(6.0), Inches(12.1), Inches(1.2),
         ["Dashed box = box footprint (black hole in the right panel: the belly is hidden by the box there). "
          "The box raises the pressure on the belly just ahead of it (orange) and causes suction along its sides (blue); "
          "elsewhere on the underside the change is small (speckle = mesh-to-mesh noise)."], size=13, color=MUTED)

# 11 belly line + span loading ---------------------------------------------------------
s = new_slide(prs, "Left: pressure along the bottom centreline. Right: how lift is spread along the span.")
title(s, "Belly pressure and spanwise lift, 4°", "Bottom centreline Cp (suction up) · lift per metre of span")
# stacked on the left (each figure is wide and short), explanation in a column on the right
image(s, FIG / "belly_cp_4deg.png", Inches(0.35), Inches(1.45), h=Inches(2.85))
image(s, FIG / "span_lift_4deg.png", Inches(0.35), Inches(4.4), h=Inches(2.85))
text(s, Inches(8.75), Inches(1.6), Inches(4.0), Inches(5.5),
     ["Belly: ahead of the box the flow stagnates against it and the belly pressure rises (Cp up to about +0.8); the "
      "flow then accelerates round the box's front edge (strong suction) and stays in mild suction under the box.",
      "Span: outboard of the motor booms (|x| > 0.3 m) the lift distribution is unchanged; between the booms the box "
      "lowers the lift slightly, most of all just beside the centreline."], size=14)

# 12 Fluent renders ------------------------------------------------------------------
pod_r, nob_r = CASE["box"] / "renders", CASE["nobox"] / "renders"
if (nob_r / "aoa4_2-surface-pressure_pod.png").exists():
    s = new_slide(prs, "Fluent surface pressure, same colour scale (−1.5 to 1.0) and camera, 4°.")
    title(s, "Fluent: surface pressure with and without the box, 4°", "Pressure coefficient, same scale and camera")
    # 2 x 2 grid: columns = with / without box, rows = two camera views; labels instead of captions (space)
    iw = Inches(5.0)
    for j, (c, lab) in enumerate((("box", "With box"), ("nobox", "Without box"))):
        text(s, Inches(1.75) + j * Inches(5.15), Inches(1.33), iw, Inches(0.35), lab, size=15, bold=True,
             color=COL[c], align=PP_ALIGN.CENTER)
    for i, (scene, view, cap) in enumerate((("2-surface-pressure", "pod", "close-up\nfrom below"),
                                             ("2-surface-pressure", "bottom", "underside"))):
        y = Inches(1.72) + i * Inches(2.88)
        text(s, Inches(0.4), y + Inches(1.1), Inches(1.25), Inches(0.8), cap, size=13, color=MUTED)
        image(s, pod_r / f"aoa4_{scene}_{view}.png", Inches(1.75), y, w=iw)
        image(s, nob_r / f"aoa4_{scene}_{view}.png", Inches(6.9), y, w=iw)
    s = new_slide(prs, "Streamlines released ahead of the nose, viewed from below, 4°.")
    title(s, "Fluent: streamlines past the belly, 4°", "Coloured by speed, 14–26 m/s")
    iw = Inches(6.0)
    image(s, pod_r / "aoa4_3-streamlines_pod.png", Inches(0.6), Inches(1.6), w=iw, caption="With box")
    image(s, nob_r / "aoa4_3-streamlines_pod.png", Inches(6.73), Inches(1.6), w=iw, caption="Without box")
    text(s, Inches(0.6), Inches(5.6), Inches(12.1), Inches(1.2),
         ["Same streamline rake, colour scale and camera in both pictures; the surface is coloured by pressure "
          "coefficient (same scale as the previous slide)."], size=13, color=MUTED)

# 13 convergence ----------------------------------------------------------------------
s = new_slide(prs, "Convergence of both runs. Spread = (max − min) / mean of the coefficient over the last 50 iterations.")
title(s, "Convergence, both runs", "Criterion: CL and CD change < 0.2 % per 50 iterations (150–600 iterations)")
rows = [("AoA", "Configuration", "Iterations", "CL spread, last 50", "CD spread, last 50", "Status")]
for a in ANGLES:
    for c in ("nobox", "box"):
        rows.append((f"{a:g}°", LABEL[c], F[c][a]["iterations"], f"{spread(c, a, 1):.2f} %", f"{spread(c, a, 2):.2f} %",
                     "converged" if F[c][a]["status"] == "converged" else "not converged (mean of last 200)"))
table(s, rows, Inches(0.6), Inches(1.6), [Inches(w) for w in (0.7, 1.55, 1.1, 1.6, 1.6, 3.0)], row_h=Inches(0.42), size=12,
      color_fn=lambda r, c, v: case_color(r, c, v) or (COL["box"] if "not" in v else None))
history_chart(s, Inches(0.6), Inches(4.75), Inches(5.95), Inches(2.5), "CL history, 0° (thin) and 4° (thick)", 1, "0.00")
history_chart(s, Inches(6.75), Inches(4.75), Inches(5.95), Inches(2.5), "CD history, 0° (thin) and 4° (thick)", 2, "0.000")

# 14 notes -----------------------------------------------------------------------------
s = new_slide(prs, "What the comparison does and doesn't cover.")
title(s, "Modelling notes")
panel(s, Inches(0.6), Inches(1.5), Inches(12.1), Inches(4.6))
text(s, Inches(0.95), Inches(1.8), Inches(11.4), Inches(4.2),
     [f"Same geometry, mesh settings, solver and reference values for both runs; meshes {CELLS['nobox']:,} vs "
      f"{CELLS['box']:,} cells (Ansys Student limit ~1M), so absolute drag is approximate but the difference is consistent.",
      "Box removed together with its hatch; the two mount lugs under the fuselage stay in both runs.",
      "Propellers not modelled; motors are static shapes. Openings under 24 mm were sealed by the shrink-wrap in both runs.",
      "8° did not converge in either run (unsteady flow); its values are averages of the last 200 iterations.",
      "Static margin, trim and cruise combine the CFD with the mass model (LW-PLA 0.54 g/cm³, 20 % infill, "
      "0.8 or 1.2 mm walls; catalogue component masses). The box is in its original position (not the 120 mm-forward layout)."],
     size=15)
text(s, Inches(0.6), Inches(6.35), Inches(12.1), Inches(0.6),
     "Files: aero_sim/cfd_pod (with box) · aero_sim/cfd_nobox (without box) · aero_sim/box_effect (comparison, "
     "box_effect.json, figures)", size=12, color=MUTED)

OUT.parent.mkdir(exist_ok=True)
prs.save(OUT)
print(f"wrote {OUT}  ({len(prs.slides)} slides)")
