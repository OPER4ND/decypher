"""Decypher overlay for Valorant agent-select actions and death muting."""
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from decypher.audio.audio_control import AUDIO_AVAILABLE, MUTE_TARGET_BOTH, MUTE_TARGET_COMMS, MUTE_TARGET_DEFAULT, mute_valorant_target, reset_audio_session_cache
from decypher.audio.death_mute_state import DeathMuteGateState
from decypher.audio.game_log import GameLogTailer
from decypher.audio.mute_state import MuteState
from decypher.app.hotkey_settings import HotkeySettings
from decypher.app.hotkeys import HOTKEY_ACTIONS, event_to_hotkey, format_hotkey, hotkey_is_pressed
from decypher.app.tray_icon import TrayIcon
from decypher.platform.win32_window import WINDOWS, ForegroundProcessTracker, apply_overlay_styles, user32
from decypher.ui.agent_select import _OverlayBase
from decypher.ui.agent_select_coordinator import AgentSelectCoordinator
from decypher.ui.visual_detection import SCREEN_GRAB_AVAILABLE, VisualDeathDetector
from decypher.valorant.presence import get_local_player, get_match_presence, presence_title
from decypher.valorant.valorant_api import ValorantLocalAPI
APP_ICON_RELATIVE_PATH = os.path.join('assets', 'decypher.ico')
DRAGNSCROLL_RELATIVE_PATH = os.path.join('scripts', 'dragnscroll.ahk')
VALORANT_PROCESS_NAME = 'valorant-win64-shipping.exe'
SUPPORTED_MUTE_MODE_KEYWORDS = ('competitive', 'unrated', 'swift', 'swiftplay')

class DecypherOverlay(_OverlayBase):
    HOTKEY_ACTIONS = HOTKEY_ACTIONS

    def __init__(self):
        self.api = ValorantLocalAPI()
        self.api_connection_generation = self.api.connection_generation
        self.running = True
        self.visible = False
        self.tray_forced_visible = False
        self.click_through = False
        self.in_match = False
        self.in_pregame = False
        self.agent_select = None
        self._drag_data = {'x': 0, 'y': 0}
        self.config_path = os.path.join(self._runtime_base_dir(), 'decypher_config.json')
        self.app_icon_path = os.path.join(self._resource_base_dir(), APP_ICON_RELATIVE_PATH)
        self.hotkey_settings = HotkeySettings(self.config_path)
        self.hotkey_widgets = {}
        self.binding_capture = None
        self._hotkey_resume_after = 0.0
        self._closing = False
        self.death_mute_enabled = False
        self.selected_mute_targets = {MUTE_TARGET_DEFAULT, MUTE_TARGET_COMMS}
        self.mute_state = MuteState(mute_func=self._apply_selected_mute_target)
        self.player_dead = False
        self.death_mute_gate = DeathMuteGateState()
        self.live_score_total = None
        self.last_live_score_poll_ts = 0.0
        self.live_score_poll_interval = 0.5
        self.current_mode_id = ''
        self.current_game_state = 'Menu'
        self.current_agent_id = None
        self.current_agent_name = None
        self.visual_detector = VisualDeathDetector()
        self.menu_button_detected = False
        self.last_menu_button_seen_ts = 0.0
        self.dragnscroll_script_path = os.path.join(self._resource_base_dir(), DRAGNSCROLL_RELATIVE_PATH)
        self.dragnscroll_process = None
        self._dragnscroll_last_active = None
        self._dragnscroll_game_running = False
        self._dragnscroll_resolve_failed = False
        self._autohotkey_checked_for_session = False
        self._cached_autohotkey_executable = None
        self._foreground_process_name = None
        self.foreground_tracker = None
        self.window_width = 320
        self._create_root_window()
        self._create_app_services()
        self._build_main_window()
        self._start_background_tasks()
        self._bind_root_events()
        self.root.after(300, self._apply_default_state)

    def _create_root_window(self):
        self.root = tk.Tk()
        self.root.title('DECYPHER')
        self._apply_app_icon()
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.92)
        self.root.overrideredirect(True)
        self.root.configure(bg='#0d1117')
        self.root.geometry(f'{self.window_width}x1+0+50')

    def _create_app_services(self):
        self.tray_icon = TrayIcon(root=self.root, is_visible=lambda: self.visible, is_click_through=lambda: self.click_through, on_toggle_visibility=self._toggle_tray_visibility, on_toggle_click_through=self.toggle_click_through, on_exit=self.close, icon_path=self.app_icon_path)
        self.agent_select = AgentSelectCoordinator(api=self.api, root=self.root, can_preload=self._can_preload_agent_select)
        self.game_log_tailer = GameLogTailer(root=self.root, on_death=self._on_log_death, on_revival=self._on_log_revival, on_clove_ult_window=self._on_log_clove_ult_window, on_clove_ult_used=self._on_log_clove_ult_used)

    def _build_main_window(self):
        self._build_header()
        self._build_footer()
        self._position_main_window()
        self.root.withdraw()

    def _build_header(self):
        self.header = tk.Frame(self.root, bg='#161b22')
        self.header.pack(fill='x')
        title_row = tk.Frame(self.header, bg='#161b22')
        title_row.pack(fill='x', padx=10, pady=8)
        title = tk.Label(title_row, text='DECYPHER', font=(self.FONT_FAMILY, 16, 'bold'), fg='#58a6ff', bg='#161b22')
        title.pack(side='left')
        btn_frame = tk.Frame(title_row, bg='#161b22')
        btn_frame.pack(side='right')
        self.click_through_btn = tk.Label(btn_frame, text='🖱', font=(self.FONT_FAMILY, 11), fg='#8b949e', bg='#161b22', anchor='center', width=2, height=1, cursor='hand2')
        self.click_through_btn.pack(side='left', padx=(0, 4))
        self.click_through_btn.bind('<Button-1>', self.toggle_click_through)
        close_btn = tk.Label(btn_frame, text='X', font=(self.FONT_FAMILY, 12), fg='#8b949e', bg='#161b22', anchor='center', width=2, height=1, cursor='hand2')
        close_btn.pack(side='left', padx=(0, 0))
        close_btn.bind('<Button-1>', lambda _event: self.close())
        close_btn.bind('<Enter>', lambda _event: close_btn.configure(fg='#f85149'))
        close_btn.bind('<Leave>', lambda _event: close_btn.configure(fg='#8b949e'))
        self.status_label = tk.Label(self.header, text='Waiting for Valorant...', font=(self.FONT_FAMILY, 11), fg='#8b949e', bg='#161b22', anchor='center')
        self.status_label.pack(fill='x', padx=10)
        self._bind_drag_widgets(self.header, title_row, title, self.status_label)

    def _bind_drag_widgets(self, *widgets):
        for widget in widgets:
            widget.configure(cursor='fleur')
            widget.bind('<Button-1>', self.on_drag_start)
            widget.bind('<B1-Motion>', self.on_drag_motion)

    def _build_footer(self):
        footer = tk.Frame(self.root, bg='#161b22')
        footer.pack(fill='x', side='bottom')
        hints_frame = tk.Frame(footer, bg='#161b22')
        hints_frame.pack(fill='x', padx=10, pady=(8, 6))
        self._build_hotkey_controls(hints_frame)
        if AUDIO_AVAILABLE:
            self._build_audio_controls(footer)

    def _build_audio_controls(self, footer):
        toggle_frame = tk.Frame(footer, bg='#161b22')
        toggle_frame.pack(fill='x', padx=10, pady=(0, 10))
        self.mute_toggle = tk.Label(toggle_frame, text='[   ] Mute on Death', font=(self.FONT_FAMILY, 11), fg='#c9d1d9', bg='#161b22', cursor='hand2')
        self.mute_toggle.pack(anchor='w')
        self.mute_toggle.bind('<Button-1>', self.toggle_death_mute)
        self.defer_toggle = tk.Label(toggle_frame, text='[   ] Manual mute defers to score change', font=(self.FONT_FAMILY, 11), fg='#c9d1d9', bg='#161b22', cursor='hand2')
        self.defer_toggle.pack(anchor='w')
        self.defer_toggle.bind('<Button-1>', self.toggle_manual_defers_to_auto)
        self.mute_target_label = tk.Label(toggle_frame, text='Mute target: default output, comms output, or both', font=(self.FONT_FAMILY, 10), fg='#8b949e', bg='#161b22')
        self.mute_target_label.pack(anchor='w', pady=(8, 3))
        target_row = tk.Frame(toggle_frame, bg='#161b22')
        target_row.pack(fill='x')
        for column in range(3):
            target_row.grid_columnconfigure(column, weight=1, uniform='mute-target')
        self.mute_target_buttons = {}
        button_specs = [(MUTE_TARGET_DEFAULT, 'Default', self.toggle_default_output_target), (MUTE_TARGET_COMMS, 'Comms Output', self.toggle_comms_output_target), (MUTE_TARGET_BOTH, 'Both', self.toggle_both_output_target)]
        for column, (target, label, command) in enumerate(button_specs):
            button = tk.Label(target_row, text=label, font=(self.FONT_FAMILY, 10, 'bold'), fg='#8b949e', bg='#21262d', padx=8, pady=4, cursor='hand2')
            button.grid(row=0, column=column, sticky='ew', padx=(0 if column == 0 else 4, 0))
            button.bind('<Button-1>', command)
            self.mute_target_buttons[target] = button
        self._refresh_mute_target_buttons()

    def _start_background_tasks(self):
        if WINDOWS:
            self.root.after(100, self._apply_overlay_styles)
            self.root.after(150, self._create_tray_icon)
            self.root.after(150, self._refresh_death_detection_loop)
            self.root.after(200, self._start_foreground_tracker)
            self.root.after(200, self._start_log_tailer)
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        if WINDOWS:
            self.hotkey_thread = threading.Thread(target=self.hotkey_listener, daemon=True)
            self.hotkey_thread.start()

    def _bind_root_events(self):
        self.root.bind('<KeyPress>', self._handle_hotkey_capture)
        self.root.bind('<Escape>', self._handle_escape)

    def _apply_default_state(self):
        if AUDIO_AVAILABLE:
            self.death_mute_gate.auto_death_mute_pending = True
            self._enable_death_mute(force_startup_gate=True)
        self.click_through = True
        self.click_through_btn.configure(fg='#58a6ff')
        self.root.attributes('-alpha', 0.6)
        self._apply_overlay_styles()

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
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    @staticmethod
    def _resource_base_dir() -> str:
        return getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    def _resolve_autohotkey_executable(self) -> str | None:
        if self._autohotkey_checked_for_session:
            return self._cached_autohotkey_executable
        candidates = [shutil.which('AutoHotkey64.exe'), shutil.which('AutoHotkey.exe'), 'C:\\Program Files\\AutoHotkey\\v2\\AutoHotkey64.exe', 'C:\\Program Files\\AutoHotkey\\v2\\AutoHotkey.exe']
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                self._cached_autohotkey_executable = candidate
                self._autohotkey_checked_for_session = True
                return candidate
        self._cached_autohotkey_executable = None
        self._autohotkey_checked_for_session = True
        return None

    def _reset_dragnscroll_session_cache(self):
        self._dragnscroll_resolve_failed = False
        self._autohotkey_checked_for_session = False
        self._cached_autohotkey_executable = None

    def _dragnscroll_gate_state(self) -> tuple[bool, str | None, bool]:
        game_running = self.api.is_game_running()
        if not WINDOWS or not game_running:
            return (game_running, None, False)
        if self.in_match and (not self.in_pregame):
            return (game_running, None, False)
        foreground_process = self._foreground_process_name
        return (game_running, foreground_process, foreground_process == VALORANT_PROCESS_NAME)

    def _start_dragnscroll(self):
        if self.dragnscroll_process and self.dragnscroll_process.poll() is None:
            return
        self.dragnscroll_process = None
        if not os.path.exists(self.dragnscroll_script_path):
            if not self._dragnscroll_resolve_failed:
                self._dragnscroll_resolve_failed = True
            return
        autohotkey_exe = self._resolve_autohotkey_executable()
        if not autohotkey_exe:
            if not self._dragnscroll_resolve_failed:
                self._dragnscroll_resolve_failed = True
            return
        try:
            self.dragnscroll_process = subprocess.Popen([autohotkey_exe, self.dragnscroll_script_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self._dragnscroll_resolve_failed = False
        except Exception as exc:
            self.dragnscroll_process = None
            if not self._dragnscroll_resolve_failed:
                self._dragnscroll_resolve_failed = True

    def _stop_dragnscroll(self):
        process = self.dragnscroll_process
        self.dragnscroll_process = None
        if not process:
            return
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=1.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _sync_dragnscroll(self):
        game_running, foreground_process, should_run = self._dragnscroll_gate_state()
        if game_running != self._dragnscroll_game_running:
            self._dragnscroll_game_running = game_running
            self._reset_dragnscroll_session_cache()
        if should_run:
            self._start_dragnscroll()
        else:
            self._stop_dragnscroll()
        if should_run != self._dragnscroll_last_active:
            self._dragnscroll_last_active = should_run

    def _apply_app_icon(self):
        if not os.path.exists(self.app_icon_path):
            return
        try:
            self.root.iconbitmap(self.app_icon_path)
        except Exception as exc:
            pass

    @property
    def death_muted(self) -> bool:
        return self.mute_state.death_muted

    @death_muted.setter
    def death_muted(self, value: bool):
        self.mute_state.death_muted = value

    @property
    def manual_muted(self) -> bool:
        return self.mute_state.manual_muted

    @manual_muted.setter
    def manual_muted(self, value: bool):
        self.mute_state.manual_override = True if value else None

    @property
    def manual_unmuted(self) -> bool:
        return self.mute_state.manual_unmuted

    @property
    def manual_defers_to_auto(self) -> bool:
        return self.mute_state.manual_defers_to_auto

    @manual_defers_to_auto.setter
    def manual_defers_to_auto(self, value: bool):
        self.mute_state.manual_defers_to_auto = value

    def _apply_selected_mute_target(self, mute: bool) -> bool:
        return mute_valorant_target(self._effective_mute_target(), mute)

    def _effective_mute_target(self) -> str:
        if self.selected_mute_targets == {MUTE_TARGET_DEFAULT, MUTE_TARGET_COMMS}:
            return MUTE_TARGET_BOTH
        if MUTE_TARGET_COMMS in self.selected_mute_targets:
            return MUTE_TARGET_COMMS
        return MUTE_TARGET_DEFAULT

    def _mute_target_log_value(self) -> str:
        if self.selected_mute_targets == {MUTE_TARGET_DEFAULT, MUTE_TARGET_COMMS}:
            return 'default_output+communications_output'
        return next(iter(self.selected_mute_targets))

    def _hotkey(self, name):
        return self.hotkey_settings.get(name)

    def _mute_mode_allowed(self, mode_id: str | None=None, game_state: str | None=None) -> bool:
        mode_key = f'{mode_id or self.current_mode_id} {game_state or self.current_game_state}'.lower()
        return any((keyword in mode_key for keyword in SUPPORTED_MUTE_MODE_KEYWORDS))

    def _main_overlay_allowed(self) -> bool:
        return self.in_match and self._mute_mode_allowed()

    def _set_main_overlay_visibility(self, visible: bool):
        if visible:
            if self.visible:
                return
            self.visible = True
            self.root.after(0, self.root.deiconify)
            return
        if not self.visible:
            return
        self.tray_forced_visible = False
        self.visible = False
        self.root.after(0, self.root.withdraw)

    def _clear_mute_runtime_state(self):
        self._clear_death_mute_gates()
        if self.death_muted or self.mute_state.manual_override is not None:
            self.mute_state.clear_all()

    def _set_hotkey(self, name, hotkey):
        save_error = self.hotkey_settings.set(name, hotkey)
        if save_error:
            pass
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
        key_label = tk.Label(item, text=self._hotkey(name), font=(self.FONT_FAMILY, 10, 'bold'), fg='#0d1117', bg='#8b949e', padx=5, pady=0, width=8, cursor='hand2')
        key_label.pack(side='left')
        action_label = tk.Label(item, text=f' {label}', font=(self.FONT_FAMILY, 10), fg='#8b949e', bg='#161b22', cursor='hand2')
        action_label.pack(side='left')
        self.hotkey_widgets[name] = {'item': item, 'key': key_label, 'action': action_label}
        for widget in (item, key_label, action_label):
            widget.bind('<Button-1>', lambda _event, hotkey_name=name: self._begin_hotkey_capture(hotkey_name))

    def _refresh_hotkey_controls(self):
        for name, widgets in self.hotkey_widgets.items():
            is_active = self.binding_capture == name
            widgets['key'].configure(text='...' if is_active else self._hotkey(name), fg='#0d1117', bg='#d29922' if is_active else '#8b949e')

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
        hotkey = event_to_hotkey(event)
        if hotkey == 'ESC':
            self._cancel_hotkey_capture()
            return 'break'
        hotkey = format_hotkey(hotkey)
        if not hotkey:
            self._flash_hotkey_error(name)
            return 'break'
        if self.hotkey_settings.has_conflict(name, hotkey):
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

    def _create_tray_icon(self):
        self.tray_icon.create()

    def _remove_tray_icon(self):
        self.tray_icon.remove()

    def _start_foreground_tracker(self):
        if not WINDOWS or self.foreground_tracker is not None:
            return
        self.foreground_tracker = ForegroundProcessTracker(self._on_foreground_process_changed)
        self.foreground_tracker.start()

    def _stop_foreground_tracker(self):
        tracker = self.foreground_tracker
        self.foreground_tracker = None
        if tracker:
            tracker.stop()

    def _on_foreground_process_changed(self, process_name: str | None):
        self._foreground_process_name = process_name
        self._request_dragnscroll_sync()

    def _request_dragnscroll_sync(self):
        if self._closing:
            return
        try:
            self.root.after(0, self._sync_dragnscroll)
        except Exception:
            pass

    def _show_from_tray(self):
        if not self._main_overlay_allowed():
            return
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
        if self.binding_capture or not self._mute_mode_allowed():
            return
        self.death_mute_gate.auto_death_mute_pending = False
        if self.death_mute_enabled:
            self._disable_death_mute()
        else:
            self._enable_death_mute()

    def _enable_death_mute(self, force_startup_gate=False):
        gate = self.death_mute_gate
        self.death_mute_enabled = True
        now = time.time()
        gate.mute_armed_ts = now
        menu_recent = self._menu_seen_recently(now)
        needs_startup_gate = bool(force_startup_gate or self.player_dead or menu_recent)
        if needs_startup_gate:
            self._begin_startup_gate()
        else:
            gate.revive_gate = False
            self._clear_startup_gate()
        self.mute_toggle.configure(text='[ X ] Mute on Death', fg='#3fb950')
        if menu_recent:
            pass
        elif force_startup_gate:
            pass
        elif gate.revive_gate:
            pass
        self._refresh_defer_toggle_style()

    def _disable_death_mute(self):
        self.death_mute_gate.auto_death_mute_pending = False
        self.death_mute_enabled = False
        self.mute_toggle.configure(text='[   ] Mute on Death', fg='#c9d1d9')
        if self.death_muted:
            self.mute_state.release_death()
        self._clear_death_mute_gates()
        self._refresh_defer_toggle_style()

    def toggle_manual_mute(self, event=None):
        if self.binding_capture or not self._mute_mode_allowed():
            return
        result = self.mute_state.toggle_manual()
        if not result.changed:
            return
        if result.muted:
            pass
        elif result.unmuted:
            pass

    def toggle_manual_defers_to_auto(self, event=None):
        if not self._mute_mode_allowed():
            return
        enabled = self.mute_state.toggle_manual_defers_to_auto()
        self._refresh_defer_toggle_style()

    def toggle_default_output_target(self, event=None):
        self._toggle_mute_target_selection(MUTE_TARGET_DEFAULT)

    def toggle_comms_output_target(self, event=None):
        self._toggle_mute_target_selection(MUTE_TARGET_COMMS)

    def toggle_both_output_target(self, event=None):
        self._toggle_mute_target_selection(MUTE_TARGET_BOTH)

    def _toggle_mute_target_selection(self, target: str):
        if self.binding_capture:
            return
        next_targets = set(self.selected_mute_targets)
        if target == MUTE_TARGET_BOTH:
            next_targets = {MUTE_TARGET_DEFAULT, MUTE_TARGET_COMMS}
        elif target in next_targets:
            next_targets = {target}
        else:
            next_targets.add(target)
        self._set_mute_target_selection(next_targets)

    def _set_mute_target_selection(self, selected_targets: set[str]):
        normalized = {target for target in selected_targets if target in (MUTE_TARGET_DEFAULT, MUTE_TARGET_COMMS)}
        if not normalized:
            normalized = {MUTE_TARGET_DEFAULT, MUTE_TARGET_COMMS}
        if normalized == self.selected_mute_targets:
            self._refresh_mute_target_buttons()
            return
        self.selected_mute_targets = normalized
        self._refresh_mute_target_buttons()
        self.mute_state.sync_target_mute()
        if self.death_muted:
            gate = self.death_mute_gate
            _ = gate.score_total_at_mute

    def _refresh_mute_target_buttons(self):
        effective = self._effective_mute_target()
        for target, button in self.mute_target_buttons.items():
            active = target == effective if target == MUTE_TARGET_BOTH else target in self.selected_mute_targets
            button.configure(fg='#0d1117' if active else '#8b949e', bg='#58a6ff' if active else '#21262d')

    def _refresh_defer_toggle_style(self):
        checked = self.manual_defers_to_auto
        active = self.death_mute_enabled
        text = '[ X ] Manual mute defers to score change' if checked else '[   ] Manual mute defers to score change'
        if checked:
            fg = '#3fb950' if active else '#2d5c38'
        else:
            fg = '#c9d1d9' if active else '#4a5568'
        self.defer_toggle.configure(text=text, fg=fg)

    def _maybe_clear_deferred_manual(self):
        if self.mute_state.clear_deferred_manual(self.death_mute_enabled):
            pass

    def _clear_startup_gate(self):
        self.death_mute_gate.clear_startup_gate()

    def _begin_startup_gate(self):
        self.death_mute_gate.begin_startup_gate()

    def _clear_clove_ult_wait(self, clear_ready_ts: bool=False):
        self.death_mute_gate.clear_clove_ult_wait(clear_ready_ts)

    def _clear_round_start_gate(self, clear_cooldown: bool=False):
        self.death_mute_gate.clear_round_start_gate(clear_cooldown)

    def _clear_death_mute_gates(self):
        self.death_mute_gate.clear_death_mute_gates()

    def _menu_seen_recently(self, now=None):
        return self.visual_detector.menu_seen_recently(now)

    def _detect_strip_death(self):
        if self.death_muted:
            return
        prev_menu = self.menu_button_detected
        prev_dead = self.player_dead
        detection = self.visual_detector.detect(self.death_mute_enabled)
        self.menu_button_detected = detection.menu_detected
        self.last_menu_button_seen_ts = self.visual_detector.last_menu_button_seen_ts
        self.player_dead = detection.player_dead
        if not detection.window_found:
            return
        if self.menu_button_detected != prev_menu:
            pass
        if self.player_dead != prev_dead:
            pass

    def _start_log_tailer(self):
        self.game_log_tailer.start()

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
        gate = self.death_mute_gate
        gate.clove_ult_detected = False
        self._apply_death_mute(self.in_match and (not self.in_pregame))

    def _on_log_clove_ult_window(self):
        if not self.running:
            return
        now = time.time()
        gate = self.death_mute_gate
        gate.clove_ult_detected = True
        gate.clove_ult_last_ready_ts = now
        self.root.after(3000, self._clear_clove_ult_if_stale)

    def _on_log_clove_ult_used(self):
        if not self.running:
            return
        gate = self.death_mute_gate
        gate.clove_ult_detected = False
        gate.clove_ult_last_ready_ts = 0.0

    def _clear_clove_ult_if_stale(self):
        if not self.running:
            return
        gate = self.death_mute_gate
        if gate.clove_ult_detected and time.time() - gate.clove_ult_last_ready_ts >= 2.5:
            gate.clove_ult_detected = False

    def _refresh_death_detection_loop(self):
        gate = self.death_mute_gate
        if not self.running:
            return
        if not self._mute_mode_allowed():
            self.player_dead = False
            gate.clove_ult_detected = False
            self.menu_button_detected = False
            self.last_menu_button_seen_ts = 0.0
            self.visual_detector.reset()
            self._track_live_score_transition(False)
            self._clear_mute_runtime_state()
            self.root.after(100, self._refresh_death_detection_loop)
            return
        live_match_active = self.in_match and (not self.in_pregame)
        if not WINDOWS or not live_match_active:
            self.player_dead = False
            gate.clove_ult_detected = False
            self.menu_button_detected = False
            self.last_menu_button_seen_ts = 0.0
            self.visual_detector.reset()
            self._track_live_score_transition(False)
            if gate.auto_death_mute_pending and self.death_mute_enabled and (not self.death_muted):
                pass
            else:
                self._apply_death_mute(False)
            self.root.after(100, self._refresh_death_detection_loop)
            return
        if gate.auto_death_mute_pending:
            gate.auto_death_mute_pending = False
            self._begin_startup_gate()
        is_clove = self._is_current_agent_clove()
        if not is_clove:
            self._detect_strip_death()
        now_ts = time.time()
        self._track_live_score_transition(live_match_active)
        self._apply_death_mute(live_match_active)
        self.root.after(250 if not is_clove else 100, self._refresh_death_detection_loop)

    def _poll_score_delta(self, baseline_score):
        gate = self.death_mute_gate
        now = time.time()
        if now - gate.last_score_poll_ts < gate.score_poll_interval_muted:
            return ('wait', baseline_score, None)
        gate.last_score_poll_ts = now
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
        gate = self.death_mute_gate
        now = time.time() if now is None else now
        gate.round_start_cooldown_seconds = gate.extended_round_start_cooldown_seconds if self._uses_extended_buy_phase(previous_score, current_score) else gate.normal_round_start_cooldown_seconds
        gate.round_start_cooldown_until = now + gate.round_start_cooldown_seconds
        gate.round_start_requires_clear = True
        gate.round_start_clear_since = None
        gate.revive_gate = bool(self.player_dead)
        self._maybe_clear_deferred_manual()

    def _is_current_agent_clove(self):
        return (self.current_agent_name or '').lower() == 'clove'

    def _apply_round_start_gate(self, now):
        gate = self.death_mute_gate
        if self.death_muted:
            return False
        if gate.round_start_cooldown_until > now:
            if self.player_dead:
                gate.revive_gate = True
                gate.round_start_clear_since = None
            remaining = max(1, int(gate.round_start_cooldown_until - now))
            if self.player_dead and now - gate.last_cooldown_block_log_ts >= 5.0:
                gate.last_cooldown_block_log_ts = now
            return True
        if gate.round_start_cooldown_until > 0:
            gate.round_start_cooldown_until = 0.0
        if not gate.round_start_requires_clear:
            return False
        if self.player_dead:
            if not gate.revive_gate or gate.round_start_clear_since is not None:
                pass
            gate.revive_gate = True
            gate.round_start_clear_since = None
            return True
        gate.revive_gate = False
        if gate.round_start_clear_since is None:
            gate.round_start_clear_since = now
            return True
        clear_for = now - gate.round_start_clear_since
        if clear_for < gate.round_start_clear_seconds:
            return True
        self._clear_round_start_gate()
        gate.revive_gate = False
        return True

    def _apply_clove_ult_gate(self, now):
        gate = self.death_mute_gate
        if gate.clove_ult_pending_until <= 0:
            return False
        score_status, baseline_score, current_score = self._poll_score_delta(gate.clove_ult_pending_score_total)
        if score_status == 'baseline':
            gate.clove_ult_pending_score_total = baseline_score
        elif score_status == 'changed':
            self._clear_clove_ult_wait()
            self._begin_round_start_cooldown(now, baseline_score, current_score)
            return True
        if not self.player_dead:
            self._clear_clove_ult_wait(clear_ready_ts=True)
            gate.mute_armed_ts = 0.0
            return True
        if now < gate.clove_ult_pending_until:
            return True
        self._clear_clove_ult_wait()
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

    def _apply_death_mute(self, live_match_active):
        if not AUDIO_AVAILABLE or not self.death_mute_enabled:
            return
        if not live_match_active:
            self._on_match_end()
            return
        now = time.time()
        gate = self.death_mute_gate
        if gate.startup_revive_gate:
            self._handle_startup_gate(now)
            return
        if self._apply_round_start_gate(now):
            return
        if self._apply_clove_ult_gate(now):
            return
        if self.player_dead and (not self.death_muted):
            self._on_death_trigger(now)
            return
        if not self.player_dead and gate.revive_gate:
            self._on_revive_clear()
            return
        if self.death_muted:
            self._on_muted_poll()

    def _on_match_end(self):
        self._clear_death_mute_gates()
        self._maybe_clear_deferred_manual()
        if self.death_muted and self.mute_state.release_death() > 0:
            self._begin_round_start_cooldown()

    def _handle_startup_gate(self, now):
        gate = self.death_mute_gate
        score_status, baseline_score, current_score = self._poll_score_delta(gate.startup_score_baseline)
        if not self.player_dead:
            if self._menu_seen_recently(now):
                gate.startup_revival_since = None
                return
            if gate.startup_revival_since is None:
                gate.startup_revival_since = now
            clear_for = now - gate.startup_revival_since
            if clear_for >= gate.startup_revival_seconds:
                self._clear_startup_gate()
                gate.revive_gate = False
                gate.mute_armed_ts = 0.0
            return
        gate.startup_revival_since = None
        if score_status == 'wait':
            return
        if score_status == 'baseline':
            gate.startup_score_baseline = baseline_score
            if current_score is not None:
                pass
            return
        if score_status == 'changed':
            self._clear_startup_gate()
            self._begin_round_start_cooldown(now, baseline_score, current_score)
            gate.mute_armed_ts = 0.0

    def _on_death_trigger(self, now):
        gate = self.death_mute_gate
        current_score = self.api.get_round_score_total()
        if current_score is not None and self.live_score_total is not None and (current_score != self.live_score_total):
            previous_score = self.live_score_total
            self.live_score_total = current_score
            self._begin_round_start_cooldown(now, previous_score, current_score)
            return
        if gate.revive_gate:
            return
        if gate.mute_armed_ts > 0 and now - gate.mute_armed_ts <= gate.mute_arm_grace_seconds:
            self._begin_startup_gate()
            self._clear_round_start_gate(clear_cooldown=True)
            return
        clove_ult_recently_ready = gate.clove_ult_detected or now - gate.clove_ult_last_ready_ts <= gate.clove_ult_ready_grace_seconds
        if self._is_current_agent_clove() and clove_ult_recently_ready:
            gate.clove_ult_pending_until = now + gate.clove_ult_pending_seconds
            gate.clove_ult_pending_score_total = current_score
            gate.last_score_poll_ts = 0.0
            return
        if self.mute_state.engage_death() > 0:
            gate.mute_armed_ts = 0.0
            gate.score_total_at_mute = self.api.get_round_score_total()
            gate.last_score_poll_ts = time.time()

    def _on_revive_clear(self):
        gate = self.death_mute_gate
        gate.revive_gate = False
        gate.mute_armed_ts = 0.0
        if not self.death_muted:
            pass

    def _on_muted_poll(self):
        gate = self.death_mute_gate
        score_status, baseline_score, current_score = self._poll_score_delta(gate.score_total_at_mute)
        if score_status == 'wait':
            return
        if score_status == 'baseline':
            gate.score_total_at_mute = baseline_score
            if current_score is not None:
                pass
            return
        if score_status == 'changed':
            self.player_dead = False
            self._begin_round_start_cooldown(previous_score=baseline_score, current_score=current_score)
            if self.mute_state.release_death() <= 0:
                return
            gate.score_total_at_mute = None
            gate.mute_armed_ts = 0.0

    def toggle_visibility(self):
        if self.binding_capture:
            return
        if not self.visible and (not self._main_overlay_allowed()):
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
        apply_overlay_styles(self.root, click_through=self.click_through, allow_activate=bool(self.binding_capture))

    def hotkey_listener(self):
        if not WINDOWS:
            return
        user32_local = user32
        while self.running:
            try:
                if self.binding_capture or time.time() < self._hotkey_resume_after:
                    time.sleep(0.05)
                    continue
                fired = False
                if hotkey_is_pressed(self._hotkey('hide_show'), user32_local):
                    self.root.after(0, self.toggle_visibility)
                    fired = True
                if hotkey_is_pressed(self._hotkey('click_through'), user32_local):
                    self.root.after(0, self.toggle_click_through)
                    fired = True
                if AUDIO_AVAILABLE and self._mute_mode_allowed() and hotkey_is_pressed(self._hotkey('mute_on_death'), user32_local):
                    self.root.after(0, self.toggle_death_mute)
                    fired = True
                if AUDIO_AVAILABLE and self._mute_mode_allowed() and hotkey_is_pressed(self._hotkey('manual_mute'), user32_local):
                    self.root.after(0, self.toggle_manual_mute)
                    fired = True
                time.sleep(0.3 if fired else 0.05)
            except Exception:
                pass

    def auto_show(self):
        if self._main_overlay_allowed():
            self._set_main_overlay_visibility(True)

    def auto_hide(self):
        self._set_main_overlay_visibility(False)

    def _can_preload_agent_select(self):
        return not (self.in_match and (not self.in_pregame))

    def update_status(self, text: str):
        self.root.after(0, lambda: self.status_label.configure(text=text))

    def update_presence_panel(self, game_state: str, source: str):
        self.current_game_state = game_state
        title = presence_title(game_state, source)
        self.root.after(0, lambda: self.status_label.configure(text=title))

    def _sync_audio_cache_with_api_connection(self):
        generation = self.api.connection_generation
        if generation == self.api_connection_generation:
            return
        self.api_connection_generation = generation
        reset_audio_session_cache()

    def update_loop(self):
        while self.running:
            try:
                if not self.api.is_game_running() or not self.api.connect():
                    self._set_inactive_state()
                    time.sleep(2)
                    continue
                self._sync_audio_cache_with_api_connection()
                self.agent_select.ensure_catalog_loading()
                presence = get_match_presence(self.api)
                self.current_mode_id = presence.mode_id
                self.update_presence_panel(presence.game_state, presence.source)
                mute_mode_allowed = self._mute_mode_allowed(presence.mode_id, presence.game_state)
                if presence.source == 'pregame':
                    if not self.in_match:
                        self.in_match = True
                    if mute_mode_allowed:
                        self.auto_show()
                    else:
                        self.auto_hide()
                    if not self.in_pregame:
                        self.in_pregame = True
                        self.agent_select.show()
                    selection = self.agent_select.sync_from_players(presence.players)
                    if selection and selection.agent_id:
                        self.current_agent_id = selection.agent_id
                        self.current_agent_name = selection.agent_name
                    self._request_dragnscroll_sync()
                    time.sleep(1)
                    continue
                if presence.source == 'coregame':
                    local = get_local_player(presence.players)
                    if local and local.get('agent'):
                        self.current_agent_id = local['agent']
                        self.current_agent_name = self.api.get_agent_name(local['agent'])
                    if not self.in_match:
                        self.in_match = True
                    if mute_mode_allowed:
                        self.auto_show()
                    else:
                        self.auto_hide()
                    if self.in_pregame:
                        self.in_pregame = False
                        self.agent_select.destroy()
                    self._request_dragnscroll_sync()
                    time.sleep(1)
                    continue
                self._set_inactive_state()
                self.root.after(0, self.agent_select.preload_if_allowed)
                time.sleep(3)
            except Exception as exc:
                self.update_status(f'Error: {str(exc)[:25]}')
                time.sleep(3)

    def _set_inactive_state(self):
        self._stop_dragnscroll()
        if self.in_match or self.in_pregame:
            self.in_match = False
            self.in_pregame = False
            self.agent_select.destroy()
            self.current_agent_id = None
            self.current_agent_name = None
            gate = self.death_mute_gate
            gate.clove_ult_pending_until = 0.0
            gate.clove_ult_pending_score_total = None
            gate.clove_ult_detected = False
        if self.visible and (not self.tray_forced_visible):
            self.auto_hide()
        self.update_presence_panel('Menu', 'none')
        self._request_dragnscroll_sync()

    def _finalize_close(self):
        self._stop_dragnscroll()
        self._stop_foreground_tracker()
        self.game_log_tailer.stop()
        self.agent_select.destroy()
        self._remove_tray_icon()
        if self.death_muted or self.mute_state.manual_override is not None:
            self.mute_state.clear_all()
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def close(self):
        if self._closing:
            return
        self._closing = True
        self.running = False
        try:
            self.root.after(0, self._finalize_close)
        except Exception:
            self._finalize_close()

    def run(self):
        signal.signal(signal.SIGINT, lambda *_: self.close())
        self.root.after(200, self._check_signal)
        self.root.mainloop()

    def _check_signal(self):
        if self.running and (not self._closing):
            self.root.after(200, self._check_signal)
if __name__ == '__main__':
    DecypherOverlay().run()
