"""Standalone Clove ult strip detector — shows scan region and detection result only."""

import ctypes
import signal
import time
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
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


# --- Tunable parameters ---
# x0_ratio, x1_ratio, y0_ratio, y1_ratio  (fractions of the Valorant window)
REGION = (0.5707, 0.6053, 0.966, 0.970)  # 2x original width -10%, shifted right +0.013, raised +0.003

READY_RGB = (95, 238, 184)
RGB_TOLERANCE = 24
MIN_HORIZONTAL_RATIO = 0.22             # fraction of row pixels that must match
MIN_RUN_ROWS = 2                        # consecutive qualifying rows needed
VERBOSE = True                          # print pixel samples to console
# --------------------------

POLL_MS = 150


def _enum_valorant_window():
    results = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if "valorant" in buf.value.strip().lower():
            results.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return results[0] if results else None


def _get_rect(hwnd):
    rect = RECT()
    if dwmapi:
        try:
            if dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            ) == 0:
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def _build_bbox(rect, region):
    left, top, right, bottom = rect
    w = max(0, right - left)
    h = max(0, bottom - top)
    x0r, x1r, y0r, y1r = region
    x0 = left + int(round(w * x0r))
    x1 = left + int(round(w * x1r))
    y0 = top  + int(round(h * y0r))
    y1 = top  + int(round(h * y1r))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _pixel_matches(rgb):
    try:
        r, g, b = rgb[:3]
    except Exception:
        return False
    tr, tg, tb = READY_RGB
    tol = RGB_TOLERANCE
    return abs(r - tr) <= tol and abs(g - tg) <= tol and abs(b - tb) <= tol


def _analyze(bbox, verbose=False):
    if not PIL_AVAILABLE or not bbox:
        return False
    try:
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
    except Exception:
        return False
    pixels = img.load()
    width, height = img.size
    run = 0
    best = 0
    for y in range(height):
        row = [pixels[x, y][:3] for x in range(width)]
        hits = sum(1 for rgb in row if _pixel_matches(rgb))
        ratio = hits / max(1, width)
        if verbose:
            sample = row[width // 2]
            print(f"  y={y} ratio={ratio:.2f} mid_px={sample}")
        if ratio >= MIN_HORIZONTAL_RATIO:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best >= MIN_RUN_ROWS


class DebugOverlay:
    THICKNESS = 3
    PAD = 4

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#ffbf00")

        self.outlines = {}
        for side in ("top", "bottom", "left", "right"):
            w = tk.Toplevel(self.root)
            w.overrideredirect(True)
            w.attributes("-topmost", True)
            w.configure(bg="#ffbf00")
            w.withdraw()
            self.outlines[side] = w
            w.after(120, lambda win=w: self._make_passthrough(win))

        self.root.after(POLL_MS, self._tick)

    def _make_passthrough(self, win):
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def _draw(self, bbox, detected):
        x0, y0, x1, y1 = bbox
        p = self.PAD
        t = self.THICKNESS
        ox0, oy0 = x0 - p, y0 - p
        ox1, oy1 = x1 + p, y1 + p
        w = max(1, ox1 - ox0)
        h = max(1, oy1 - oy0)
        color = "#39ff14" if detected else "#ffbf00"
        geoms = {
            "top":    (ox0,     oy0 - t, w, t),
            "bottom": (ox0,     oy1,     w, t),
            "left":   (ox0 - t, oy0,     t, h),
            "right":  (ox1,     oy0,     t, h),
        }
        for side, (x, y, sw, sh) in geoms.items():
            win = self.outlines[side]
            win.configure(bg=color)
            win.geometry(f"{sw}x{sh}+{x}+{y}")
            win.deiconify()
            win.lift()

    def _hide(self):
        for w in self.outlines.values():
            w.withdraw()

    def _tick(self):
        hwnd = _enum_valorant_window()
        if hwnd:
            rect = _get_rect(hwnd)
            bbox = _build_bbox(rect, REGION)
            if bbox:
                detected = _analyze(bbox, verbose=VERBOSE)
                self._draw(bbox, detected)
            else:
                self._hide()
        else:
            self._hide()
        self.root.after(POLL_MS, self._tick)

    def run(self):
        signal.signal(signal.SIGINT, lambda *_: self.root.destroy())
        self.root.after(200, self._check_signal)
        self.root.mainloop()

    def _check_signal(self):
        self.root.after(200, self._check_signal)


if __name__ == "__main__":
    DebugOverlay().run()
