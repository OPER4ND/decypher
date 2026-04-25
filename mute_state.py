"""Mute state transitions for death and manual mute."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from audio_control import mute_valorant


@dataclass(frozen=True)
class ManualMuteResult:
    changed: bool
    muted: bool
    unmuted: bool
    mute_failed: bool = False


class MuteState:
    def __init__(self, mute_func: Callable[[bool], bool] = mute_valorant):
        self.mute_func = mute_func
        self.death_muted = False
        self.manual_override: bool | None = None
        self.manual_defers_to_auto = True

    @property
    def manual_muted(self) -> bool:
        return self.manual_override is True

    @property
    def manual_unmuted(self) -> bool:
        return self.manual_override is False

    def target_muted(self) -> bool:
        if self.manual_override is None:
            return self.death_muted
        return self.manual_override

    def sync_target_mute(self) -> int:
        return 1 if self.mute_func(self.target_muted()) else 0

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
        previous = self.manual_override
        self.manual_override = not self.target_muted()
        if self.sync_target_mute() <= 0:
            self.manual_override = previous
            self.sync_target_mute()
            return ManualMuteResult(
                changed=False,
                muted=previous is True,
                unmuted=previous is False,
                mute_failed=True,
            )

        return ManualMuteResult(
            changed=True,
            muted=self.manual_muted,
            unmuted=self.manual_unmuted,
        )

    def toggle_manual_defers_to_auto(self) -> bool:
        self.manual_defers_to_auto = not self.manual_defers_to_auto
        return self.manual_defers_to_auto

    def clear_deferred_manual(self, death_mute_enabled: bool) -> bool:
        if not (
            self.manual_defers_to_auto
            and death_mute_enabled
            and self.manual_override is not None
        ):
            return False
        self.manual_override = None
        self.sync_target_mute()
        return True

    def clear_all(self) -> int:
        self.death_muted = False
        self.manual_override = None
        return 1 if self.mute_func(False) else 0
