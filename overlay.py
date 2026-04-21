"""Decypher overlay for Valorant agent-select actions and death muting."""
import json
import os
import re
import signal
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from agent_select import AgentSelectOverlay, _OverlayBase
from valorant_api import AUDIO_AVAILABLE, ValorantLocalAPI, mute_valorant
from visual_detection import SCREEN_GRAB_AVAILABLE, VisualDeathDetector
try:
    import ctypes
    WINDOWS = True
except ImportError:
    WINDOWS = False
WS_EX_TRANSPARENT = 32
WS_EX_TOOLWINDOW = 128
WS_EX_NOACTIVATE = 134217728
GWL_EXSTYLE = -20
WM_APP = 32768
WM_TRAYICON = WM_APP + 1
WM_LBUTTONUP = 514
WM_RBUTTONUP = 517
WM_CONTEXTMENU = 123
NIM_ADD = 0
NIM_DELETE = 2
NIF_MESSAGE = 1
NIF_ICON = 2
NIF_TIP = 4
IDI_APPLICATION = 32512
MF_STRING = 0
MF_SEPARATOR = 2048
TPM_RIGHTBUTTON = 2
TPM_RETURNCMD = 256
TRAY_UID = 1
TRAY_SHOW_HIDE_ID = 1001
TRAY_CLICK_THROUGH_ID = 1002
TRAY_EXIT_ID = 1003
if WINDOWS:
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
else:
    user32 = None
    shell32 = None

class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('hWnd', wintypes.HWND), ('uID', wintypes.UINT), ('uFlags', wintypes.UINT), ('uCallbackMessage', wintypes.UINT), ('hIcon', wintypes.HICON), ('szTip', wintypes.WCHAR * 128), ('dwState', wintypes.DWORD), ('dwStateMask', wintypes.DWORD), ('szInfo', wintypes.WCHAR * 256), ('uTimeoutOrVersion', wintypes.UINT), ('szInfoTitle', wintypes.WCHAR * 64), ('dwInfoFlags', wintypes.DWORD), ('guidItem', ctypes.c_byte * 16), ('hBalloonIcon', wintypes.HICON)]
WM_QUIT = 18
_TRAY_CLASS = 'DecypherTrayMsgWnd'
TrayWndProc = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

class MSG(ctypes.Structure):
    _fields_ = [('hwnd', wintypes.HWND), ('message', wintypes.UINT), ('wParam', wintypes.WPARAM), ('lParam', wintypes.LPARAM), ('time', wintypes.DWORD), ('pt', POINT)]

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.UINT), ('style', wintypes.UINT), ('lpfnWndProc', TrayWndProc), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int), ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON), ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HANDLE), ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR), ('hIconSm', wintypes.HICON)]
if WINDOWS:
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.LoadIconW.restype = wintypes.HICON
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
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
_SHOOTER_GAME_LOG = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'VALORANT', 'Saved', 'Logs', 'ShooterGame.log')
_LOG_DEATH_RE = re.compile('LogPlayerController:.*AcknowledgePossession\\([\'\\"]?.+_PostDeath_')
_LOG_REVIVAL_RE = re.compile('LogPlayerController:.*ClientRestart_Implementation.+_PostDeath_')
_LOG_CLOVE_ULT_WINDOW_RE = re.compile('LogAbilitySystem:.*ReactiveRes_InDeathCastWindow_C')
_LOG_CLOVE_ULT_USED_RE = re.compile('LogAbilitySystem:.*DelayDeathUltPointReward_C')

class DecypherOverlay(_OverlayBase):
    DEFAULT_HOTKEYS = {'hide_show': 'F2', 'click_through': 'F3', 'mute_on_death': 'F4', 'manual_mute': 'F5'}
    HOTKEY_ACTIONS = (('hide_show', 'Hide/Show'), ('click_through', 'Click-through'), ('mute_on_death', 'Auto-Mute'), ('manual_mute', 'Manual Mute'))
    MODIFIER_ORDER = ('CTRL', 'ALT', 'SHIFT')
    MODIFIER_VK = {'CTRL': 17, 'ALT': 18, 'SHIFT': 16}
    KEY_ALIASES = {'CONTROL': 'CTRL', 'CONTROL_L': 'CTRL', 'CONTROL_R': 'CTRL', 'CTRL_L': 'CTRL', 'CTRL_R': 'CTRL', 'ALT_L': 'ALT', 'ALT_R': 'ALT', 'SHIFT_L': 'SHIFT', 'SHIFT_R': 'SHIFT', 'ESCAPE': 'ESC', 'RETURN': 'ENTER', 'PRIOR': 'PAGEUP', 'NEXT': 'PAGEDOWN', 'PGUP': 'PAGEUP', 'PGDN': 'PAGEDOWN', 'DEL': 'DELETE', 'INS': 'INSERT', 'EQUALS': 'EQUAL', 'QUOTE': 'APOSTROPHE', 'BRACKETLEFT': 'LBRACKET', 'BRACKETRIGHT': 'RBRACKET', ' ': 'SPACE'}
    KEY_NAME_TO_VK = {**{f'F{index}': 112 + index - 1 for index in range(1, 25)}, **{chr(code): code for code in range(ord('A'), ord('Z') + 1)}, **{str(index): 48 + index for index in range(10)}, 'SPACE': 32, 'TAB': 9, 'ENTER': 13, 'BACKSPACE': 8, 'INSERT': 45, 'DELETE': 46, 'HOME': 36, 'END': 35, 'PAGEUP': 33, 'PAGEDOWN': 34, 'LEFT': 37, 'UP': 38, 'RIGHT': 39, 'DOWN': 40, 'CAPSLOCK': 20, 'NUMLOCK': 144, 'SCROLLLOCK': 145, 'PAUSE': 19, 'PRINTSCREEN': 44, 'SEMICOLON': 186, 'EQUAL': 187, 'COMMA': 188, 'MINUS': 189, 'PERIOD': 190, 'SLASH': 191, 'GRAVE': 192, 'LBRACKET': 219, 'BACKSLASH': 220, 'RBRACKET': 221, 'APOSTROPHE': 222, 'NUMPAD0': 96, 'NUMPAD1': 97, 'NUMPAD2': 98, 'NUMPAD3': 99, 'NUMPAD4': 100, 'NUMPAD5': 101, 'NUMPAD6': 102, 'NUMPAD7': 103, 'NUMPAD8': 104, 'NUMPAD9': 105}

    def __init__(self):
        self.api = ValorantLocalAPI()
        self.running = True
        self.visible = False
        self.tray_forced_visible = False
        self.click_through = False
        self.in_match = False
        self.in_pregame = False
        self.agent_overlay = None
        self._drag_data = {'x': 0, 'y': 0}
        self.config_path = os.path.join(self._runtime_base_dir(), 'decypher_config.json')
        self.hotkeys = self._load_hotkeys()
        self.hide_show_hotkey = self.hotkeys['hide_show']
        self.click_through_hotkey = self.hotkeys['click_through']
        self.mute_on_death_hotkey = self.hotkeys['mute_on_death']
        self.manual_mute_hotkey = self.hotkeys['manual_mute']
        self.hotkey_widgets = {}
        self.binding_capture = None
        self._hotkey_resume_after = 0.0
        self.death_mute_enabled = False
        self.death_muted = False
        self.manual_muted = False
        self.manual_defers_to_auto = True
        self.player_dead = False
        self.revive_gate = False
        self.startup_revive_gate = False
        self.startup_score_baseline = None
        self.startup_revival_since = None
        self.startup_revival_seconds = 1.25
        self.round_start_cooldown_until = 0.0
        self.round_start_cooldown_seconds = 25.0
        self.last_cooldown_block_log_ts = 0.0
        self.round_start_requires_clear = False
        self.round_start_clear_since = None
        self.round_start_clear_seconds = 4.0
        self.mute_armed_ts = 0.0
        self.mute_arm_grace_seconds = 0.75
        self.score_total_at_mute = None
        self.last_score_poll_ts = 0.0
        self.score_poll_interval_muted = 1.0
        self.live_score_total = None
        self.last_live_score_poll_ts = 0.0
        self.live_score_poll_interval = 0.5
        self.current_mode_id = ''
        self.current_game_state = 'Menu'
        self.current_agent_id = None
        self.current_agent_name = None
        self.normal_round_start_cooldown_seconds = 25.0
        self.extended_round_start_cooldown_seconds = 42.0
        self.agent_catalog_load_started = False
        self.clove_ult_detected = False
        self.clove_ult_last_ready_ts = 0.0
        self.clove_ult_ready_grace_seconds = 1.5
        self.clove_ult_pending_until = 0.0
        self.clove_ult_pending_score_total = None
        self.clove_ult_pending_seconds = 2.5
        self.tray_hwnd = None
        self.tray_icon_added = False
        self.tray_wndproc = None
        self._tray_menu_hwnd = None
        self._tray_pump_thread_id = None
        self._log_tailer_stop = threading.Event()
        self._log_tailer_thread = None
        self.visual_detector = VisualDeathDetector()
        self._strip_outline_wins = {}
        self._strip_outline_bbox = None
        self._strip_outline_last_state = None
        self._strip_outline_visible = False
        self.menu_button_detected = False
        self.last_menu_button_seen_ts = 0.0
        self.root = tk.Tk()
        self.root.title('Decypher')
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.92)
        self.root.overrideredirect(True)
        self.root.configure(bg='#0d1117')
        self.window_width = 320
        self.root.geometry(f'{self.window_width}x1+0+50')
        self.header = tk.Frame(self.root, bg='#161b22')
        self.header.pack(fill='x')
        title_row = tk.Frame(self.header, bg='#161b22')
        title_row.pack(fill='x', padx=10, pady=8)
        title = tk.Label(title_row, text='DECYPHER', font=(self.FONT_FAMILY, 16, 'bold'), fg='#58a6ff', bg='#161b22')
        title.pack(side='left')
        btn_frame = tk.Frame(title_row, bg='#161b22')
        btn_frame.pack(side='right')
        self.click_through_btn = tk.Label(btn_frame, text='🖱', font=(self.FONT_FAMILY, 12), fg='#8b949e', bg='#161b22', cursor='hand2')
        self.click_through_btn.pack(side='left', padx=4)
        self.click_through_btn.bind('<Button-1>', self.toggle_click_through)
        close_btn = tk.Label(btn_frame, text='X', font=(self.FONT_FAMILY, 16), fg='#8b949e', bg='#161b22', cursor='hand2')
        close_btn.pack(side='left', padx=4)
        close_btn.bind('<Button-1>', lambda _event: self.close())
        close_btn.bind('<Enter>', lambda _event: close_btn.configure(fg='#f85149'))
        close_btn.bind('<Leave>', lambda _event: close_btn.configure(fg='#8b949e'))
        self.status_label = tk.Label(self.header, text='Waiting for Valorant...', font=(self.FONT_FAMILY, 11), fg='#8b949e', bg='#161b22', anchor='center')
        self.status_label.pack(fill='x', padx=10)
        for widget in [self.header, title_row, title, self.status_label]:
            widget.configure(cursor='fleur')
            widget.bind('<Button-1>', self.on_drag_start)
            widget.bind('<B1-Motion>', self.on_drag_motion)
        footer = tk.Frame(self.root, bg='#161b22')
        footer.pack(fill='x', side='bottom')
        hints_frame = tk.Frame(footer, bg='#161b22')
        hints_frame.pack(fill='x', padx=10, pady=(8, 6))
        self._build_hotkey_controls(hints_frame)
        if AUDIO_AVAILABLE:
            toggle_frame = tk.Frame(footer, bg='#161b22')
            toggle_frame.pack(fill='x', padx=10, pady=(0, 10))
            self.mute_toggle = tk.Label(toggle_frame, text='[   ] Mute on Death', font=(self.FONT_FAMILY, 11), fg='#c9d1d9', bg='#161b22', cursor='hand2')
            self.mute_toggle.pack(anchor='center')
            self.mute_toggle.bind('<Button-1>', self.toggle_death_mute)
            self.mute_status = tk.Label(toggle_frame, text='disabled', font=(self.FONT_FAMILY, 10), fg='#6e7681', bg='#161b22')
            self.mute_status.pack(anchor='center')
            self.defer_toggle = tk.Label(toggle_frame, text='[   ] Manual defers to round', font=(self.FONT_FAMILY, 11), fg='#c9d1d9', bg='#161b22', cursor='hand2')
            self.defer_toggle.pack(anchor='center')
            self.defer_toggle.bind('<Button-1>', self.toggle_manual_defers_to_auto)
        self._position_main_window()
        self.root.withdraw()
        if WINDOWS:
            self.root.after(100, self._apply_overlay_styles)
            self.root.after(120, self._create_strip_outline)
            self.root.after(150, self._create_tray_icon)
            self.root.after(150, self._refresh_death_detection_loop)
            self.root.after(200, self._start_log_tailer)
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        if WINDOWS:
            self.hotkey_thread = threading.Thread(target=self.hotkey_listener, daemon=True)
            self.hotkey_thread.start()
        self.root.bind('<KeyPress>', self._handle_hotkey_capture)
        self.root.bind('<Escape>', self._handle_escape)
        self.root.after(300, self._apply_default_state)

    def _apply_default_state(self):
        self.death_mute_enabled = True
        self.mute_toggle.configure(text='[ x ] Mute on Death', fg='#3fb950')
        self.mute_status.configure(text='armed', fg='#3fb950')
        self.click_through = True
        self.click_through_btn.configure(fg='#58a6ff')
        self.root.attributes('-alpha', 0.6)
        self._apply_overlay_styles()
        self._refresh_defer_toggle_style()

    def _position_main_window(self):
        self.root.update_idletasks()
        height = max(1, self.root.winfo_reqheight())
        screen_width = self.root.winfo_screenwidth()
        x_pos = screen_width - self.window_width - 20
        y_pos = 50
        self.root.geometry(f'{self.window_width}x{height}+{x_pos}+{y_pos}')

    @staticmethod
    def _runtime_base_dir() -> str:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.argv[0]))
        return os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def _clean_key_name(cls, key):
        key = str(key or '').strip().upper().replace('<', '').replace('>', '')
        key = key.replace('-', '+')
        return cls.KEY_ALIASES.get(key, key)

    @classmethod
    def _parse_hotkey(cls, value):
        raw_parts = [part for part in str(value or '').replace(' ', '').split('+') if part]
        if not raw_parts:
            return None
        modifiers = []
        main_key = None
        for raw_part in raw_parts:
            key = cls._clean_key_name(raw_part)
            if key in cls.MODIFIER_VK:
                if key not in modifiers:
                    modifiers.append(key)
                continue
            if key == 'ESC' or key not in cls.KEY_NAME_TO_VK or main_key is not None:
                return None
            main_key = key
        if main_key is None:
            return None
        ordered_modifiers = [modifier for modifier in cls.MODIFIER_ORDER if modifier in modifiers]
        return (ordered_modifiers, main_key)

    @classmethod
    def _format_hotkey(cls, value):
        parsed = cls._parse_hotkey(value)
        if not parsed:
            return None
        modifiers, main_key = parsed
        return '+'.join([*modifiers, main_key])

    @classmethod
    def _normalize_hotkey(cls, value, fallback):
        return cls._format_hotkey(value) or fallback

    def _load_hotkeys(self):
        hotkeys = dict(self.DEFAULT_HOTKEYS)
        try:
            with open(self.config_path, 'r', encoding='utf-8') as config_file:
                config = json.load(config_file)
        except FileNotFoundError:
            return hotkeys
        except Exception:
            return hotkeys
        if isinstance(config, dict):
            for name, fallback in self.DEFAULT_HOTKEYS.items():
                hotkeys[name] = self._normalize_hotkey(config.get(name), fallback)
        return hotkeys

    def _save_hotkeys(self):
        config = {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as config_file:
                loaded_config = json.load(config_file)
            if isinstance(loaded_config, dict):
                config.update(loaded_config)
        except FileNotFoundError:
            pass
        except Exception:
            pass
        config.update(self.hotkeys)
        try:
            with open(self.config_path, 'w', encoding='utf-8') as config_file:
                json.dump(config, config_file, indent=2)
                config_file.write('\n')
        except Exception as exc:
            pass

    def _set_hotkey(self, name, hotkey):
        self.hotkeys[name] = hotkey
        self.hide_show_hotkey = self.hotkeys['hide_show']
        self.click_through_hotkey = self.hotkeys['click_through']
        self.mute_on_death_hotkey = self.hotkeys['mute_on_death']
        self.manual_mute_hotkey = self.hotkeys['manual_mute']
        self._save_hotkeys()
        self._refresh_hotkey_controls()

    def _hotkey_action_enabled(self, name):
        return AUDIO_AVAILABLE or name not in ('mute_on_death', 'manual_mute')

    def _build_hotkey_controls(self, parent):
        actions = [action for action in self.HOTKEY_ACTIONS if self._hotkey_action_enabled(action[0])]
        for row_start in range(0, len(actions), 2):
            row = tk.Frame(parent, bg='#161b22')
            row.pack(fill='x', pady=1)
            row.grid_columnconfigure(0, weight=1, uniform='hotkeys')
            row.grid_columnconfigure(1, weight=1, uniform='hotkeys')
            for column, (name, label) in enumerate(actions[row_start:row_start + 2]):
                self._create_hotkey_item(row, name, label, column)

    def _create_hotkey_item(self, parent, name, label, column):
        item = tk.Frame(parent, bg='#161b22', cursor='hand2')
        item.grid(row=0, column=column, sticky='w', padx=(0, 8), pady=1)
        key_label = tk.Label(item, text=self.hotkeys[name], font=(self.FONT_FAMILY, 10, 'bold'), fg='#0d1117', bg='#8b949e', padx=5, pady=0, width=8, cursor='hand2')
        key_label.pack(side='left')
        action_label = tk.Label(item, text=f' {label}', font=(self.FONT_FAMILY, 10), fg='#8b949e', bg='#161b22', cursor='hand2')
        action_label.pack(side='left')
        self.hotkey_widgets[name] = {'item': item, 'key': key_label, 'action': action_label}
        for widget in (item, key_label, action_label):
            widget.bind('<Button-1>', lambda _event, hotkey_name=name: self._begin_hotkey_capture(hotkey_name))

    def _refresh_hotkey_controls(self):
        for name, widgets in self.hotkey_widgets.items():
            is_active = self.binding_capture == name
            widgets['key'].configure(text='...' if is_active else self.hotkeys[name], fg='#0d1117', bg='#d29922' if is_active else '#8b949e')

    def _begin_hotkey_capture(self, name):
        self.binding_capture = name
        self._refresh_hotkey_controls()
        self._apply_overlay_styles()
        self.root.lift()
        self.root.focus_force()
        return 'break'

    def _cancel_hotkey_capture(self):
        if not self.binding_capture:
            return False
        name = self.binding_capture
        self.binding_capture = None
        self._refresh_hotkey_controls()
        self._apply_overlay_styles()
        return True

    def _event_to_hotkey(self, event):
        key = self._clean_key_name(event.keysym)
        if key == 'ESC':
            return 'ESC'
        if key in self.MODIFIER_VK:
            return None
        if key.startswith('KP_'):
            keypad_key = key[3:]
            if keypad_key.isdigit():
                key = f'NUMPAD{keypad_key}'
        if key not in self.KEY_NAME_TO_VK:
            char = self._clean_key_name(getattr(event, 'char', ''))
            if len(char) == 1 and char.isalnum():
                key = char
            else:
                return None
        modifiers = []
        state = int(getattr(event, 'state', 0))
        if state & 4:
            modifiers.append('CTRL')
        if state & 131072 or state & 8:
            modifiers.append('ALT')
        if state & 1:
            modifiers.append('SHIFT')
        return '+'.join([*modifiers, key])

    def _flash_hotkey_error(self, name):
        widgets = self.hotkey_widgets.get(name)
        if not widgets:
            return
        widgets['key'].configure(fg='white', bg='#f85149')
        self.root.after(350, self._refresh_hotkey_controls)

    def _handle_hotkey_capture(self, event):
        if not self.binding_capture:
            return None
        name = self.binding_capture
        hotkey = self._event_to_hotkey(event)
        if hotkey == 'ESC':
            self._cancel_hotkey_capture()
            return 'break'
        hotkey = self._format_hotkey(hotkey)
        if not hotkey:
            self._flash_hotkey_error(name)
            return 'break'
        for other_name, other_hotkey in self.hotkeys.items():
            if other_name != name and other_hotkey == hotkey:
                self._flash_hotkey_error(name)
                return 'break'
        self.binding_capture = None
        self._hotkey_resume_after = time.time() + 0.5
        self._apply_overlay_styles()
        self._set_hotkey(name, hotkey)
        return 'break'

    def _handle_escape(self, event=None):
        if self._cancel_hotkey_capture():
            return 'break'
        return 'break'

    def _hotkey_is_pressed(self, hotkey, user32_local):
        parsed = self._parse_hotkey(hotkey)
        if not parsed:
            return False
        modifiers, main_key = parsed
        for modifier in modifiers:
            if not user32_local.GetAsyncKeyState(self.MODIFIER_VK[modifier]) & 32768:
                return False
        return bool(user32_local.GetAsyncKeyState(self.KEY_NAME_TO_VK[main_key]) & 32768)

    def _create_tray_icon(self):
        if not WINDOWS or not shell32 or self.tray_icon_added:
            return
        try:
            self.root.update_idletasks()
            self._tray_menu_hwnd = user32.GetParent(self.root.winfo_id())
            t = threading.Thread(target=self._tray_pump, daemon=True, name='tray-pump')
            t.start()
        except Exception as exc:
            pass

    def _remove_tray_icon(self):
        if not WINDOWS or not shell32:
            return
        if self.tray_icon_added and self.tray_hwnd:
            nd = NOTIFYICONDATA()
            nd.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nd.hWnd = self.tray_hwnd
            nd.uID = TRAY_UID
            try:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nd))
            except Exception:
                pass
            self.tray_icon_added = False
        thread_id = self._tray_pump_thread_id
        if thread_id:
            try:
                user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
            self._tray_pump_thread_id = None
        self.tray_hwnd = None
        self.tray_wndproc = None

    def _tray_pump(self):
        """Dedicated background message pump for the tray icon.

        Runs in its own thread with its own message-only HWND so tkinter's
        GetMessage/DispatchMessage loop never consumes our WM_TRAYICON messages.
        The Python WINFUNCTYPE callback is safe here because this thread has a
        proper Python thread state — no conflict with tkinter's GIL management.
        """
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._tray_pump_thread_id = kernel32.GetCurrentThreadId()
        hinstance = kernel32.GetModuleHandleW(None)
        hwnd = None
        registered = False

        @TrayWndProc
        def wnd_proc(hwnd_cb, msg, wparam, lparam):
            if msg == WM_TRAYICON:
                ev = lparam & 65535
                if ev == WM_LBUTTONUP:
                    self.root.after(0, self._toggle_tray_visibility)
                elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self.root.after(0, self._show_tray_menu)
                return 0
            return user32.DefWindowProcW(hwnd_cb, msg, wparam, lparam)
        self.tray_wndproc = wnd_proc
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
            self.tray_hwnd = hwnd
            notify_data = NOTIFYICONDATA()
            notify_data.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            notify_data.hWnd = hwnd
            notify_data.uID = TRAY_UID
            notify_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            notify_data.uCallbackMessage = WM_TRAYICON
            notify_data.hIcon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
            notify_data.szTip = 'Decypher'
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(notify_data)):
                return
            self.tray_icon_added = True
            msg_buf = MSG()
            while user32.GetMessageW(ctypes.byref(msg_buf), None, 0, 0) > 0:
                user32.DispatchMessageW(ctypes.byref(msg_buf))
        except Exception as exc:
            pass
        finally:
            if self.tray_icon_added and hwnd:
                nd = NOTIFYICONDATA()
                nd.cbSize = ctypes.sizeof(NOTIFYICONDATA)
                nd.hWnd = hwnd
                nd.uID = TRAY_UID
                try:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nd))
                except Exception:
                    pass
                self.tray_icon_added = False
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
            self.tray_hwnd = None
            self.tray_wndproc = None
            self._tray_pump_thread_id = None

    def _show_tray_menu(self):
        if not WINDOWS:
            return
        menu_hwnd = self._tray_menu_hwnd
        if not menu_hwnd:
            return
        point = POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        show_hide_text = 'Hide Decypher' if self.visible else 'Show Decypher'
        click_text = 'Disable Click-through' if self.click_through else 'Enable Click-through'
        user32.AppendMenuW(menu, MF_STRING, TRAY_SHOW_HIDE_ID, show_hide_text)
        user32.AppendMenuW(menu, MF_STRING, TRAY_CLICK_THROUGH_ID, click_text)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, TRAY_EXIT_ID, 'Exit')
        user32.SetForegroundWindow(menu_hwnd)
        command = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, point.x, point.y, 0, menu_hwnd, None)
        user32.DestroyMenu(menu)
        if command == TRAY_SHOW_HIDE_ID:
            self._toggle_tray_visibility()
        elif command == TRAY_CLICK_THROUGH_ID:
            self.toggle_click_through()
        elif command == TRAY_EXIT_ID:
            self.close()

    def _show_from_tray(self):
        self.tray_forced_visible = True
        self.visible = True
        self._position_main_window()
        self.root.deiconify()
        self.root.lift()
        self._apply_overlay_styles()

    def _hide_from_tray(self):
        self.tray_forced_visible = False
        self.visible = False
        self.root.withdraw()

    def _toggle_tray_visibility(self):
        if self.visible:
            self._hide_from_tray()
        else:
            self._show_from_tray()

    def toggle_death_mute(self, event=None):
        if self.binding_capture:
            return
        self.death_mute_enabled = not self.death_mute_enabled
        if self.death_mute_enabled:
            now = time.time()
            self.mute_armed_ts = now
            menu_recent = self._menu_seen_recently(now)
            self.revive_gate = bool(self.player_dead or menu_recent)
            self.startup_revive_gate = self.revive_gate
            self.startup_score_baseline = None
            self.startup_revival_since = None
            if self.startup_revive_gate:
                self.last_score_poll_ts = 0.0
            self.mute_toggle.configure(text='[ x ] Mute on Death', fg='#3fb950')
            if menu_recent:
                self.mute_status.configure(text='waiting for menu to close', fg='#d29922')
            elif self.revive_gate:
                self.mute_status.configure(text='waiting for revival', fg='#d29922')
            else:
                self.mute_status.configure(text='armed', fg='#3fb950')
            self._refresh_defer_toggle_style()
            return
        self.mute_toggle.configure(text='[   ] Mute on Death', fg='#c9d1d9')
        self.mute_status.configure(text='disabled', fg='#6e7681')
        if self.death_muted:
            self._release_death_mute()
        self.revive_gate = False
        self.startup_revive_gate = False
        self.startup_score_baseline = None
        self.startup_revival_since = None
        self.clove_ult_pending_until = 0.0
        self.clove_ult_pending_score_total = None
        self.mute_armed_ts = 0.0
        self.score_total_at_mute = None
        self._refresh_defer_toggle_style()

    def toggle_manual_mute(self, event=None):
        if self.binding_capture:
            return
        if self.manual_defers_to_auto and self.death_mute_enabled and self.death_muted and self.manual_muted:
            return
        previous = self.manual_muted
        self.manual_muted = not self.manual_muted
        if self._sync_target_mute() <= 0:
            self.manual_muted = previous
            self._sync_target_mute()
            return
        if self.manual_muted:
            pass

    def toggle_manual_defers_to_auto(self, event=None):
        self.manual_defers_to_auto = not self.manual_defers_to_auto
        self._refresh_defer_toggle_style()

    def _refresh_defer_toggle_style(self):
        checked = self.manual_defers_to_auto
        active = self.death_mute_enabled
        text = '[ x ] Manual defers to round' if checked else '[   ] Manual defers to round'
        if checked:
            fg = '#3fb950' if active else '#2d5c38'
        else:
            fg = '#c9d1d9' if active else '#4a5568'
        self.defer_toggle.configure(text=text, fg=fg)

    def _maybe_clear_deferred_manual(self):
        if self.manual_defers_to_auto and self.death_mute_enabled and self.manual_muted:
            self.manual_muted = False
            self._sync_target_mute()
    _OUTLINE_HIT = '#39ff14'
    _OUTLINE_MISS = '#ffbf00'
    _OUTLINE_THICKNESS = 3
    _OUTLINE_PAD = 4

    def _create_strip_outline(self):
        for side in ('top', 'bottom', 'left', 'right'):
            w = tk.Toplevel(self.root)
            w.overrideredirect(True)
            w.attributes('-topmost', True)
            w.configure(bg=self._OUTLINE_MISS)
            w.withdraw()
            self._strip_outline_wins[side] = w
            w.after(120, lambda win=w: self._make_passthrough(win))

    def _make_passthrough(self, win):
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def _show_strip_outline(self, bbox, detected):
        if not self._strip_outline_wins:
            return
        color = self._OUTLINE_HIT if detected else self._OUTLINE_MISS
        state = (bbox, color)
        if self._strip_outline_visible and self._strip_outline_last_state == state:
            return
        x0, y0, x1, y1 = bbox
        ox0 = x0 - self._OUTLINE_PAD
        oy0 = y0 - self._OUTLINE_PAD
        ox1 = x1 + self._OUTLINE_PAD
        oy1 = y1 + self._OUTLINE_PAD
        W = max(1, ox1 - ox0)
        H = max(1, oy1 - oy0)
        T = self._OUTLINE_THICKNESS
        geoms = {'top': (ox0, oy0 - T, W, T), 'bottom': (ox0, oy1, W, T), 'left': (ox0 - T, oy0, T, H), 'right': (ox1, oy0, T, H)}
        for side, (x, y, w, h) in geoms.items():
            win = self._strip_outline_wins[side]
            win.configure(bg=color)
            win.geometry(f'{w}x{h}+{x}+{y}')
            win.deiconify()
            win.lift()
        self._strip_outline_last_state = state
        self._strip_outline_visible = True

    def _hide_strip_outline(self):
        if not self._strip_outline_visible:
            return
        for win in self._strip_outline_wins.values():
            win.withdraw()
        self._strip_outline_visible = False
        self._strip_outline_last_state = None

    def _menu_seen_recently(self, now=None):
        return self.visual_detector.menu_seen_recently(now)

    def _detect_strip_death(self):
        if self.death_muted:
            self._hide_strip_outline()
            return
        prev_menu = self.menu_button_detected
        prev_dead = self.player_dead
        detection = self.visual_detector.detect(self.death_mute_enabled)
        self.menu_button_detected = detection.menu_detected
        self.last_menu_button_seen_ts = self.visual_detector.last_menu_button_seen_ts
        self.player_dead = detection.player_dead
        if not detection.window_found:
            self._hide_strip_outline()
            return
        if self.menu_button_detected != prev_menu:
            pass
        if self.player_dead != prev_dead:
            pass
        combined = detection.combined_strip_bbox
        if combined:
            self._show_strip_outline(combined, self.player_dead)
        else:
            self._hide_strip_outline()

    def _start_log_tailer(self):
        self._log_tailer_thread = threading.Thread(target=self._log_tail_worker, daemon=True)
        self._log_tailer_thread.start()

    def _log_tail_worker(self):
        log_path = _SHOOTER_GAME_LOG
        while not self._log_tailer_stop.is_set():
            try:
                if not os.path.exists(log_path):
                    self._log_tailer_stop.wait(5)
                    continue
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(0, 2)
                    idle_ticks = 0
                    while not self._log_tailer_stop.is_set():
                        line = f.readline()
                        if not line:
                            idle_ticks += 1
                            if idle_ticks >= 40:
                                idle_ticks = 0
                                try:
                                    if os.path.getsize(log_path) < f.tell():
                                        break
                                except OSError:
                                    break
                            self._log_tailer_stop.wait(0.05)
                            continue
                        idle_ticks = 0
                        if _LOG_DEATH_RE.search(line):
                            self.root.after(0, self._on_log_death)
                        elif _LOG_REVIVAL_RE.search(line):
                            self.root.after(0, self._on_log_revival)
                        elif _LOG_CLOVE_ULT_WINDOW_RE.search(line):
                            self.root.after(0, self._on_log_clove_ult_window)
                        elif _LOG_CLOVE_ULT_USED_RE.search(line):
                            self.root.after(0, self._on_log_clove_ult_used)
            except Exception:
                self._log_tailer_stop.wait(2)

    def _on_log_death(self):
        if not self.running:
            return
        self.player_dead = True
        if self.death_mute_enabled and (not self.death_muted):
            if self._is_current_agent_clove():
                self.root.after(200, self._on_log_death_delayed)
            else:
                self._apply_death_mute(self.in_match and (not self.in_pregame))

    def _on_log_death_delayed(self):
        if not self.running or not self.player_dead or self.death_muted:
            return
        self._apply_death_mute(self.in_match and (not self.in_pregame))

    def _on_log_revival(self):
        if not self.running:
            return
        self.player_dead = False
        self.clove_ult_detected = False
        self._apply_death_mute(self.in_match and (not self.in_pregame))

    def _on_log_clove_ult_window(self):
        if not self.running:
            return
        now = time.time()
        self.clove_ult_detected = True
        self.clove_ult_last_ready_ts = now
        self.root.after(3000, self._clear_clove_ult_if_stale)

    def _on_log_clove_ult_used(self):
        if not self.running:
            return
        self.clove_ult_detected = False
        self.clove_ult_last_ready_ts = 0.0

    def _clear_clove_ult_if_stale(self):
        if not self.running:
            return
        if self.clove_ult_detected and time.time() - self.clove_ult_last_ready_ts >= 2.5:
            self.clove_ult_detected = False

    def _refresh_death_detection_loop(self):
        if not self.running:
            return
        live_match_active = self.in_match and (not self.in_pregame)
        if not WINDOWS or not live_match_active:
            self.player_dead = False
            self.clove_ult_detected = False
            self.menu_button_detected = False
            self.last_menu_button_seen_ts = 0.0
            self.visual_detector.reset()
            self._hide_strip_outline()
            self._track_live_score_transition(False)
            self._apply_death_mute(False)
            self.root.after(100, self._refresh_death_detection_loop)
            return
        is_clove = self._is_current_agent_clove()
        if not is_clove:
            self._detect_strip_death()
        now_ts = time.time()
        if now_ts - self._last_debug_dump_ts >= 3.0:
            pass
        self._track_live_score_transition(live_match_active)
        self._apply_death_mute(live_match_active)
        self.root.after(250 if not is_clove else 100, self._refresh_death_detection_loop)

    def _poll_score_delta(self, baseline_score):
        now = time.time()
        if now - self.last_score_poll_ts < self.score_poll_interval_muted:
            return ('wait', baseline_score, None)
        self.last_score_poll_ts = now
        current_score = self.api.get_round_score_total()
        if baseline_score is None:
            return ('baseline', current_score, current_score)
        if current_score is None:
            return ('missing', baseline_score, None)
        if current_score != baseline_score:
            return ('changed', baseline_score, current_score)
        return ('same', baseline_score, current_score)

    def _half_change_score_for_current_mode(self):
        mode = f'{self.current_mode_id} {self.current_game_state}'.lower()
        if 'swift' in mode:
            return 4
        if 'spikerush' in mode or 'spike rush' in mode or 'quickbomb' in mode:
            return 3
        return 12

    def _uses_extended_buy_phase(self, previous_score, current_score):
        if previous_score is None or current_score is None:
            return False
        if current_score <= previous_score:
            return False
        half_score = self._half_change_score_for_current_mode()
        if current_score == half_score:
            return True
        if half_score == 12 and current_score >= 24 and ((current_score - 24) % 2 == 0):
            return True
        return False

    def _begin_round_start_cooldown(self, now=None, previous_score=None, current_score=None):
        now = time.time() if now is None else now
        self.round_start_cooldown_seconds = self.extended_round_start_cooldown_seconds if self._uses_extended_buy_phase(previous_score, current_score) else self.normal_round_start_cooldown_seconds
        self.round_start_cooldown_until = now + self.round_start_cooldown_seconds
        self.round_start_requires_clear = True
        self.round_start_clear_since = None
        self.revive_gate = bool(self.player_dead)
        self._maybe_clear_deferred_manual()

    def _is_current_agent_clove(self):
        return (self.current_agent_name or '').lower() == 'clove'

    def _apply_round_start_gate(self, now):
        if self.death_muted:
            return False
        if self.round_start_cooldown_until > now:
            if self.player_dead:
                self.revive_gate = True
                self.round_start_clear_since = None
            remaining = max(1, int(self.round_start_cooldown_until - now))
            self.mute_status.configure(text=f'round-start cooldown {remaining}s', fg='#d29922')
            if self.player_dead and now - self.last_cooldown_block_log_ts >= 2.0:
                self.last_cooldown_block_log_ts = now
            return True
        if self.round_start_cooldown_until > 0:
            self.round_start_cooldown_until = 0.0
        if not self.round_start_requires_clear:
            return False
        if self.player_dead:
            if not self.revive_gate or self.round_start_clear_since is not None:
                pass
            self.revive_gate = True
            self.round_start_clear_since = None
            self.mute_status.configure(text='waiting for strip clear', fg='#d29922')
            return True
        self.revive_gate = False
        if self.round_start_clear_since is None:
            self.round_start_clear_since = now
            self.mute_status.configure(text='confirming strip clear', fg='#d29922')
            return True
        clear_for = now - self.round_start_clear_since
        if clear_for < self.round_start_clear_seconds:
            self.mute_status.configure(text=f'confirming strip clear {int(clear_for)}s', fg='#d29922')
            return True
        self.round_start_requires_clear = False
        self.round_start_clear_since = None
        self.revive_gate = False
        self.mute_status.configure(text='armed', fg='#3fb950')
        return True

    def _apply_clove_ult_gate(self, now):
        if self.clove_ult_pending_until <= 0:
            return False
        score_status, baseline_score, current_score = self._poll_score_delta(self.clove_ult_pending_score_total)
        if score_status == 'baseline':
            self.clove_ult_pending_score_total = baseline_score
        elif score_status == 'changed':
            self.clove_ult_pending_until = 0.0
            self.clove_ult_pending_score_total = None
            self._begin_round_start_cooldown(now, baseline_score, current_score)
            self.mute_status.configure(text=f'score changed; round-start cooldown {int(self.round_start_cooldown_seconds)}s', fg='#d29922')
            return True
        if not self.player_dead:
            self.clove_ult_pending_until = 0.0
            self.clove_ult_pending_score_total = None
            self.clove_ult_last_ready_ts = 0.0
            self.mute_armed_ts = 0.0
            self.mute_status.configure(text='armed', fg='#3fb950')
            return True
        if now < self.clove_ult_pending_until:
            remaining = max(0.1, self.clove_ult_pending_until - now)
            self.mute_status.configure(text=f'waiting for Clove ult {remaining:.1f}s', fg='#d29922')
            return True
        self.clove_ult_pending_until = 0.0
        self.clove_ult_pending_score_total = None
        return False

    def _track_live_score_transition(self, live_match_active: bool):
        if not live_match_active:
            return
        now = time.time()
        if now - self.last_live_score_poll_ts < self.live_score_poll_interval:
            return
        self.last_live_score_poll_ts = now
        current_score = self.api.get_round_score_total()
        if current_score is None:
            return
        if self.live_score_total is None:
            self.live_score_total = current_score
            return
        if current_score == self.live_score_total:
            return
        previous_score = self.live_score_total
        self.live_score_total = current_score
        if not self.death_muted:
            self._begin_round_start_cooldown(now, previous_score, current_score)
            if self.death_mute_enabled and AUDIO_AVAILABLE:
                self.mute_status.configure(text=f'score changed; round-start cooldown {int(self.round_start_cooldown_seconds)}s', fg='#d29922')

    def _apply_death_mute(self, live_match_active):
        if not AUDIO_AVAILABLE or not self.death_mute_enabled:
            return
        if not live_match_active:
            self._on_match_end()
            return
        now = time.time()
        if self.startup_revive_gate:
            self._handle_startup_gate(now)
            return
        if self._apply_round_start_gate(now):
            return
        if self._apply_clove_ult_gate(now):
            return
        if self.player_dead and (not self.death_muted):
            self._on_death_trigger(now)
            return
        if not self.player_dead and self.revive_gate:
            self._on_revive_clear()
            return
        if self.death_muted:
            self._on_muted_poll()

    def _on_match_end(self):
        self.revive_gate = False
        self.startup_revive_gate = False
        self.startup_score_baseline = None
        self.startup_revival_since = None
        self.mute_armed_ts = 0.0
        self.clove_ult_pending_until = 0.0
        self.clove_ult_pending_score_total = None
        self.score_total_at_mute = None
        self._maybe_clear_deferred_manual()
        if self.death_muted and self._release_death_mute() > 0:
            self._begin_round_start_cooldown()
            status_text = 'death mute released; manual mute still on' if self.manual_muted else 'unmuted (not in live match)'
            self.mute_status.configure(text=status_text, fg='#3fb950')

    def _handle_startup_gate(self, now):
        score_status, baseline_score, current_score = self._poll_score_delta(self.startup_score_baseline)
        if not self.player_dead:
            if self._menu_seen_recently(now):
                self.startup_revival_since = None
                self.mute_status.configure(text='waiting for menu to close', fg='#d29922')
                return
            if self.startup_revival_since is None:
                self.startup_revival_since = now
                self.mute_status.configure(text='confirming revival', fg='#d29922')
            clear_for = now - self.startup_revival_since
            if clear_for >= self.startup_revival_seconds:
                self.startup_revive_gate = False
                self.startup_score_baseline = None
                self.startup_revival_since = None
                self.revive_gate = False
                self.mute_armed_ts = 0.0
                self.mute_status.configure(text='armed', fg='#3fb950')
            else:
                self.mute_status.configure(text=f'confirming revival {int(clear_for)}s', fg='#d29922')
            return
        self.startup_revival_since = None
        if score_status == 'wait':
            self.mute_status.configure(text='waiting for revival', fg='#d29922')
            return
        if score_status == 'baseline':
            self.startup_score_baseline = baseline_score
            if current_score is not None:
                self.mute_status.configure(text=f'waiting for revival or score change from {current_score}', fg='#d29922')
            return
        if score_status == 'changed':
            self.startup_revive_gate = False
            self.startup_score_baseline = None
            self.startup_revival_since = None
            self._begin_round_start_cooldown(now, baseline_score, current_score)
            self.mute_armed_ts = 0.0
            self.mute_status.configure(text=f'round-start cooldown {int(self.round_start_cooldown_seconds)}s', fg='#d29922')

    def _on_death_trigger(self, now):
        current_score = self.api.get_round_score_total()
        if current_score is not None and self.live_score_total is not None and (current_score != self.live_score_total):
            previous_score = self.live_score_total
            self.live_score_total = current_score
            self._begin_round_start_cooldown(now, previous_score, current_score)
            self.mute_status.configure(text=f'score changed; round-start cooldown {int(self.round_start_cooldown_seconds)}s', fg='#d29922')
            return
        if self.revive_gate:
            return
        if self.mute_armed_ts > 0 and now - self.mute_armed_ts <= self.mute_arm_grace_seconds:
            self.revive_gate = True
            self.startup_revive_gate = True
            self.startup_score_baseline = None
            self.startup_revival_since = None
            self.round_start_cooldown_until = 0.0
            self.round_start_requires_clear = False
            self.round_start_clear_since = None
            self.last_score_poll_ts = 0.0
            self.mute_status.configure(text='waiting for revival', fg='#d29922')
            return
        clove_ult_recently_ready = self.clove_ult_detected or now - self.clove_ult_last_ready_ts <= self.clove_ult_ready_grace_seconds
        if self._is_current_agent_clove() and clove_ult_recently_ready:
            self.clove_ult_pending_until = now + self.clove_ult_pending_seconds
            self.clove_ult_pending_score_total = current_score
            self.last_score_poll_ts = 0.0
            self.mute_status.configure(text=f'waiting for Clove ult {self.clove_ult_pending_seconds:.1f}s', fg='#d29922')
            return
        if self._engage_death_mute() > 0:
            self.mute_armed_ts = 0.0
            self.score_total_at_mute = self.api.get_round_score_total()
            self.last_score_poll_ts = time.time()
            if self.score_total_at_mute is None:
                self.mute_status.configure(text='muted whole game; waiting for live score', fg='#f85149')
            else:
                self.mute_status.configure(text=f'muted whole game; waiting for score change from {self.score_total_at_mute}', fg='#f85149')

    def _on_revive_clear(self):
        self.revive_gate = False
        self.mute_armed_ts = 0.0
        if not self.death_muted:
            self.mute_status.configure(text='armed', fg='#3fb950')

    def _on_muted_poll(self):
        score_status, baseline_score, current_score = self._poll_score_delta(self.score_total_at_mute)
        if score_status == 'wait':
            return
        if score_status == 'baseline':
            self.score_total_at_mute = baseline_score
            if current_score is not None:
                self.mute_status.configure(text=f'muted whole game; waiting for score change from {current_score}', fg='#f85149')
            return
        if score_status == 'changed':
            self.player_dead = False
            self._begin_round_start_cooldown(previous_score=baseline_score, current_score=current_score)
            if self._release_death_mute() <= 0:
                return
            self.score_total_at_mute = None
            self.mute_armed_ts = 0.0
            status_text = f'death mute released; manual mute still on; cooldown {int(self.round_start_cooldown_seconds)}s' if self.manual_muted else f'unmuted; round-start cooldown {int(self.round_start_cooldown_seconds)}s'
            self.mute_status.configure(text=status_text, fg='#d29922')

    def _sync_target_mute(self) -> int:
        return 1 if mute_valorant(self.death_muted or self.manual_muted) else 0

    def _engage_death_mute(self) -> int:
        self.death_muted = True
        if self._sync_target_mute() > 0:
            return 1
        self.death_muted = False
        return 0

    def _release_death_mute(self) -> int:
        self.death_muted = False
        return self._sync_target_mute()

    def toggle_visibility(self):
        if self.binding_capture:
            return
        if not self.visible and (not self.in_match):
            return
        self.visible = not self.visible
        if self.visible:
            self.root.deiconify()
        else:
            self.root.withdraw()

    def toggle_click_through(self, event=None):
        if self.binding_capture:
            return
        self.click_through = not self.click_through
        self.click_through_btn.configure(fg='#58a6ff' if self.click_through else '#8b949e')
        self.root.attributes('-alpha', 0.6 if self.click_through else 0.92)
        self._apply_overlay_styles()

    def _apply_overlay_styles(self):
        if not WINDOWS:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_TOOLWINDOW
            if self.binding_capture:
                style &= ~WS_EX_NOACTIVATE
                style &= ~WS_EX_TRANSPARENT
            else:
                style |= WS_EX_NOACTIVATE
            if self.click_through and (not self.binding_capture):
                style |= WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def hotkey_listener(self):
        if not WINDOWS:
            return
        user32_local = ctypes.windll.user32
        while self.running:
            try:
                if self.binding_capture or time.time() < self._hotkey_resume_after:
                    time.sleep(0.05)
                    continue
                fired = False
                if self._hotkey_is_pressed(self.hide_show_hotkey, user32_local):
                    self.root.after(0, self.toggle_visibility)
                    fired = True
                if self._hotkey_is_pressed(self.click_through_hotkey, user32_local):
                    self.root.after(0, self.toggle_click_through)
                    fired = True
                if AUDIO_AVAILABLE and self._hotkey_is_pressed(self.mute_on_death_hotkey, user32_local):
                    self.root.after(0, self.toggle_death_mute)
                    fired = True
                if AUDIO_AVAILABLE and self._hotkey_is_pressed(self.manual_mute_hotkey, user32_local):
                    self.root.after(0, self.toggle_manual_mute)
                    fired = True
                time.sleep(0.3 if fired else 0.05)
            except Exception:
                pass

    def auto_show(self):
        if not self.visible:
            self.visible = True
            self.root.after(0, self.root.deiconify)

    def auto_hide(self):
        if self.visible:
            self.visible = False
            self.root.after(0, self.root.withdraw)

    def ensure_agent_select_overlay(self):
        if self.agent_overlay is None:
            self.agent_overlay = AgentSelectOverlay(self.api, master=self.root)
        return self.agent_overlay

    def show_agent_select(self):
        overlay = self.ensure_agent_select_overlay()
        self.root.after(0, overlay.show)

    def hide_agent_select(self):
        if self.agent_overlay:
            self.root.after(0, self.agent_overlay.hide)

    def destroy_agent_select(self):
        if not self.agent_overlay:
            return
        overlay = self.agent_overlay
        self.agent_overlay = None
        self.root.after(0, overlay.close)

    def _ensure_agent_catalog_loading(self):
        if self.agent_catalog_load_started:
            return
        self.agent_catalog_load_started = True

        def load_catalog():
            self.api.load_agent_catalog_once()
            self.root.after(0, self._preload_agent_select_overlay)
        threading.Thread(target=load_catalog, daemon=True).start()

    def _preload_agent_select_overlay(self):
        if self.in_match and (not self.in_pregame):
            return
        overlay = self.ensure_agent_select_overlay()
        overlay._refresh_agent_grid()
        overlay.preload_agent_images()

    def update_status(self, text: str):
        self.root.after(0, lambda: self.status_label.configure(text=text))

    def update_presence_panel(self, game_state: str, source: str):
        self.current_game_state = game_state
        title = game_state if source != 'none' else 'Waiting for Valorant...'
        self.root.after(0, lambda: self.status_label.configure(text=title))

    def sync_agent_select_from_players(self, players: list):
        if not self.agent_overlay:
            return
        overlay = self.agent_overlay
        local_player = next((player for player in players if player.get('is_local')), None)
        if not local_player:
            return
        agent_id = local_player.get('agent')
        if agent_id:
            self.current_agent_id = agent_id
            self.current_agent_name = self.api.get_agent_name(agent_id)
        selection_state = local_player.get('selection_state')
        self.root.after(0, lambda o=overlay, a=agent_id, s=selection_state: o.sync_from_game(a, s))

    def update_loop(self):
        while self.running:
            try:
                if not self.api.is_game_running() or not self.api.connect():
                    self._set_inactive_state()
                    time.sleep(2)
                    continue
                self._ensure_agent_catalog_loading()
                players, game_state, source, mode_id = self.get_match_players()
                self.current_mode_id = mode_id
                self.update_presence_panel(game_state, source)
                if source == 'pregame':
                    if not self.in_match:
                        self.in_match = True
                        self.auto_show()
                    if not self.in_pregame:
                        self.in_pregame = True
                        self.show_agent_select()
                    self.sync_agent_select_from_players(players)
                    time.sleep(1)
                    continue
                if source == 'coregame':
                    local = next((p for p in players if p.get('is_local')), None)
                    if local and local.get('agent'):
                        self.current_agent_id = local['agent']
                        self.current_agent_name = self.api.get_agent_name(local['agent'])
                    if not self.in_match:
                        self.in_match = True
                        self.auto_show()
                    if self.in_pregame:
                        self.in_pregame = False
                        self.destroy_agent_select()
                    time.sleep(1)
                    continue
                self._set_inactive_state()
                self.root.after(0, self._preload_agent_select_overlay)
                time.sleep(3)
            except Exception as exc:
                self.update_status(f'Error: {str(exc)[:25]}')
                time.sleep(3)

    def _set_inactive_state(self):
        if self.in_match or self.in_pregame:
            self.in_match = False
            self.in_pregame = False
            self.destroy_agent_select()
            self.current_agent_id = None
            self.current_agent_name = None
            self.clove_ult_pending_until = 0.0
            self.clove_ult_pending_score_total = None
            self.clove_ult_detected = False
        if self.visible and (not self.tray_forced_visible):
            self.auto_hide()
        self.update_presence_panel('Menu', 'none')

    def get_match_players(self) -> tuple[list, str, str, str]:
        """Return (players, game_state, source, mode_id) without mutating instance state."""
        coregame = self.api.get_coregame_match()
        if coregame:
            mode = coregame.get('ModeID', 'In-game')
            mode_id = str(mode or '')
            game_state = self._display_game_state(mode)
            players = [{'puuid': player.get('Subject'), 'team': player.get('TeamID'), 'agent': player.get('CharacterID'), 'is_local': player.get('Subject') == self.api.puuid} for player in coregame.get('Players', [])]
            return (players, game_state, 'coregame', mode_id)
        pregame = self.api.get_pregame_match()
        if pregame:
            ally_team = pregame.get('AllyTeam', {}).get('Players', [])
            players = [{'puuid': player.get('Subject'), 'team': 'ally', 'agent': player.get('CharacterID'), 'selection_state': player.get('CharacterSelectionState'), 'is_local': player.get('Subject') == self.api.puuid} for player in ally_team]
            return (players, 'Agent Select', 'pregame', '')
        return ([], 'Menu', 'none', '')

    def _display_game_state(self, mode_id: str) -> str:
        mode = (mode_id or '').lower()
        if 'deathmatch' in mode:
            return 'Deathmatch'
        if 'competitive' in mode:
            return 'Competitive'
        if 'unrated' in mode:
            return 'Unrated'
        return 'In-game'

    def close(self):
        self._log_tailer_stop.set()
        self._remove_tray_icon()
        if self.death_muted or self.manual_muted:
            self.death_muted = False
            self.manual_muted = False
            mute_valorant(False)
        self.running = False
        os._exit(0)

    def run(self):
        signal.signal(signal.SIGINT, lambda *_: self.close())
        self.root.after(200, self._check_signal)
        self.root.mainloop()

    def _check_signal(self):
        self.root.after(200, self._check_signal)
if __name__ == '__main__':
    DecypherOverlay().run()
