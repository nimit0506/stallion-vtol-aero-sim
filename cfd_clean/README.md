# cfd_clean: clean airframe CFD case

Input: `../geometry/source/stallion_v2_assembled.stl` (59 overlapping CAD parts, mm).
Full explanation, replication steps and results: **[../README.md](../README.md)**.

```bat
run_all.bat          :: wrap -> check -> mesh -> solve 0/4/8 deg -> demo case + renders (about 1 h)
demo.bat             :: live demo in the Fluent GUI (keys 1-7 scenes, a = next angle, f = forces, h = help)
```

Step by step (from this folder):
```bat
..\.venv\Scripts\python.exe 01_prep_stl.py --close-mm 24
..\.venv\Scripts\python.exe check_solid.py aircraft_wrapped.stl
..\.venv\Scripts\python.exe 02_mesh.py            :: --gui to watch
..\.venv\Scripts\python.exe 03_solve.py           :: --aoa 8 for one angle, --iterations 50 for a smoke test
..\.venv\Scripts\python.exe 04_demo_setup.py --orbit
```

Result (`results/forces.csv`): CL 0.313 / 0.713 / 0.951 and L/D 6.8 / 10.5 / 7.8 at 0 / 4 / 8 deg.
8 deg did not converge, so its row is the mean of the last 200 iterations. Mesh: 514k cells.
