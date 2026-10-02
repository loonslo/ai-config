@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\start.py" guide backup
  goto finish
)
py -3 -c "import sys; sys.exit(0)" >nul 2>nul
if not errorlevel 1 (
  py -3 "scripts\start.py" guide backup
  goto finish
)
python -c "import sys; sys.exit(0)" >nul 2>nul
if not errorlevel 1 (
  python "scripts\start.py" guide backup
  goto finish
)
powershell -NoProfile -Command "[Console]::WriteLine([IO.File]::ReadAllText((Join-Path (Get-Location) 'docs/python-required.txt'),[Text.Encoding]::UTF8))"
pause
exit /b 2
:finish
set "RESULT=%ERRORLEVEL%"
if %RESULT% GEQ 2 pause
exit /b %RESULT%
