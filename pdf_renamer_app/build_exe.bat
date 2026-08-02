@echo off
REM ============================================================
REM  PDF ISO Drawing Renamer — Windows .exe build helper
REM  v3 — fully self-contained, no PATH assumptions
REM ============================================================

REM Step 0: move into the folder this .bat lives in
cd /d "%~dp0"

echo ============================================================
echo  Working folder: %CD%
echo ============================================================
echo.
echo === PDF ISO Drawing Renamer ^- PyInstaller Build ===
echo.

REM ── Check Python ────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.10-3.13 from https://www.python.org/ and try again.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo Python found: %%v
echo.

REM ── Install dependencies (python -m pip avoids PATH issues) ──
echo [1/3] Installing Python dependencies from "%~dp0requirements.txt" ...
python -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed. See output above.
    pause
    exit /b 1
)

REM ── Install PyInstaller ──────────────────────────────────────
echo.
echo [2/3] Installing PyInstaller...
python -m pip install pyinstaller
if errorlevel 1 (
    echo.
    echo ERROR: Could not install PyInstaller. See output above.
    pause
    exit /b 1
)

REM ── Build the .exe ───────────────────────────────────────────
echo.
echo [3/3] Building .exe (this takes 2-4 minutes)...
python -m PyInstaller "%~dp0PDF_ISO_Renamer.spec"
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed. See output above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  BUILD COMPLETE
echo  Your .exe is at:  %~dp0dist\PDF_ISO_Renamer.exe
echo ============================================================
echo.
pause
