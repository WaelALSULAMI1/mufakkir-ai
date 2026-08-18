@echo off
cd /d "%~dp0"
title Qwen3 CUDA Server
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "STATUS=%~dp0.server_status.txt"
del "%STATUS%" >nul 2>&1

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if exist "C:\Users\Admin\Downloads\Summer_Arabic_Problem_Solver_Best_READY\Summer_Arabic_Problem_Solver_Best\.venv\Scripts\python.exe" set "PY=C:\Users\Admin\Downloads\Summer_Arabic_Problem_Solver_Best_READY\Summer_Arabic_Problem_Solver_Best\.venv\Scripts\python.exe"

if not defined PY (
  echo Model environment not found in this folder.
  echo Run setup_model_windows.bat here once, then try again.
  echo ERROR> "%STATUS%"
  pause
  exit /b 1
)
if not exist "Summer_Arabic_Problem_Solver_PEFT\adapter_model.safetensors" (
  echo Adopted PEFT adapter not found:
  echo %~dp0Summer_Arabic_Problem_Solver_PEFT\adapter_model.safetensors
  echo ERROR> "%STATUS%"
  pause
  exit /b 1
)

set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"

echo Using:
echo %PY%
echo Loading Qwen3-8B + PEFT adapter from local cache.
echo Do not close this window.
"%PY%" transformers_server_cuda.py --model Qwen/Qwen3-8B --adapter-path "%~dp0Summer_Arabic_Problem_Solver_PEFT" --host 127.0.0.1 --port 8090 --max-input-tokens 8192
if errorlevel 1 (
  echo.
  echo Model server stopped with an error.
  echo ERROR> "%STATUS%"
  pause
)
