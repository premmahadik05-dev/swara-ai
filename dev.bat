@echo off
setlocal EnableExtensions
cd /d "%~dp0"
rem Developer mode: API with auto-reload on :8000 and the Vite dev server on :5173 (open http://localhost:5173).
if not exist "backend\.venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo Node packages are missing. Install Node.js and run setup.bat first.
  pause
  exit /b 1
)
start "SWARA AI API" /d "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000"
start "SWARA AI UI" /d "%~dp0frontend" cmd /k "npm run dev"
echo Two windows were opened. Open http://localhost:5173 in your browser.
