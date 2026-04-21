"""Small Win32 window-style helpers for Tk overlay windows."""

import ctypes
from ctypes import wintypes

try:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    WINDOWS = True
except (AttributeError, OSError):
    user32 = None
    WINDOWS = False


WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE = -20


if WINDOWS:
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]


def get_parent_hwnd(widget):
    if not WINDOWS:
        return None
    return user32.GetParent(widget.winfo_id())


def update_ex_style(widget, set_bits=0, clear_bits=0):
    if not WINDOWS:
        return False
    try:
        hwnd = get_parent_hwnd(widget)
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= set_bits
        style &= ~clear_bits
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        return True
    except Exception:
        return False


def apply_no_activate_toolwindow(widget):
    return update_ex_style(widget, set_bits=WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


def apply_passthrough_toolwindow(widget):
    return update_ex_style(
        widget,
        set_bits=WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT,
    )


def apply_overlay_styles(widget, click_through=False, allow_activate=False):
    set_bits = WS_EX_TOOLWINDOW
    clear_bits = 0

    if allow_activate:
        clear_bits |= WS_EX_NOACTIVATE | WS_EX_TRANSPARENT
    else:
        set_bits |= WS_EX_NOACTIVATE

    if click_through and not allow_activate:
        set_bits |= WS_EX_TRANSPARENT
    else:
        clear_bits |= WS_EX_TRANSPARENT

    return update_ex_style(widget, set_bits=set_bits, clear_bits=clear_bits)
