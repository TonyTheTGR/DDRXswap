@echo off
cd /d "%~dp0"
py ddrx_gui.py
if errorlevel 1 (
  echo.
  echo Launcher failed. Install Python 3.10 or later and NumPy.
  pause
)
