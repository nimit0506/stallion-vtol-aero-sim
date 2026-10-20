@echo off
rem Pod variant, full pipeline: GLB -> STL -> wrap -> check -> mesh -> solve (0/4/8 deg) -> renders -> deck.
rem Fluent output goes to logs\*.txt (open them to follow progress). About 1-1.5 h in total.
rem run from this folder, whatever the current directory is
cd /d "%~dp0"
rem first run: build the shared Python environment
if not exist "..\.venv\Scripts\python.exe" (
  call "%~dp0..\setup_env.bat" || exit /b 1
  cd /d "%~dp0"
)
rem Python with PyFluent (shared by every case, one folder up)
set "PY=..\.venv\Scripts\python.exe"
if not exist logs mkdir logs

echo ===== 1/7  GLB -^> raw STL =====
"%PY%" 00_import_glb.py || exit /b 1
echo ===== 2/7  repair + shrink-wrap (seal hatch gaps up to 24 mm) =====
"%PY%" 01_prep_stl.py --units mm --close-mm 24 || exit /b 1
echo ===== 3/7  check the wrap is solid =====
"%PY%" check_solid.py aircraft_wrapped.stl || exit /b 1

rem Ansys Student: one Fluent at a time, and the licence needs ~45 s to free up after each exit.
rem (the wait is 'ping -n 46', not 'timeout': timeout aborts when this script's output is redirected)
echo ===== 4/7  mesh  (logs\mesh_log.txt) =====
"%PY%" -u 02_mesh.py > logs\mesh_log.txt 2>&1 || (echo mesh failed - see logs\mesh_log.txt & exit /b 1)
ping -n 46 127.0.0.1 > nul
echo ===== 5/7  solve  (logs\solve_log.txt) =====
"%PY%" -u 03_solve.py > logs\solve_log.txt 2>&1 || (echo solve failed - see logs\solve_log.txt & exit /b 1)
ping -n 46 127.0.0.1 > nul
echo ===== 6/7  demo case + renders  (logs\render_log.txt) =====
"%PY%" -u 04_demo_setup.py --orbit > logs\render_log.txt 2>&1 || (echo renders failed - see logs\render_log.txt & exit /b 1)
echo ===== 7/7  slide deck =====
"%PY%" make_ppt_pod.py || exit /b 1
echo.
type results\forces.csv
echo.
echo Done. Results in results\, pictures in renders\, deck in ..\presentations\, live demo: demo.bat
