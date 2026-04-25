"""Windows notification-area icon support for Decypher."""
import ctypes
import threading
from ctypes import wintypes
WM_APP = 32768
WM_TRAYICON = WM_APP + 1
WM_LBUTTONUP = 514
WM_RBUTTONUP = 517
WM_CONTEXTMENU = 123
WM_QUIT = 18
NIM_ADD = 0
NIM_DELETE = 2
NIF_MESSAGE = 1
NIF_ICON = 2
NIF_TIP = 4
IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE = 16
LR_DEFAULTSIZE = 64
MF_STRING = 0
MF_SEPARATOR = 2048
TPM_RIGHTBUTTON = 2
TPM_RETURNCMD = 256
TRAY_UID = 1
TRAY_SHOW_HIDE_ID = 1001
TRAY_CLICK_THROUGH_ID = 1002
TRAY_EXIT_ID = 1003
_TRAY_CLASS = 'DecypherTrayMsgWnd'
try:
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    WINDOWS = True
except (AttributeError, OSError):
    WINDOWS = False
    user32 = None
    shell32 = None

class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('hWnd', wintypes.HWND), ('uID', wintypes.UINT), ('uFlags', wintypes.UINT), ('uCallbackMessage', wintypes.UINT), ('hIcon', wintypes.HICON), ('szTip', wintypes.WCHAR * 128), ('dwState', wintypes.DWORD), ('dwStateMask', wintypes.DWORD), ('szInfo', wintypes.WCHAR * 256), ('uTimeoutOrVersion', wintypes.UINT), ('szInfoTitle', wintypes.WCHAR * 64), ('dwInfoFlags', wintypes.DWORD), ('guidItem', ctypes.c_byte * 16), ('hBalloonIcon', wintypes.HICON)]
TrayWndProc = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

class MSG(ctypes.Structure):
    _fields_ = [('hwnd', wintypes.HWND), ('message', wintypes.UINT), ('wParam', wintypes.WPARAM), ('lParam', wintypes.LPARAM), ('time', wintypes.DWORD), ('pt', POINT)]

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.UINT), ('style', wintypes.UINT), ('lpfnWndProc', TrayWndProc), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int), ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON), ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HANDLE), ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR), ('hIconSm', wintypes.HICON)]
if WINDOWS:
    user32.LoadIconW.restype = wintypes.HICON
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.DestroyIcon.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    user32.TrackPopupMenu.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.DispatchMessageW.restype = ctypes.c_longlong
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.UnregisterClassW.restype = wintypes.BOOL
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user32.DefWindowProcW.restype = ctypes.c_longlong
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

class TrayIcon:

    def __init__(self, root, is_visible, is_click_through, on_toggle_visibility, on_toggle_click_through, on_exit, tooltip='decypher', icon_path=None):
        self.root = root
        self.is_visible = is_visible
        self.is_click_through = is_click_through
        self.on_toggle_visibility = on_toggle_visibility
        self.on_toggle_click_through = on_toggle_click_through
        self.on_exit = on_exit
        self.tooltip = tooltip
        self.icon_path = icon_path
        self.hwnd = None
        self.hicon = None
        self.owns_hicon = False
        self.icon_added = False
        self.wndproc = None
        self.menu_hwnd = None
        self.pump_thread_id = None

    def create(self):
        if not WINDOWS or not shell32 or self.icon_added:
            return
        try:
            self.root.update_idletasks()
            self.menu_hwnd = user32.GetParent(self.root.winfo_id())
            thread = threading.Thread(target=self._pump, daemon=True, name='tray-pump')
            thread.start()
        except Exception as exc:
            pass

    def remove(self):
        if not WINDOWS or not shell32:
            return
        if self.icon_added and self.hwnd:
            nd = NOTIFYICONDATA()
            nd.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nd.hWnd = self.hwnd
            nd.uID = TRAY_UID
            try:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nd))
            except Exception:
                pass
            self.icon_added = False
        thread_id = self.pump_thread_id
        if thread_id:
            try:
                user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
            self.pump_thread_id = None
        self.hwnd = None
        self._destroy_icon()
        self.wndproc = None

    def _load_icon(self):
        if self.icon_path:
            try:
                hicon = user32.LoadImageW(None, self.icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
                if hicon:
                    self.owns_hicon = True
                    return hicon
            except Exception as exc:
                pass
        self.owns_hicon = False
        return user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))

    def _destroy_icon(self):
        if self.hicon and self.owns_hicon:
            try:
                user32.DestroyIcon(self.hicon)
            except Exception:
                pass
        self.hicon = None
        self.owns_hicon = False

    def _pump(self):
        """Dedicated background message pump for the tray icon."""
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self.pump_thread_id = kernel32.GetCurrentThreadId()
        hinstance = kernel32.GetModuleHandleW(None)
        hwnd = None
        registered = False

        @TrayWndProc
        def wnd_proc(hwnd_cb, msg, wparam, lparam):
            if msg == WM_TRAYICON:
                ev = lparam & 65535
                if ev == WM_LBUTTONUP:
                    self.root.after(0, self.on_toggle_visibility)
                elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self.root.after(0, self.show_menu)
                return 0
            return user32.DefWindowProcW(hwnd_cb, msg, wparam, lparam)
        self.wndproc = wnd_proc
        try:
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.lpfnWndProc = wnd_proc
            wc.hInstance = hinstance
            wc.lpszClassName = _TRAY_CLASS
            atom = user32.RegisterClassExW(ctypes.byref(wc))
            if not atom:
                err = ctypes.get_last_error()
                if err != 1410:
                    return
            else:
                registered = True
            hwnd = user32.CreateWindowExW(0, _TRAY_CLASS, None, 0, 0, 0, 0, 0, ctypes.c_void_p(-3), None, hinstance, None)
            if not hwnd:
                return
            self.hwnd = hwnd
            notify_data = NOTIFYICONDATA()
            notify_data.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            notify_data.hWnd = hwnd
            notify_data.uID = TRAY_UID
            notify_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            notify_data.uCallbackMessage = WM_TRAYICON
            self.hicon = self._load_icon()
            notify_data.hIcon = self.hicon
            notify_data.szTip = self.tooltip
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(notify_data)):
                return
            self.icon_added = True
            msg_buf = MSG()
            while user32.GetMessageW(ctypes.byref(msg_buf), None, 0, 0) > 0:
                user32.DispatchMessageW(ctypes.byref(msg_buf))
        except Exception as exc:
            pass
        finally:
            if self.icon_added and hwnd:
                nd = NOTIFYICONDATA()
                nd.cbSize = ctypes.sizeof(NOTIFYICONDATA)
                nd.hWnd = hwnd
                nd.uID = TRAY_UID
                try:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nd))
                except Exception:
                    pass
                self.icon_added = False
            if hwnd:
                try:
                    user32.DestroyWindow(hwnd)
                except Exception:
                    pass
            if registered:
                try:
                    user32.UnregisterClassW(_TRAY_CLASS, hinstance)
                except Exception:
                    pass
            self._destroy_icon()
            self.hwnd = None
            self.wndproc = None
            self.pump_thread_id = None

    def show_menu(self):
        if not WINDOWS:
            return
        menu_hwnd = self.menu_hwnd
        if not menu_hwnd:
            return
        point = POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        show_hide_text = 'Hide decypher' if self.is_visible() else 'Show decypher'
        click_text = 'Disable Click-through' if self.is_click_through() else 'Enable Click-through'
        user32.AppendMenuW(menu, MF_STRING, TRAY_SHOW_HIDE_ID, show_hide_text)
        user32.AppendMenuW(menu, MF_STRING, TRAY_CLICK_THROUGH_ID, click_text)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, TRAY_EXIT_ID, 'Exit')
        user32.SetForegroundWindow(menu_hwnd)
        command = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, point.x, point.y, 0, menu_hwnd, None)
        user32.DestroyMenu(menu)
        if command == TRAY_SHOW_HIDE_ID:
            self.on_toggle_visibility()
        elif command == TRAY_CLICK_THROUGH_ID:
            self.on_toggle_click_through()
        elif command == TRAY_EXIT_ID:
            self.on_exit()
