@echo off
REM ============================================================
REM  PDF Circuit ID Extractor — Self-Contained Build Script v7
REM  Only needs app.py in the same folder. No other files needed.
REM
REM  Default OCR engine: Google Gemini Flash (FREE).
REM  EasyOCR is also installed as a local fallback.
REM
REM  NOTE: Uses --onedir because EasyOCR/PyTorch are too large
REM        for a single-file bundle.
REM  Finished app: dist\PDF_Circ_ID_Extractor\PDF_Circ_ID_Extractor.exe
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
echo [1/3] Installing dependencies...
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

REM ── Build the app ────────────────────────────────────────────
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
echo  DONE!
echo  Your app is in:  %~dp0dist\PDF_Circ_ID_Extractor\
echo  Run:  PDF_Circ_ID_Extractor.exe  inside that folder.
echo.
echo  FIRST LAUNCH STEPS:
echo  1. Click the "OCR" button in the app
echo  2. Make sure "Gemini Flash (FREE)" is selected
echo  3. Paste your free Google API key
echo     Get one at: aistudio.google.com/app/apikey
echo  4. Click Save and Close
echo  5. Add your PDFs and go!
echo ============================================================
echo.
pause
