"""Small Win32 window-style helpers for Tk overlay windows."""

import ctypes
import os
import threading
from ctypes import wintypes

try:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    WINDOWS = True
except (AttributeError, OSError):
    user32 = None
    kernel32 = None
    WINDOWS = False


WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE = -20
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
WM_QUIT = 0x0012


if WINDOWS:
    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt_x", ctypes.c_long),
            ("pt_y", ctypes.c_long),
        ]

    WinEventProc = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        ctypes.c_long,
        ctypes.c_long,
        wintypes.DWORD,
        wintypes.DWORD,
    )

    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetForegroundWindow.argtypes = []
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.GetCurrentThreadId.argtypes = []
    user32.SetWinEventHook.restype = wintypes.HANDLE
    user32.SetWinEventHook.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HMODULE,
        WinEventProc,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    user32.UnhookWinEvent.restype = wintypes.BOOL
    user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = ctypes.c_longlong
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]


def get_parent_hwnd(widget):
    if not WINDOWS:
        return None
    return user32.GetParent(widget.winfo_id())


def get_window_process_name(hwnd):
    try:
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return None
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return None
            return os.path.basename(buffer.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def get_foreground_process_name():
    if not WINDOWS:
        return None
    return get_window_process_name(user32.GetForegroundWindow())


class ForegroundProcessTracker:
    def __init__(self, callback):
        self.callback = callback
        self._thread = None
        self._thread_id = None
        self._hook = None
        self._proc = None

    def start(self):
        if not WINDOWS:
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="foreground-tracker")
        self._thread.start()

    def stop(self):
        if not WINDOWS:
            return
        thread_id = self._thread_id
        if thread_id:
            try:
                user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        self._thread = None

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()

        @WinEventProc
        def win_event_proc(_hook, event, hwnd, _id_object, _id_child, _thread, _time_ms):
            if event != EVENT_SYSTEM_FOREGROUND:
                return
            try:
                self.callback(get_window_process_name(hwnd))
            except Exception:
                pass

        self._proc = win_event_proc
        hook = None
        try:
            hook = user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND,
                EVENT_SYSTEM_FOREGROUND,
                None,
                self._proc,
                0,
                0,
                WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
            )
            self._hook = hook
            try:
                self.callback(get_foreground_process_name())
            except Exception:
                pass
            if not hook:
                return

            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if hook:
                try:
                    user32.UnhookWinEvent(hook)
                except Exception:
                    pass
            self._hook = None
            self._proc = None
            self._thread_id = None


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
