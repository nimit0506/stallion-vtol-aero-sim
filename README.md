# Stallion VTOL: aero simulation and mass/CG

This folder takes the Stallion VTOL CAD and produces the following:

1. **External-aero CFD** in Ansys Fluent: lift, drag and pitching moment at 0°, 4° and 8° angle of attack (AoA), 20 m/s.
   It runs for two airframes:
   - the **clean** airframe (`cfd_clean`);
   - the airframe **with the payload pod** (`cfd_pod`);
   - the same equipped airframe **with the payload box removed** (`cfd_nobox`), to isolate the box's effect.
2. **Pictures and a live Fluent demo** of the flow, plus a PowerPoint deck.
3. **Weight, centre of gravity and static margin** from the CAD, using the CFD's pitching moment.
4. **Moving parts in the GLB** to fix the CG, with a collision check.

Everything is driven by Python. Fluent is controlled through **PyFluent**, Ansys's official Python API. No clicking is needed, so every number can be reproduced by rerunning the scripts.

---

## 1. Folder map

```
aero_sim/
├─ README.md                  this guide
├─ setup_env.bat              one-time: creates .venv (Python + PyFluent + python-pptx)
├─ .venv/                     shared Python environment (built on the Python bundled with Ansys)
├─ geometry/
│  ├─ source/                 the two input models (copies)
│  │  ├─ stallion_v2_assembled.stl              clean airframe, 59 CAD parts, mm
│  │  └─ stallion_v2_equipped_with_pod.glb      pod variant, 96 named parts, metres, Y-up
│  ├─ stallion_v2_watertight_mm.stl             repaired clean skin, ready for Workbench
│  └─ stallion_v2_pod_watertight_mm.stl         repaired pod skin, ready for Workbench
├─ cfd_clean/                 CFD case: clean airframe
│  ├─ 01_prep_stl.py  check_solid.py  02_mesh.py  03_solve.py  04_demo_setup.py
│  ├─ demo_common.py  demo.py  demo.bat  run_all.bat  config.json
│  ├─ aircraft_wrapped.stl  geometry_report.json      (outputs of step 1)
│  ├─ mesh/        aircraft.msh.h5                    (step 2)
│  ├─ results/     forces.csv, aoa_*.cas.h5/.dat.h5, aoa_*_forces.out, fluent-*.trn   (step 3)
│  ├─ demo/        stallion_demo.cas.h5/.dat.h5       (step 4)
│  ├─ renders/     aoa<a>_<scene>_<view>.png, orbit_aoa4.gif                           (step 4)
│  └─ logs/        mesh_log.txt, solve_log.txt, render_log.txt
├─ cfd_pod/                   CFD case: with pod. Same scripts, plus:
│  ├─ 00_import_glb.py        GLB -> raw STL (step 0)
│  ├─ input/stallion_pod_raw.stl
│  ├─ export_wall.py          wall pressure + shear of both cases -> results/wall_*.npz (one Fluent session)
│  ├─ force_breakdown.py      drag/lift/Cm split by region (box, boom fronts, rest) -> results/force_breakdown.json
│  └─ make_ppt_pod.py, make_ppt.py   -> ../presentations/
├─ cfd_nobox/                 CFD case: the pod GLB with only the box (VIAL POD + hatch) removed; same scripts
│  ├─ run_all.bat            GLB -> wrap -> mesh -> solve -> wall export (uses ../geometry/stallion_v2_pod_nobox.glb)
│  └─ export_wall.py         wall pressure + shear -> results/wall_nobox_aoa{0,4}.npz
├─ box_effect/
│  ├─ box_effect.py          with vs without box: CL/CD/Cm, centre of pressure, NP, static margin, cruise, region split, Cp maps
│  ├─ make_ppt_box.py        -> ../presentations/Stallion_box_vs_nobox_CFD.pptx
│  └─ box_effect.json, figures/
├─ mass_cg/
│  ├─ cg.py                   mass, CG, neutral point, static margin, hover split
│  ├─ move_parts.py           move parts in the GLB + collision check
│  ├─ fix_cg.py               the box/battery CG fix for 0.8 and 1.2 mm walls
│  ├─ render_box.py           matching renders with / without the box -> box_renders/
│  ├─ cg_report.json, cg_items.npy, cg_plot.png
│  └─ cg_fix/                 the 4 moved GLBs, cg_fix_report.json, renders/
└─ presentations/
   ├─ Stallion_pod_CFD.pptx              pod results deck (13 slides)
   ├─ Stallion_pod_CFD_results.pptx      older pod-vs-clean comparison deck
   └─ Stallion_box_vs_nobox_CFD.pptx     with vs without the payload box, all metrics of both runs
```

The two CFD folders run **the same pipeline code**. `02_mesh.py`, `03_solve.py`, `04_demo_setup.py`, `check_solid.py` and `demo.bat` are identical in both. The only differences are:

| | `cfd_clean` | `cfd_pod` |
|---|---|---|
| input | STL | GLB → STL (`00_import_glb.py`) |
| `01_prep_stl.py` default input | `geometry/source/…stl` | `input/stallion_pod_raw.stl` |
| `demo_common.py` | – | a "pod" camera view, and the fuselage streamline rake extended down past the pod |
| `config.json` | reference values estimated from this geometry | the same reference values, copied in so the two cases compare 1:1 |

---

## 2. Replicating it from scratch

### What you need
- Windows, with **Ansys 2026 R1 Student** installed (Fluent 26.1). The scripts use the `AWP_ROOT261` environment variable that the installer sets.
- About 16 GB RAM, 4 cores (set in `config.json → processors`), and about 3 GB of disk per case.
- **Student licence rules that shape the setup:**
  - one Fluent session at a time;
  - meshes of at most about 1M cells;
  - about 45 s for the licence to free up after Fluent exits.

### Commands
```bat
cd aero_sim
setup_env.bat                    :: once: makes .venv, installs ansys-fluent-core 0.43.0 + python-pptx 1.0.2
cfd_clean\run_all.bat            :: clean airframe, about 1 h
cfd_pod\run_all.bat              :: pod airframe + slide deck, about 1 h
```
Run the two cases **one after the other, never at the same time** (one licence). Then run the mass/CG tools, which need no Fluent:
```bat
cd mass_cg
..\.venv\Scripts\python.exe cg.py --wall-mm 0.8          :: or 1.2; prints mass, CG, static margin
..\.venv\Scripts\python.exe fix_cg.py                     :: box + battery moves for both wall thicknesses
```

### Steps, timings and what "good" looks like

| step | command (run inside the case folder) | time | check |
|---|---|---|---|
| 0 (pod only) | `00_import_glb.py` | seconds | prints 96 parts and the bounds |
| 1 | `01_prep_stl.py --close-mm 24` (pod: add `--units mm`) | a few min | `wrapped: open_edges 0, non_manifold_edges 0, bodies 1`, about 300k facets |
| 1b | `check_solid.py aircraft_wrapped.stl` | seconds | prints `SOLID` |
| 2 | `02_mesh.py` | about 1.5 min | `Total cells : ~514k` (clean) / `~562k` (pod) in `logs/mesh_log.txt` |
| 3 | `03_solve.py` | about 50 min | `results/forces.csv` has 3 rows; 0° and 4° `converged` |
| 4 | `04_demo_setup.py --orbit` | about 5 min | 37 (clean) / 43 (pod) files in `renders/` |
| deck | `make_ppt_pod.py` | seconds | `presentations/Stallion_pod_CFD.pptx` |
| split (pod, after both cases) | `export_wall.py` then `force_breakdown.py` | about 3 min | region totals equal Fluent's CL/CD/Cm (printed side by side) |

Useful single runs:
- `03_solve.py --aoa 8` reruns one angle and replaces only that row.
- `03_solve.py --iterations 50` is a quick smoke test.
- `02_mesh.py --gui` lets you watch Fluent Meshing work.

---

## 3. How it works: the concepts

### 3.1 Frames and units
- **CFD frame**, used everywhere: **x = span (+ right), y = forward (the nose points +Y), z = up**, in metres.
  This is simply the frame the CAD was drawn in.
- **STL files are in mm,** because Fluent Meshing assumes STL is mm.
- **The GLB is glTF: Y-up, metres.** Converting to the CFD frame is `(x, y, z) = (gx, −gz, gy)`. The same line appears in `00_import_glb.py`, `cg.py` and `move_parts.py`.

### 3.2 Why the geometry has to be rebuilt (step 1)
The CAD is an *assembly*, not one surface:
- **Clean:** 662,930 triangles in 59 separate closed parts. Wing panels, fuselage pieces, servos and spars all overlap and touch, which gives 2,363 *non-manifold* edges (edges shared by three or more triangles).
- **Pod:** 96 parts, 250 separate pieces.

CFD needs **one closed, non-self-intersecting outer skin**: it has to know what is "air" and what is "aircraft". Repairing triangles one by one can't merge overlapping parts, and Fluent's own wrapper refused the file. So `01_prep_stl.py` **rebuilds the skin from scratch with voxels**.

How the "shrink-wrap" works, in 2-D:

```
  1. voxelise            2. flood-fill the air     3. exact surface        4. outer skin
  ┌────────────┐         ┌────────────┐            from the real CAD
  │            │         │~~~~~~~~~~~~│           (signed distance)      one closed surface,
  │   ██████   │         │~~~██████~~~│                                   300k triangles
  │   █ ▓▓ █   │  ──►    │~~~██████~~~│   ──►    ──────────────   ──►    (marching cubes,
  │   ██████   │         │~~~██████~~~│           sub-voxel accuracy       smooth, decimate)
  │            │         │~~~~~~~~~~~~│
  └────────────┘         └────────────┘
  every 1.5 mm cube a    air (~) = everything reachable from the box edge.
  triangle touches       Whatever air can't reach is "aircraft": internal parts (▓),
                         overlaps and tiny gaps all disappear automatically.
```

- **The `--close-mm 24` sealing.** The CAD skin has open hatch slots. Without sealing, the "air" flows in through them and the fuselage comes out hollow. A hollow fuselage means thin double walls that Fluent can't mesh within the cell limit. The fix:
  - Thicken the walls by *k* = 24 mm / (2 × 1.5 mm) = 8 voxels, so every opening narrower than about 24 mm closes.
  - Flood-fill.
  - Grow the air back by 8 voxels. It returns to the real skin everywhere except inside those openings.
- **The signed distance.** It is computed from the *original* triangles, so the new surface lies within a fraction of a voxel of the CAD rather than on the 1.5 mm staircase. The bounding box moved by 0.8 mm (clean) and 2.3 mm (pod, at the sealed openings).
- **Decimation** brings the surface down to about 300k triangles, because Ansys Student refuses much bigger surfaces. It runs in ≤2.5× steps with a local repair after each, because one big step tore thin parts.
- **`check_solid.py`** is the test for the hollow problem. It shoots vertical rays through the fuselage and fails if it finds more than 15 mm of air *inside* the skin.

### 3.3 Domain and mesh (step 2)
```
                 4 m above
          ┌──────────────────────────────────────────┐
  inflow  │                                          │ outflow
  4 m ──► │  ←── 4 m ──►  ✈  ◄──────── 8 m ───────►  │ (pressure outlet, behind the tail)
  ahead   │                                          │
          └──────────────────────────────────────────┘
          4 m below, 4 m to each side; the top, bottom and side faces are also inlets
```
- **A wind-tunnel box** built from the aircraft's bounds plus the distances in `config.json → domain`. It is far enough away that the walls don't disturb the flow.
- **Surface mesh on the aircraft:** curvature-based, 5.5–26 mm. Small cells where the surface bends (leading edges, tips), big cells on flat panels. Feature edges sharper than 40° are kept, so trailing edges stay sharp.
- **3 prism (boundary-layer) layers:**
  - the first cell is 0.5 mm high, and each layer is 1.2× thicker;
  - this gives a wall **y+** of about 5–25. y+ is the first cell height measured in viscous units; values like this mean the solver uses wall functions rather than resolving the very thin viscous sublayer.
  - That is fine for forces, but not fine enough to predict laminar transition.
- **Poly-hexcore volume fill:** cubes in the far field (efficient) and polyhedra near the aircraft (flexible). Result: **514k cells (clean), 562k (pod)**, below the 1M student cap.

### 3.4 Physics and solver (step 3)
- **Equations:** steady **RANS** (the time-averaged flow equations) with the **k-ω SST** turbulence model, the standard choice for external aero with possible separation.
  - Air is **incompressible** (ρ = 1.225 kg/m³). At 20 m/s the Mach number is 0.06, so compressibility doesn't matter.
  - Pressure-based **coupled** solver.
- **Angle of attack by tilting the wind, not the aircraft.** The inlet velocity is `V·(−cos α · forward + sin α · up)`. One mesh therefore serves every angle, and each angle starts from the previous solution, which is much faster.
- **Forces:**
  - **lift** ⟂ to the wind;
  - **drag** ∥ to the wind;
  - **pitching moment** about the moment centre, around the axis forward × up (nose-up positive).
- **Coefficients:** CL = L / (q·S), CD = D / (q·S), Cm = M / (q·S·c), with q = ½ρV² = **245 Pa**.
  - **Fixed reference values:** S = **0.22068 m²** (wing area), c = **0.16409 m** (mean chord), moment centre **(0, −0.27655, 0.07831) m** (wing quarter-chord). They are estimated from the clean geometry and used for *both* cases, so the coefficients compare directly.
- **Convergence rule:**
  - Iterate in chunks of 50.
  - Stop when CL and CD each change by less than 0.2% over a chunk (minimum 150 iterations, maximum 600).
  - **If 600 is reached, the angle is "NOT converged"** and `forces.csv` stores the **mean of the last 200 iterations**. A steady solver on flow that is starting to separate oscillates, and the mean is the meaningful number.

### 3.5 Post-processing and demo (step 4)
Fluent itself makes the pictures. Everything is created once and **saved inside a case file**, so it also appears in Fluent's Outline tree:
- slice planes, and streamline seed lines ("rakes");
- contours, pathlines and 7 scenes.

The renders are then done angle by angle. Only the `.dat` file (the solution) is swapped, because the mesh is shared.

### 3.6 Mass, CG and static margin (`mass_cg/cg.py`)

**Masses:**
- **Real components** (battery 700 g, motors 49 g + 7 g prop, servos, RX, FC…) use catalogue masses, placed at the centroid of their CAD part.
- **Things not in the CAD** (ESC 12 g, power board 6 g, capacitor 4 g, wiring 35 g) are placed at the flight controller.
- **Carbon** = volume × 1.55 g/cm³.
- **3-D printed LW-PLA parts** = solid walls + sparse infill:
  ```
  shell  = surface area × wall thickness             (at the part's area centroid)
  infill = 20 % × (volume − shell)                   (at the part's volume centroid)
  mass   = (shell + infill) × 0.54 g/cm³
  ```
  This is why the 0.8 and 1.2 mm walls differ by about 260 g: 2268 g vs 2529 g.

**CG** = Σ mᵢ·rᵢ / Σ mᵢ.

**Neutral point (NP), from the CFD:**
- The NP is the point about which the pitching moment doesn't change with lift.
- From the converged 0° and 4° runs (pod case): `dCm/dCL = (−0.0472 − 0.0104) / (0.6971 − 0.3099) = −0.1487`.
- Then `y_NP = y_ref + c · dCm/dCL = −0.2766 + 0.1641 × (−0.1487) = −0.3009 m`, which is **39.8% of the mean aerodynamic chord (MAC)**.
  - The MAC leading edge is at y = −0.2356 m.

**Static margin:**
- `SM = (y_CG − y_NP) / c`. It is positive when the CG is ahead of the NP, which is stable. Typical targets are 5–15%.

**Results:**

| | mass | CG (% MAC) | SM |
|---|---|---|---|
| 0.8 mm walls, as built | 2268 g | 32.8% | 7.0% |
| 1.2 mm walls, as built | 2529 g | 36.7% | 3.1% (too small) |

The script also reports:
- the **trim CL**, where Cm about the CG = 0;
- the **hover thrust split**: a lever balance between the front motor pair and the tail motor. The tail carries about 32%.

### 3.7 Moving parts and the CG fix (`move_parts.py`, `fix_cg.py`)
- **Why moving is simple:** every part in the GLB is its own node, with its triangles already in final position. Moving a part means adding a `"translation"` to its node. The file is repacked with the binary geometry untouched, which is lossless and fast.
- **The collision check:**
  - exact triangle–triangle intersection (`vtkCollisionDetectionFilter`) against nearby parts;
  - plus the smallest vertex-to-surface gap.
- **The CG fix:**
  - The box (the `VIAL POD`) is only 40–52 g, so moving it 120 mm forward adds just 1.3–1.5% SM. 120 mm is as far as its mounting pad stays on the flat belly.
  - The battery (700 g) does the rest. The CG moves linearly with the shift, so the shift is solved directly.

| | box | battery | SM |
|---|---|---|---|
| 0.8 mm | +120 mm fwd, +1.4 mm up | +10 mm fwd | 7.0 → 8.3 → **10.2%** |
| 1.2 mm | +120 mm fwd, +1.4 mm up | +33 mm fwd, +4 mm up (clears the curved floor) | 3.1 → 4.6 → **10.2%** |

---

## 4. File-by-file

The line numbers refer to the `cfd_pod` copies; the `cfd_clean` and `cfd_nobox` copies match. Every script is commented block by block, so the code itself explains each step.

### `setup_env.bat`
1. Creates `.venv` from the Ansys CPython 3.10 with `--system-site-packages`. numpy, scipy, pyvista, vtk, matplotlib and Pillow come with Ansys.
2. pip-installs PyFluent and python-pptx, pinned to the versions used here.

### `cfd_pod/00_import_glb.py`
1. Reads the GLB with VTK's glTF reader.
2. Walks the block tree and merges all parts.
3. Rotates Y-up → Z-up, converts m → mm, and writes `input/stallion_pod_raw.stl`.

No repair happens here.

### `01_prep_stl.py`
| function | line | what it does |
|---|---|---|
| `edge_stats` | 32 | counts open edges (holes) and non-manifold edges (intersections) |
| `remove_degenerate_and_duplicates` | 44 | drops zero-area and repeated triangles |
| `estimate_reference` | 62 | samples the top view on a 2 mm grid; rows wider than 80% of the span = wing → area, mean chord, quarter-chord |
| `repair_local` | 106 | cuts out the triangles around bad edges and refills the holes; keeps the largest shell |
| `shrink_wrap` | 126 | the voxel wrap of §3.2, as below |
| `write_binary_stl` | 238 | STL writer; the 80-byte header becomes the Fluent zone name `aircraft` |
| `main` | 252 | units guess → diagnostics → repair → wrap → `aircraft_wrapped.stl` + `geometry_report.json` |

`shrink_wrap` steps:
- shell voxels (line 149, comment "# 1.");
- flood fill and `close_gap` sealing (line 165, "# 2.");
- signed distance, with `near_air` treating internal faces as solid (line 179, "# 3.");
- marching cubes, smoothing and staged decimation (line 202, "# 4.").

Options: `--voxel-mm` (resolution, default 1.5), `--close-mm` (sealing), `--units`.

### `check_solid.py`
- Shoots 80 vertical rays and sorts the hits.
- Hits alternate enter/exit, so a gap between an exit and the next entry above z = 5 mm is air inside the fuselage.
- Exits with status 1 if any gap is over 15 mm, so `run_all.bat` stops.

### `02_mesh.py`
- **Workflow helpers:**
  - **`run_task`** sets the arguments of one workflow step, runs it and checks it reached "Up-to-date".
  - **`add_child`** does the same for steps that take children: sizing, regions, boundary layers.
- **`domain_box_mm`** builds the tunnel box.
- **`build`** is the Fault-tolerant Meshing workflow in order:
  1. import;
  2. external flow plus the box;
  3. feature edges;
  4. a fluid material point ahead of the nose, so Fluent knows which side is air;
  5. the inside of the aircraft marked "dead";
  6. curvature sizing;
  7. surface mesh;
  8. boundary types (`tunnel-ymin` = outlet, the other faces = inlets);
  9. prism layers;
  10. poly-hexcore volume, then write `mesh/aircraft.msh.h5`.
- A licence error is turned into "you hit the 1M-cell cap: coarsen `config.json → mesh`".

### `03_solve.py`
| function | line | what it does |
|---|---|---|
| `directions` | 53 | wind, drag, lift and pitch-axis vectors for an AoA |
| `reference` | 64 | S, c and moment centre from `config.json` (or the step-1 estimates if they are null) |
| `setup` | 73 | models, air properties, reference values, boundary conditions, coupled solver, residual targets |
| `set_aoa` | 123 | inlet velocity for this angle; `cl`/`cd`/`cm` report definitions; the history file `aoa_X_forces.out` |
| `history_average` | 188 | mean of the last 200 iterations from the `.out` file |
| `iterate_to_convergence` | 200 | the chunked 0.2% rule of §3.4 |
| `main` | 222 | read the mesh → for each angle: set, (initialise the first), iterate, compute, save `aoa_X.cas/.dat.h5`, update `forces.csv` |

### `demo_common.py`, `04_demo_setup.py`, `demo.py`, `demo.bat`
- **`demo_common.py`** holds everything shared between the setup script and the live presenter:
  - planes, rakes, contours, pathlines and meshes;
  - the 7 scenes, the camera views, and the picture style (dark theme, 1920×1080).
  - **`_camera_steps`** works around a Fluent quirk: Fluent shows a blocking dialog if the camera's up-vector ever points along the line of sight while you change the view. The function finds an order of updates where that never happens.
- **`04_demo_setup.py`**:
  - **`build`** creates every object from `demo_common` and saves `demo/stallion_demo.cas.h5`;
  - **`render`** loads each angle's `.dat` and saves every scene and view;
  - **`make_orbit`** rotates the camera 6° a frame for 60 frames → GIF.
- **`demo.py`** opens Fluent **with its GUI** and drives it from single keypresses:

  | key | action |
  |---|---|
  | `1`–`7` | scenes |
  | `a` | next angle |
  | `v` | next view |
  | `f` | forces table |
  | `s` | screenshot |
  | `q` | quit |
  | `x` | leave Fluent open |

  Each scene prints a one-line talking point.
- **`demo.bat`** builds the demo case if it's missing, then runs `demo.py`.

### `make_ppt_pod.py` (and `make_ppt.py`)
- Builds the deck with python-pptx from this case's files only:
  - `forces.csv` and the `aoa_*_forces.out` histories;
  - residuals parsed from Fluent's transcript (`results/fluent-*.trn`);
  - the cell count from `logs/mesh_log.txt`;
  - the renders.
- Charts are native PowerPoint charts. The residual chart gets a log axis by inserting `c:logBase` into the chart XML.
- `make_ppt.py` is the older pod-vs-clean comparison, built the same way.

### `mass_cg/cg.py`
| function | line | what it does |
|---|---|---|
| `read_parts` | 40 | parses the GLB by hand (header, JSON, BIN chunk; accessor → bufferView → offset). Per part: volume and volume centroid from signed tetrahedra `a·(b×c)/6` centred at `(a+b+c)/4`; area and area centroid |
| `build_items` | 94 | mass and position of everything (§3.6). Names are matched by prefix: `"BATTERY -"` deliberately doesn't match `"BATTERY PAD"` |
| `analyse` | 122 | CG; `dCm/dCL` (line 138); NP (139); SM (140); Cm moved to the CG (142); trim CL (145); hover split (147) |
| `main` | 175 | options `--glb --wall-mm --infill --rho --payload-g --report` |

It reads the CFD numbers from `../cfd_pod/config.json` and `../cfd_pod/results/forces.csv`.

### `mass_cg/move_parts.py`
| function | line | what it does |
|---|---|---|
| `load_glb` / `save_glb` | 29 / 38 | read and repack the GLB (JSON padded to 4 bytes; BIN unchanged) |
| `apply_moves` | 55 | `"NAME PREFIX=dx,dy,dz"` mm (CFD frame) → glTF translation `[dx, dz, −dy]/1000` |
| `part_meshes` | 75 | every part as a pyvista mesh in mm, CFD frame, with the translations applied |
| `_contacts` / `_gap` | 97 / 106 | exact intersection count; smallest vertex-to-surface distance (approximate, to about 1 mm) |
| `clearance` | 115 | checks moved parts against every part within 10 mm |

Example:
```bat
..\.venv\Scripts\python.exe move_parts.py --move "VIAL POD=0,120,1.4" --move "BATTERY -=0,10,0" --out my.glb
```

### `mass_cg/fix_cg.py`
For each wall thickness:
1. **Baseline.**
2. **Box only:** box +120 mm (`--pod-mm`) and raised `POD_RAISE_MM` = 1.4 mm.
3. **Box + battery:**
   - battery shift = `(y_target − y_CG) · M / 700 g` (line 132);
   - lift the battery in 2 mm steps until it touches only its pad (line 134).
4. Writes the GLBs, `cg_fix_report.json`, the renders and the CG-vs-NP chart.

### `config.json`, per case
| block | keys |
|---|---|
| `flight` | speed, list of AoA, air density/viscosity, inlet turbulence (1%, viscosity ratio 2) |
| `axes` | forward = +Y, up = +Z |
| `reference` | S, c, moment centre (fixed; `null` = use the step-1 estimate) |
| `domain` | tunnel distances |
| `mesh` | surface sizes, curvature angle, prism layers, volume fill |
| `solver` | max/min iterations, chunk size, tolerance |

Save it as **plain UTF-8** (not "UTF-8 with BOM"). `02_mesh.py` and `03_solve.py` fail to read it otherwise.

---

## 5. Results

At 20 m/s, sea-level air, k-ω SST. The 8° values are the mean of the last 200 iterations; that angle did not converge.

| AoA | clean CL | clean CD | clean L/D | pod CL | pod CD | pod L/D | pod drag increase |
|---|---|---|---|---|---|---|---|
| 0° | 0.313 | 0.0461 | 6.8 | 0.310 | 0.0665 | 4.7 | +44% |
| 4° | 0.713 | 0.0678 | 10.5 | 0.697 | 0.0867 | 8.0 | +28% |
| 8° | 0.951 | 0.122 | 7.8 | 0.911 | 0.142 | 6.4 | +16% |

At 4°, lift is 38.6 N (clean) / 37.7 N (pod), and drag is 3.7 N / 4.7 N. The pod barely changes lift, but it is a large drag item.

---

## 6. Explaining it

### Two-minute talk track
1. **Problem:**
   - The CAD is an assembly of dozens of overlapping parts with open slots, which CFD can't mesh.
   - I rebuilt the outer skin with a voxel shrink-wrap that seals gaps under 24 mm.
   - It follows the CAD to within a millimetre or two and gives one closed 300k-triangle surface. A ray test proves it isn't hollow.
2. **Mesh:**
   - Wind-tunnel box 4 m ahead / 8 m behind.
   - Curvature-based surface mesh with 3 prism layers.
   - Poly-hexcore, about 0.5M cells, within the student licence.
3. **Solver:**
   - Steady RANS, k-ω SST, 20 m/s.
   - AoA set by tilting the wind, so one mesh serves 0/4/8°.
   - Each angle runs until CL and CD stop changing by 0.2%.
4. **Results:**
   - Best L/D is around 4° (10.5 clean, 8.0 with the pod).
   - The pod costs +28% drag at cruise, with almost no lift change.
   - At 8° the forces keep oscillating, the onset of separation, so I report the average.
5. **Stability:**
   - The CFD gives the neutral point at 40% MAC.
   - The CAD-based mass model puts the CG at 33% (0.8 mm walls), so the static margin is 7%.
   - Moving the pod forward 120 mm and the battery forward 10 mm reaches 10%.

### Questions you will probably get
- **Why not use the STL directly?** Overlapping parts and internal faces make "inside" and "outside" undefined, and Fluent's wrapper refused it. A voxel wrap defines "outside" as "reachable by air", which can't be ambiguous.
- **Does the wrap change the shape?** The surface is placed using the exact distance to the original triangles, so it's within a fraction of the 1.5 mm voxel. The bounding box moved 0.8 mm. Trailing edges thinner than about 1.5 mm get slightly blunter, and openings under 24 mm are filled. That is correct for an external-aero model.
- **Why tilt the wind instead of the plane?** It's the same physics, needs one mesh instead of three, and lets each angle start from the last one.
- **How accurate is it?**
  - **Good for:** trends and comparisons, such as clean vs pod with identical settings.
  - **Ballpark for:** absolute drag. The mesh is coarse because of the student cap, there are y+ wall functions, and no laminar transition is modelled.
  - **Not modelled:** propellers.
- **Why fixed reference values?** So clean and pod coefficients are directly comparable. Changing S or c only rescales the coefficients, not the forces in newtons.
- **What does "not converged" at 8° mean?** The steady solver can't settle because the flow is starting to separate and unsteady. The last-200-iteration mean is reported, and the deck shows the oscillation.
- **Where does the neutral point come from?** From the slope of Cm against CL between the two converged angles, 0° and 4°. It isn't a formula guess.
- **Why 0.8 vs 1.2 mm walls?** The print settings are uncertain. The thicker walls add about 260 g of printed plastic, which moves the CG 6 mm aft and cuts the static margin from 7% to 3%. That's why the fix is given for both.

---

## 7. Limits and assumptions
- **Mesh and physics:**
  - The mesh is coarse because of the student cap.
  - Turbulence model: k-ω SST with wall functions.
  - No propellers or motors running; no sideslip.
  - Steady solver.
- **Neutral point:**
  - It comes from the pod case with the pod in its **original** place. Moving 40 g of pod changes it only slightly, but that wasn't simulated.
  - It uses only the 0°/4° pair, i.e. it assumes Cm is linear in CL there.
- **Mass model:**
  - The printed-part mass assumes uniform walls and infill.
  - Components not in the CAD are lumped at the flight controller.
  - The "provisional" battery is taken as 700 g.
- **`fix_cg.py` hard-codes:**
  - `POD_RAISE_MM` = 1.4 mm, measured for the 120 mm move. If you change `--pod-mm`, check the clearance output.
  - The MAC leading edge (only for the chart).
- **The pod mounting lugs** are moulded into the FUS 3 print, so the moved GLBs still show them at the old position.

## 8. Troubleshooting
| symptom | cause and fix |
|---|---|
| Fluent launch fails right after another run | the licence is still held: wait about 45 s (`run_all.bat` does this) |
| "Exiting due to license issue" while meshing | over about 1M cells: raise `min_size_mm` / `aircraft_max_size_mm` in `config.json` |
| meshing grinds for ages / huge cell count | the wrap came out hollow: `check_solid.py` says HOLLOW → raise `--close-mm` |
| `JSONDecodeError` reading `config.json` | the file was saved with a BOM: re-save as plain UTF-8 |
| `geometry_report.json` shows old `C:\…\cfd_pod\` paths | informational only (written before the folder moved); rerunning step 1 refreshes it |
| `pip.exe` in `.venv\Scripts` errors after moving the folder | use `..\.venv\Scripts\python.exe -m pip …` (pip's launcher stores its old path) |
