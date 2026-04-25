"""Death-mute gate state for Decypher."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DeathMuteGateState:
    auto_death_mute_pending: bool = False
    revive_gate: bool = False
    startup_revive_gate: bool = False
    startup_score_baseline: int | None = None
    startup_revival_since: float | None = None
    startup_revival_seconds: float = 1.25
    round_start_cooldown_until: float = 0.0
    round_start_cooldown_seconds: float = 25.0
    last_cooldown_block_log_ts: float = 0.0
    round_start_requires_clear: bool = False
    round_start_clear_since: float | None = None
    round_start_clear_seconds: float = 4.0
    mute_armed_ts: float = 0.0
    mute_arm_grace_seconds: float = 0.75
    score_total_at_mute: int | None = None
    last_score_poll_ts: float = 0.0
    score_poll_interval_muted: float = 1.0
    normal_round_start_cooldown_seconds: float = 30.0
    extended_round_start_cooldown_seconds: float = 42.0
    clove_ult_detected: bool = False
    clove_ult_last_ready_ts: float = 0.0
    clove_ult_ready_grace_seconds: float = 1.5
    clove_ult_pending_until: float = 0.0
    clove_ult_pending_score_total: int | None = None
    clove_ult_pending_seconds: float = 2.5

    def clear_startup_gate(self):
        self.startup_revive_gate = False
        self.startup_score_baseline = None
        self.startup_revival_since = None

    def begin_startup_gate(self):
        self.revive_gate = True
        self.startup_revive_gate = True
        self.startup_score_baseline = None
        self.startup_revival_since = None
        self.last_score_poll_ts = 0.0

    def clear_clove_ult_wait(self, clear_ready_ts: bool = False):
        self.clove_ult_pending_until = 0.0
        self.clove_ult_pending_score_total = None
        if clear_ready_ts:
            self.clove_ult_last_ready_ts = 0.0

    def clear_round_start_gate(self, clear_cooldown: bool = False):
        if clear_cooldown:
            self.round_start_cooldown_until = 0.0
        self.round_start_requires_clear = False
        self.round_start_clear_since = None

    def clear_death_mute_gates(self):
        self.revive_gate = False
        self.clear_startup_gate()
        self.clear_clove_ult_wait()
        self.mute_armed_ts = 0.0
        self.score_total_at_mute = None
