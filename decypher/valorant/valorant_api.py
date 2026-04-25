"""Minimal Valorant local/GLZ API client used by Decypher."""

import requests
import time
import urllib3

from decypher.valorant.agent_catalog import AgentCatalog
from decypher.valorant.presence_score import round_score_total_from_presences
from decypher.valorant.valorant_local import ValorantLocalClient
from decypher.valorant.valorant_remote import (
    ValorantRemoteClient,
    extract_puuid_from_access_token,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PARTY_QUEUE_TTL = 2.0

class ValorantLocalAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.local = ValorantLocalClient(self.session)
        self.puuid = None
        self.remote = ValorantRemoteClient(self.session, self._request)
        self.agent_catalog = AgentCatalog()
        self._runtime_generation = 0
        self._party_queue_cache = ""
        self._party_queue_cache_ts = 0.0
        self._queue_hint = ""

    def is_game_running(self) -> bool:
        return self.local.is_game_running()

    def connect(self) -> bool:
        if not self.local.is_game_running():
            self.local.lockfile_mtime = None
            self.reset_runtime_state()
            return False

        if self.local.has_current_connection() and self.puuid:
            return True

        if not self.local.connect():
            self.reset_runtime_state()
            return False

        if self.local.connection_generation != self._runtime_generation:
            self._runtime_generation = self.local.connection_generation
            self.reset_runtime_state()

        self.remote.reset_headers()
        self._get_local_player_info()
        return True

    def load_agent_catalog_once(self, force: bool = False) -> dict:
        return self.agent_catalog.load_once(self.session, force)

    def get_agent_catalog(self) -> dict:
        return self.agent_catalog.get_catalog()

    def get_agent_uuid(self, agent_name: str) -> str | None:
        return self.agent_catalog.get_uuid(agent_name)

    def get_agent_name(self, agent_id: str) -> str | None:
        return self.agent_catalog.get_name(agent_id)

    @property
    def agent_catalog_source(self) -> str:
        return self.agent_catalog.source

    @property
    def connection_generation(self) -> int:
        return self.local.connection_generation

    def _request(self, endpoint: str, method: str = "GET") -> dict | None:
        return self.local.request(endpoint, method)

    def _glz_request(self, endpoint: str, method: str = "GET", data: dict = None) -> dict | None:
        return self.remote.request(endpoint, method, data)

    def _get_local_player_info(self):
        session = self._request("/chat/v1/session")
        if session:
            self.puuid = session.get("puuid")

        if not self.puuid:
            entitlements = self._request("/entitlements/v1/token") or {}
            self.puuid = extract_puuid_from_access_token(entitlements.get("accessToken", ""))

        product_session = self._request("/product-session/v1/external-sessions")
        if product_session:
            for key, value in product_session.items():
                if "valorant" not in key.lower():
                    continue
                launch_args = value.get("launchConfiguration", {}).get("arguments", [])
                for arg in launch_args:
                    if "-ares-deployment=" in arg:
                        self.remote.region = arg.split("=")[1]
                    if "-config-endpoint=" in arg:
                        endpoint = arg.split("=")[1]
                        if "pbe" in endpoint:
                            self.remote.shard = "pbe"
                        elif ".eu." in endpoint:
                            self.remote.shard = "eu"
                        elif ".ap." in endpoint:
                            self.remote.shard = "ap"
                        elif ".kr." in endpoint:
                            self.remote.shard = "kr"
                        else:
                            self.remote.shard = "na"
                break

        self.remote.region = self.remote.region or "na"
        self.remote.shard = self.remote.shard or "na"

    @property
    def region(self):
        return self.remote.region

    @property
    def shard(self):
        return self.remote.shard

    def get_presences(self) -> list:
        data = self._request("/chat/v4/presences")
        return data.get("presences", []) if data else []

    def get_round_score_total(self) -> int | None:
        return round_score_total_from_presences(self.get_presences(), self.puuid)

    def reset_runtime_state(self):
        self._party_queue_cache = ""
        self._party_queue_cache_ts = 0.0
        self._queue_hint = ""

    def remember_queue_hint(self, queue_id: str | None):
        queue_value = str(queue_id or "").strip()
        if queue_value:
            self._queue_hint = queue_value

    def get_queue_hint(self) -> str:
        return self._queue_hint

    def clear_queue_hint(self):
        self._queue_hint = ""

    def get_party_player(self) -> dict | None:
        if not self.puuid:
            return None
        return self._glz_request(f"/parties/v1/players/{self.puuid}")

    def get_current_party(self) -> dict | None:
        party_player = self.get_party_player()
        party_id = party_player.get("CurrentPartyID") if party_player else None
        if not party_id:
            return None
        return self._glz_request(f"/parties/v1/parties/{party_id}")

    def get_party_queue_id(self) -> str | None:
        now = time.time()
        if (now - self._party_queue_cache_ts) < PARTY_QUEUE_TTL:
            return self._party_queue_cache or None

        party = self.get_current_party()
        queue_id = ""
        if party:
            matchmaking = party.get("MatchmakingData") or {}
            queue_id = str(matchmaking.get("QueueID") or "").strip()

        self._party_queue_cache = queue_id
        self._party_queue_cache_ts = now
        return queue_id or None

    def get_coregame_match(self) -> dict | None:
        match_info = self._glz_request(f"/core-game/v1/players/{self.puuid}")
        match_id = match_info.get("MatchID") if match_info else None
        if not match_id:
            return None
        return self._glz_request(f"/core-game/v1/matches/{match_id}")

    def get_pregame_match(self) -> dict | None:
        match_info = self._glz_request(f"/pregame/v1/players/{self.puuid}")
        match_id = match_info.get("MatchID") if match_info else None
        if not match_id:
            return None
        return self._glz_request(f"/pregame/v1/matches/{match_id}")

    def get_pregame_match_id(self) -> str | None:
        match_info = self._glz_request(f"/pregame/v1/players/{self.puuid}")
        return match_info.get("MatchID") if match_info else None

    def select_agent(self, agent_id: str) -> bool:
        match_id = self.get_pregame_match_id()
        if not match_id:
            return False
        result = self._glz_request(f"/pregame/v1/matches/{match_id}/select/{agent_id}", method="POST")
        return result is not None

    def lock_agent(self, agent_id: str) -> bool:
        match_id = self.get_pregame_match_id()
        if not match_id:
            return False
        result = self._glz_request(f"/pregame/v1/matches/{match_id}/lock/{agent_id}", method="POST")
        return result is not None

    def dodge_match(self) -> bool:
        match_id = self.get_pregame_match_id()
        if not match_id:
            return False
        result = self._glz_request(f"/pregame/v1/matches/{match_id}/quit", method="POST")
        return result is not None
