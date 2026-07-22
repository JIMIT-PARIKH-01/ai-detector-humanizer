@echo off
REM ============================================================
REM  Double-click launcher for the AI Text Toolkit GUI.
REM ============================================================
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0gui.py"
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0gui.py"
    goto :eof
)

echo Python was not found on PATH. Install Python 3.8+ and try again.
pause
