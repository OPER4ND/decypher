"""Visualises all three detection strips with live detection state."""

import ctypes
import signal
import tkinter as tk
from ctypes import wintypes

try:
    from PIL import ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

DWMWA_EXTENDED_FRAME_BOUNDS = 9
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_NOACTIVATE = 0x08000000

user32 = ctypes.WinDLL("user32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
except OSError:
    dwmapi = None


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    ]


# ── Strip (report card) ──────────────────────────────────────────────────────
STRIP_X_REGIONS      = ((0.8875, 0.9225),)
STRIP_Y_MIN          = 0.27
STRIP_Y_MAX          = 0.56
STRIP_RGB            = (240, 49, 86)
STRIP_TOLERANCE      = 24
STRIP_H_RATIO        = 0.68
STRIP_RUN_ROWS       = 24

# ── Menu button ──────────────────────────────────────────────────────────────
MENU_REGION          = (0.43, 0.57, 0.91, 0.958)
MENU_GREEN_RGB       = (37, 186, 129)
MENU_GREEN_TOL       = 70
MENU_H_RATIO         = 0.18
MENU_H_RUN_ROWS      = 2
MENU_V_RATIO         = 0.18
MENU_V_RUN_COLS      = 2
MENU_WHITE_RATIO     = 0.58
MENU_WHITE_RUN_ROWS  = 18

# ── Clove ult ────────────────────────────────────────────────────────────────
CLOVE_REGION         = (0.5707, 0.6053, 0.966, 0.970)
CLOVE_RGB            = (95, 238, 184)
CLOVE_TOLERANCE      = 24
CLOVE_H_RATIO        = 0.22
CLOVE_RUN_ROWS       = 2

POLL_MS   = 200
THICKNESS = 3
PAD       = 4
COLOR_HIT = "#39ff14"
COLOR_MISS = "#ffbf00"


# ── Window helpers ────────────────────────────────────────────────────────────

def _find_valorant():
    results = []
    Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd): return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0: return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if "valorant" in buf.value.strip().lower():
            results.append(hwnd)
        return True
    user32.EnumWindows(Proc(cb), 0)
    return results[0] if results else None


def _get_rect(hwnd):
    r = RECT()
    if dwmapi:
        try:
            if dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd),
                    wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                    ctypes.byref(r), ctypes.sizeof(r)) == 0:
                return r.left, r.top, r.right, r.bottom
        except Exception:
            pass
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _ratio_bbox(rect, x0r, x1r, y0r, y1r):
    l, t, r, b = rect
    w, h = max(0, r - l), max(0, b - t)
    x0 = l + int(round(w * x0r)); x1 = l + int(round(w * x1r))
    y0 = t + int(round(h * y0r)); y1 = t + int(round(h * y1r))
    if x1 <= x0 or y1 <= y0: return None
    return x0, y0, x1, y1


def _grab(bbox):
    try:
        return ImageGrab.grab(bbox=bbox, all_screens=True)
    except Exception:
        return None


# ── Detection logic ───────────────────────────────────────────────────────────

def _match(rgb, target, tol):
    return all(abs(rgb[i] - target[i]) <= tol for i in range(3))


def _detect_strip(rect):
    l, t, r, b = rect
    w, h = max(0, r - l), max(0, b - t)
    y0 = t + int(round(h * STRIP_Y_MIN))
    y1 = t + int(round(h * STRIP_Y_MAX))
    bboxes = []
    for x0r, x1r in STRIP_X_REGIONS:
        x0 = l + int(round(w * x0r)); x1 = l + int(round(w * x1r))
        if x1 > x0: bboxes.append((x0, y0, x1, y1))
    if not bboxes: return False, bboxes
    imgs = [_grab(bb) for bb in bboxes]
    if any(i is None for i in imgs): return False, bboxes
    height = min(i.size[1] for i in imgs)
    run = best = 0
    for y in range(height):
        row_ok = True
        for img in imgs:
            px = img.load()
            hits = sum(1 for x in range(img.size[0]) if _match(px[x, y][:3], STRIP_RGB, STRIP_TOLERANCE))
            if hits / max(1, img.size[0]) < STRIP_H_RATIO:
                row_ok = False; break
        if row_ok:
            run += 1; best = max(best, run)
        else:
            run = 0
    return best >= STRIP_RUN_ROWS, bboxes


def _detect_menu(rect):
    bbox = _ratio_bbox(rect, *MENU_REGION)
    if not bbox: return False, None
    img = _grab(bbox)
    if not img: return False, bbox
    px = img.load(); W, H = img.size

    def green(rgb): return (rgb[1] >= rgb[0] + 35 and rgb[1] >= rgb[2] + 20
        and all(abs(rgb[i] - MENU_GREEN_RGB[i]) <= MENU_GREEN_TOL for i in range(3)))
    def white(rgb): return rgb[0] >= 185 and rgb[1] >= 185 and rgb[2] >= 175 and max(rgb) - min(rgb) <= 55

    h_run = v_run = w_run = 0
    has_h = has_v = has_w = False
    for y in range(H):
        row = [px[x, y][:3] for x in range(W)]
        if sum(1 for p in row if green(p)) / max(1, W) >= MENU_H_RATIO:
            h_run += 1
            if h_run >= MENU_H_RUN_ROWS: has_h = True
        else: h_run = 0
        if sum(1 for p in row if white(p)) / max(1, W) >= MENU_WHITE_RATIO:
            w_run += 1
            if w_run >= MENU_WHITE_RUN_ROWS: has_w = True
        else: w_run = 0
    for x in range(W):
        col = [px[x, y][:3] for y in range(H)]
        if sum(1 for p in col if green(p)) / max(1, H) >= MENU_V_RATIO:
            v_run += 1
            if v_run >= MENU_V_RUN_COLS: has_v = True
        else: v_run = 0

    detected = (has_h and has_v) or has_w
    return detected, bbox


def _detect_clove(rect):
    bbox = _ratio_bbox(rect, *CLOVE_REGION)
    if not bbox: return False, None
    img = _grab(bbox)
    if not img: return False, bbox
    px = img.load(); W, H = img.size
    run = best = 0
    for y in range(H):
        hits = sum(1 for x in range(W) if _match(px[x, y][:3], CLOVE_RGB, CLOVE_TOLERANCE))
        if hits / max(1, W) >= CLOVE_H_RATIO:
            run += 1; best = max(best, run)
        else: run = 0
    return best >= CLOVE_RUN_ROWS, bbox


# ── Overlay ───────────────────────────────────────────────────────────────────

class Strip:
    """One coloured outline around a bbox."""
    def __init__(self, root, label):
        self.wins = {}
        for side in ("top", "bottom", "left", "right"):
            w = tk.Toplevel(root)
            w.overrideredirect(True)
            w.attributes("-topmost", True)
            w.configure(bg=COLOR_MISS)
            w.withdraw()
            self.wins[side] = w
            w.after(120, lambda win=w: self._passthrough(win))
        self._lwin = tk.Toplevel(root)
        self._lwin.overrideredirect(True)
        self._lwin.attributes("-topmost", True)
        self._lwin.configure(bg="#111111")
        self._lwin.withdraw()
        self._lbl = tk.Label(self._lwin, text=label, font=("Consolas", 9),
                             fg="#ffffff", bg="#111111", padx=4, pady=1)
        self._lbl.pack()

    def _passthrough(self, win):
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def show(self, bbox, detected):
        x0, y0, x1, y1 = bbox
        ox0, oy0, ox1, oy1 = x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD
        W, H = max(1, ox1 - ox0), max(1, oy1 - oy0)
        color = COLOR_HIT if detected else COLOR_MISS
        for win in self.wins.values():
            win.configure(bg=color)
        geoms = {
            "top":    (ox0, oy0 - THICKNESS, W, THICKNESS),
            "bottom": (ox0, oy1, W, THICKNESS),
            "left":   (ox0 - THICKNESS, oy0, THICKNESS, H),
            "right":  (ox1, oy0, THICKNESS, H),
        }
        for side, (x, y, w, h) in geoms.items():
            self.wins[side].geometry(f"{w}x{h}+{x}+{y}")
            self.wins[side].deiconify()
            self.wins[side].lift()
        self._lwin.geometry(f"+{x0}+{max(0, oy0 - 18)}")
        self._lwin.deiconify()
        self._lwin.lift()

    def hide(self):
        for w in self.wins.values():
            w.withdraw()
        self._lwin.withdraw()


class DebugOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.strip_outline = Strip(self.root, "strip")
        self.menu_outline  = Strip(self.root, "menu")
        self.clove_outline = Strip(self.root, "clove ult")
        self.root.after(POLL_MS, self._tick)

    def _tick(self):
        hwnd = _find_valorant()
        if hwnd:
            rect = _get_rect(hwnd)
            strip_hit, strip_bboxes = _detect_strip(rect)
            menu_hit,  menu_bbox    = _detect_menu(rect)
            clove_hit, clove_bbox   = _detect_clove(rect)

            if strip_bboxes:
                # show outline around the combined extent of all strip regions
                x0 = min(b[0] for b in strip_bboxes); y0 = min(b[1] for b in strip_bboxes)
                x1 = max(b[2] for b in strip_bboxes); y1 = max(b[3] for b in strip_bboxes)
                self.strip_outline.show((x0, y0, x1, y1), strip_hit)
            else:
                self.strip_outline.hide()

            if menu_bbox:
                self.menu_outline.show(menu_bbox, menu_hit)
            else:
                self.menu_outline.hide()

            if clove_bbox:
                self.clove_outline.show(clove_bbox, clove_hit)
            else:
                self.clove_outline.hide()
        else:
            self.strip_outline.hide()
            self.menu_outline.hide()
            self.clove_outline.hide()

        self.root.after(POLL_MS, self._tick)

    def run(self):
        signal.signal(signal.SIGINT, lambda *_: self.root.destroy())
        self.root.after(200, lambda: None)  # keep signal responsive
        self.root.mainloop()


if __name__ == "__main__":
    DebugOverlay().run()
