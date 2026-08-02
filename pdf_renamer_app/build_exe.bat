@echo off
REM ============================================================
REM  PDF ISO Drawing Renamer — Self-Contained Build Script v4
REM  Only needs app.py in the same folder. No other files needed.
REM ============================================================
cd /d "%~dp0"

echo.
echo ============================================================
echo  PDF ISO Drawing Renamer - Building .exe
echo  Working folder: %CD%
echo ============================================================
echo.

REM ── Check Python ────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://www.python.org/
    pause & exit /b 1
)

REM ── Install all dependencies inline (no requirements.txt needed) ──
echo [1/3] Installing dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install customtkinter Pillow PyMuPDF pytesseract opencv-python tkinterdnd2 numpy
if errorlevel 1 (
    echo ERROR: Dependency install failed.
    pause & exit /b 1
)

REM ── Install PyInstaller ──────────────────────────────────────
echo.
echo [2/3] Installing PyInstaller...
python -m pip install pyinstaller
if errorlevel 1 (
    echo ERROR: PyInstaller install failed.
    pause & exit /b 1
)

REM ── Build the .exe ───────────────────────────────────────────
echo.
echo [3/3] Building .exe (takes 2-5 minutes, please wait)...
python -m PyInstaller ^
    --name "PDF_ISO_Renamer" ^
    --onefile ^
    --windowed ^
    --hidden-import customtkinter ^
    --hidden-import tkinterdnd2 ^
    --hidden-import PIL._tkinter_finder ^
    --collect-data customtkinter ^
    --collect-data tkinterdnd2 ^
    "%~dp0app.py"

if errorlevel 1 (
    echo.
    echo ERROR: Build failed. See output above.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  DONE! Your .exe is here:
echo  %~dp0dist\PDF_ISO_Renamer.exe
echo  Double-click that file to run the app.
echo ============================================================
echo.
pause
