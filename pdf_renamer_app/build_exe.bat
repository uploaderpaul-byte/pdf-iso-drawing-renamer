@echo off
REM ============================================================
REM  PDF Circuit ID Extractor — Self-Contained Build Script v6
REM  Only needs app.py in the same folder. No other files needed.
REM  NOTE: Uses --onedir (not --onefile) because EasyOCR/PyTorch
REM        are too large for a single-file bundle.
REM  The finished app will be in:  dist\PDF_Circ_ID_Extractor\
REM ============================================================
cd /d "%~dp0"

echo.
echo ============================================================
echo  PDF Circuit ID Extractor - Building .exe
echo  Working folder: %CD%
echo ============================================================
echo.

REM ── Check Python ────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://www.python.org/
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo Python: %%v

REM ── Install dependencies ────────────────────────────────────
echo.
echo [1/3] Installing dependencies (easyocr download may take a moment)...
python -m pip install --upgrade pip --quiet
python -m pip install customtkinter Pillow PyMuPDF easyocr opencv-python numpy
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

REM ── Build the app folder ─────────────────────────────────────
REM  --onedir is used because EasyOCR bundles PyTorch which is
REM  ~1-2 GB — onefile would work but extraction on every launch
REM  would be very slow.  onedir creates a folder you can zip
REM  and share, with PDF_Circ_ID_Extractor.exe inside.
echo.
echo [3/3] Building app (takes 3-8 minutes, please wait)...
python -m PyInstaller ^
    --name "PDF_Circ_ID_Extractor" ^
    --onedir ^
    --windowed ^
    --hidden-import customtkinter ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import easyocr ^
    --hidden-import torch ^
    --hidden-import torchvision ^
    --collect-data customtkinter ^
    --collect-all easyocr ^
    "%~dp0app.py"

if errorlevel 1 (
    echo.
    echo ERROR: Build failed. See output above.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  DONE!  Your app folder is here:
echo  %~dp0dist\PDF_Circ_ID_Extractor\
echo.
echo  Double-click PDF_Circ_ID_Extractor.exe inside that folder.
echo  NOTE: On first launch, EasyOCR will download its model
echo        (~100 MB) to your user profile. This only happens once.
echo ============================================================
echo.
pause
