# PDF ISO Drawing Renamer

A Python desktop application that extracts handwritten **Circuit ID / Equipment** text from engineering PDF title blocks using OCR, renames each file to `[Circuit ID] ISO DWG.pdf`, and organises everything into per-drawing sub-folders inside a single master output folder.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Running the App](#running-the-app)
4. [How to Use](#how-to-use)
5. [Configuring the ROI (Title-Block Region)](#configuring-the-roi)
6. [Compiling to a Windows .exe with PyInstaller](#compiling-to-a-windows-exe)
7. [Troubleshooting](#troubleshooting)
8. [File Structure After Processing](#file-structure-after-processing)

---

## Prerequisites

| Tool | Version | Download |
|------|---------|----------|
| Python | 3.10 – 3.12 (64-bit) | https://www.python.org/downloads/ |
| Tesseract-OCR | 5.x (Windows installer) | https://github.com/UB-Mannheim/tesseract/wiki |

> **Important – Tesseract path**  
> After installing Tesseract, the app expects it at:  
> `C:\Program Files\Tesseract-OCR\tesseract.exe`  
> If you installed it elsewhere, open `app.py` and change the `TESSERACT_PATH` constant near the top of the file.

---

## Installation

Open a **Command Prompt** (or PowerShell) in the `pdf_renamer_app` folder and run:

```bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> If you see errors about `tkinter`, it ships with Python on Windows – make sure you installed the full Python distribution (not just the embeddable package).

---

## Running the App

From the `pdf_renamer_app` folder:

```bat
python app.py
```

---

## How to Use

1. **Add PDFs** – Click the blue "Add PDF Files" button, or drag-and-drop multiple `.pdf` files onto the drop zone.
2. **Set output folder** *(optional)* – Click "Browse" next to "Output folder". If left blank, a `Processed_ISO_Drawings` folder is created in the same directory as your first input PDF.
3. **Verify the ROI** – Click **🔍 Preview ROI** to see a red box drawn over the first PDF's title block. The red box should cover the handwritten Circuit ID cell. Adjust via **⚙ Configure ROI** if needed (see below).
4. **Process** – Click **▶ Process Files**. Watch the log box for per-file results and any OCR errors.
5. **Collect results** – Open the `Processed_ISO_Drawings` output folder. Each drawing will have its own sub-folder:
   ```
   Processed_ISO_Drawings/
   ├── CB-101-A ISO DWG/
   │   └── CB-101-A ISO DWG.pdf
   ├── MCC-2B ISO DWG/
   │   └── MCC-2B ISO DWG.pdf
   └── ...
   ```

---

## Configuring the ROI

The **Region of Interest (ROI)** tells the app which rectangular area of each PDF page to crop and send to OCR. Values are expressed as **fractions of the page size** (0.0 = left/top edge, 1.0 = right/bottom edge), so they work regardless of paper size (A1, A2, A3, A4 …).

Default values (bottom-right title block area):

| Setting | Default | Meaning |
|---------|---------|---------|
| Left    | 0.50    | Start at 50 % of page width |
| Top     | 0.88    | Start at 88 % of page height |
| Right   | 0.85    | End at 85 % of page width |
| Bottom  | 0.95    | End at 95 % of page height |

**Steps to adjust:**

1. Click **🔍 Preview ROI** with one of your drawings selected.  
2. Examine the red box – does it cover the handwritten Circuit ID cell?  
3. If not, click **⚙ Configure ROI**, drag the sliders or type values, then click **Apply**.  
4. Preview again to confirm, then process.

---

## Compiling to a Windows .exe

PyInstaller bundles the app and all its dependencies into a single distributable `.exe` that runs on any Windows machine **without requiring Python or pip** to be installed.

### Step 1 – Install PyInstaller

```bat
pip install pyinstaller
```

### Step 2 – Generate the .exe

From inside the `pdf_renamer_app` folder, run:

```bat
python -m PyInstaller ^
  --name "PDF_ISO_Renamer" ^
  --onefile ^
  --windowed ^
  --hidden-import customtkinter ^
  --hidden-import tkinterdnd2 ^
  --hidden-import PIL._tkinter_finder ^
  --collect-data customtkinter ^
  --collect-data tkinterdnd2 ^
  app.py
```

> **Note:** `python -m PyInstaller` is used instead of the bare `pyinstaller` command because Python 3.14 does not automatically add the Scripts folder to PATH on Windows.

> **`--onefile`** – packages everything into a single `.exe`  
> **`--windowed`** – suppresses the console window  
> **`--icon icon.ico`** – optional; remove this flag if you don't have an icon file

The output will be at:
```
pdf_renamer_app/
└── dist/
    └── PDF_ISO_Renamer.exe   ← this is your distributable
```

### Step 3 – Bundle Tesseract with the .exe (optional but recommended)

If the target machine does **not** have Tesseract installed, you can bundle the Tesseract binaries alongside the `.exe`:

1. Copy the entire `C:\Program Files\Tesseract-OCR\` folder into `pdf_renamer_app/tesseract/`.
2. Add these flags to the PyInstaller command:
   ```bat
   --add-data "tesseract;tesseract"
   ```
3. In `app.py`, update the `TESSERACT_PATH` to resolve relative to the bundled location:
   ```python
   import sys, os
   if getattr(sys, "frozen", False):
       # Running as a PyInstaller bundle
       BASE = sys._MEIPASS
   else:
       BASE = os.path.dirname(os.path.abspath(__file__))
   TESSERACT_PATH = os.path.join(BASE, "tesseract", "tesseract.exe")
   pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
   ```

### Alternative: `--onedir` (folder distribution)

If the single-file build is slow to launch (it extracts to `%TEMP%` on every run), use `--onedir` instead of `--onefile`:

```bat
pyinstaller ^
  --name "PDF_ISO_Renamer" ^
  --onedir ^
  --windowed ^
  --collect-data customtkinter ^
  --collect-data tkinterdnd2 ^
  app.py
```

This produces a `dist/PDF_ISO_Renamer/` folder. Zip it up and distribute the whole folder; users run `PDF_ISO_Renamer.exe` inside it.

### Using the included `.spec` file

A pre-configured `PDF_ISO_Renamer.spec` file is included. After installing PyInstaller, you can build with:

```bat
pyinstaller PDF_ISO_Renamer.spec
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `TesseractNotFoundError` | Verify Tesseract is installed and `TESSERACT_PATH` in `app.py` matches your installation path. |
| OCR returns empty or garbage text | Open **⚙ Configure ROI** and adjust the region so it precisely covers the handwritten cell. Try increasing `RENDER_DPI` to `400` in `app.py`. |
| Drag-and-drop doesn't work | `tkinterdnd2` may not have installed correctly. Run `pip install tkinterdnd2` again. The app still works without it (use the file browser button). |
| `.exe` crashes on launch | Run from the command line (`PDF_ISO_Renamer.exe` in `dist/`) to see the error output, then re-run PyInstaller with `--console` instead of `--windowed` to debug. |
| `ModuleNotFoundError: fitz` | Run `pip install PyMuPDF` – the package name is `PyMuPDF` but the import is `fitz`. |
| Files renamed to `UNKNOWN ISO DWG.pdf` | OCR found no text. Check the ROI and ensure the handwriting is dark and legible. Try increasing `RENDER_DPI`. |

---

## File Structure After Processing

```
Processed_ISO_Drawings/            ← master output folder
├── CB-101-A ISO DWG/
│   └── CB-101-A ISO DWG.pdf
├── MCC-2B ISO DWG/
│   └── MCC-2B ISO DWG.pdf
└── SWBD-14C ISO DWG/
    └── SWBD-14C ISO DWG.pdf
```

The original input PDFs are **not deleted** – the app copies them to the output structure.
