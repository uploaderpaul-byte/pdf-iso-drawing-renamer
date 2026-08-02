@echo off
REM ============================================================
REM  PDF ISO Drawing Renamer — Windows .exe build helper
REM  Double-click this file (or run from Command Prompt) from
REM  inside the pdf_renamer_app folder.
REM ============================================================

echo === PDF ISO Drawing Renamer — PyInstaller Build ===
echo.

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10-3.12 from https://www.python.org/
    pause
    exit /b 1
)

REM Install / upgrade dependencies
echo [1/3] Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed. Check the error above.
    pause
    exit /b 1
)

REM Install PyInstaller
echo.
echo [2/3] Installing PyInstaller...
pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Could not install PyInstaller.
    pause
    exit /b 1
)

REM Build the .exe
echo.
echo [3/3] Building .exe with PyInstaller...
pyinstaller PDF_ISO_Renamer.spec

if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed. See output above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  BUILD COMPLETE
echo  Your .exe is at:  dist\PDF_ISO_Renamer.exe
echo ============================================================
echo.
pause
