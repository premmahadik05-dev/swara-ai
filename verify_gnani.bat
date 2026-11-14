@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SWARA AI - verify Gnani
rem Makes real Gnani calls with the key from .env: 3 per language (about 33 for all 11 languages): text-to-speech, the language code, then
rem speech-to-text on the spoken audio. Add --langs ta mr to check only some languages. Results: eval\results\live_verification.json
if not exist "backend\.venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
"backend\.venv\Scripts\python.exe" scripts\verify_gnani.py %*
pause
