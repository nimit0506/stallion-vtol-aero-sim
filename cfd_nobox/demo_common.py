"""
Shared definitions for the Fluent demo: surfaces, graphics objects, scenes and camera views.
Used by 04_demo_setup.py (builds and renders them) and demo.py (live presenter).

Model axes (from the STL): nose points +Y, up is +Z, span is X; lengths in metres.
Aircraft bounds roughly x -0.67..0.67, y -0.93..0.06, z 0..0.22; wing at y -0.39..-0.24.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config.json").read_text())
RESULTS = HERE / "results"                     # solved cases from 03_solve.py
DEMO_DIR = HERE / "demo"
DEMO_CASE = DEMO_DIR / "stallion_demo.cas.h5"  # 4 deg case with every demo object saved in it
RENDERS = HERE / "renders"                     # PNG stills / GIF
ANGLES = CFG["flight"]["aoa_deg"]              # [0, 4, 8]

WING_SECTION_X = 0.55          # airfoil cut: outboard of the boom, clear of a sealed servo-bay pocket at x~0.45
WAKE_Y = (-0.5, -0.8)          # cross-flow planes: just behind the wing trailing edge (y=-0.40), and mid-boom
# The far-field mesh is coarse, so the tip vortices smear out within ~1 span: keep wake planes close.

# ---- surfaces ---------------------------------------------------------------
PLANES = {
    "plane-center": {"method": "yz-plane", "x": 0.0},
    "plane-wing": {"method": "yz-plane", "x": WING_SECTION_X},
    "plane-wake-1-full": {"method": "zx-plane", "y": WAKE_Y[0]},
    "plane-wake-2-full": {"method": "zx-plane", "y": WAKE_Y[1]},
}
# planes cut the whole 8 m tunnel; clip them to a window around the aircraft (applied in order)
CLIPS = {
    "wake-1-x": ("plane-wake-1-full", "x-coordinate", -0.85, 0.85),
    "plane-wake-1": ("wake-1-x", "z-coordinate", -0.12, 0.30),
    "wake-2-x": ("plane-wake-2-full", "x-coordinate", -0.85, 0.85),
    "plane-wake-2": ("wake-2-x", "z-coordinate", -0.12, 0.30),
}
RAKES = {
    # spanwise sheet just above wing height (wing is at z 0.075-0.095), upstream of the nose
    "rake-wing": {"p0": [-0.66, 0.25, 0.11], "p1": [0.66, 0.25, 0.11], "number_of_points": 50},
    # vertical rake on the centreline -> flow over the fuselage and into the V-tail
    # extended down to z=-0.09 so lines also pass the under-fuselage pod (bottom at z=-0.065)
    "rake-fuselage": {"p0": [0.02, 0.25, -0.09], "p1": [0.02, 0.25, 0.24], "number_of_points": 24},
    # Tip vortices at 4 deg, measured on the y=-0.5 plane: cores at x=+-0.657, z=0.101 (y-vorticity
    # +-405 1/s), decaying to +-55 1/s by y=-0.8 (coarse far-field mesh).
    # Rake just under each tip (lower skin z~0.077), from mid-chord: lines wrap up round the tip.
    "rake-tip-r": {"p0": [0.60, -0.29, 0.068], "p1": [0.71, -0.29, 0.068], "number_of_points": 14},
    "rake-tip-l": {"p0": [-0.60, -0.29, 0.068], "p1": [-0.71, -0.29, 0.068], "number_of_points": 14},
}

# ---- graphics objects -------------------------------------------------------
# contour: field, surfaces, (min, max) or None for auto, colormap
CONTOURS = {
    "cp-aircraft": ("pressure-coefficient", ["aircraft"], (-1.5, 1.0), "bgr-modern"),
    "cp-aircraft-ctx": ("pressure-coefficient", ["aircraft"], (-1.5, 1.0), "bgr-modern"),  # no legend
    "vel-center": ("velocity-magnitude", ["plane-center"], (0.0, 28.0), "field-velocity"),
    "vel-wing-section": ("velocity-magnitude", ["plane-wing"], (0.0, 28.0), "field-velocity"),
    "cp-wing-section": ("pressure-coefficient", ["plane-wing"], (-1.5, 1.0), "bgr-modern"),
    "vort-wake": ("y-vorticity", ["plane-wake-1", "plane-wake-2"], (-40.0, 40.0), "diverging-cool-to-warm"),
    "yplus-aircraft": ("y-plus", ["aircraft"], (0.0, 30.0), "sequential-viridis"),
}
NO_LEGEND = ["cp-aircraft-ctx", "path-fuselage"]   # avoid stacked duplicate colour bars
PATH_STEPS = 800      # pathline length cap; 3000 ran every line out to the tunnel outlet 8 m downstream
# pathline: release rakes, colour field, (min, max), colormap
PATHLINES = {
    "path-wing": (["rake-wing"], "velocity-magnitude", (14.0, 26.0), "field-velocity"),
    "path-fuselage": (["rake-fuselage"], "velocity-magnitude", (14.0, 26.0), "field-velocity"),
    # coloured by streamwise vorticity: the spinning vortex lines light up (red/blue = opposite rotation)
    "path-tips": (["rake-tip-r", "rake-tip-l"], "y-vorticity", (-60.0, 60.0), "diverging-cool-to-warm"),
}
MESHES = {
    "aircraft-solid": (["aircraft"], False),     # plain shaded aircraft, for context
    "mesh-aircraft": (["aircraft"], True),       # surface mesh edges
    "mesh-center": (["plane-center"], True),     # volume mesh slice: prism layers + poly-hexcore
}
VECTORS = {
    "vec-wing-section": (["plane-wing"], (0.0, 28.0)),
}

# ---- scenes (the demo storyline) ---------------------------------------------
# key -> (scene name, title, graphics objects, default view)
SCENES = {
    "1": ("1-geometry-mesh", "Repaired geometry & CFD mesh", ["mesh-aircraft", "mesh-center"], "mesh-closeup"),
    "2": ("2-surface-pressure", "Surface pressure coefficient", ["cp-aircraft"], "iso"),
    "3": ("3-streamlines", "Streamlines over the aircraft", ["cp-aircraft-ctx", "path-wing", "path-fuselage"], "iso"),
    "4": ("4-wing-section", "Flow around the wing section", ["vel-wing-section"], "section"),
    "5": ("5-tip-vortices", "Wing-tip vortices", ["cp-aircraft-ctx", "path-tips"], "tip"),
    "6": ("6-wake", "Wake: streamwise vorticity", ["cp-aircraft-ctx", "vort-wake"], "wake"),
    "7": ("7-wall-yplus", "Mesh check: wall y+", ["yplus-aircraft"], "top"),
}

# ---- camera views (position, target, up, field width/height in m) -------------
VIEWS = {
    "iso": {"position": [1.75, 1.15, 1.05], "target": [0.0, -0.42, 0.08], "up_vector": [0, 0, 1], "field": [1.25, 1.25]},
    "top": {"position": [0.0, -0.43, 4.0], "target": [0.0, -0.43, 0.1], "up_vector": [0, 1, 0], "field": [1.6, 1.6]},
    "bottom": {"position": [0.0, -0.43, -4.0], "target": [0.0, -0.43, 0.1], "up_vector": [0, 1, 0], "field": [1.6, 1.6]},
    "front": {"position": [0.0, 4.0, 0.12], "target": [0.0, -0.43, 0.12], "up_vector": [0, 0, 1], "field": [1.5, 1.5]},
    "section": {"position": [3.0, -0.33, 0.085], "target": [WING_SECTION_X, -0.33, 0.085], "up_vector": [0, 0, 1], "field": [0.36, 0.36]},
    "tip": {"position": [1.75, -0.15, 0.6], "target": [0.38, -0.7, 0.1], "up_vector": [0, 0, 1], "field": [0.85, 0.85]},
    "wake": {"position": [1.6, 0.7, 1.0], "target": [0.0, -0.6, 0.08], "up_vector": [0, 0, 1], "field": [1.4, 1.4]},
    "rear": {"position": [-1.4, -3.4, 0.8], "target": [0.0, -0.6, 0.08], "up_vector": [0, 0, 1], "field": [1.6, 1.6]},
    # under-fuselage pod close-up from below, front quarter
    "pod": {"position": [0.75, 0.45, -0.5], "target": [0.0, -0.25, -0.01], "up_vector": [0, 0, 1], "field": [0.6, 0.6]},
    "mesh-closeup": {"position": [1.2, 0.35, 0.45], "target": [0.0, -0.25, 0.08], "up_vector": [0, 0, 1], "field": [0.65, 0.65]},
}
# extra stills rendered per scene besides its default view
EXTRA_VIEWS = {"2-surface-pressure": ["top", "bottom", "front", "pod"], "3-streamlines": ["top", "pod"],
               "6-wake": ["rear"]}


def apply_graphics_style(s, effects=True):
    """Dark theme, no grid, full-HD pictures; ground reflection + shadow when effects=True.
    The live GUI places the reflection plane differently (a big mirrored aircraft appears in view),
    so demo.py passes effects=False.
    Also switches off overwrite confirmations: with a hidden window an unanswered dialog hangs Fluent."""
    try:
        s.settings.file.confirm_overwrite = False
        s.settings.file.batch_options.confirm_overwrite = False
    except Exception:
        pass                                     # setting names differ between Fluent versions
    g = s.settings.results.graphics
    g.colors.graphics_color_theme = "dark"
    try:
        # preferences live outside the case file; not every version exposes them through PyFluent
        ge = s.preferences.Graphics.GraphicsEffects
        ge.GridPlaneEnabled = False
        ge.ReflectionsEnabled = effects
        ge.SimpleShadowsEnabled = effects
    except Exception:
        pass
    pic = g.picture
    pic.use_window_resolution = False            # fixed 1920x1080, whatever the window size
    pic.x_resolution = 1920
    pic.y_resolution = 1080
    pic.invert_background = False


def set_view(s, view):
    """Fluent applies each camera property on its own and rejects (with a warning dialog, which
    hangs a hidden-GUI session) any state where the up vector lies along the line of sight.
    So pick an order of the three updates in which every intermediate state is valid."""
    cam = s.settings.results.graphics.views.camera
    v = VIEWS[view]
    for op, value in _camera_steps(list(cam.position()), list(cam.target()), list(cam.up_vector()), v):
        setattr(cam, op, value)
    cam.field = v["field"]                       # zoom: width/height of the visible window, m


def _parallel(a, b):
    """True if vectors a and b are (nearly) parallel, or one is zero: an invalid up/sight pair."""
    cross = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return na * nb == 0 or sum(x * x for x in cross) ** 0.5 < 0.05 * na * nb


def _camera_steps(pos, tgt, up, v):
    """Order in which to set position / target / up_vector so no intermediate camera is invalid.
    Tries all 6 orders, then the same with a temporary helper up vector set first."""
    from itertools import permutations
    goal = {"position": v["position"], "target": v["target"], "up_vector": v["up_vector"]}
    # optional first step: a helper up vector, for when no direct order works
    for pre in [None, [1, 0, 0], [0, 1, 0], [0, 0, 1]]:
        for order in permutations(goal):
            state = {"position": pos, "target": tgt, "up_vector": up}
            steps = ([("up_vector", pre)] if pre else []) + [(k, goal[k]) for k in order]
            ok = True
            for k, val in steps:                         # simulate the steps, check each state
                state = {**state, k: val}
                sight = [t - p for t, p in zip(state["target"], state["position"])]   # line of sight
                if _parallel(state["up_vector"], sight):
                    ok = False
                    break
            if ok:
                return steps
    raise ValueError(f"no valid camera path to {v}")


def show_scene(s, key_or_name, view=None):
    """Display a scene by menu key ('1'..) or name, then move the camera."""
    for k, (name, title, objs, default_view) in SCENES.items():
        if key_or_name in (k, name):
            s.settings.results.scene[name].display()
            set_view(s, view or default_view)
            return name, title
    raise KeyError(key_or_name)


def data_file(aoa):
    """Solution data of one angle (03_solve.py names negative angles with 'm', e.g. aoa_m2)."""
    return RESULTS / f"aoa_{aoa:g}.dat.h5".replace("-", "m")


def forces_table():
    """Rows of results/forces.csv as dicts (empty list before the solver has run)."""
    import csv
    path = RESULTS / "forces.csv"
    if not path.exists():
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))
