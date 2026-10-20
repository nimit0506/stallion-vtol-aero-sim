@echo off
rem No-box variant: the pod GLB with the two VIAL POD parts removed (everything else identical to ..\cfd_pod).
rem GLB -> STL -> wrap -> check -> mesh -> solve (0/4/8 deg) -> wall export. Logs in logs\*.txt.
rem run from this folder, whatever the current directory is
cd /d "%~dp0"
rem Python with PyFluent (shared by every case, one folder up)
set "PY=..\.venv\Scripts\python.exe"
if not exist logs mkdir logs

echo ===== 1/6  GLB -^> raw STL =====
"%PY%" 00_import_glb.py --input ..\geometry\stallion_v2_pod_nobox.glb --output input\stallion_nobox_raw.stl || exit /b 1
echo ===== 2/6  repair + shrink-wrap =====
"%PY%" 01_prep_stl.py --input input\stallion_nobox_raw.stl --units mm --close-mm 24 || exit /b 1
echo ===== 3/6  check the wrap is solid =====
"%PY%" check_solid.py aircraft_wrapped.stl || exit /b 1
rem Ansys Student: one Fluent at a time, and the licence needs ~45 s to free up after each exit.
rem (the wait is 'ping -n 46', not 'timeout': timeout aborts when this script's output is redirected)
echo ===== 4/6  mesh  (logs\mesh_log.txt) =====
"%PY%" -u 02_mesh.py > logs\mesh_log.txt 2>&1 || (echo mesh failed - see logs\mesh_log.txt & exit /b 1)
ping -n 46 127.0.0.1 > nul
echo ===== 5/6  solve  (logs\solve_log.txt) =====
"%PY%" -u 03_solve.py > logs\solve_log.txt 2>&1 || (echo solve failed - see logs\solve_log.txt & exit /b 1)
ping -n 46 127.0.0.1 > nul
echo ===== 6/6  wall export  (logs\export_log.txt) =====
"%PY%" -u export_wall.py > logs\export_log.txt 2>&1 || (echo export failed - see logs\export_log.txt & exit /b 1)
type results\forces.csv
echo DONE
