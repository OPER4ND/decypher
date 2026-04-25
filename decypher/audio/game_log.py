"""Valorant ShooterGame.log event tailing."""
from __future__ import annotations
import os
import re
import threading
from typing import Callable
SHOOTER_GAME_LOG = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'VALORANT', 'Saved', 'Logs', 'ShooterGame.log')
LOG_DEATH_RE = re.compile('LogPlayerController:.*AcknowledgePossession\\([\'\\"]?.+_PostDeath_')
LOG_REVIVAL_RE = re.compile('LogPlayerController:.*ClientRestart_Implementation.+_PostDeath_')
LOG_CLOVE_ULT_WINDOW_RE = re.compile('LogAbilitySystem:.*ReactiveRes_InDeathCastWindow_C')
LOG_CLOVE_ULT_USED_RE = re.compile('LogAbilitySystem:.*DelayDeathUltPointReward_C')

class GameLogTailer:

    def __init__(self, root, on_death: Callable[[], None], on_revival: Callable[[], None], on_clove_ult_window: Callable[[], None], on_clove_ult_used: Callable[[], None], path: str=SHOOTER_GAME_LOG):
        self.root = root
        self.path = path
        self.callbacks = {LOG_DEATH_RE: on_death, LOG_REVIVAL_RE: on_revival, LOG_CLOVE_ULT_WINDOW_RE: on_clove_ult_window, LOG_CLOVE_ULT_USED_RE: on_clove_ult_used}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _worker(self):
        while not self._stop.is_set():
            try:
                if not os.path.exists(self.path):
                    self._stop.wait(5)
                    continue
                with open(self.path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(0, 2)
                    idle_ticks = 0
                    while not self._stop.is_set():
                        line = f.readline()
                        if not line:
                            idle_ticks += 1
                            if idle_ticks >= 40:
                                idle_ticks = 0
                                try:
                                    if os.path.getsize(self.path) < f.tell():
                                        break
                                except OSError:
                                    break
                            self._stop.wait(0.05)
                            continue
                        idle_ticks = 0
                        self._dispatch(line)
            except Exception:
                self._stop.wait(2)

    def _dispatch(self, line: str):
        for pattern, callback in self.callbacks.items():
            if pattern.search(line):
                self.root.after(0, callback)
                return
