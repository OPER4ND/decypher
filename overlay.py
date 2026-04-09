"""
Decypher Overlay - Lightweight transparent overlay for Valorant
Shows hidden IGNs in a small always-on-top window
"""
import tkinter as tk
import threading
import time
import webbrowser
import urllib.parse
import urllib.request
import io
from valorant_api import ValorantLocalAPI, mute_valorant, is_valorant_muted, AUDIO_AVAILABLE
from agent_select import AgentSelectOverlay
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
try:
    import ctypes
    WINDOWS = True
except:
    WINDOWS = False
WS_EX_TRANSPARENT = 32
WS_EX_TOOLWINDOW = 128
WS_EX_NOACTIVATE = 134217728
GWL_EXSTYLE = -20

class DecypherOverlay:
    RANK_TIERS = {'Unranked': 0, 'Iron 1': 3, 'Iron 2': 4, 'Iron 3': 5, 'Bronze 1': 6, 'Bronze 2': 7, 'Bronze 3': 8, 'Silver 1': 9, 'Silver 2': 10, 'Silver 3': 11, 'Gold 1': 12, 'Gold 2': 13, 'Gold 3': 14, 'Platinum 1': 15, 'Platinum 2': 16, 'Platinum 3': 17, 'Diamond 1': 18, 'Diamond 2': 19, 'Diamond 3': 20, 'Ascendant 1': 21, 'Ascendant 2': 22, 'Ascendant 3': 23, 'Immortal 1': 24, 'Immortal 2': 25, 'Immortal 3': 26, 'Radiant': 27}
    COMP_TIER_UUID = '03621f52-342b-cf4e-4f86-9350a49c6d04'
    PARTY_COLORS = ['#f97316', '#22c55e', '#a855f7', '#eab308', '#06b6d4']

    def __init__(self):
        self.api = ValorantLocalAPI()
        self.rank_icons = {}
        self.running = True
        self.visible = False
        self.click_through = False
        self.player_data = {}
        self._drag_data = {'x': 0, 'y': 0}
        self.in_match = False
        self.in_pregame = False
        self.agent_overlay = None
        self.current_match_id = None
        self.death_mute_enabled = False
        self.muted_by_us = False
        self.last_death_count = None
        self.last_round_score_total = None
        self.root = tk.Tk()
        self.root.title('Decypher')
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.92)
        self.root.overrideredirect(True)
        self.root.configure(bg='#0d1117')
        window_width = 320
        window_height = 700
        screen_width = self.root.winfo_screenwidth()
        x_pos = screen_width - window_width - 20
        y_pos = 50
        self.root.geometry(f'{window_width}x{window_height}+{x_pos}+{y_pos}')
        self.header = tk.Frame(self.root, bg='#161b22')
        self.header.pack(fill='x')
        title_row = tk.Frame(self.header, bg='#161b22')
        title_row.pack(fill='x', padx=10, pady=8)
        title = tk.Label(title_row, text='DECYPHER', font=('Segoe UI', 12, 'bold'), fg='#58a6ff', bg='#161b22')
        title.pack(side='left')
        btn_frame = tk.Frame(title_row, bg='#161b22')
        btn_frame.pack(side='right')
        self.pin_btn = tk.Label(btn_frame, text='📌', font=('Segoe UI', 10), fg='#8b949e', bg='#161b22', cursor='hand2')
        self.pin_btn.pack(side='left', padx=4)
        self.pin_btn.bind('<Button-1>', self.toggle_click_through)
        close_btn = tk.Label(btn_frame, text='✕', font=('Segoe UI', 11), fg='#8b949e', bg='#161b22', cursor='hand2')
        close_btn.pack(side='left', padx=4)
        close_btn.bind('<Button-1>', lambda e: self.close())
        close_btn.bind('<Enter>', lambda e: close_btn.configure(fg='#f85149'))
        close_btn.bind('<Leave>', lambda e: close_btn.configure(fg='#8b949e'))
        self.status_label = tk.Label(self.header, text='Waiting for Valorant...', font=('Segoe UI', 9), fg='#8b949e', bg='#161b22')
        self.status_label.pack(anchor='w', padx=10)
        for w in [self.header, title_row, title, self.status_label]:
            w.configure(cursor='fleur')
            w.bind('<Button-1>', self.on_drag_start)
            w.bind('<B1-Motion>', self.on_drag_motion)
        self.player_frame = tk.Frame(self.root, bg='#0d1117')
        self.player_frame.pack(fill='both', expand=True, padx=10, pady=(10, 5))
        footer = tk.Frame(self.root, bg='#161b22')
        footer.pack(fill='x', side='bottom')
        hints_frame = tk.Frame(footer, bg='#161b22')
        hints_frame.pack(fill='x', padx=10, pady=(6, 4))
        hint1 = tk.Label(hints_frame, text='Click name → Tracker.gg', font=('Segoe UI', 8), fg='#8b949e', bg='#161b22')
        hint1.pack(anchor='w')
        hint2 = tk.Label(hints_frame, text='F2: Hide/Show  |  F3: Click-through', font=('Segoe UI', 8), fg='#8b949e', bg='#161b22')
        hint2.pack(anchor='w')
        if AUDIO_AVAILABLE:
            sep = tk.Frame(footer, bg='#30363d', height=1)
            sep.pack(fill='x', padx=10, pady=4)
            toggle_frame = tk.Frame(footer, bg='#161b22')
            toggle_frame.pack(fill='x', padx=10, pady=(0, 8))
            self.mute_toggle = tk.Label(toggle_frame, text='[ ] Mute on Death', font=('Consolas', 9), fg='#c9d1d9', bg='#161b22', cursor='hand2')
            self.mute_toggle.pack(anchor='w')
            self.mute_toggle.bind('<Button-1>', self.toggle_death_mute)
            self.mute_status = tk.Label(toggle_frame, text='disabled', font=('Segoe UI', 8), fg='#6e7681', bg='#161b22')
            self.mute_status.pack(anchor='w', padx=(28, 0))
        self.root.withdraw()
        if WINDOWS:
            self.root.after(100, self._apply_overlay_styles)
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        if WINDOWS:
            self.hotkey_thread = threading.Thread(target=self.hotkey_listener, daemon=True)
            self.hotkey_thread.start()
        self.root.bind('<F2>', lambda e: self.toggle_visibility())
        self.root.bind('<F3>', lambda e: self.toggle_click_through())
        self.root.bind('<Escape>', lambda e: self.close())

    def toggle_death_mute(self, event=None):
        """Toggle immediate mute mode (API-independent fallback)."""
        self.death_mute_enabled = not self.death_mute_enabled
        if self.death_mute_enabled:
            self.mute_toggle.configure(text='[x] Mute on Death', fg='#3fb950')
            mute_valorant(True)
            self.muted_by_us = True
            self.mute_status.configure(text='muted (manual fallback)', fg='#3fb950')
            self.last_death_count = None
            self.last_round_score_total = None
        else:
            self.mute_toggle.configure(text='[ ] Mute on Death', fg='#c9d1d9')
            self.mute_status.configure(text='disabled', fg='#6e7681')
            if self.muted_by_us:
                mute_valorant(False)
                self.muted_by_us = False
            self.last_death_count = None
            self.last_round_score_total = None

    def check_death_mute(self, game_state: str):
        """Legacy auto-mute path disabled while live death endpoint is unavailable."""
        if not self.death_mute_enabled or not AUDIO_AVAILABLE:
            return
        muted_now = is_valorant_muted()
        if muted_now != self.muted_by_us:
            self.muted_by_us = muted_now
            status = 'muted (manual fallback)' if muted_now else 'enabled (manual fallback)'
            color = '#3fb950' if muted_now else '#d29922'
            self.root.after(0, lambda: self.mute_status.configure(text=status, fg=color))

    def _split_players(self, players: list, game_state: str) -> tuple[list, list]:
        """Split players into allies/enemies with robust fallbacks for varying TeamID formats."""
        if not players:
            return ([], [])
        local_player = next((p for p in players if p.get('is_local')), None)
        local_team = str(local_player.get('team') or '').strip().lower() if local_player else ''
        if game_state == 'Deathmatch':
            allies = [p for p in players if p.get('is_local')]
            if not allies and players:
                allies = [players[0]]
            enemies = [p for p in players if p not in allies]
            return (allies, enemies)
        normalized_groups = {}
        for p in players:
            team_key = str(p.get('team') or '').strip().lower()
            normalized_groups.setdefault(team_key, []).append(p)
        non_empty_team_keys = [k for k in normalized_groups.keys() if k]
        if local_team:
            allies = [p for p in players if str(p.get('team') or '').strip().lower() == local_team]
            enemies = [p for p in players if p not in allies]
            return (allies, enemies)
        if len(non_empty_team_keys) == 2:
            team_a, team_b = non_empty_team_keys
            allies = normalized_groups[team_a]
            enemies = normalized_groups[team_b]
            if team_b in {'blue', 'ally', 'allies', 'teamone', 'team1'}:
                allies, enemies = (enemies, allies)
            return (allies, enemies)
        allies = []
        enemies = []
        for p in players:
            team = str(p.get('team') or '').strip().lower()
            if team in {'ally', 'blue', 'allies', 'teamone', 'team1'}:
                allies.append(p)
            elif team:
                enemies.append(p)
            else:
                allies.append(p)
        return (allies, enemies)

    def on_drag_start(self, event):
        self._drag_data['x'] = event.x_root - self.root.winfo_x()
        self._drag_data['y'] = event.y_root - self.root.winfo_y()

    def on_drag_motion(self, event):
        x = event.x_root - self._drag_data['x']
        y = event.y_root - self._drag_data['y']
        self.root.geometry(f'+{x}+{y}')

    def toggle_visibility(self):
        if not self.visible and (not self.in_match):
            return
        self.visible = not self.visible
        if self.visible:
            self.root.deiconify()
        else:
            self.root.withdraw()

    def toggle_click_through(self, event=None):
        self.click_through = not self.click_through
        if self.click_through:
            self.pin_btn.configure(fg='#58a6ff')
            self.root.attributes('-alpha', 0.6)
        else:
            self.pin_btn.configure(fg='#8b949e')
            self.root.attributes('-alpha', 0.92)
        self._apply_overlay_styles()

    def _apply_overlay_styles(self):
        """Keep overlay from taking focus, and optionally pass mouse through."""
        if not WINDOWS:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            if self.click_through:
                style |= WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except:
            pass

    def hotkey_listener(self):
        if not WINDOWS:
            return
        user32 = ctypes.windll.user32
        while self.running:
            try:
                if user32.GetAsyncKeyState(113) & 32768:
                    self.root.after(0, self.toggle_visibility)
                    time.sleep(0.3)
                if user32.GetAsyncKeyState(114) & 32768:
                    self.root.after(0, self.toggle_click_through)
                    time.sleep(0.3)
                time.sleep(0.05)
            except:
                pass

    def auto_show(self):
        if not self.visible:
            self.visible = True
            self.root.after(0, self.root.deiconify)
            self.root.after(30, self._apply_overlay_styles)

    def auto_hide(self):
        if self.visible and (not self.click_through):
            self.visible = False
            self.root.after(0, self.root.withdraw)

    def show_agent_select(self):
        if self.agent_overlay is None:
            self.agent_overlay = AgentSelectOverlay(self.api)
        self.root.after(0, self.agent_overlay.show)

    def hide_agent_select(self):
        if self.agent_overlay:
            self.root.after(0, self.agent_overlay.hide)

    def clear_players(self):
        for widget in self.player_frame.winfo_children():
            widget.destroy()

    def add_team_header(self, text: str, is_enemy: bool=False):
        header_frame = tk.Frame(self.player_frame, bg='#0d1117')
        header_frame.pack(fill='x', pady=(10, 4))
        color = '#f85149' if is_enemy else '#58a6ff'
        label = tk.Label(header_frame, text=text, font=('Segoe UI', 9, 'bold'), fg=color, bg='#0d1117', anchor='w')
        label.pack(side='left', padx=(10, 0))
        peak_header = tk.Label(header_frame, text='PEAK', font=('Segoe UI', 7), fg='#8b949e', bg='#0d1117', width=6)
        peak_header.pack(side='right', padx=(0, 14))
        current_header = tk.Label(header_frame, text='CURRENT', font=('Segoe UI', 7), fg='#8b949e', bg='#0d1117', width=8)
        current_header.pack(side='right', padx=(0, 6))

    def add_player(self, puuid: str, name: str, current_rank: str, peak_rank: str, is_local: bool=False, party_color: str=None):
        frame = tk.Frame(self.player_frame, bg='#161b22', cursor='hand2')
        frame.pack(fill='x', pady=1)
        self.player_data[puuid] = {'name': name, 'current': current_rank, 'peak': peak_rank}
        if party_color:
            party_bar = tk.Frame(frame, bg=party_color, width=4)
            party_bar.pack(side='left', fill='y')
            party_bar.pack_propagate(False)
        name_color = '#58a6ff' if is_local else '#c9d1d9'
        name_label = tk.Label(frame, text=name, font=('Segoe UI', 9), fg=name_color, bg='#161b22', anchor='w', cursor='hand2')
        name_label.pack(side='left', padx=(10 if not party_color else 6, 0), pady=3)
        peak_label = tk.Label(frame, bg='#161b22', width=24, height=24)
        peak_label.pack(side='right', padx=(0, 10), pady=3)
        self._set_rank_icon(peak_label, peak_rank)
        current_label = tk.Label(frame, bg='#161b22', width=24, height=24)
        current_label.pack(side='right', padx=(0, 16), pady=3)
        self._set_rank_icon(current_label, current_rank)
        widgets = [frame, name_label, current_label, peak_label]

        def on_enter(e):
            for w in widgets:
                w.configure(bg='#21262d')

        def on_leave(e):
            for w in widgets:
                w.configure(bg='#161b22')
        for w in [frame, name_label]:
            w.bind('<Enter>', on_enter)
            w.bind('<Leave>', on_leave)
            w.bind('<Button-1>', lambda e, n=name: self.open_tracker_profile(n))

    def _set_rank_icon(self, label, rank_name: str):
        """Set rank icon on label, loading async if needed"""
        if not PIL_AVAILABLE:
            label.configure(text=rank_name[:3], font=('Segoe UI', 7), fg=self.get_rank_color(rank_name))
            return
        tier = self.RANK_TIERS.get(rank_name, 0)
        if tier in self.rank_icons:
            label.configure(image=self.rank_icons[tier], width=24, height=24)
            label.image = self.rank_icons[tier]
        else:

            def load():
                try:
                    url = f'https://media.valorant-api.com/competitivetiers/{self.COMP_TIER_UUID}/{tier}/smallicon.png'
                    with urllib.request.urlopen(url, timeout=5) as resp:
                        data = resp.read()
                        img = Image.open(io.BytesIO(data)).resize((24, 24), Image.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        self.rank_icons[tier] = photo
                        self.root.after(0, lambda: self._apply_icon(label, photo))
                except:
                    pass
            threading.Thread(target=load, daemon=True).start()

    def _apply_icon(self, label, photo):
        try:
            label.configure(image=photo, width=24, height=24)
            label.image = photo
        except:
            pass

    def get_rank_color(self, rank: str) -> str:
        r = rank.lower()
        if 'radiant' in r:
            return '#fffb8a'
        if 'immortal' in r:
            return '#ff5551'
        if 'ascendant' in r:
            return '#3fb950'
        if 'diamond' in r:
            return '#a78bfa'
        if 'platinum' in r:
            return '#22d3ee'
        if 'gold' in r:
            return '#fbbf24'
        if 'silver' in r:
            return '#9ca3af'
        if 'bronze' in r:
            return '#d97706'
        if 'iron' in r:
            return '#78716c'
        return '#8b949e'

    def open_tracker_profile(self, name: str):
        if '#' in name:
            g, t = name.split('#', 1)
            url = f'https://tracker.gg/valorant/profile/riot/{urllib.parse.quote(g)}%23{urllib.parse.quote(t)}/overview'
            webbrowser.open(url)

    def update_status(self, text: str):
        self.root.after(0, lambda: self.status_label.configure(text=text))

    def update_display(self, players: list, names: dict, current_ranks: dict, peak_ranks: dict, parties: dict, game_state: str):

        def update():
            self.status_label.configure(text=game_state)
            self.clear_players()
            allies, enemies = self._split_players(players, game_state)
            party_color_map = {}
            party_counts = {}
            for puuid, party_id in parties.items():
                party_counts[party_id] = party_counts.get(party_id, 0) + 1
            color_idx = 0
            for party_id, count in party_counts.items():
                if count >= 2:
                    party_color_map[party_id] = self.PARTY_COLORS[color_idx % len(self.PARTY_COLORS)]
                    color_idx += 1

            def get_party_color(puuid):
                party_id = parties.get(puuid)
                if party_id:
                    return party_color_map.get(party_id)
                return None
            if game_state == 'Deathmatch' and len(allies) == 1:
                self.add_team_header('YOU', is_enemy=False)
                for p in allies:
                    puuid = p.get('puuid')
                    self.add_player(puuid, names.get(puuid, 'Unknown'), current_ranks.get(puuid, '?'), peak_ranks.get(puuid, '-'), True, None)
                self.add_team_header('ENEMIES', is_enemy=True)
                for p in enemies:
                    puuid = p.get('puuid')
                    self.add_player(puuid, names.get(puuid, 'Unknown'), current_ranks.get(puuid, '?'), peak_ranks.get(puuid, '-'), False, get_party_color(puuid))
            else:
                if allies:
                    self.add_team_header('YOUR TEAM', is_enemy=False)
                    for p in allies:
                        puuid = p.get('puuid')
                        self.add_player(puuid, names.get(puuid, 'Unknown'), current_ranks.get(puuid, '?'), peak_ranks.get(puuid, '-'), p.get('is_local', False), get_party_color(puuid))
                if enemies:
                    self.add_team_header('ENEMY TEAM', is_enemy=True)
                    for p in enemies:
                        puuid = p.get('puuid')
                        self.add_player(puuid, names.get(puuid, 'Unknown'), current_ranks.get(puuid, '?'), peak_ranks.get(puuid, '-'), False, get_party_color(puuid))
                elif allies and len(allies) >= 8:
                    self.status_label.configure(text=f'{game_state} (team data limited)')
        self.root.after(0, update)

    def update_loop(self):
        last_players = []
        print('[DEBUG] update_loop entering main cycle')
        while self.running:
            try:
                if not self.api.is_game_running():
                    print('[DEBUG] Valorant not running / lockfile missing')
                    if self.in_match or self.visible:
                        self.in_match = False
                        self.in_pregame = False
                        self.auto_hide()
                        self.hide_agent_select()
                    time.sleep(2)
                    continue
                if not self.api.connect():
                    print('[DEBUG] Failed to connect to local API')
                    if self.in_match or self.visible:
                        self.in_match = False
                        self.in_pregame = False
                        self.auto_hide()
                        self.hide_agent_select()
                    time.sleep(2)
                    continue
                print('[DEBUG] Connected to local API')
                players, game_state = self.get_match_players()
                print(f'[DEBUG] match players count={len(players)} game_state={game_state}')
                self.check_death_mute(game_state)
                if not players:
                    print('[DEBUG] no players detected; overlay stays hidden')
                    if self.in_match or self.visible:
                        self.in_match = False
                        self.in_pregame = False
                        self.auto_hide()
                        self.hide_agent_select()
                    time.sleep(3)
                    continue
                if not self.in_match:
                    self.in_match = True
                    self.auto_show()
                is_pregame = game_state == 'Agent Select'
                if is_pregame and (not self.in_pregame):
                    self.in_pregame = True
                    self.show_agent_select()
                elif not is_pregame and self.in_pregame:
                    self.in_pregame = False
                    self.hide_agent_select()
                current_puuids = sorted([p['puuid'] for p in players])
                if current_puuids != last_players:
                    last_players = current_puuids
                    puuids = [p['puuid'] for p in players]
                    names = self.api.get_player_names(puuids)
                    current_ranks, peak_ranks = self.api.get_player_ranks(puuids)
                    parties = self.api.get_party_members()
                    self.update_display(players, names, current_ranks, peak_ranks, parties, game_state)
                time.sleep(1)
            except Exception as e:
                self.update_status(f'Error: {str(e)[:25]}')
                time.sleep(3)

    def get_match_players(self) -> tuple[list, str]:
        players = []
        game_state = 'Menu'
        coregame = self.api.get_coregame_match()
        if coregame:
            self.current_match_id = coregame.get('MatchID')
            game_state = coregame.get('ModeID', 'In Game')
            if 'deathmatch' in game_state.lower():
                game_state = 'Deathmatch'
            elif 'competitive' in game_state.lower():
                game_state = 'Competitive'
            elif 'unrated' in game_state.lower():
                game_state = 'Unrated'
            else:
                game_state = 'In Game'
            for player in coregame.get('Players', []):
                players.append({'puuid': player.get('Subject'), 'team': player.get('TeamID'), 'agent': player.get('CharacterID'), 'is_local': player.get('Subject') == self.api.puuid})
            return (players, game_state)
        pregame = self.api.get_pregame_match()
        if pregame:
            self.current_match_id = None
            game_state = 'Agent Select'
            ally_team = pregame.get('AllyTeam', {}).get('Players', [])
            for player in ally_team:
                players.append({'puuid': player.get('Subject'), 'team': 'ally', 'agent': player.get('CharacterID'), 'is_local': player.get('Subject') == self.api.puuid})
            return (players, game_state)
        self.current_match_id = None
        return (players, game_state)

    def close(self):
        if self.muted_by_us:
            mute_valorant(False)
        self.running = False
        self.root.quit()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
if __name__ == '__main__':
    DecypherOverlay().run()
