@echo off
setlocal
cd /d "%~dp0"
echo [1/4] Creating virtual environment...
if not exist .venv py -m venv .venv
call .venv\Scripts\activate.bat

echo [2/4] Installing requirements...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt

echo [3/4] Creating .env if needed...
if not exist .env copy /Y .env.example .env >nul
python -c "from pathlib import Path; import secrets; p=Path('.env'); s=p.read_text(encoding='utf-8'); s=s.replace('CHANGE_ME_RANDOM_SECRET', secrets.token_urlsafe(48)); p.write_text(s, encoding='utf-8')"
python hash_manager_password.py --migrate --ensure-demo

echo [4/4] Preparing database...
python -c "from dotenv import load_dotenv; load_dotenv(); from database import init_db; init_db(); print('Database ready.')"

echo.
echo Setup completed successfully.
echo Manager email is in .env. The password is stored as a PBKDF2 hash only.
echo To change it: python hash_manager_password.py "new-password"
echo Run run_windows.bat to start the platform.
pause
