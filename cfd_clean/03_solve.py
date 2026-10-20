"""
Step 3 - Run the Fluent solver on the mesh from step 2 for each angle of attack (PyFluent).

  ..\\.venv\\Scripts\\python.exe 03_solve.py               (all angles in config.json)
  ..\\.venv\\Scripts\\python.exe 03_solve.py --aoa 4       (just one angle)
  ..\\.venv\\Scripts\\python.exe 03_solve.py --iterations 50   (quick smoke test)

Physics: steady, incompressible air, pressure-based coupled solver, k-omega SST.
The angle of attack is set by tilting the free-stream velocity, so one mesh is
used for every angle. Lift is perpendicular to the free stream, drag along it.

Output (results/):
  forces.csv                 CL, CD, Cm, L/D, lift and drag in newtons per angle
  aoa_<a>.cas.h5 / .dat.h5   Fluent case + data - open in Fluent or CFD-Post
  aoa_<a>_forces.out         convergence history of CL / CD / Cm
"""
import argparse
import csv
import json
import math
from pathlib import Path

import ansys.fluent.core as pf

HERE = Path(__file__).resolve().parent                                 # this case's folder
CFG = json.loads((HERE / "config.json").read_text())                   # flight, reference, solver settings
REPORT = json.loads((HERE / "geometry_report.json").read_text())       # geometry estimates from step 1
MESH_FILE = HERE / "mesh" / "aircraft.msh.h5"                          # written by 02_mesh.py
RES = HERE / "results"

# Wind-tunnel faces from 02_mesh.py. Every face except the one behind the tail is a velocity inlet,
# so tilting the inlet velocity vector changes the angle of attack without re-meshing.
INLETS = ["tunnel-ymax", "tunnel-xmin", "tunnel-xmax", "tunnel-zmin", "tunnel-zmax"]
OUTLET = "tunnel-ymin"


def log(msg):
    """Progress line, flushed so logs\\solve_log.txt updates live."""
    print(f"[solve] {msg}", flush=True)


def unit(v):
    """Normalise a 3-vector (plain lists: Fluent settings want lists, not numpy arrays)."""
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v]


def cross(a, b):
    """Cross product a x b."""
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def directions(aoa_deg):
    """Free-stream, drag, lift unit vectors and pitch axis in model coordinates."""
    f, u = unit(CFG["axes"]["forward"]), unit(CFG["axes"]["up"])
    a = math.radians(aoa_deg)
    # air comes at the nose and, at positive AoA, from below
    flow = [-math.cos(a) * fi + math.sin(a) * ui for fi, ui in zip(f, u)]
    lift = [math.sin(a) * fi + math.cos(a) * ui for fi, ui in zip(f, u)]
    pitch_axis = cross(f, u)            # nose-up moment is positive about this axis
    return flow, flow, lift, pitch_axis  # drag direction = free-stream direction


def reference():
    """Reference area, length (chord) and moment centre: config.json values, or step-1 estimates if null."""
    r, est = CFG["reference"], REPORT["reference"]
    area = r["area_m2"] or est["wing_area_est_m2"]
    length = r["length_m"] or est["mean_chord_est_m"]
    cg = r["moment_center_m"] or est["moment_center_est_m"]
    return area, length, cg


def setup(s, wall_zones):
    """Physics, material, reference values, boundary types and numerics (everything except the AoA)."""
    fl = CFG["flight"]
    st = s.settings.setup
    # pressure-based solver + k-omega SST: the standard choice for low-speed external aero
    st.general.solver.type = "pressure-based"
    st.models.viscous.model = "k-omega"
    st.models.viscous.k_omega_model = "sst"

    # 20 m/s is Mach 0.06: constant-density (incompressible) air is accurate
    air = st.materials.fluid["air"]
    air.density.option = "constant"
    air.density.value = fl["density_kg_m3"]
    air.viscosity.option = "constant"
    air.viscosity.value = fl["viscosity_kg_m_s"]

    # Fluent turns forces into coefficients with these: C = F / (0.5 rho V^2 * area), Cm also / length
    area, length, _ = reference()
    rv = st.reference_values
    rv.area = area
    rv.length = length
    rv.velocity = fl["speed_m_s"]
    rv.density = fl["density_kg_m3"]
    rv.viscosity = fl["viscosity_kg_m_s"]

    # outlet at free-stream pressure; inlets get their velocity vector later in set_aoa()
    bc = st.boundary_conditions
    po = bc.pressure_outlet[OUTLET]
    po.momentum.gauge_pressure.value = 0.0
    po.turbulence.turbulence_specification = "Intensity and Viscosity Ratio"
    po.turbulence.backflow_turbulent_intensity = fl["turbulence_intensity"]
    po.turbulence.backflow_turbulent_viscosity_ratio = fl["turbulent_viscosity_ratio"]
    for z in INLETS:
        vi = bc.velocity_inlet[z]
        vi.momentum.velocity_specification_method = "Components"
        vi.turbulence.turbulence_specification = "Intensity and Viscosity Ratio"
        vi.turbulence.turbulent_intensity = fl["turbulence_intensity"]
        vi.turbulence.turbulent_viscosity_ratio = fl["turbulent_viscosity_ratio"]

    # coupled pressure-velocity solver with pseudo-time stepping: robust and quick to converge
    sol = s.settings.solution
    sol.methods.p_v_coupling.flow_scheme = "Coupled"
    sol.methods.pseudo_time_method.formulation.coupled_solver = "global-time-step"
    sol.methods.high_order_term_relaxation.enable = True

    # residual targets set low on purpose: convergence is judged on the forces (iterate_to_convergence)
    for eq in sol.monitor.residual.equations.keys():
        sol.monitor.residual.equations[eq].absolute_criteria = 1e-5


def set_aoa(s, aoa, wall_zones, tag):
    """Point the free stream for this angle and (re)define the CL / CD / Cm reports and their output file."""
    fl = CFG["flight"]
    V = fl["speed_m_s"]
    flow, drag, lift, axis = directions(aoa)
    bc = s.settings.setup.boundary_conditions
    for z in INLETS:
        mom = bc.velocity_inlet[z].momentum
        mom.velocity_components = [V * c for c in flow]

    # force reports: lift/drag are projected on the AoA-dependent directions, so they are redone per angle
    _, _, cg = reference()
    rd = s.settings.solution.report_definitions
    for name, kind, vec, out in (("cl", rd.lift, lift, "Lift Coefficient"),
                                 ("cd", rd.drag, drag, "Drag Coefficient")):
        if name not in kind:
            kind.create(name)
        kind[name].zones = wall_zones
        kind[name].force_vector = vec
        kind[name].report_output_type = out
    if "cm" not in rd.moment:
        rd.moment.create("cm")
    rd.moment["cm"].zones = wall_zones
    rd.moment["cm"].mom_center = cg
    rd.moment["cm"].mom_axis = axis
    rd.moment["cm"].report_output_type = "Moment Coefficient"

    # write CL/CD/Cm every iteration to results/<tag>_forces.out (the convergence history)
    mon = s.settings.solution.monitor
    if "forces" not in mon.report_files:
        mon.report_files.create("forces")
    out = RES / f"{tag}_forces.out"
    out.unlink(missing_ok=True)          # otherwise Fluent writes <tag>_forces_1_1.out
    mon.report_files["forces"].report_defs = ["cl", "cd", "cm"]
    mon.report_files["forces"].file_name = str(out)
    if "forces-plot" not in mon.report_plots:
        mon.report_plots.create("forces-plot")
    mon.report_plots["forces-plot"].report_defs = ["cl", "cd"]


def compute(s, names):
    """Evaluate report definitions now -> {name: value}."""
    out = {}
    for item in s.settings.solution.report_definitions.compute(report_defs=names):
        for k, v in item.items():
            out[k] = v[0] if isinstance(v, (list, tuple)) else v
    return out


def write_table(row):
    """Add/replace this angle's row in results/forces.csv, keeping the other angles."""
    path = RES / "forces.csv"
    rows = {}
    if path.exists():
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                if set(r) == set(row):                   # skip rows from an older column layout
                    rows[float(r["aoa_deg"])] = r
    rows[float(row["aoa_deg"])] = row
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerows(rows[k] for k in sorted(rows))


def history_average(path, n=200):
    """Mean CL, CD, Cm over the last n iterations of a Fluent report file."""
    rows = []
    for line in Path(path).read_text().splitlines()[3:]:    # 3 header lines
        parts = line.split()
        if len(parts) == 4:                                  # iteration, cl, cd, cm
            rows.append([float(p) for p in parts[1:]])
    rows = rows[-n:]
    m = [sum(c) / len(rows) for c in zip(*rows)]
    return {"cl": m[0], "cd": m[1], "cm": m[2]}, len(rows)


def iterate_to_convergence(s, max_iters):
    """Iterate in chunks; stop when CL and CD both change < tol (relative) over a chunk."""
    sc = CFG["solver"]
    chunk, min_it, tol = sc["check_every"], sc["min_iterations"], sc["force_tolerance"]
    done, prev = 0, None
    while done < max_iters:
        n = min(chunk, max_iters - done)
        s.settings.solution.run_calculation.iterate(iter_count=n)
        done += n
        r = compute(s, ["cl", "cd"])
        if prev:
            # relative change over the last chunk; floors stop a near-zero CL/CD from inflating it
            dcl = abs(r["cl"] - prev["cl"]) / max(abs(r["cl"]), 0.05)
            dcd = abs(r["cd"] - prev["cd"]) / max(abs(r["cd"]), 1e-3)
            log(f"  it {done}: CL={r['cl']:.4f} CD={r['cd']:.5f}  change {dcl:.2%} / {dcd:.2%}")
            if done >= min_it and dcl < tol and dcd < tol:
                return done, True
        prev = r
    log(f"  WARNING: CL/CD still changing after {done} iterations - treat this angle with care")
    return done, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoa", type=float, nargs="*", help="override the angle list in config.json")
    ap.add_argument("--iterations", type=int, help="override iterations per angle")
    ap.add_argument("--gui", action="store_true")
    ap.add_argument("--connect", help="attach to a running Fluent: text file with ip, port, password")
    args = ap.parse_args()
    RES.mkdir(exist_ok=True)
    angles = args.aoa if args.aoa else CFG["flight"]["aoa_deg"]
    iters = args.iterations or CFG["solver"]["iterations"]

    if not MESH_FILE.exists():
        raise SystemExit(f"{MESH_FILE} not found - run 02_mesh.py first")
    # attach to an open Fluent, or launch one (cwd = results so Fluent's own files land there)
    if args.connect:
        ip, port, pw = Path(args.connect).read_text().split()
        s = pf.connect_to_fluent(ip=ip, port=int(port), password=pw,
                                 cleanup_on_exit=False, start_watchdog=False)
    else:
        log("launching Fluent solver ...")
        s = pf.launch_fluent(mode="solver", precision="double", dimension=3,
                             processor_count=CFG["processors"],
                             ui_mode="gui" if args.gui else "no_gui",
                             cwd=str(RES), start_timeout=300)
    try:
        s.settings.file.read_mesh(file_name=str(MESH_FILE))
        s.settings.mesh.check()                              # fails loudly on negative volumes etc.
        walls = [z for z in s.settings.setup.boundary_conditions.wall.keys()]
        log(f"wall zones (forces are integrated on these): {walls}")
        setup(s, walls)

        area, length, cg = reference()
        log(f"reference area {area:.4f} m2, length {length:.4f} m, moment centre {cg}")
        q = 0.5 * CFG["flight"]["density_kg_m3"] * CFG["flight"]["speed_m_s"] ** 2   # dynamic pressure, Pa
        for i, aoa in enumerate(angles):
            tag = f"aoa_{aoa:g}".replace("-", "m")
            log(f"=== AoA {aoa:g} deg ===")
            set_aoa(s, aoa, walls, tag)
            if i == 0:
                # first angle only: hybrid initialisation (a potential-flow guess of the field)
                s.settings.solution.initialization.hybrid_initialize()
            # later angles start from the previous solution: converges much faster
            done, converged = iterate_to_convergence(s, iters)
            r = compute(s, ["cl", "cd", "cm"])
            note = "converged"
            if not converged:
                # oscillating (usually separated flow): the average is more useful than the last value
                r, n = history_average(RES / f"{tag}_forces.out")
                note = f"NOT converged - mean of last {n} iterations"
            row = {"aoa_deg": aoa, "CL": r["cl"], "CD": r["cd"], "Cm": r["cm"],
                   "L_over_D": r["cl"] / r["cd"] if r["cd"] else float("nan"),
                   "lift_N": r["cl"] * q * area, "drag_N": r["cd"] * q * area, "q_Pa": q,
                   "iterations": done, "status": note}
            log(f"CL={row['CL']:.4f} CD={row['CD']:.5f} Cm={row['Cm']:.4f} L/D={row['L_over_D']:.2f} "
                f"lift={row['lift_N']:.2f} N drag={row['drag_N']:.2f} N  ({note})")
            # keep the full solution of every angle (for post-processing) and update the table
            s.settings.file.write(file_type="case-data", file_name=str(RES / tag))
            write_table(row)
        log(f"done -> {RES / 'forces.csv'}")
    finally:
        # free the single Student licence for the next step
        if not args.gui and not args.connect:
            s.exit()


if __name__ == "__main__":
    main()
