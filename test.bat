@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SWARA AI - tests
if not exist "backend\.venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
"backend\.venv\Scripts\python.exe" -m pip install -q -r backend\requirements-dev.txt
echo.
echo ==== Backend tests (pytest) ====
"backend\.venv\Scripts\python.exe" -m pytest
set "BACK=%errorlevel%"

set "FRONT=skipped"
where node >nul 2>nul
if errorlevel 1 goto summary
if not exist "frontend\node_modules" goto summary
echo.
echo ==== Frontend tests (vitest) ====
pushd frontend
call npm test
if errorlevel 1 (set "FRONT=failed") else (set "FRONT=passed")
popd

:summary
echo.
if "%BACK%"=="0" (echo Backend: passed) else (echo Backend: FAILED)
echo Frontend: %FRONT%
pause
