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
    if "competitive" in mode:
        return "Competitive"
    if "unrated" in mode:
        return "Unrated"
    return "In-game"


def presence_title(game_state: str, source: str) -> str:
    return game_state if source != "none" else "Waiting for Valorant..."


def get_local_player(players: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((player for player in players if player.get("is_local")), None)


def get_match_presence(api) -> MatchPresence:
    coregame = api.get_coregame_match()
    if coregame:
        mode = coregame.get("ModeID", "In-game")
        mode_id = str(mode or "")
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
        return MatchPresence(players, "Agent Select", "pregame", "")

    return MatchPresence([], "Menu", "none", "")
