"""Decypher overlay for Valorant agent-select actions and death muting."""
import json
import os
import re
import signal
import sys
import threading
import time
import tkinter as tk
from agent_select import AgentSelectOverlay, _OverlayBase
from hotkeys import DEFAULT_HOTKEYS, HOTKEY_ACTIONS, event_to_hotkey, format_hotkey, hotkey_is_pressed, normalize_hotkey
from tray_icon import TrayIcon
from valorant_api import AUDIO_AVAILABLE, ValorantLocalAPI, mute_valorant
from visual_detection import SCREEN_GRAB_AVAILABLE, VisualDeathDetector
from win32_window import WINDOWS, apply_overlay_styles, apply_passthrough_toolwindow, user32
_SHOOTER_GAME_LOG = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'VALORANT', 'Saved', 'Logs', 'ShooterGame.log')
_LOG_DEATH_RE = re.compile('LogPlayerController:.*AcknowledgePossession\\([\'\\"]?.+_PostDeath_')
_LOG_REVIVAL_RE = re.compile('LogPlayerController:.*ClientRestart_Implementation.+_PostDeath_')
_LOG_CLOVE_ULT_WINDOW_RE = re.compile('LogAbilitySystem:.*ReactiveRes_InDeathCastWindow_C')
_LOG_CLOVE_ULT_USED_RE = re.compile('LogAbilitySystem:.*DelayDeathUltPointReward_C')

class DecypherOverlay(_OverlayBase):
    DEFAULT_HOTKEYS = DEFAULT_HOTKEYS
    HOTKEY_ACTIONS = HOTKEY_ACTIONS

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
        self.tray_icon = TrayIcon(root=self.root, is_visible=lambda: self.visible, is_click_through=lambda: self.click_through, on_toggle_visibility=self._toggle_tray_visibility, on_toggle_click_through=self.toggle_click_through, on_exit=self.close)
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
        close_btn = tk.Label(btn_frame, text='X', font=(self.FONT_FAMILY, 13), fg='#8b949e', bg='#161b22', cursor='hand2')
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
            self.mute_toggle.pack(anchor='w')
            self.mute_toggle.bind('<Button-1>', self.toggle_death_mute)
            self.mute_status = tk.Label(toggle_frame, text='disabled', font=(self.FONT_FAMILY, 10), fg='#6e7681', bg='#161b22')
            self.defer_toggle = tk.Label(toggle_frame, text='[   ] Manual defers to round', font=(self.FONT_FAMILY, 11), fg='#c9d1d9', bg='#161b22', cursor='hand2')
            self.defer_toggle.pack(anchor='w')
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
        self.mute_toggle.configure(text='[ X ] Mute on Death', fg='#3fb950')
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
                hotkeys[name] = normalize_hotkey(config.get(name), fallback)
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

    def _create_tray_icon(self):
        self.tray_icon.create()

    def _remove_tray_icon(self):
        self.tray_icon.remove()

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
            self.mute_toggle.configure(text='[ X ] Mute on Death', fg='#3fb950')
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
        text = '[ X ] Manual defers to round' if checked else '[   ] Manual defers to round'
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
        apply_passthrough_toolwindow(win)

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
                if hotkey_is_pressed(self.hide_show_hotkey, user32_local):
                    self.root.after(0, self.toggle_visibility)
                    fired = True
                if hotkey_is_pressed(self.click_through_hotkey, user32_local):
                    self.root.after(0, self.toggle_click_through)
                    fired = True
                if AUDIO_AVAILABLE and hotkey_is_pressed(self.mute_on_death_hotkey, user32_local):
                    self.root.after(0, self.toggle_death_mute)
                    fired = True
                if AUDIO_AVAILABLE and hotkey_is_pressed(self.manual_mute_hotkey, user32_local):
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
