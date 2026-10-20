@echo off
rem Live CFD demo: opens Fluent (GUI) on the pre-built demo case + a one-key presenter console.
rem   demo.bat                 presenter (keys 1-7 scenes, a = angle of attack, f = forces, h = help)
rem   demo.bat --fluent-only   just open Fluent on the demo case
cd /d "%~dp0"
rem the shared Python environment must exist (setup_env.bat makes it)
if not exist ..\.venv\Scripts\python.exe (
    echo Python environment missing - run ..\setup_env.bat first.
    pause
    exit /b 1
)
rem first time: build the demo case (graphics objects only, no renders)
if not exist demo\stallion_demo.cas.h5 (
    echo Demo case not built yet - building it now ^(about 3 minutes^) ...
    ..\.venv\Scripts\python.exe 04_demo_setup.py --no-render || (pause & exit /b 1)
)
rem %* passes the options through (e.g. --fluent-only); on an error keep the window open to read it
..\.venv\Scripts\python.exe demo.py %*
if errorlevel 1 pause
