@echo off
setlocal EnableExtensions
cd /d "%~dp0"

for %%I in ("%~dp0..\model") do set "MODEL_DIR=%%~fI"
set "MODEL_PORT=8090"
set "MODEL_URL=http://127.0.0.1:%MODEL_PORT%/v1/models"
set "MODEL_PY=%MODEL_DIR%\.venv\Scripts\python.exe"
set "FALLBACK_PY=C:\Users\Admin\Downloads\Summer_Arabic_Problem_Solver_Best_READY\Summer_Arabic_Problem_Solver_Best\.venv\Scripts\python.exe"
set "STATUS=%MODEL_DIR%\.server_status.txt"

if not exist ".venv\Scripts\python.exe" (
  echo Please run setup_windows.bat first.
  pause
  exit /b 1
)
if not exist "%MODEL_DIR%\run_cuda_server.bat" (
  echo Model launcher not found:
  echo %MODEL_DIR%\run_cuda_server.bat
  pause
  exit /b 1
)
if not exist "%MODEL_PY%" if exist "%FALLBACK_PY%" set "MODEL_PY=%FALLBACK_PY%"
if not exist "%MODEL_PY%" (
  echo Model environment not found.
  echo The CMD was waiting because the model Python is missing.
  echo Run this once, then try again:
  echo   %MODEL_DIR%\setup_model_windows.bat
  pause
  exit /b 1
)

echo ============================================
echo Starting model + adapter + website together
echo ============================================
echo.

powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%MODEL_URL%' -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL%==0 (
  echo Model server is already ready on port %MODEL_PORT%.
  goto START_WEB
)

echo [1/3] Starting Qwen3-8B + PEFT in a separate window.
echo That window can stay minimized. Do not close it.
start "Qwen3 CUDA Server" cmd /k "%MODEL_DIR%\run_cuda_server.bat"

echo [2/3] Waiting until the model is ready...
echo Loading from local cache usually takes 30 to 90 seconds.
powershell -NoProfile -Command "$url='%MODEL_URL%'; $status='%STATUS%'; $started=$false; for ($i=1; $i -le 240; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3; if ($r.StatusCode -eq 200) { Write-Host 'Model ready.'; exit 0 } } catch {} ; if (Test-Path -LiteralPath $status) { Write-Host 'Model window reported an error. Read that window.'; exit 1 } ; $alive = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'transformers_server_cuda.py' }; if ($alive) { $started = $true } elseif ($started -or $i -ge 8) { Write-Host 'Model process is not running. Read the Qwen3 CUDA Server window.'; exit 1 } ; if (($i %% 6) -eq 0) { Write-Host ('Still loading... ' + ($i * 5) + ' seconds') }; Start-Sleep -Seconds 5 }; Write-Host 'Timed out waiting for the model.'; exit 1"
if errorlevel 1 (
  echo.
  echo The model did not become ready.
  echo Read the window titled "Qwen3 CUDA Server".
  pause
  exit /b 1
)

:START_WEB
echo [3/3] Starting website on http://127.0.0.1:8000
start "" "http://127.0.0.1:8000"
call .venv\Scripts\activate.bat
python -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
