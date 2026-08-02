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
import json

def _show_fatal(exc):
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _r = _tk.Tk(); _r.withdraw()
        _mb.showerror("Startup Error",
            f"The application failed to start:\n\n{exc}\n\n"
            "Ensure all dependencies are installed:\n"
            "  python -m pip install customtkinter Pillow PyMuPDF "
            "pytesseract opencv-python numpy\n\n"
            "Also make sure Tesseract-OCR is installed at:\n"
            r"  C:\Program Files\Tesseract-OCR\tesseract.exe")
        _r.destroy()
    except Exception:
        pass
    sys.exit(1)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
try:
    import os, re, shutil, threading
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception as e:
    _show_fatal(f"tkinter import failed: {e}")

try:
    import customtkinter as ctk
except Exception as e:
    _show_fatal(f"customtkinter not installed.\nRun: python -m pip install customtkinter\n\n{e}")

try:
    import fitz
except Exception as e:
    _show_fatal(f"PyMuPDF not installed.\nRun: python -m pip install PyMuPDF\n\n{e}")

try:
    import cv2, numpy as np
except Exception as e:
    _show_fatal(f"opencv-python/numpy not installed.\nRun: python -m pip install opencv-python numpy\n\n{e}")

try:
    import pytesseract
    from PIL import Image, ImageTk, ImageDraw
except Exception as e:
    _show_fatal(f"pytesseract/Pillow not installed.\nRun: python -m pip install pytesseract Pillow\n\n{e}")

# ---------------------------------------------------------------------------
# Tesseract path
# ---------------------------------------------------------------------------
_BASE = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
_BUNDLED_TESS = os.path.join(_BASE, "tesseract", "tesseract.exe")
_SYSTEM_TESS  = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_BUNDLED_TESS):
    pytesseract.pytesseract.tesseract_cmd = _BUNDLED_TESS
elif os.path.exists(_SYSTEM_TESS):
    pytesseract.pytesseract.tesseract_cmd = _SYSTEM_TESS

# ---------------------------------------------------------------------------
# Config persistence  (~/.pdf_iso_renamer_config.json)
# ---------------------------------------------------------------------------
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".pdf_iso_renamer_config.json")

DEFAULT_ROI = {"left": 0.50, "top": 0.88, "right": 0.85, "bottom": 0.95}
RENDER_DPI  = 300


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# ===========================================================================
# OCR helpers
# ===========================================================================

def preprocess_for_ocr(img_gray: np.ndarray) -> np.ndarray:
    h, w = img_gray.shape
    if w < 400:
        scale = 400 / w
        img_gray = cv2.resize(img_gray, (int(w * scale), int(h * scale)),
                              interpolation=cv2.INTER_CUBIC)
    img_gray = cv2.fastNlMeansDenoising(img_gray, h=15,
                                        templateWindowSize=7, searchWindowSize=21)
    binary = cv2.adaptiveThreshold(
        img_gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31, C=10)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.dilate(binary, kernel, iterations=1)


def extract_text_from_region(pdf_path: str, roi: dict, page_index: int = 0) -> str:
    doc  = fitz.open(pdf_path)
    page = doc[page_index]
    pw, ph = page.rect.width, page.rect.height
    clip = fitz.Rect(roi["left"]*pw, roi["top"]*ph,
                     roi["right"]*pw, roi["bottom"]*ph)
    mat  = fitz.Matrix(RENDER_DPI/72, RENDER_DPI/72)
    pix  = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csGRAY)
    doc.close()
    arr  = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    proc = preprocess_for_ocr(arr)
    text = pytesseract.image_to_string(proc,
               config=r"--oem 3 --psm 6 -c tessedit_char_blacklist=|")
    return text.strip()


def sanitise_filename(raw: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', raw)
    safe = re.sub(r'[_\s]+', ' ', safe).strip('_ ')
    return (safe[:200] if safe else "UNKNOWN")


# ===========================================================================
# Auto-detect title block
# ===========================================================================

def auto_detect_title_block(pdf_path: str, page_index: int = 0) -> dict:
    """
    Tries to locate the title block rectangle automatically using OpenCV.
    Engineering ISO drawings usually place the title block in the bottom-right.
    Falls back to a sensible default if detection fails.
    """
    doc  = fitz.open(pdf_path)
    page = doc[page_index]
    pw, ph = page.rect.width, page.rect.height
    mat  = fitz.Matrix(1.5, 1.5)
    pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    doc.close()

    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    full_h, full_w = img.shape

    # Work on the bottom 50% of the page
    crop_y = int(full_h * 0.50)
    cropped = img[crop_y:, :]

    # Threshold to binary
    _, thresh = cv2.threshold(cropped, 0, 255,
                              cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Find all contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)

    best, best_score = None, 0
    page_area = full_h * full_w

    for c in contours:
        peri  = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        area   = cv2.contourArea(c)
        if area < page_area * 0.005:        # too small
            continue
        if area > page_area * 0.60:         # too large (probably the border)
            continue
        x, y, w, h = cv2.boundingRect(c)
        aspect = w / h if h > 0 else 0
        # Title blocks are typically wider than tall
        if not (1.5 < aspect < 8.0):
            continue
        # Prefer rectangles that are more 4-sided
        rect_score = area / (w * h + 1)
        score = area * rect_score
        if score > best_score:
            best_score = score
            best = (x, y + crop_y, w, h)   # y is in full-image coords

    if best:
        x, y, w, h = best
        pad = 5   # small padding in pixels
        return {
            "left":   max(0.0, (x - pad) / full_w),
            "top":    max(0.0, (y - pad) / full_h),
            "right":  min(1.0, (x + w + pad) / full_w),
            "bottom": min(1.0, (y + h + pad) / full_h),
        }

    # Fallback: bottom-right area
    return {"left": 0.50, "top": 0.75, "right": 0.95, "bottom": 0.95}


# ===========================================================================
# Interactive ROI Editor
# ===========================================================================

class InteractiveROIDialog(ctk.CTkToplevel):
    """
    Shows the full PDF page.  The user drags a rectangle over the title block.
    Includes auto-detect and a live OCR test button.
    Result is written to self.roi_result on Apply.
    """

    HANDLE_R = 6   # handle circle radius in pixels

    def __init__(self, parent, pdf_path: str, initial_roi: dict):
        super().__init__(parent)
        self.title("Set ROI — Drag a box over the title block, then click Apply")
        self.resizable(True, True)
        self.configure(fg_color="#1a1a2e")
        self.grab_set()

        self.pdf_path    = pdf_path
        self.roi         = dict(initial_roi)
        self.roi_result  = None   # set when user clicks Apply

        self._start_x = self._start_y = None
        self._drag_mode = None   # "draw" | "move" | corner handle tag
        self._drag_ox = self._drag_oy = 0

        self._render_page()
        self._build_ui()
        self._redraw()

    # ------------------------------------------------------------------
    # Page rendering
    # ------------------------------------------------------------------

    def _render_page(self):
        doc  = fitz.open(self.pdf_path)
        page = doc[0]
        self.page_w = page.rect.width
        self.page_h = page.rect.height
        mat  = fitz.Matrix(1.5, 1.5)
        pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        doc.close()
        self._full_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self._orig_w   = pix.width
        self._orig_h   = pix.height

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ── compute display size (fit within 950 × 700) ──────────────
        max_w, max_h  = 950, 680
        scale_w = max_w / self._orig_w
        scale_h = max_h / self._orig_h
        self.disp_scale = min(scale_w, scale_h, 1.0)
        self.disp_w = int(self._orig_w * self.disp_scale)
        self.disp_h = int(self._orig_h * self.disp_scale)
        self.geometry(f"{self.disp_w + 30}x{self.disp_h + 140}")

        # ── canvas ───────────────────────────────────────────────────
        canvas_frame = tk.Frame(self, bg="#1a1a2e")
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        self.canvas = tk.Canvas(canvas_frame, width=self.disp_w, height=self.disp_h,
                                cursor="crosshair", bg="#1a1a2e",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Scale page image once
        disp_img = self._full_img.resize((self.disp_w, self.disp_h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(disp_img)
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img, tags="bg")

        # Mouse bindings
        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # ── status label ─────────────────────────────────────────────
        self._status_var = tk.StringVar(
            value="Drag to draw a new ROI  ·  or use Auto-Detect  ·  then click Apply")
        status_lbl = ctk.CTkLabel(self, textvariable=self._status_var,
                                  font=ctk.CTkFont(size=11), text_color="#9e9e9e")
        status_lbl.pack(pady=(2, 4))

        # ── button row ───────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(0, 10))

        ctk.CTkButton(btn_row, text="🔍  Auto-Detect Title Block",
                      fg_color="#2a5298", hover_color="#1e3f7a", width=200, height=32,
                      command=self._auto_detect).pack(side="left", padx=6)

        ctk.CTkButton(btn_row, text="🧪  Test OCR",
                      fg_color="#1a4a80", hover_color="#0f3460", width=120, height=32,
                      command=self._test_ocr).pack(side="left", padx=6)

        ctk.CTkButton(btn_row, text="✔  Apply",
                      fg_color="#e94560", hover_color="#c73652", width=100, height=32,
                      command=self._apply).pack(side="left", padx=6)

        ctk.CTkButton(btn_row, text="Cancel",
                      fg_color="#2d2d4e", hover_color="#3d3d5e", width=80, height=32,
                      command=self.destroy).pack(side="left", padx=6)

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _frac_to_px(self, fx, fy):
        return fx * self.disp_w, fy * self.disp_h

    def _px_to_frac(self, cx, cy):
        return (max(0.0, min(1.0, cx / self.disp_w)),
                max(0.0, min(1.0, cy / self.disp_h)))

    def _roi_rect_px(self):
        x0, y0 = self._frac_to_px(self.roi["left"],  self.roi["top"])
        x1, y1 = self._frac_to_px(self.roi["right"], self.roi["bottom"])
        return x0, y0, x1, y1

    def _update_status(self):
        r = self.roi
        self._status_var.set(
            f"ROI — left:{r['left']:.3f}  top:{r['top']:.3f}  "
            f"right:{r['right']:.3f}  bottom:{r['bottom']:.3f}"
        )

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self):
        self.canvas.delete("roi")
        x0, y0, x1, y1 = self._roi_rect_px()
        hr = self.HANDLE_R

        # Semi-transparent overlay on the rest of the page
        # (tk Canvas doesn't support alpha natively, so we draw a dashed rect)
        self.canvas.create_rectangle(x0, y0, x1, y1,
                                     outline="#e94560", width=3,
                                     dash=(10, 5), tags="roi")

        # Corner handles
        for hx, hy, tag in [(x0, y0, "h_tl"), (x1, y0, "h_tr"),
                             (x0, y1, "h_bl"), (x1, y1, "h_br")]:
            self.canvas.create_oval(hx-hr, hy-hr, hx+hr, hy+hr,
                                    fill="#e94560", outline="#ffffff", width=1,
                                    tags=("roi", tag))

        self._update_status()

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _hit_handle(self, cx, cy):
        x0, y0, x1, y1 = self._roi_rect_px()
        hr = self.HANDLE_R + 4
        corners = [("h_tl", x0, y0), ("h_tr", x1, y0),
                   ("h_bl", x0, y1), ("h_br", x1, y1)]
        for tag, hx, hy in corners:
            if abs(cx - hx) < hr and abs(cy - hy) < hr:
                return tag
        return None

    def _hit_inside(self, cx, cy):
        x0, y0, x1, y1 = self._roi_rect_px()
        return x0 < cx < x1 and y0 < cy < y1

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def _on_press(self, event):
        cx, cy = event.x, event.y
        handle = self._hit_handle(cx, cy)
        if handle:
            self._drag_mode = handle
        elif self._hit_inside(cx, cy):
            self._drag_mode = "move"
            self._drag_ox = cx - self._frac_to_px(self.roi["left"],  self.roi["top"])[0]
            self._drag_oy = cy - self._frac_to_px(self.roi["left"],  self.roi["top"])[1]
        else:
            self._drag_mode = "draw"
            self._start_x = cx
            self._start_y = cy

    def _on_motion(self, event):
        cx, cy = event.x, event.y
        mode = self._drag_mode
        if not mode:
            return
        r = self.roi

        if mode == "draw":
            fx, fy = self._px_to_frac(cx, cy)
            sx, sy = self._px_to_frac(self._start_x, self._start_y)
            self.roi = {
                "left":   min(sx, fx), "top":    min(sy, fy),
                "right":  max(sx, fx), "bottom": max(sy, fy),
            }

        elif mode == "move":
            rw = r["right"] - r["left"]
            rh = r["bottom"] - r["top"]
            fl, ft = self._px_to_frac(cx - self._drag_ox, cy - self._drag_oy)
            fl = max(0.0, min(1.0 - rw, fl))
            ft = max(0.0, min(1.0 - rh, ft))
            self.roi = {"left": fl, "top": ft,
                        "right": fl + rw, "bottom": ft + rh}

        else:  # corner handle
            fx, fy = self._px_to_frac(cx, cy)
            if mode == "h_tl":
                self.roi = {**r, "left": min(fx, r["right"]-0.01),
                                  "top":  min(fy, r["bottom"]-0.01)}
            elif mode == "h_tr":
                self.roi = {**r, "right":  max(fx, r["left"]+0.01),
                                  "top":   min(fy, r["bottom"]-0.01)}
            elif mode == "h_bl":
                self.roi = {**r, "left":   min(fx, r["right"]-0.01),
                                  "bottom": max(fy, r["top"]+0.01)}
            elif mode == "h_br":
                self.roi = {**r, "right":  max(fx, r["left"]+0.01),
                                  "bottom": max(fy, r["top"]+0.01)}

        self._redraw()

    def _on_release(self, event):
        self._drag_mode = None

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def _auto_detect(self):
        self._status_var.set("Auto-detecting title block…")
        self.update()
        try:
            detected = auto_detect_title_block(self.pdf_path)
            self.roi = detected
            self._redraw()
            self._status_var.set(
                f"Auto-detected — drag handles to refine, then Test OCR or Apply")
        except Exception as exc:
            self._status_var.set(f"Auto-detect failed: {exc}")

    def _test_ocr(self):
        self._status_var.set("Running OCR on selected region…")
        self.update()
        try:
            text = extract_text_from_region(self.pdf_path, self.roi)
            if text:
                self._status_var.set(f"OCR result: {repr(text)}")
            else:
                self._status_var.set("OCR returned empty — try adjusting the box or "
                                     "check the drawing quality")
        except Exception as exc:
            self._status_var.set(f"OCR error: {exc}")

    def _apply(self):
        if self.roi["right"] - self.roi["left"] < 0.01 or \
           self.roi["bottom"] - self.roi["top"] < 0.01:
            messagebox.showwarning("Too small",
                "Please draw a larger selection.", parent=self)
            return
        self.roi_result = dict(self.roi)
        self.destroy()


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
        self.processing = False

        # Load persisted config
        cfg = load_config()
        self.roi: dict = cfg.get("roi", dict(DEFAULT_ROI))

        self._build_ui()
        self._log("ROI loaded from saved config." if "roi" in cfg else
                  "Using default ROI — click 'Set ROI' to configure.", "info")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        outer = ctk.CTkFrame(root, fg_color=self.BG, corner_radius=0)
        outer.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        outer.grid_rowconfigure(4, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(outer, text="PDF ISO Drawing Renamer",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=self.HILIGHT
                     ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        ctk.CTkLabel(outer,
                     text="Extract handwritten Circuit IDs via OCR  ·  Rename  ·  Organise",
                     font=ctk.CTkFont(size=12), text_color=self.FG_DIM
                     ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        ctrl = ctk.CTkFrame(outer, fg_color=self.PANEL, corner_radius=10)
        ctrl.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ctrl.grid_columnconfigure(0, weight=1)

        self._build_file_area(ctrl)
        self._build_settings_row(ctrl)
        self._build_file_list(ctrl)

        ctk.CTkLabel(outer, text="Processing Log",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=self.FG
                     ).grid(row=3, column=0, sticky="w", pady=(8, 2))

        self.log_box = ctk.CTkTextbox(
            outer, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=self.PANEL, text_color=self.FG,
            corner_radius=8, wrap="word", state="disabled")
        self.log_box.grid(row=4, column=0, sticky="nsew", pady=(0, 8))

        bottom = ctk.CTkFrame(outer, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self.progress_var = ctk.DoubleVar(value=0)
        ctk.CTkProgressBar(
            bottom, variable=self.progress_var,
            fg_color=self.ACCENT, progress_color=self.HILIGHT,
            height=8, corner_radius=4
        ).grid(row=0, column=0, sticky="ew", padx=(0, 12))

        self.run_btn = ctk.CTkButton(
            bottom, text="▶  Process Files",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.HILIGHT, hover_color="#c73652",
            width=150, corner_radius=8,
            command=self._start_processing)
        self.run_btn.grid(row=0, column=1)

    def _build_file_area(self, parent):
        dz = ctk.CTkFrame(parent, fg_color="transparent")
        dz.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        dz.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(dz,
            text="📂  Click to Add PDF Files",
            font=ctk.CTkFont(size=13),
            fg_color=self.ACCENT, hover_color="#1a4a80",
            height=52, corner_radius=10,
            border_width=2, border_color=self.HILIGHT,
            command=self._browse_files
        ).grid(row=0, column=0, columnspan=2, sticky="ew")

        self.file_count_lbl = ctk.CTkLabel(
            dz, text="0 files selected",
            font=ctk.CTkFont(size=11), text_color=self.FG_DIM)
        self.file_count_lbl.grid(row=1, column=0, sticky="w", pady=(4, 0))

        ctk.CTkButton(dz, text="Clear", width=70, height=24,
            font=ctk.CTkFont(size=11),
            fg_color=self.ACCENT, hover_color="#1a4a80", corner_radius=6,
            command=self._clear_files
        ).grid(row=1, column=1, sticky="e", pady=(4, 0))

    def _build_settings_row(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        row.grid_columnconfigure(1, weight=1)

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
        ).grid(row=0, column=2, padx=(0, 6))

        self.roi_lbl = ctk.CTkLabel(row,
            text=self._roi_summary(),
            font=ctk.CTkFont(size=10), text_color=self.FG_DIM)
        self.roi_lbl.grid(row=0, column=3, sticky="e", padx=(0, 6))

        ctk.CTkButton(row, text="🗺  Set ROI", width=120, height=28,
            font=ctk.CTkFont(size=11),
            fg_color=self.HILIGHT, hover_color="#c73652", corner_radius=6,
            command=self._open_roi_editor
        ).grid(row=0, column=4)

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
            font=("Consolas", 10), height=5, activestyle="none")
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
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")])
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
            text=f"{n} file{'s' if n != 1 else ''} selected")

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select Output Folder")
        if d:
            self.output_dir = d
            self.out_dir_var.set(d)

    # ------------------------------------------------------------------
    # ROI editor
    # ------------------------------------------------------------------

    def _roi_summary(self):
        r = self.roi
        return (f"ROI  L:{r['left']:.2f}  T:{r['top']:.2f}  "
                f"R:{r['right']:.2f}  B:{r['bottom']:.2f}")

    def _open_roi_editor(self):
        if not self.pdf_files:
            messagebox.showinfo("No Files",
                "Please add at least one PDF first so it can be used as a preview.")
            return
        dlg = InteractiveROIDialog(self.root, self.pdf_files[0], self.roi)
        self.root.wait_window(dlg)
        if dlg.roi_result:
            self.roi = dlg.roi_result
            # Persist immediately
            cfg = load_config()
            cfg["roi"] = self.roi
            save_config(cfg)
            self.roi_lbl.configure(text=self._roi_summary())
            self._log(f"ROI saved: {self.roi}", "success")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, msg: str, level: str = "info"):
        colours  = {"info": self.FG, "success": self.SUCCESS,
                    "warning": self.WARNING, "error": self.ERROR}
        prefixes = {"info": "  ", "success": "✔ ", "warning": "⚠ ", "error": "✖ "}
        colour = colours.get(level, self.FG)
        line   = prefixes.get(level, "  ") + msg + "\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line)
        tag = f"tag_{level}"
        start = self.log_box.index("end - 2 lines")
        end   = self.log_box.index("end - 1 chars")
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
        files  = list(self.pdf_files)
        total  = len(files)
        roi    = dict(self.roi)   # snapshot so mid-run changes don't affect it

        if self.output_dir:
            master_dir = os.path.join(self.output_dir, "Processed_ISO_Drawings")
        else:
            master_dir = os.path.join(os.path.dirname(files[0]),
                                      "Processed_ISO_Drawings")
        os.makedirs(master_dir, exist_ok=True)
        self._log(f"Master output folder: {master_dir}", "info")
        self._log("─" * 60, "info")

        success_count = fail_count = 0

        for idx, pdf_path in enumerate(files, start=1):
            fname = os.path.basename(pdf_path)
            self._log(f"[{idx}/{total}] {fname}", "info")
            try:
                raw_text = extract_text_from_region(pdf_path, roi)
                self._log(f"       OCR: {repr(raw_text)}", "info")
                if not raw_text:
                    raise ValueError(
                        "OCR returned empty — open 'Set ROI' and refine the box, "
                        "or try Auto-Detect")
                clean    = sanitise_filename(raw_text)
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
            f"Done — {success_count} succeeded, {fail_count} failed.  "
            f"Output: {master_dir}",
            "success" if fail_count == 0 else "warning")
        self.root.after(0, self._processing_complete)

    def _processing_complete(self):
        self.processing = False
        self.run_btn.configure(state="normal", text="▶  Process Files")

    def run(self):
        self.root.mainloop()


# ===========================================================================
# Entry point
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
