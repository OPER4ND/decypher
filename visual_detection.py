"""Screen-based Valorant death/menu detection used by Decypher."""

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass

try:
    import mss as _mss
    import numpy as _np

    _mss_instance = _mss.mss()
    SCREEN_GRAB_AVAILABLE = True

    def _screen_grab(bbox):
        x0, y0, x1, y1 = bbox
        monitor = {"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0}
        shot = _mss_instance.grab(monitor)
        # Returns (H, W, 4) uint8 array in BGRA channel order.
        return _np.frombuffer(shot.bgra, dtype=_np.uint8).reshape(shot.height, shot.width, 4)

except Exception:
    SCREEN_GRAB_AVAILABLE = False
    _np = None

    def _screen_grab(bbox):
        return None

DWMWA_EXTENDED_FRAME_BOUNDS = 9

try:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    except OSError:
        dwmapi = None
    WINDOWS = True
except (AttributeError, OSError):
    WINDOWS = False
    user32 = None
    dwmapi = None


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


EnumWindowsProc = (
    ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    if WINDOWS
    else None
)


@dataclass(frozen=True)
class DetectionProfile:
    strip_x_regions: tuple[tuple[float, float], ...] = ((0.8875, 0.9225),)
    strip_y_min: float = 0.27
    strip_y_max: float = 0.502
    strip_rgb: tuple[int, int, int] = (240, 49, 86)
    strip_tolerance: int = 24
    strip_h_ratio: float = 0.68
    strip_run_rows: int = 24
    menu_x_min: float = 0.43
    menu_x_max: float = 0.57
    menu_y_min: float = 0.91
    menu_y_max: float = 0.958
    menu_green_rgb: tuple[int, int, int] = (37, 186, 129)
    menu_green_tolerance: int = 70
    menu_h_ratio: float = 0.18
    menu_h_run_rows: int = 2
    menu_v_ratio: float = 0.18
    menu_v_run_cols: int = 2
    menu_white_fill_ratio: float = 0.58
    menu_white_fill_rows: int = 18
    menu_recent_seconds: float = 2.25


@dataclass(frozen=True)
class DetectionResult:
    player_dead: bool
    menu_detected: bool
    strip_bboxes: tuple[tuple[int, int, int, int], ...] | None
    window_found: bool = True

    @property
    def combined_strip_bbox(self) -> tuple[int, int, int, int] | None:
        if not self.strip_bboxes:
            return None
        return (
            min(b[0] for b in self.strip_bboxes),
            min(b[1] for b in self.strip_bboxes),
            max(b[2] for b in self.strip_bboxes),
            max(b[3] for b in self.strip_bboxes),
        )


class VisualDeathDetector:
    """Detect local death state from Valorant's death report card strip."""

    def __init__(self, profile: DetectionProfile | None = None):
        self.profile = profile or DetectionProfile()
        self.menu_button_detected = False
        self.last_menu_button_seen_ts = 0.0
        self._valorant_hwnd = None
        self._valorant_rect = None
        self._cached_strip_bboxes = None
        self._cached_menu_bbox = None

    def reset(self):
        self.menu_button_detected = False
        self.last_menu_button_seen_ts = 0.0
        self.reset_window_cache()

    def reset_window_cache(self):
        self._valorant_hwnd = None
        self._valorant_rect = None
        self._cached_strip_bboxes = None
        self._cached_menu_bbox = None

    def menu_seen_recently(self, now=None):
        now = now or time.time()
        return (
            self.menu_button_detected
            or (
                self.last_menu_button_seen_ts > 0
                and (now - self.last_menu_button_seen_ts) < self.profile.menu_recent_seconds
            )
        )

    def detect(self, menu_detection_enabled: bool) -> DetectionResult:
        hwnd = self._find_valorant_window()
        if not hwnd:
            self.menu_button_detected = False
            self.reset_window_cache()
            return DetectionResult(False, False, None, window_found=False)

        rect = self._get_window_rect(hwnd)
        if rect != self._valorant_rect:
            self._valorant_rect = rect
            self._cached_strip_bboxes = self._build_strip_bbox(rect)
            self._cached_menu_bbox = self._build_menu_button_bbox(rect)

        strip_bboxes = self._cached_strip_bboxes
        menu_bbox = self._cached_menu_bbox

        if menu_detection_enabled:
            self.menu_button_detected = (
                self._analyze_menu_button_bbox(menu_bbox) if menu_bbox else False
            )
            if self.menu_button_detected:
                self.last_menu_button_seen_ts = time.time()
        else:
            self.menu_button_detected = False

        player_dead = self._analyze_strip_bbox(strip_bboxes) if strip_bboxes else False
        if self.menu_button_detected:
            player_dead = False

        return DetectionResult(
            player_dead,
            self.menu_button_detected,
            tuple(strip_bboxes) if strip_bboxes else None,
        )

    def _enum_visible_windows(self):
        if not WINDOWS:
            return []

        results = []

        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if title:
                results.append((hwnd, title))
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        return results

    def _get_window_rect(self, hwnd):
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

    def _find_valorant_window(self):
        if self._valorant_hwnd:
            return self._valorant_hwnd
        for hwnd, title in self._enum_visible_windows():
            if "valorant" in title.lower():
                self._valorant_hwnd = hwnd
                return hwnd
        self._valorant_hwnd = None
        return None

    def _build_strip_bbox(self, rect):
        left, top, right, bottom = rect
        width = max(0, right - left)
        height = max(0, bottom - top)
        if not width or not height:
            return None
        y0 = top + int(round(height * self.profile.strip_y_min))
        y1 = top + int(round(height * self.profile.strip_y_max))
        bboxes = []
        for xr0, xr1 in self.profile.strip_x_regions:
            x0 = left + int(round(width * xr0))
            x1 = left + int(round(width * xr1))
            if x1 > x0:
                bboxes.append((x0, y0, x1, y1))
        return bboxes or None

    def _analyze_strip_bbox(self, bboxes):
        if not SCREEN_GRAB_AVAILABLE or not bboxes:
            return False
        tr, tg, tb = self.profile.strip_rgb
        tol = self.profile.strip_tolerance
        row_ok = None
        for bb in bboxes:
            arr = _screen_grab(bb)
            if arr is None:
                return False
            h = arr.shape[0]
            if row_ok is None:
                row_ok = _np.ones(h, dtype=bool)
            else:
                h = min(h, len(row_ok))
                row_ok = row_ok[:h]
            r = arr[:h, :, 2].astype(_np.int16)
            g = arr[:h, :, 1].astype(_np.int16)
            b = arr[:h, :, 0].astype(_np.int16)
            red_mask = (
                (_np.abs(r - tr) <= tol) &
                (_np.abs(g - tg) <= tol) &
                (_np.abs(b - tb) <= tol)
            )
            row_ok &= red_mask.mean(axis=1) >= self.profile.strip_h_ratio
        if row_ok is None:
            return False
        run = 0
        for ok in row_ok[::-1]:
            if ok:
                run += 1
                if run >= self.profile.strip_run_rows:
                    return True
            else:
                run = 0
        return False

    def _build_menu_button_bbox(self, rect):
        left, top, right, bottom = rect
        width = max(0, right - left)
        height = max(0, bottom - top)
        if not width or not height:
            return None
        x0 = left + int(round(width * self.profile.menu_x_min))
        x1 = left + int(round(width * self.profile.menu_x_max))
        y0 = top + int(round(height * self.profile.menu_y_min))
        y1 = top + int(round(height * self.profile.menu_y_max))
        return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None

    def _analyze_menu_button_bbox(self, bbox):
        if not SCREEN_GRAB_AVAILABLE or not bbox:
            return False
        arr = _screen_grab(bbox)
        if arr is None:
            return False
        tr, tg, tb = self.profile.menu_green_rgb
        tol = self.profile.menu_green_tolerance
        r = arr[:, :, 2].astype(_np.int16)
        g = arr[:, :, 1].astype(_np.int16)
        b = arr[:, :, 0].astype(_np.int16)
        green_mask = (
            (g >= r + 35) & (g >= b + 20) &
            (_np.abs(r - tr) <= tol) &
            (_np.abs(g - tg) <= tol) &
            (_np.abs(b - tb) <= tol)
        )
        run = 0
        has_h = False
        for ratio in green_mask.mean(axis=1):
            run = run + 1 if ratio >= self.profile.menu_h_ratio else 0
            if run >= self.profile.menu_h_run_rows:
                has_h = True
                break
        run = 0
        has_v = False
        for ratio in green_mask.mean(axis=0):
            run = run + 1 if ratio >= self.profile.menu_v_ratio else 0
            if run >= self.profile.menu_v_run_cols:
                has_v = True
                break
        raw = arr[:, :, :3]
        white_mask = (
            (raw[:, :, 2] >= 185) &
            (raw[:, :, 1] >= 185) &
            (raw[:, :, 0] >= 175) &
            (raw.max(axis=2).astype(_np.int16) - raw.min(axis=2).astype(_np.int16) <= 55)
        )
        run = 0
        has_white = False
        for ratio in white_mask.mean(axis=1):
            run = run + 1 if ratio >= self.profile.menu_white_fill_ratio else 0
            if run >= self.profile.menu_white_fill_rows:
                has_white = True
                break
        return (has_h and has_v) or has_white
