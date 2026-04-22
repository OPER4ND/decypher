"""Minimal Valorant local/GLZ API client used by Decypher."""

import requests
import urllib3

from agent_catalog import AgentCatalog
from presence_score import round_score_total_from_presences
from valorant_local import ValorantLocalClient
from valorant_remote import ValorantRemoteClient, extract_puuid_from_access_token

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


_cached_volume = None


def _is_valorant_audio_process(session) -> bool:
    process = getattr(session, "Process", None)
    if not process:
        return False

    try:
        name = process.name().lower()
    except Exception:
        return False

    return name == "valorant-win64-shipping.exe"


def _get_valorant_volume():
    global _cached_volume
    if _cached_volume is not None:
        return _cached_volume

    try:
        for session in AudioUtilities.GetAllSessions():
            if _is_valorant_audio_process(session):
                _cached_volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                return _cached_volume
    except Exception:
        pass
    return None


def reset_audio_session_cache():
    global _cached_volume
    _cached_volume = None


def mute_valorant(mute: bool = True) -> bool:
    """Mute or unmute the VALORANT audio session in the Windows volume mixer."""
    global _cached_volume
    if not AUDIO_AVAILABLE:
        return False

    try:
        volume = _get_valorant_volume()
        if volume:
            volume.SetMute(1 if mute else 0, None)
            return True
    except Exception:
        _cached_volume = None
    return False


class ValorantLocalAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.local = ValorantLocalClient(self.session)
        self.puuid = None
        self.remote = ValorantRemoteClient(self.session, self._request)
        self.agent_catalog = AgentCatalog()

    def is_game_running(self) -> bool:
        return self.local.is_game_running()

    def connect(self) -> bool:
        if not self.local.is_game_running():
            self.local.lockfile_mtime = None
            return False

        if self.local.has_current_connection() and self.puuid:
            return True

        if not self.local.connect():
            return False

        self.remote.reset_headers()
        reset_audio_session_cache()
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
