@echo off
setlocal
cd /d "%~dp0"
title Setup Qwen3 CUDA environment

if not exist ".venv\Scripts\python.exe" (
  echo Creating model virtual environment...
  py -3.11 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" py -m venv .venv
)

if not exist ".venv\Scripts\python.exe" (
  echo Could not create .venv. Install Python 3.11 and try again.
  pause
  exit /b 1
)

echo Installing CUDA model requirements. This can take several minutes the first time.
".venv\Scripts\python.exe" -m pip install -U pip
".venv\Scripts\python.exe" -m pip install -r requirements-windows.txt
if errorlevel 1 (
  echo.
  echo Install failed. If PyTorch has no CUDA, install a CUDA build of torch first, then rerun this file.
  pause
  exit /b 1
)

echo.
echo Model environment is ready.
echo You do not need to download Qwen3-8B again if it is already cached on this PC.
echo Next: run website\run_windows.bat
pause
