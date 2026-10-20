@echo off
rem One-time setup: Python environment with PyFluent, built on the Python that ships with Ansys.
cd /d "%~dp0"
rem AWP_ROOT261 is set by the Ansys 2026 R1 installer and points at its install folder
if "%AWP_ROOT261%"=="" (
  echo AWP_ROOT261 is not set - is Ansys 2026 R1 installed?
  exit /b 1
)
set "ANSYS_PY=%AWP_ROOT261%\commonfiles\CPython\3_10\winx64\Release\python\python.exe"
rem create .venv only once; --system-site-packages lets it see the Ansys Python's own packages
if not exist ".venv\Scripts\python.exe" (
  "%ANSYS_PY%" -m venv .venv --system-site-packages || exit /b 1
)
rem numpy, scipy, pyvista, vtk, matplotlib and Pillow come from the Ansys Python (--system-site-packages).
rem Versions pinned to the ones these scripts were run with.
".venv\Scripts\python.exe" -m pip install ansys-fluent-core==0.43.0 python-pptx==1.0.2 || exit /b 1
echo.
echo Environment ready. Next: cfd_clean\run_all.bat  or  cfd_pod\run_all.bat
