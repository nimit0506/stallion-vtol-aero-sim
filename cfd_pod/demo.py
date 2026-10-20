"""
Live demo presenter: opens Fluent WITH its GUI on the demo case and drives it from this console,
one key per action, so nothing has to be set up live on stage.

  demo.bat                      (or)  ..\\.venv\\Scripts\\python.exe demo.py
  demo.bat --fluent-only        just open Fluent on the demo case and leave it to you

Keys:  1-7 scenes   a cycle angle of attack (0/4/8 deg)   v next camera view   f forces table
       r reset camera   s save a screenshot to renders/   h help   q quit (closes Fluent)
       x exit this console but leave Fluent open

The Fluent window stays fully interactive: rotate/zoom with the mouse, open anything from the
Outline tree (Results > Graphics / Scenes hold every object this script uses).
Needs demo/stallion_demo.cas.h5 from 04_demo_setup.py (demo.bat builds it if missing).
"""
import argparse
import sys
import time

import ansys.fluent.core as pf

from demo_common import (ANGLES, CFG, DEMO_CASE, DEMO_DIR, EXTRA_VIEWS, RENDERS, SCENES,
                         apply_graphics_style, data_file, forces_table, show_scene)

# one-liners for the presenter, printed when a scene comes up
TALK = {
    "1": "96-part GLB with pod -> sealed voxel shrink-wrap -> watertight skin; poly-hexcore, 3 prism layers, 562k cells.",
    "2": "Blue = suction on the wing upper surface (lift), red = stagnation at the nose and leading edges.",
    "3": "Streamlines bend up ahead of the wing (upwash) and down behind it (downwash) - that turning is lift.",
    "4": "Wing section at 0.55 m span: fast flow over the top (suction peak), slower underneath.",
    "5": "Tip vortices: high pressure below spills round the tip; red/blue = opposite rotation each side.",
    "6": "Wake planes 0.1 m and 0.4 m behind the wing: the vortex pair weakens as it moves downstream.",
    "7": "Wall y+ ~ 5-25: wall functions regime; fine for forces, too coarse to resolve laminar transition.",
}


def say(msg=""):
    """Print immediately (the console is the presenter's only feedback)."""
    print(msg, flush=True)


def print_forces(current=None):
    """Forces table from results/forces.csv; '>' marks the angle currently loaded."""
    rows = forces_table()
    if not rows:
        say("  (results/forces.csv not found)")
        return
    say("   AoA     CL       CD       Cm      L/D    lift N  drag N   status")
    for r in rows:
        mark = ">" if current is not None and float(r["aoa_deg"]) == current else " "
        say(f" {mark}{float(r['aoa_deg']):4.0f}  {float(r['CL']):7.4f}  {float(r['CD']):7.4f}  {float(r['Cm']):7.4f}"
            f"  {float(r['L_over_D']):5.2f}  {float(r['lift_N']):6.2f}  {float(r['drag_N']):6.2f}   {r['status']}")
    say(f"  ({CFG['flight']['speed_m_s']:g} m/s, sea-level air, k-omega SST; 8 deg = mean of last 200 iterations)")


def help_text():
    """List of keys and scenes."""
    say("\n  scenes:")
    for k, (name, title, objs, view) in SCENES.items():
        say(f"    {k}  {title}")
    say("  a  next angle of attack     v  next camera view of this scene     f  forces table")
    say("  r  reset camera             s  screenshot -> renders/             h  this help")
    say("  q  quit (closes Fluent)     x  leave Fluent open and exit this console\n")


def read_key():
    """single keypress without Enter on Windows consoles; falls back to input()"""
    try:
        import msvcrt                              # Windows-only console module
        if sys.stdin.isatty():
            ch = msvcrt.getwch()                   # blocks until a key is pressed
            if ch in ("\x00", "\xe0"):      # arrow/function keys: swallow the second byte
                msvcrt.getwch()
                return ""
            return ch.lower()
    except ImportError:
        pass
    return input("> ").strip().lower()[:1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fluent-only", action="store_true", help="open Fluent on the demo case, no presenter")
    ap.add_argument("--aoa", type=float, default=4.0, help="starting angle of attack")
    args = ap.parse_args()
    if not DEMO_CASE.exists():
        raise SystemExit(f"{DEMO_CASE} not found - run 04_demo_setup.py first (demo.bat does it for you)")

    say("Starting Fluent with its GUI (about a minute) ...")
    # with --fluent-only Fluent must outlive this script, so don't let PyFluent close it on exit
    s = pf.launch_fluent(mode="solver", precision="double", dimension=3,
                         processor_count=CFG["processors"], ui_mode="gui", cwd=str(DEMO_DIR),
                         start_timeout=300, cleanup_on_exit=not args.fluent_only)
    s.settings.file.read_case_data(file_name=str(DEMO_CASE))   # 4 deg data
    apply_graphics_style(s, effects=False)                      # no reflections in the live window
    aoa = 4.0
    if args.aoa != aoa:                                         # start on another angle: swap data only
        s.settings.file.read_data(file_name=str(data_file(args.aoa)))
        aoa = args.aoa
    scene_key = "2"                                             # open on the surface-pressure scene
    show_scene(s, scene_key)

    if args.fluent_only:
        say("Fluent is open on the demo case: Outline tree > Results > Scenes / Graphics. This console can close.")
        return

    view_idx = 0                                                # which camera view of the scene is up
    say(f"\nVTOL 'Stallion' CFD demo - AoA {aoa:g} deg loaded. Press h for help.")
    help_text()
    say(f"[{scene_key}] {SCENES[scene_key][1]}\n    {TALK[scene_key]}")
    # presenter loop: one key = one action
    while True:
        k = read_key()
        if not k:
            continue
        try:
            if k in SCENES:                                     # 1-7: switch scene, default view
                scene_key, view_idx = k, 0
                show_scene(s, k)
                say(f"[{k}] {SCENES[k][1]}  (AoA {aoa:g} deg)\n    {TALK[k]}")
            elif k == "a":                                      # next angle: reload data, keep scene + view
                aoa = ANGLES[(ANGLES.index(aoa) + 1) % len(ANGLES)] if aoa in ANGLES else ANGLES[0]
                say(f"loading AoA {aoa:g} deg ...")
                t0 = time.time()
                s.settings.file.read_data(file_name=str(data_file(aoa)))
                name = SCENES[scene_key][0]
                views = [SCENES[scene_key][3]] + EXTRA_VIEWS.get(name, [])
                show_scene(s, scene_key, views[view_idx % len(views)])
                say(f"AoA {aoa:g} deg  ({time.time() - t0:.0f} s)")
                print_forces(aoa)
            elif k == "v":                                      # cycle this scene's camera views
                name = SCENES[scene_key][0]
                views = [SCENES[scene_key][3]] + EXTRA_VIEWS.get(name, []) + ["iso", "top", "front"]
                views = list(dict.fromkeys(views))              # de-duplicate, keep order
                view_idx = (view_idx + 1) % len(views)
                show_scene(s, scene_key, views[view_idx])
                say(f"view: {views[view_idx]}")
            elif k == "r":                                      # back to the scene's default view
                view_idx = 0
                show_scene(s, scene_key)
            elif k == "f":
                print_forces(aoa)
            elif k == "s":                                      # screenshot of the current window
                RENDERS.mkdir(exist_ok=True)
                out = RENDERS / f"live_{time.strftime('%H%M%S')}_aoa{aoa:g}_{SCENES[scene_key][0]}.png"
                s.settings.results.graphics.picture.save_picture(file_name=str(out))
                say(f"saved {out}")
            elif k == "h":
                help_text()
            elif k == "x":
                say("Leaving Fluent open. Close it from its own window (File > Exit).")
                s.exit = lambda *a, **kw: None      # keep the server alive
                return
            elif k == "q":
                say("Closing Fluent ...")
                s.exit()
                return
        except Exception as e:                       # keep the show going
            say(f"  ! {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
