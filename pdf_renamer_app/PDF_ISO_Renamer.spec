# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec file for PDF ISO Drawing Renamer
# Build with:  pyinstaller PDF_ISO_Renamer.spec

import sys
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# Collect customtkinter and tkinterdnd2 data files automatically
# ---------------------------------------------------------------------------
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ctk_datas   = collect_data_files("customtkinter")
dnd_datas   = collect_data_files("tkinterdnd2")
all_datas   = ctk_datas + dnd_datas

ctk_hiddens  = collect_submodules("customtkinter")
dnd_hiddens  = collect_submodules("tkinterdnd2")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=all_datas,
    hiddenimports=[
        *ctk_hiddens,
        *dnd_hiddens,
        "PIL._tkinter_finder",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "cv2",
        "numpy",
        "fitz",
        "pytesseract",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "jupyter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PDF_ISO_Renamer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",      # uncomment and point to your .ico file
)
