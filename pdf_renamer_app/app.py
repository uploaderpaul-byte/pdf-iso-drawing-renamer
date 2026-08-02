"""
PDF ISO Drawing Renamer
=======================
Extracts handwritten Circuit ID / Equipment text from the title block of
engineering PDFs using OCR, renames each file to "[Circuit ID] ISO DWG.pdf",
and organises everything into per-drawing sub-folders inside a master output
folder.
"""

# ---------------------------------------------------------------------------
# Top-level crash guard — shows a popup instead of silently closing
# ---------------------------------------------------------------------------
import sys
import traceback

def _show_fatal(exc):
    """Last-resort: show the error in a plain tkinter messagebox."""
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _r = _tk.Tk(); _r.withdraw()
        _mb.showerror(
            "Startup Error",
            f"The application failed to start:\n\n{exc}\n\n"
            "Check that all dependencies are installed:\n"
            "  python -m pip install customtkinter Pillow PyMuPDF "
            "pytesseract opencv-python numpy\n\n"
            "Also make sure Tesseract-OCR is installed at:\n"
            r"  C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        _r.destroy()
    except Exception:
        pass  # truly nothing left to do
    sys.exit(1)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
try:
    import os
    import re
    import shutil
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception as e:
    _show_fatal(f"tkinter import failed: {e}")

try:
    import customtkinter as ctk
except Exception as e:
    _show_fatal(f"customtkinter not installed.\n\nRun: python -m pip install customtkinter\n\nDetail: {e}")

try:
    import fitz          # PyMuPDF
except Exception as e:
    _show_fatal(f"PyMuPDF not installed.\n\nRun: python -m pip install PyMuPDF\n\nDetail: {e}")

try:
    import cv2
    import numpy as np
except Exception as e:
    _show_fatal(f"opencv-python / numpy not installed.\n\nRun: python -m pip install opencv-python numpy\n\nDetail: {e}")

try:
    import pytesseract
    from PIL import Image, ImageTk
except Exception as e:
    _show_fatal(f"pytesseract / Pillow not installed.\n\nRun: python -m pip install pytesseract Pillow\n\nDetail: {e}")

# ---------------------------------------------------------------------------
# Tesseract path
# ---------------------------------------------------------------------------
import sys as _sys

# When frozen by PyInstaller, Tesseract may be bundled alongside the .exe
if getattr(_sys, "frozen", False):
    _BASE = _sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

_BUNDLED_TESS = os.path.join(_BASE, "tesseract", "tesseract.exe")
_SYSTEM_TESS  = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if os.path.exists(_BUNDLED_TESS):
    pytesseract.pytesseract.tesseract_cmd = _BUNDLED_TESS
elif os.path.exists(_SYSTEM_TESS):
    pytesseract.pytesseract.tesseract_cmd = _SYSTEM_TESS
# else: let pytesseract try to find it on PATH; will show an error at OCR time

# ---------------------------------------------------------------------------
# Title-block ROI configuration (fractions of page size)
# ---------------------------------------------------------------------------
DEFAULT_ROI = {
    "left":   0.50,
    "top":    0.88,
    "right":  0.85,
    "bottom": 0.95,
}

RENDER_DPI = 300

# ===========================================================================
# OCR helpers
# ===========================================================================

def preprocess_for_ocr(img_gray: np.ndarray) -> np.ndarray:
    h, w = img_gray.shape
    if w < 400:
        scale = 400 / w
        img_gray = cv2.resize(img_gray, (int(w * scale), int(h * scale)),
                              interpolation=cv2.INTER_CUBIC)
    img_gray = cv2.fastNlMeansDenoising(img_gray, h=15, templateWindowSize=7,
                                        searchWindowSize=21)
    binary = cv2.adaptiveThreshold(
        img_gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31, C=10
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.dilate(binary, kernel, iterations=1)
    return binary


def extract_text_from_region(pdf_path: str, roi: dict, page_index: int = 0) -> str:
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pw, ph = page.rect.width, page.rect.height
    x0 = roi["left"]   * pw
    y0 = roi["top"]    * ph
    x1 = roi["right"]  * pw
    y1 = roi["bottom"] * ph
    clip = fitz.Rect(x0, y0, x1, y1)
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csGRAY)
    doc.close()
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    processed = preprocess_for_ocr(img_array)
    custom_cfg = r"--oem 3 --psm 6 -c tessedit_char_blacklist=|"
    text = pytesseract.image_to_string(processed, config=custom_cfg)
    return text.strip()


def sanitise_filename(raw: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', raw)
    safe = re.sub(r'[_\s]+', ' ', safe).strip('_ ')
    safe = safe[:200]
    return safe if safe else "UNKNOWN"


def get_roi_preview_image(pdf_path: str, roi: dict, page_index: int = 0) -> Image.Image:
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pw, ph = page.rect.width, page.rect.height
    rect = fitz.Rect(
        roi["left"]   * pw, roi["top"]    * ph,
        roi["right"]  * pw, roi["bottom"] * ph
    )
    annot = page.add_rect_annot(rect)
    annot.set_colors(stroke=(1, 0, 0))
    annot.set_border(width=3)
    annot.update()
    mat = fitz.Matrix(1.5, 1.5)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    doc.close()
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


# ===========================================================================
# Main Application
# ===========================================================================

class PDFRenamerApp:
    BG      = "#1a1a2e"
    PANEL   = "#16213e"
    ACCENT  = "#0f3460"
    HILIGHT = "#e94560"
    FG      = "#e0e0e0"
    FG_DIM  = "#9e9e9e"
    SUCCESS = "#4caf50"
    WARNING = "#ff9800"
    ERROR   = "#f44336"

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("PDF ISO Drawing Renamer")
        self.root.geometry("900x720")
        self.root.minsize(760, 600)
        self.root.configure(fg_color=self.BG)

        self.pdf_files: list = []
        self.output_dir: str = ""
        self.roi = dict(DEFAULT_ROI)
        self.processing = False

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        outer = ctk.CTkFrame(root, fg_color=self.BG, corner_radius=0)
        outer.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        outer.grid_rowconfigure(3, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            outer, text="PDF ISO Drawing Renamer",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.HILIGHT
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        ctk.CTkLabel(
            outer,
            text="Extract handwritten Circuit IDs via OCR  ·  Rename  ·  Organise",
            font=ctk.CTkFont(size=12), text_color=self.FG_DIM
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        ctrl_frame = ctk.CTkFrame(outer, fg_color=self.PANEL, corner_radius=10)
        ctrl_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ctrl_frame.grid_columnconfigure(0, weight=1)

        self._build_file_area(ctrl_frame)
        self._build_settings_row(ctrl_frame)
        self._build_file_list(ctrl_frame)

        ctk.CTkLabel(outer, text="Processing Log",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=self.FG
                     ).grid(row=3, column=0, sticky="w", pady=(8, 2))

        self.log_box = ctk.CTkTextbox(
            outer, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=self.PANEL, text_color=self.FG,
            corner_radius=8, wrap="word", state="disabled"
        )
        self.log_box.grid(row=4, column=0, sticky="nsew", pady=(0, 8))
        outer.grid_rowconfigure(4, weight=1)

        bottom = ctk.CTkFrame(outer, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self.progress_var = ctk.DoubleVar(value=0)
        self.progress_bar = ctk.CTkProgressBar(
            bottom, variable=self.progress_var,
            fg_color=self.ACCENT, progress_color=self.HILIGHT,
            height=8, corner_radius=4
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        self.run_btn = ctk.CTkButton(
            bottom, text="▶  Process Files",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.HILIGHT, hover_color="#c73652",
            width=150, corner_radius=8,
            command=self._start_processing
        )
        self.run_btn.grid(row=0, column=1)

    def _build_file_area(self, parent):
        dz = ctk.CTkFrame(parent, fg_color="transparent")
        dz.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        dz.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            dz,
            text="📂  Click to Add PDF Files",
            font=ctk.CTkFont(size=13),
            fg_color=self.ACCENT, hover_color="#1a4a80",
            height=52, corner_radius=10,
            border_width=2, border_color=self.HILIGHT,
            command=self._browse_files
        ).grid(row=0, column=0, columnspan=2, sticky="ew")

        self.file_count_lbl = ctk.CTkLabel(
            dz, text="0 files selected",
            font=ctk.CTkFont(size=11), text_color=self.FG_DIM
        )
        self.file_count_lbl.grid(row=1, column=0, sticky="w", pady=(4, 0))

        ctk.CTkButton(
            dz, text="Clear", width=70, height=24,
            font=ctk.CTkFont(size=11),
            fg_color=self.ACCENT, hover_color="#1a4a80", corner_radius=6,
            command=self._clear_files
        ).grid(row=1, column=1, sticky="e", pady=(4, 0))

    def _build_settings_row(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        for i in range(6):
            row.grid_columnconfigure(i, weight=1 if i in (1, 3) else 0)

        ctk.CTkLabel(row, text="Output folder:",
                     text_color=self.FG_DIM,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w")

        self.out_dir_var = tk.StringVar(value="(same folder as input PDFs)")
        ctk.CTkEntry(row, textvariable=self.out_dir_var,
                     font=ctk.CTkFont(size=11),
                     fg_color=self.ACCENT, text_color=self.FG,
                     border_color=self.ACCENT, height=28
                     ).grid(row=0, column=1, sticky="ew", padx=6)

        ctk.CTkButton(row, text="Browse", width=70, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color=self.ACCENT, hover_color="#1a4a80", corner_radius=6,
                      command=self._browse_output
                      ).grid(row=0, column=2)

        ctk.CTkLabel(row, text="  ").grid(row=0, column=3)

        ctk.CTkButton(row, text="🔍  Preview ROI", width=120, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color="#2a5298", hover_color="#1e3f7a", corner_radius=6,
                      command=self._show_roi_preview
                      ).grid(row=0, column=4, padx=(0, 6))

        ctk.CTkButton(row, text="⚙  Configure ROI", width=130, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color=self.ACCENT, hover_color="#1a4a80", corner_radius=6,
                      command=self._open_roi_dialog
                      ).grid(row=0, column=5)

    def _build_file_list(self, parent):
        fl = ctk.CTkFrame(parent, fg_color="transparent")
        fl.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        fl.grid_columnconfigure(0, weight=1)

        self.file_listbox_var = tk.Variable(value=[])
        self.file_listbox = tk.Listbox(
            fl, listvariable=self.file_listbox_var,
            bg=self.ACCENT, fg=self.FG,
            selectbackground=self.HILIGHT,
            relief="flat", bd=0,
            font=("Consolas", 10), height=5, activestyle="none"
        )
        self.file_listbox.grid(row=0, column=0, sticky="ew")

        sb = tk.Scrollbar(fl, orient="vertical", command=self.file_listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.file_listbox.configure(yscrollcommand=sb.set)

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def _browse_files(self):
        paths = filedialog.askopenfilenames(
            title="Select PDF Files",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if paths:
            self._add_files(list(paths))

    def _add_files(self, paths: list):
        for p in paths:
            if p.lower().endswith(".pdf") and p not in self.pdf_files:
                self.pdf_files.append(p)
        self._refresh_file_list()

    def _clear_files(self):
        self.pdf_files.clear()
        self._refresh_file_list()

    def _refresh_file_list(self):
        names = [os.path.basename(p) for p in self.pdf_files]
        self.file_listbox_var.set(names)
        n = len(self.pdf_files)
        self.file_count_lbl.configure(
            text=f"{n} file{'s' if n != 1 else ''} selected"
        )

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select Output Folder")
        if d:
            self.output_dir = d
            self.out_dir_var.set(d)

    # ------------------------------------------------------------------
    # ROI dialogs
    # ------------------------------------------------------------------

    def _open_roi_dialog(self):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Configure Title-Block ROI")
        dlg.geometry("420x340")
        dlg.grab_set()
        dlg.configure(fg_color=self.BG)

        ctk.CTkLabel(dlg, text="ROI Fractions  (0.0 – 1.0 of page size)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=self.FG).pack(pady=(16, 4))
        ctk.CTkLabel(dlg, text="Tip: use 'Preview ROI' to verify on a sample drawing.",
                     font=ctk.CTkFont(size=11), text_color=self.FG_DIM).pack(pady=(0, 12))

        fields = {}
        for key in ("left", "top", "right", "bottom"):
            r = ctk.CTkFrame(dlg, fg_color="transparent")
            r.pack(fill="x", padx=24, pady=3)
            ctk.CTkLabel(r, text=f"{key.capitalize()}:", width=70, anchor="w",
                         text_color=self.FG).pack(side="left")
            var = tk.DoubleVar(value=self.roi[key])
            fields[key] = var
            ctk.CTkEntry(r, textvariable=var, width=80,
                         fg_color=self.ACCENT, text_color=self.FG).pack(side="left")
            ctk.CTkSlider(r, from_=0.0, to=1.0, variable=var,
                          width=200, progress_color=self.HILIGHT).pack(side="left", padx=8)

        def _apply():
            try:
                new = {k: float(v.get()) for k, v in fields.items()}
                assert 0 <= new["left"] < new["right"] <= 1
                assert 0 <= new["top"] < new["bottom"] <= 1
                self.roi = new
                self._log("ROI updated: " + str(new), "info")
                dlg.destroy()
            except Exception:
                messagebox.showerror("Invalid ROI",
                    "Values must be 0–1, with left < right and top < bottom.",
                    parent=dlg)

        ctk.CTkButton(dlg, text="Apply", fg_color=self.HILIGHT,
                      hover_color="#c73652", command=_apply).pack(pady=14)

    def _show_roi_preview(self):
        if not self.pdf_files:
            messagebox.showinfo("No Files", "Please add at least one PDF first.")
            return
        try:
            img = get_roi_preview_image(self.pdf_files[0], self.roi)
        except Exception as exc:
            messagebox.showerror("Preview Error", str(exc))
            return

        dlg = ctk.CTkToplevel(self.root)
        dlg.title(f"ROI Preview — {os.path.basename(self.pdf_files[0])}")
        dlg.configure(fg_color=self.BG)
        dlg.grab_set()

        img.thumbnail((900, 700), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        lbl = tk.Label(dlg, image=tk_img, bg=self.BG)
        lbl.image = tk_img
        lbl.pack(padx=8, pady=8)
        ctk.CTkLabel(dlg,
                     text="Red box = region sent to OCR.  Adjust via ⚙ Configure ROI if needed.",
                     font=ctk.CTkFont(size=11), text_color=self.FG_DIM).pack(pady=(0, 8))

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, msg: str, level: str = "info"):
        colours = {"info": self.FG, "success": self.SUCCESS,
                   "warning": self.WARNING, "error": self.ERROR}
        prefixes = {"info": "  ", "success": "✔ ", "warning": "⚠ ", "error": "✖ "}
        colour = colours.get(level, self.FG)
        line = prefixes.get(level, "  ") + msg + "\n"

        self.log_box.configure(state="normal")
        self.log_box.insert("end", line)
        start = self.log_box.index("end - 2 lines")
        end   = self.log_box.index("end - 1 chars")
        tag = f"tag_{level}"
        self.log_box.tag_config(tag, foreground=colour)
        self.log_box.tag_add(tag, start, end)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _start_processing(self):
        if self.processing:
            return
        if not self.pdf_files:
            messagebox.showwarning("No Files", "Please add PDF files first.")
            return
        self._clear_log()
        self.processing = True
        self.run_btn.configure(state="disabled", text="Processing…")
        self.progress_var.set(0)
        threading.Thread(target=self._process_all, daemon=True).start()

    def _process_all(self):
        files = list(self.pdf_files)
        total = len(files)

        if self.output_dir:
            master_dir = os.path.join(self.output_dir, "Processed_ISO_Drawings")
        else:
            master_dir = os.path.join(os.path.dirname(files[0]), "Processed_ISO_Drawings")
        os.makedirs(master_dir, exist_ok=True)
        self._log(f"Master output folder: {master_dir}", "info")
        self._log("─" * 60, "info")

        success_count = 0
        fail_count = 0

        for idx, pdf_path in enumerate(files, start=1):
            fname = os.path.basename(pdf_path)
            self._log(f"[{idx}/{total}] Processing: {fname}", "info")
            try:
                raw_text = extract_text_from_region(pdf_path, self.roi)
                self._log(f"       OCR raw result: {repr(raw_text)}", "info")
                if not raw_text:
                    raise ValueError("OCR returned empty text – adjust the ROI or check drawing quality")
                clean = sanitise_filename(raw_text)
                new_name = f"{clean} ISO DWG"
                new_pdf  = f"{new_name}.pdf"
                sub_folder = os.path.join(master_dir, new_name)
                os.makedirs(sub_folder, exist_ok=True)
                shutil.copy2(pdf_path, os.path.join(sub_folder, new_pdf))
                self._log(f"       → {os.path.join(new_name, new_pdf)}", "success")
                success_count += 1
            except Exception as exc:
                self._log(f"       ERROR: {exc}", "error")
                fail_count += 1
            self.root.after(0, self.progress_var.set, idx / total)

        self._log("─" * 60, "info")
        self._log(
            f"Done — {success_count} succeeded, {fail_count} failed.  Output: {master_dir}",
            "success" if fail_count == 0 else "warning"
        )
        self.root.after(0, self._processing_complete)

    def _processing_complete(self):
        self.processing = False
        self.run_btn.configure(state="normal", text="▶  Process Files")

    def run(self):
        self.root.mainloop()


# ===========================================================================
# Entry point — wrapped in a try/except so any crash shows a popup
# ===========================================================================
if __name__ == "__main__":
    try:
        app = PDFRenamerApp()
        app.run()
    except Exception:
        err = traceback.format_exc()
        try:
            import tkinter as _tk
            from tkinter import messagebox as _mb
            _r = _tk.Tk(); _r.withdraw()
            _mb.showerror("Application Error", err)
            _r.destroy()
        except Exception:
            print(err)
        sys.exit(1)
