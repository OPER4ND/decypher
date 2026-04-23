"""Mute state transitions for death and manual mute."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from audio_control import mute_valorant


@dataclass(frozen=True)
class ManualMuteResult:
    changed: bool
    enabled: bool
    mute_failed: bool = False


class MuteState:
    def __init__(self, mute_func: Callable[[bool], bool] = mute_valorant):
        self.mute_func = mute_func
        self.death_muted = False
        self.manual_muted = False
        self.manual_defers_to_auto = True

    def sync_target_mute(self) -> int:
        return 1 if self.mute_func(self.death_muted or self.manual_muted) else 0

    def engage_death(self) -> int:
        self.death_muted = True
        if self.sync_target_mute() > 0:
            return 1
        self.death_muted = False
        return 0

    def release_death(self) -> int:
        self.death_muted = False
        return self.sync_target_mute()

    def toggle_manual(self) -> ManualMuteResult:
        previous = self.manual_muted
        self.manual_muted = not self.manual_muted
        if self.sync_target_mute() <= 0:
            self.manual_muted = previous
            self.sync_target_mute()
            return ManualMuteResult(changed=False, enabled=previous, mute_failed=True)

        return ManualMuteResult(changed=True, enabled=self.manual_muted)

    def toggle_manual_defers_to_auto(self) -> bool:
        self.manual_defers_to_auto = not self.manual_defers_to_auto
        return self.manual_defers_to_auto

    def clear_deferred_manual(self, death_mute_enabled: bool) -> bool:
        if not (self.manual_defers_to_auto and death_mute_enabled and self.manual_muted):
            return False
        self.manual_muted = False
        self.sync_target_mute()
        return True

    def clear_all(self) -> int:
        self.death_muted = False
        self.manual_muted = False
        return 1 if self.mute_func(False) else 0
