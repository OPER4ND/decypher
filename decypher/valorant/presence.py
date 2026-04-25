"""Presence and match-state helpers for Valorant local API data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MatchPresence:
    players: list[dict[str, Any]]
    game_state: str
    source: str
    mode_id: str


def display_game_state(mode_id: str) -> str:
    mode = (mode_id or "").lower()
    if "deathmatch" in mode:
        return "Deathmatch"
    if "swift" in mode:
        return "Swiftplay"
    if "competitive" in mode:
        return "Competitive"
    if "unrated" in mode:
        return "Unrated"
    return "In-game"


def presence_title(game_state: str, source: str) -> str:
    return game_state if source != "none" else "Waiting for Valorant..."


def get_local_player(players: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((player for player in players if player.get("is_local")), None)


def _join_mode_bits(*bits: object) -> str:
    return " ".join(str(bit).strip() for bit in bits if str(bit or "").strip()).strip()


def _queue_hint(api, *candidates: object) -> str:
    for candidate in candidates:
        queue_id = str(candidate or "").strip()
        if queue_id:
            api.remember_queue_hint(queue_id)
            return api.get_queue_hint()
    return api.get_queue_hint()


def get_match_presence(api) -> MatchPresence:
    party_queue_id = api.get_party_queue_id()
    coregame = api.get_coregame_match()
    if coregame:
        queue_hint = _queue_hint(api, coregame.get("QueueID"))
        if not queue_hint:
            queue_hint = _queue_hint(api, party_queue_id)
        mode_id = _join_mode_bits(
            queue_hint,
            coregame.get("ModeID"),
            coregame.get("ProvisioningFlowID"),
        )
        players = [
            {
                "puuid": player.get("Subject"),
                "team": player.get("TeamID"),
                "agent": player.get("CharacterID"),
                "is_local": player.get("Subject") == api.puuid,
            }
            for player in coregame.get("Players", [])
        ]
        return MatchPresence(players, display_game_state(mode_id), "coregame", mode_id)

    pregame = api.get_pregame_match()
    if pregame:
        queue_hint = _queue_hint(api, pregame.get("QueueID"), party_queue_id)
        mode_id = _join_mode_bits(
            queue_hint,
            pregame.get("Mode"),
            pregame.get("ModeID"),
            pregame.get("ProvisioningFlowID"),
        )
        ally_team = pregame.get("AllyTeam", {}).get("Players", [])
        players = [
            {
                "puuid": player.get("Subject"),
                "team": "ally",
                "agent": player.get("CharacterID"),
                "selection_state": player.get("CharacterSelectionState"),
                "is_local": player.get("Subject") == api.puuid,
            }
            for player in ally_team
        ]
        return MatchPresence(players, "Agent Select", "pregame", mode_id)

    api.clear_queue_hint()
    return MatchPresence([], "Menu", "none", "")
