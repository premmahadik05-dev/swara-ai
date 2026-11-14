@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
title SWARA AI - setup
echo ==== SWARA AI - first-time setup ====
echo.

rem ---- 1. find Python 3.10+ ----
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto have_py
python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=python"
:have_py
if not defined PY (
  echo [ERROR] Python 3.10 or newer was not found.
  echo         Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo         then open a NEW terminal and run setup.bat again.
  goto fail
)
echo Using: %PY%
%PY% --version

rem ---- 2. backend virtual environment ----
if not exist "backend\.venv\Scripts\python.exe" (
  echo.
  echo [1/4] Creating virtual environment...
  %PY% -m venv backend\.venv
  if errorlevel 1 goto fail
)
echo.
echo [2/4] Installing backend packages (needs internet the first time)...
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto fail

rem ---- 3. settings file ----
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo Created .env - open it and paste your Gnani API key into GNANI_API_KEY
  echo You can also add it later on the Settings page of the app.
)

rem ---- 4. frontend ----
echo.
echo [3/4] Frontend...
where node >nul 2>nul
if errorlevel 1 goto no_node
node -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit((a===20&&b>=19)||(a===22&&b>=12)||a>=23?0:1)" >nul 2>nul
if errorlevel 1 goto old_node
pushd frontend
if exist package-lock.json (call npm ci --no-audit --no-fund) else (call npm install --no-audit --no-fund)
if errorlevel 1 (popd & goto fail)
call npm run build
if errorlevel 1 (popd & goto fail)
popd
goto frontend_done
:no_node
if exist "frontend\dist\index.html" (
  echo Node.js not found - using the prebuilt frontend in frontend\dist. That is fine for running the app.
  goto frontend_done
)
echo [ERROR] Node.js is not installed and there is no prebuilt frontend\dist folder.
echo         Install Node.js 22 LTS (20.19 or newer also works) from https://nodejs.org/ and run setup.bat again.
goto fail
:old_node
echo Your Node.js is too old to build the frontend (it needs 20.19 or newer, or 22.12 or newer). Version found:
node -v
if exist "frontend\dist\index.html" (
  echo Using the prebuilt frontend in frontend\dist instead. That is fine for running the app.
  goto frontend_done
)
echo [ERROR] There is no prebuilt frontend\dist folder either.
echo         Install Node.js 22 LTS from https://nodejs.org/ and run setup.bat again.
goto fail
:frontend_done

echo.
echo [4/4] Creating the demo database...
"backend\.venv\Scripts\python.exe" scripts\seed_db.py
if errorlevel 1 goto fail

echo.
echo ==== Setup finished. Run start.bat to open the app. ====
echo.
pause
exit /b 0

:fail
echo.
echo ==== Setup did not finish. Read the message above, fix it, and run setup.bat again. ====
echo.
pause
exit /b 1
