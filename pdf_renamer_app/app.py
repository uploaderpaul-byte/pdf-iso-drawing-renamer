"""
PDF ISO Drawing Renamer
=======================
Extracts handwritten Circuit ID / Equipment text from the title block of
engineering PDFs using OCR, renames each file to "[Circuit ID] ISO DWG.pdf",
and organises everything into per-drawing sub-folders inside a master output
folder.

Dependencies (install with pip):
    customtkinter
    Pillow
    PyMuPDF          (fitz)
    pytesseract
    opencv-python
    tkinterdnd2

Tesseract-OCR must also be installed separately on Windows:
    https://github.com/UB-Mannheim/tesseract/wiki
"""

import os
import re
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# ---------------------------------------------------------------------------
# Optional drag-and-drop support (tkinterdnd2)
# ---------------------------------------------------------------------------
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

# ---------------------------------------------------------------------------
# Image / OCR imports
# ---------------------------------------------------------------------------
import fitz          # PyMuPDF
import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Tesseract path  (adjust if Tesseract is installed elsewhere on your machine)
# ---------------------------------------------------------------------------
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ---------------------------------------------------------------------------
# Title-block ROI (Region of Interest) configuration
#
#   These values are expressed as FRACTIONS of the page dimensions so they
#   work across different paper sizes (A1, A2, A3, A4 …).
#
#   The defaults target a typical ISO title-block "Circuit ID / Equipment"
#   cell near the bottom-right corner.  Use the built-in ROI preview (the
#   "Preview ROI" button) to verify on your specific drawings and tweak as
#   needed.
# ---------------------------------------------------------------------------
DEFAULT_ROI = {
    "left":   0.50,   # fraction of page width  – left edge of cell
    "top":    0.88,   # fraction of page height – top edge of cell
    "right":  0.85,   # fraction of page width  – right edge of cell
    "bottom": 0.95,   # fraction of page height – bottom edge of cell
}

# DPI to render the PDF page at before passing to OpenCV/Tesseract.
# Higher = better OCR accuracy but slower.
RENDER_DPI = 300


# ===========================================================================
# OCR helpers
# ===========================================================================

def preprocess_for_ocr(img_gray: np.ndarray) -> np.ndarray:
    """
    Apply a preprocessing pipeline tuned for handwritten text on
    engineering drawings (dark ink on white/light background).
    """
    # 1. Scale up if the region is small
    h, w = img_gray.shape
    if w < 400:
        scale = 400 / w
        img_gray = cv2.resize(img_gray, (int(w * scale), int(h * scale)),
                              interpolation=cv2.INTER_CUBIC)

    # 2. Light denoise
    img_gray = cv2.fastNlMeansDenoising(img_gray, h=15, templateWindowSize=7,
                                        searchWindowSize=21)

    # 3. Adaptive thresholding (handles uneven lighting / shadows)
    binary = cv2.adaptiveThreshold(
        img_gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=10
    )

    # 4. Slight dilation to connect broken strokes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.dilate(binary, kernel, iterations=1)

    return binary


def extract_text_from_region(pdf_path: str, roi: dict,
                              page_index: int = 0) -> str:
    """
    Render the specified ROI from a PDF page and run OCR on it.
    Returns the cleaned text string (may be empty if nothing is found).
    """
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pw, ph = page.rect.width, page.rect.height

    # Convert fractional ROI to absolute points
    x0 = roi["left"]   * pw
    y0 = roi["top"]    * ph
    x1 = roi["right"]  * pw
    y1 = roi["bottom"] * ph
    clip = fitz.Rect(x0, y0, x1, y1)

    # Render at high DPI
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csGRAY)
    doc.close()

    # Convert to numpy array
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width
    )

    processed = preprocess_for_ocr(img_array)

    # Tesseract config for handwritten / printed mixed content
    custom_cfg = r"--oem 3 --psm 6 -c tessedit_char_blacklist=|"
    text = pytesseract.image_to_string(processed, config=custom_cfg)
    return text.strip()


def sanitise_filename(raw: str) -> str:
    """
    Make a string safe for use as a Windows filename.
    Strips control chars, replaces illegal characters, collapses spaces.
    """
    # Replace Windows-illegal chars with underscores
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', raw)
    # Collapse multiple spaces / underscores
    safe = re.sub(r'[_\s]+', ' ', safe).strip('_ ')
    # Truncate to 200 chars to leave room for the " ISO DWG.pdf" suffix
    safe = safe[:200]
    return safe if safe else "UNKNOWN"


def get_roi_preview_image(pdf_path: str, roi: dict,
                          page_index: int = 0) -> Image.Image:
    """
    Return a PIL Image of the full page with the ROI highlighted.
    Used by the preview dialog.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pw, ph = page.rect.width, page.rect.height

    # Draw a red rectangle on the page
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
# Main Application Window
# ===========================================================================

class App(ctk.CTk if not DND_AVAILABLE else (
        type("_DndCtk", (ctk.CTk,), {}))):  # plain CTk when no DnD lib
    pass


class PDFRenamerApp:
    # Colour scheme
    BG       = "#1a1a2e"
    PANEL    = "#16213e"
    ACCENT   = "#0f3460"
    HILIGHT  = "#e94560"
    FG       = "#e0e0e0"
    FG_DIM   = "#9e9e9e"
    SUCCESS  = "#4caf50"
    WARNING  = "#ff9800"
    ERROR    = "#f44336"

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Use TkinterDnD root if available
        if DND_AVAILABLE:
            self.root = TkinterDnD.Tk()
            self.root.configure(bg=self.BG)
        else:
            self.root = ctk.CTk()

        self.root.title("PDF ISO Drawing Renamer")
        self.root.geometry("900x720")
        self.root.minsize(760, 600)
        self.root.configure(fg_color=self.BG)

        # State
        self.pdf_files: list[str] = []
        self.output_dir: str = ""
        self.roi = dict(DEFAULT_ROI)
        self.processing = False

        self._build_ui()

        if DND_AVAILABLE:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        # ── Outer frame
        outer = ctk.CTkFrame(root, fg_color=self.BG, corner_radius=0)
        outer.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        outer.grid_rowconfigure(3, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        # ── Title
        title_lbl = ctk.CTkLabel(
            outer,
            text="PDF ISO Drawing Renamer",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.HILIGHT
        )
        title_lbl.grid(row=0, column=0, sticky="w", pady=(0, 4))

        sub_lbl = ctk.CTkLabel(
            outer,
            text="Extract handwritten Circuit IDs via OCR · Rename · Organise",
            font=ctk.CTkFont(size=12),
            text_color=self.FG_DIM
        )
        sub_lbl.grid(row=1, column=0, sticky="w", pady=(0, 12))

        # ── Top controls row
        ctrl_frame = ctk.CTkFrame(outer, fg_color=self.PANEL, corner_radius=10)
        ctrl_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ctrl_frame.grid_columnconfigure(0, weight=1)

        self._build_drop_zone(ctrl_frame)
        self._build_settings_row(ctrl_frame)
        self._build_file_list(ctrl_frame)

        # ── Status log
        log_lbl = ctk.CTkLabel(outer, text="Processing Log",
                               font=ctk.CTkFont(size=13, weight="bold"),
                               text_color=self.FG)
        log_lbl.grid(row=3, column=0, sticky="w", pady=(8, 2))

        self.log_box = ctk.CTkTextbox(
            outer,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=self.PANEL,
            text_color=self.FG,
            corner_radius=8,
            wrap="word",
            state="disabled"
        )
        self.log_box.grid(row=4, column=0, sticky="nsew", pady=(0, 8))
        outer.grid_rowconfigure(4, weight=1)

        # ── Progress bar + action button
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
            bottom,
            text="▶  Process Files",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.HILIGHT,
            hover_color="#c73652",
            width=150,
            corner_radius=8,
            command=self._start_processing
        )
        self.run_btn.grid(row=0, column=1)

    def _build_drop_zone(self, parent):
        dz_outer = ctk.CTkFrame(parent, fg_color="transparent")
        dz_outer.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        dz_outer.grid_columnconfigure(1, weight=1)

        self.drop_zone = ctk.CTkButton(
            dz_outer,
            text="📂  Click to Add PDF Files  (or drag & drop here)",
            font=ctk.CTkFont(size=13),
            fg_color=self.ACCENT,
            hover_color="#1a4a80",
            height=52,
            corner_radius=10,
            border_width=2,
            border_color=self.HILIGHT,
            command=self._browse_files
        )
        self.drop_zone.grid(row=0, column=0, columnspan=3, sticky="ew")

        # File count badge
        self.file_count_lbl = ctk.CTkLabel(
            dz_outer,
            text="0 files selected",
            font=ctk.CTkFont(size=11),
            text_color=self.FG_DIM
        )
        self.file_count_lbl.grid(row=1, column=0, sticky="w", pady=(4, 0))

        clear_btn = ctk.CTkButton(
            dz_outer, text="Clear", width=70, height=24,
            font=ctk.CTkFont(size=11),
            fg_color=self.ACCENT, hover_color="#1a4a80",
            corner_radius=6,
            command=self._clear_files
        )
        clear_btn.grid(row=1, column=2, sticky="e", pady=(4, 0))

    def _build_settings_row(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        for i in range(6):
            row.grid_columnconfigure(i, weight=1 if i in (1, 3) else 0)

        # Output folder
        ctk.CTkLabel(row, text="Output folder:",
                     text_color=self.FG_DIM,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w")
        self.out_dir_var = tk.StringVar(value="(same folder as input PDFs)")
        self.out_dir_entry = ctk.CTkEntry(
            row, textvariable=self.out_dir_var,
            font=ctk.CTkFont(size=11),
            fg_color=self.ACCENT, text_color=self.FG,
            border_color=self.ACCENT, height=28
        )
        self.out_dir_entry.grid(row=0, column=1, sticky="ew", padx=6)

        ctk.CTkButton(
            row, text="Browse", width=70, height=28,
            font=ctk.CTkFont(size=11),
            fg_color=self.ACCENT, hover_color="#1a4a80",
            corner_radius=6,
            command=self._browse_output
        ).grid(row=0, column=2)

        # Separator
        ctk.CTkLabel(row, text="  ").grid(row=0, column=3)

        # ROI preview button
        ctk.CTkButton(
            row, text="🔍  Preview ROI", width=120, height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#2a5298", hover_color="#1e3f7a",
            corner_radius=6,
            command=self._show_roi_preview
        ).grid(row=0, column=4, padx=(0, 6))

        # ROI configure button
        ctk.CTkButton(
            row, text="⚙  Configure ROI", width=130, height=28,
            font=ctk.CTkFont(size=11),
            fg_color=self.ACCENT, hover_color="#1a4a80",
            corner_radius=6,
            command=self._open_roi_dialog
        ).grid(row=0, column=5)

    def _build_file_list(self, parent):
        fl_frame = ctk.CTkFrame(parent, fg_color="transparent")
        fl_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        fl_frame.grid_columnconfigure(0, weight=1)

        self.file_listbox_var = tk.Variable(value=[])
        self.file_listbox = tk.Listbox(
            fl_frame,
            listvariable=self.file_listbox_var,
            bg=self.ACCENT, fg=self.FG,
            selectbackground=self.HILIGHT,
            relief="flat", bd=0,
            font=("Consolas", 10),
            height=5,
            activestyle="none"
        )
        self.file_listbox.grid(row=0, column=0, sticky="ew")

        sb = tk.Scrollbar(fl_frame, orient="vertical",
                          command=self.file_listbox.yview)
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

    def _add_files(self, paths: list[str]):
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

    def _on_drop(self, event):
        raw = event.data
        # tkinterdnd2 returns paths wrapped in braces if they contain spaces
        paths = self.root.tk.splitlist(raw)
        self._add_files(list(paths))

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select Output Folder")
        if d:
            self.output_dir = d
            self.out_dir_var.set(d)

    # ------------------------------------------------------------------
    # ROI configuration dialog
    # ------------------------------------------------------------------

    def _open_roi_dialog(self):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Configure Title-Block ROI")
        dlg.geometry("420x340")
        dlg.grab_set()
        dlg.configure(fg_color=self.BG)

        ctk.CTkLabel(
            dlg,
            text="ROI Fractions  (0.0 – 1.0 of page size)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.FG
        ).pack(pady=(16, 4))
        ctk.CTkLabel(
            dlg,
            text="Tip: use 'Preview ROI' to verify on a sample drawing.",
            font=ctk.CTkFont(size=11),
            text_color=self.FG_DIM
        ).pack(pady=(0, 12))

        fields = {}
        for key in ("left", "top", "right", "bottom"):
            row = ctk.CTkFrame(dlg, fg_color="transparent")
            row.pack(fill="x", padx=24, pady=3)
            ctk.CTkLabel(row, text=f"{key.capitalize()}:",
                         width=70, anchor="w",
                         text_color=self.FG).pack(side="left")
            var = tk.DoubleVar(value=self.roi[key])
            fields[key] = var
            ctk.CTkEntry(row, textvariable=var, width=80,
                         fg_color=self.ACCENT,
                         text_color=self.FG).pack(side="left")
            ctk.CTkSlider(
                row, from_=0.0, to=1.0, variable=var,
                width=200, progress_color=self.HILIGHT
            ).pack(side="left", padx=8)

        def _apply():
            try:
                new = {k: float(v.get()) for k, v in fields.items()}
                assert 0 <= new["left"] < new["right"] <= 1
                assert 0 <= new["top"]  < new["bottom"] <= 1
                self.roi = new
                self._log("ROI updated: " + str(new), "info")
                dlg.destroy()
            except Exception:
                messagebox.showerror(
                    "Invalid ROI",
                    "Values must be between 0 and 1, and left < right, top < bottom.",
                    parent=dlg
                )

        ctk.CTkButton(dlg, text="Apply", fg_color=self.HILIGHT,
                      hover_color="#c73652", command=_apply).pack(pady=14)

    # ------------------------------------------------------------------
    # ROI preview dialog
    # ------------------------------------------------------------------

    def _show_roi_preview(self):
        if not self.pdf_files:
            messagebox.showinfo("No Files", "Please add at least one PDF first.")
            return
        pdf_path = self.pdf_files[0]
        try:
            img = get_roi_preview_image(pdf_path, self.roi)
        except Exception as exc:
            messagebox.showerror("Preview Error", str(exc))
            return

        dlg = ctk.CTkToplevel(self.root)
        dlg.title(f"ROI Preview — {os.path.basename(pdf_path)}")
        dlg.configure(fg_color=self.BG)
        dlg.grab_set()

        # Scale to fit screen
        max_w, max_h = 900, 700
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)

        lbl = tk.Label(dlg, image=tk_img, bg=self.BG)
        lbl.image = tk_img  # keep reference
        lbl.pack(padx=8, pady=8)

        ctk.CTkLabel(
            dlg,
            text="Red box = region sent to OCR.  Adjust via ⚙ Configure ROI if it looks wrong.",
            font=ctk.CTkFont(size=11),
            text_color=self.FG_DIM
        ).pack(pady=(0, 8))

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str, level: str = "info"):
        colour_map = {
            "info":    self.FG,
            "success": self.SUCCESS,
            "warning": self.WARNING,
            "error":   self.ERROR,
        }
        colour = colour_map.get(level, self.FG)
        prefix = {"info": "  ", "success": "✔ ", "warning": "⚠ ", "error": "✖ "}.get(level, "  ")
        line = f"{prefix}{msg}\n"

        self.log_box.configure(state="normal")
        self.log_box.insert("end", line)
        # Apply colour tag
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

        t = threading.Thread(target=self._process_all, daemon=True)
        t.start()

    def _process_all(self):
        files = list(self.pdf_files)
        total = len(files)

        # Determine master output folder
        if self.output_dir:
            master_dir = os.path.join(self.output_dir, "Processed_ISO_Drawings")
        else:
            master_dir = os.path.join(
                os.path.dirname(files[0]), "Processed_ISO_Drawings"
            )
        os.makedirs(master_dir, exist_ok=True)
        self._log(f"Master output folder: {master_dir}", "info")
        self._log("─" * 60, "info")

        success_count = 0
        fail_count = 0

        for idx, pdf_path in enumerate(files, start=1):
            fname = os.path.basename(pdf_path)
            self._log(f"[{idx}/{total}] Processing: {fname}", "info")

            try:
                # 1. OCR
                raw_text = extract_text_from_region(pdf_path, self.roi)
                self._log(f"       OCR raw result: {repr(raw_text)}", "info")

                if not raw_text:
                    raise ValueError("OCR returned empty text – check ROI or drawing quality")

                # 2. Sanitise and build new name
                clean = sanitise_filename(raw_text)
                new_name = f"{clean} ISO DWG"
                new_pdf_name = f"{new_name}.pdf"

                # 3. Create sub-folder
                sub_folder = os.path.join(master_dir, new_name)
                os.makedirs(sub_folder, exist_ok=True)

                # 4. Copy renamed file into sub-folder
                dest = os.path.join(sub_folder, new_pdf_name)
                shutil.copy2(pdf_path, dest)

                self._log(
                    f"       → Renamed & moved to: {os.path.join(new_name, new_pdf_name)}",
                    "success"
                )
                success_count += 1

            except Exception as exc:
                self._log(f"       ERROR: {exc}", "error")
                fail_count += 1

            # Update progress bar (must happen on main thread via after)
            self.root.after(0, self.progress_var.set, idx / total)

        self._log("─" * 60, "info")
        self._log(
            f"Done — {success_count} succeeded, {fail_count} failed.  "
            f"Output: {master_dir}",
            "success" if fail_count == 0 else "warning"
        )

        self.root.after(0, self._processing_complete)

    def _processing_complete(self):
        self.processing = False
        self.run_btn.configure(state="normal", text="▶  Process Files")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self):
        self.root.mainloop()


# ===========================================================================
# Run
# ===========================================================================

if __name__ == "__main__":
    app = PDFRenamerApp()
    app.run()
