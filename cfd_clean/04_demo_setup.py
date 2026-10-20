"""
Step 4 - Build the Fluent demo: slice planes, streamline rakes, vortex iso-surface, contours,
pathlines, scenes and camera views, saved INTO a Fluent case so they show up in Fluent's
Outline tree (Results > Graphics / Scenes). Then render every scene at every angle to renders/.

  ..\\.venv\\Scripts\\python.exe 04_demo_setup.py              build demo case + render stills
  ..\\.venv\\Scripts\\python.exe 04_demo_setup.py --orbit      + fly-around GIF (renders/orbit_aoa4.gif)
  ..\\.venv\\Scripts\\python.exe 04_demo_setup.py --no-render  build the demo case only

Output: demo/stallion_demo.cas.h5 (+ .dat.h5, 4 deg)   renders/aoa<a>_<scene>_<view>.png
Needs results/aoa_*.cas.h5/.dat.h5 from 03_solve.py.
"""
import argparse
import time
from pathlib import Path

import ansys.fluent.core as pf

from demo_common import (ANGLES, CFG, CLIPS, CONTOURS, DEMO_CASE, DEMO_DIR, EXTRA_VIEWS, MESHES, NO_LEGEND,
                         PATH_STEPS, PATHLINES, PLANES, RAKES, RENDERS, RESULTS, SCENES, VECTORS,
                         apply_graphics_style, data_file, show_scene)


def log(msg):
    """Timestamped progress line."""
    print(f"[demo {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get_or_create(container, name):
    """Named Fluent object (surface, graphic, scene): create it once, reuse it on reruns."""
    if name not in container:
        container.create(name)
    return container[name]


def build(s):
    """Create every surface, graphics object and scene defined in demo_common.py inside the open case."""
    r = s.settings.results
    surf, g = r.surfaces, r.graphics

    # --- surfaces: cut planes, clipped planes (e.g. a plane trimmed to the wake region), rakes
    for name, props in PLANES.items():
        get_or_create(surf.plane_surface, name).set_state(props)
    for name, (source, field, lo, hi) in CLIPS.items():
        get_or_create(surf.iso_clip, name).set_state(
            {"field": field, "surfaces": [source], "range": {"minimum": lo, "maximum": hi}})
    for name, props in RAKES.items():
        get_or_create(surf.rake_surface, name).set_state(props)
    log(f"surfaces: {list(PLANES) + list(CLIPS) + list(RAKES)}")

    # --- contours: fixed colour ranges, so the 0 / 4 / 8 deg pictures compare directly
    for name, (field, surfaces, rng, cmap) in CONTOURS.items():
        c = get_or_create(g.contour, name)
        c.field = field
        c.surfaces_list = surfaces
        if rng:
            c.range_option.option = "auto-range-off"
            c.range_option.auto_range_off.minimum = rng[0]
            c.range_option.auto_range_off.maximum = rng[1]
        c.color_map.color = cmap
        c.color_map.format = "%0.2f" if abs(rng[1] if rng else 10) < 10 else "%0.0f"   # decimals for Cp
    # --- pathlines (streamlines) released from the rakes
    for name, (rakes, field, rng, cmap) in PATHLINES.items():
        p = get_or_create(g.pathline, name)
        p.field = field
        p.release_from_surfaces = rakes
        p.step = PATH_STEPS
        p.range_options = {"auto_range": False, "minimum": rng[0], "maximum": rng[1]}
        p.style_attribute.line_width = 2
        p.color_map.color = cmap
        p.color_map.format = "%0.0f"
    # --- mesh displays (surface mesh, prism layers on the centre plane)
    for name, (surfaces, edges) in MESHES.items():
        m = get_or_create(g.mesh, name)
        m.surfaces_list = surfaces
        m.options.edges = edges
        m.options.faces = True
    # --- velocity vectors (every 3rd point, so arrows don't overlap)
    for name, (surfaces, rng) in VECTORS.items():
        v = get_or_create(g.vector, name)
        v.surfaces_list = surfaces
        v.field = "velocity-magnitude"
        v.range_options = {"auto_range": False, "minimum": rng[0], "maximum": rng[1],
                           "global_range": True, "clip_to_range": False}
        v.skip = 2
    # one colour bar per scene: hide the legend of objects that share a scene with another legend
    for kind, names in ((g.contour, CONTOURS), (g.pathline, PATHLINES)):
        for name in names:
            kind[name].color_map.visible = name not in NO_LEGEND
    log(f"graphics: {list(CONTOURS) + list(PATHLINES) + list(MESHES) + list(VECTORS)}")

    # --- scenes: groups of graphics objects shown together (the demo's numbered steps)
    for key, (name, title, objs, view) in SCENES.items():
        sc = get_or_create(r.scene, name)
        sc.title = title
        for o in list(sc.graphics_objects.get_object_names()):   # drop objects left from older runs
            if o not in objs:
                del sc.graphics_objects[o]
        for o in objs:
            sc.graphics_objects[o] = {}
    log(f"scenes: {[v[0] for v in SCENES.values()]}")
    # camera views are not stored in the case: demo.py applies them (demo_common.VIEWS)


def render(s, angles, orbit):
    """Save every scene from each of its camera views, for each angle, as a PNG."""
    RENDERS.mkdir(exist_ok=True)
    pic = s.settings.results.graphics.picture
    for aoa in angles:
        # same mesh for every angle: swapping only the data file takes seconds
        s.settings.file.read_data(file_name=str(data_file(aoa)))
        log(f"AoA {aoa:g}: data loaded, rendering")
        for key, (name, title, objs, view) in SCENES.items():
            for v in [view] + EXTRA_VIEWS.get(name, []):
                show_scene(s, name, v)
                out = RENDERS / f"aoa{aoa:g}_{name}_{v}.png"
                pic.save_picture(file_name=str(out))
        log(f"AoA {aoa:g}: {len(list(RENDERS.glob(f'aoa{aoa:g}_*.png')))} pictures")
    if orbit:
        make_orbit(s)


def make_orbit(s, aoa=4, frames=60):
    """Fly-around of the streamline scene: camera orbits 360 deg, frames -> animated GIF."""
    from PIL import Image
    s.settings.file.read_data(file_name=str(data_file(aoa)))
    show_scene(s, "3-streamlines", "iso")
    cam = s.settings.results.graphics.views.camera
    pic = s.settings.results.graphics.picture
    pic.x_resolution, pic.y_resolution = 960, 540          # smaller frames keep the GIF small
    tmp = RENDERS / "_orbit"
    tmp.mkdir(exist_ok=True)
    paths = []
    for i in range(frames):
        p = tmp / f"f{i:03d}.png"
        pic.save_picture(file_name=str(p))
        paths.append(p)
        cam.orbit(right=360.0 / frames, up=0.0)              # step the camera round the aircraft
    # GIF needs palette images; 80 ms per frame, loop forever
    imgs = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in paths]
    out = RENDERS / f"orbit_aoa{aoa}.gif"
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=80, loop=0, optimize=True)
    for p in paths:                                         # remove the temporary frames
        p.unlink()
    tmp.rmdir()
    pic.x_resolution, pic.y_resolution = 1920, 1080          # back to full-HD stills
    log(f"orbit -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--orbit", action="store_true", help="also make a fly-around GIF")
    ap.add_argument("--aoa", type=float, nargs="*", help="angles to render (default: all)")
    ap.add_argument("--connect", help="attach to a running Fluent: text file with ip, port, password")
    args = ap.parse_args()
    base = RESULTS / "aoa_4.cas.h5"                          # the demo case is built on the 4 deg solution
    if not base.exists():
        raise SystemExit(f"{base} not found - run 03_solve.py first")
    DEMO_DIR.mkdir(exist_ok=True)

    if args.connect:
        ip, port, pw = Path(args.connect).read_text().split()
        s = pf.connect_to_fluent(ip=ip, port=int(port), password=pw,
                                 cleanup_on_exit=False, start_watchdog=False)
    else:
        log("launching Fluent (hidden window, needed for pictures) ...")
        s = pf.launch_fluent(mode="solver", precision="double", dimension=3,
                             processor_count=CFG["processors"], ui_mode="hidden_gui",
                             cwd=str(DEMO_DIR), start_timeout=300)
    try:
        s.settings.file.read_case_data(file_name=str(base))
        apply_graphics_style(s)                              # dark background, fonts, lighting
        build(s)
        # saving the case stores all the objects, so they appear in Fluent's Outline tree for demo.bat
        s.settings.file.write(file_type="case-data", file_name=str(DEMO_CASE))
        log(f"wrote {DEMO_CASE}")
        if not args.no_render:
            render(s, args.aoa or ANGLES, args.orbit)
    finally:
        if not args.connect:                                 # free the Student licence
            s.exit()


if __name__ == "__main__":
    main()

