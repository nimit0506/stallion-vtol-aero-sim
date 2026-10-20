"""
Two matching renders of the aircraft: with the payload box (VIAL POD) and without it.

  ..\\.venv\\Scripts\\python.exe render_box.py [--glb file.glb]

Writes box_renders\\with_box.png and box_renders\\without_box.png (same camera).
"""
import argparse
from pathlib import Path

import pyvista as pv

import move_parts as mp

HERE = Path(__file__).resolve().parent
BOX = "VIAL POD"                        # name prefix of the box and its hatch
# part colour by name prefix (first match wins); everything else is light grey
COLOURS = [("VIAL POD", "#FF8A3D"), ("CARBON", "#2E3135"), ("MOTOR ", "#3A3E44"), ("BATTERY", "#4DA3FF")]
VIEWS = {   # camera position, focal point, up  (mm, x span, y forward, z up)
    "front": [(-1250, 900, -420), (-140, -420, 100), (0, 0, 1)],
    "side": [(-1500, -250, -260), (0, -380, 40), (0, 0, 1)],
}


def render(meshes, path, view, title):
    """Off-screen 1920x1080 render of [(name, PolyData)] from a fixed camera."""
    p = pv.Plotter(off_screen=True, window_size=(1920, 1080))
    p.set_background("#16181B", top="#2A2E33")                 # dark vertical gradient
    for nm, m in meshes:
        col = next((c for k, c in COLOURS if nm.startswith(k)), "#D9DCE0")
        p.add_mesh(m, color=col, smooth_shading=True, specular=0.25, specular_power=20)
    p.add_text(title, position="upper_left", font_size=18, color="white")
    p.camera_position = VIEWS[view]; p.camera.view_angle = 22    # fixed camera: both images match
    p.enable_anti_aliasing("ssaa")                               # supersampling: smooth edges
    p.screenshot(path); p.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", type=Path, default=mp.GLB)
    ap.add_argument("--view", choices=VIEWS, default="front")
    args = ap.parse_args()
    out = HERE / "box_renders"; out.mkdir(exist_ok=True)
    js, buf = mp.load_glb(args.glb)
    meshes = list(mp.part_meshes(js, buf).values())              # [(name, PolyData mm)]
    render(meshes, str(out / "with_box.png"), args.view, "Stallion V2 - with payload box")
    # same scene with the box parts left out
    render([m for m in meshes if not m[0].startswith(BOX)], str(out / "without_box.png"), args.view,
           "Stallion V2 - without payload box")
    print("wrote", out)


if __name__ == "__main__":
    main()
