"""Round-score parsing from Valorant presence payloads."""

from __future__ import annotations

import base64
import binascii
import json


def decode_private_presence(private_b64: str) -> dict:
    try:
        decoded = base64.b64decode(private_b64).decode("utf-8", errors="ignore")
        data = json.loads(decoded)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def round_score_total_from_private_data(private_data: dict) -> int | None:
    ally = private_data.get("partyOwnerMatchScoreAllyTeam")
    enemy = private_data.get("partyOwnerMatchScoreEnemyTeam")
    if isinstance(ally, int) and isinstance(enemy, int):
        return ally + enemy
    return None


def round_score_total_from_presences(presences: list, puuid: str | None) -> int | None:
    if not puuid:
        return None

    for presence in presences:
        if presence.get("puuid") != puuid:
            continue

        private_b64 = presence.get("private")
        if not private_b64:
            continue

        score = round_score_total_from_private_data(decode_private_presence(private_b64))
        if score is not None:
            return score

    return None
