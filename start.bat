@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not defined PORT set "PORT=8000"

if not exist "backend\.venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
if not exist ".env" echo Note: there is no .env file yet, so the app starts without a Gnani key. Run setup.bat to create it.

rem ---- is the port already taken? ----
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo.
  echo [ERROR] Port %PORT% is already in use. Another program, or a second copy of SWARA AI, is listening there.
  echo         Close it, or use another port: type  set PORT=8001  then run start.bat again.
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  where node >nul 2>nul
  if errorlevel 1 (
    echo The frontend is not built and Node.js is not installed. Run setup.bat.
    pause
    exit /b 1
  )
  echo Building the frontend once...
  pushd frontend
  call npm run build
  popd
)

echo.
title SWARA AI
echo SWARA AI - Every Voice. Smarter Commerce.
echo Starting at http://localhost:%PORT%   (close this window to stop it)
echo.
start "" /min cmd /c "ping -n 4 127.0.0.1 >nul & start http://localhost:%PORT%"
cd backend
".venv\Scripts\python.exe" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port %PORT%
pause
