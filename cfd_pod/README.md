# cfd_pod: airframe with payload pod, CFD case

Input: `../geometry/source/stallion_v2_equipped_with_pod.glb` (96 named parts, glTF Y-up, metres).
Same pipeline and settings as `../cfd_clean`, so the two compare 1:1 (`config.json → reference` is copied from the clean case).
Full explanation, replication steps and results: **[../README.md](../README.md)**.

```bat
run_all.bat          :: GLB -> wrap -> check -> mesh -> solve 0/4/8 deg -> renders -> deck (about 1 h)
demo.bat             :: live demo in the Fluent GUI
```

Step by step (from this folder):
```bat
..\.venv\Scripts\python.exe 00_import_glb.py                       :: -> input\stallion_pod_raw.stl
..\.venv\Scripts\python.exe 01_prep_stl.py --units mm --close-mm 24  :: seals the open hatch slots
..\.venv\Scripts\python.exe check_solid.py aircraft_wrapped.stl     :: must print SOLID
..\.venv\Scripts\python.exe 02_mesh.py
..\.venv\Scripts\python.exe 03_solve.py
..\.venv\Scripts\python.exe 04_demo_setup.py --orbit
..\.venv\Scripts\python.exe make_ppt_pod.py                        :: -> ..\presentations\Stallion_pod_CFD.pptx
```

How this case differs from the clean one:
* step 0 (GLB import) exists only here;
* `--close-mm 24` is essential: without it the wrap is hollow and the mesh blows past the student cap;
* `demo_common.py` adds a "pod" camera view and runs the fuselage streamline rake down past the pod.

Result: CL 0.310 / 0.697 / 0.911 and L/D 4.7 / 8.0 / 6.4 at 0 / 4 / 8 deg. Drag is +44% / +28% / +16% over the
clean airframe. Mesh: 562k cells.
