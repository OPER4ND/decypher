"""Minimal Valorant local/GLZ API client used by Decypher."""

import base64
import json
import os
import time

import requests
import urllib3

from agent_catalog import AgentCatalog
from presence_score import round_score_total_from_presences

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
    KNOWN_SHARDS = {"na", "latam", "br", "eu", "ap", "kr", "pbe"}

    _CLIENT_VERSION_TTL  = 3600.0   # re-fetch at most once per hour
    _REMOTE_HEADERS_TTL  = 60.0    # access token valid for minutes; refresh every 60s
    _LOCAL_REQUEST_TIMEOUT = 2.0
    _GLZ_REQUEST_TIMEOUT = 4.0

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.lockfile_path = os.path.join(
            os.environ["LOCALAPPDATA"],
            "Riot Games",
            "Riot Client",
            "Config",
            "lockfile",
        )
        self.port = None
        self.password = None
        self.headers = None
        self.base_url = None
        self.puuid = None
        self.region = None
        self.shard = None
        self.agent_catalog = AgentCatalog()

        self._lockfile_mtime = None
        self._client_version_cache = None
        self._client_version_ts = 0.0
        self._remote_headers_cache = None
        self._remote_headers_ts = 0.0

    def is_game_running(self) -> bool:
        return os.path.exists(self.lockfile_path)

    def connect(self) -> bool:
        if not self.is_game_running():
            self._lockfile_mtime = None
            return False

        try:
            mtime = os.path.getmtime(self.lockfile_path)
            if self.base_url and self.puuid and mtime == self._lockfile_mtime:
                return True  # already connected, lockfile unchanged
            with open(self.lockfile_path, "r", encoding="utf-8") as lockfile:
                data = lockfile.read().split(":")
            self.port = data[2]
            self.password = data[3]
            self.base_url = f"https://127.0.0.1:{self.port}"
            auth = base64.b64encode(f"riot:{self.password}".encode()).decode()
            self.headers = {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
            }
            self._lockfile_mtime = mtime
            self._remote_headers_cache = None  # force token refresh on reconnect
            reset_audio_session_cache()
            self._get_local_player_info()
            return True
        except Exception:
            self._lockfile_mtime = None
            return False

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
        if not self.base_url or not self.headers:
            return None
        try:
            response = self.session.request(
                method, f"{self.base_url}{endpoint}",
                headers=self.headers,
                verify=False,
                timeout=self._LOCAL_REQUEST_TIMEOUT,
            )
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None

    def _glz_request(self, endpoint: str, method: str = "GET", data: dict = None) -> dict | None:
        try:
            headers = self._get_remote_headers()
            url = f"https://glz-{self.region}-1.{self.shard}.a.pvp.net{endpoint}"
            response = self.session.request(
                method,
                url,
                headers=headers,
                json=data,
                verify=False,
                timeout=self._GLZ_REQUEST_TIMEOUT,
            )
            if response.status_code in {200, 204}:
                return response.json() if response.text else {"success": True}
        except Exception:
            return None
        return None

    def _get_remote_headers(self) -> dict:
        now = time.time()
        if self._remote_headers_cache and (now - self._remote_headers_ts) < self._REMOTE_HEADERS_TTL:
            return self._remote_headers_cache

        entitlements = self._request("/entitlements/v1/token") or {}
        access_token = entitlements.get("accessToken", "")
        inferred_shard = self._extract_shard_from_access_token(access_token)
        if inferred_shard:
            self.shard = inferred_shard
            if not self.region or self.region == "na":
                self.region = inferred_shard

        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Riot-Entitlements-JWT": entitlements.get("token", ""),
            "X-Riot-ClientPlatform": "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9",
            "X-Riot-ClientVersion": self._get_client_version(),
            "Content-Type": "application/json",
        }
        self._remote_headers_cache = headers
        self._remote_headers_ts = now
        return headers

    def _get_client_version(self) -> str:
        now = time.time()
        if self._client_version_cache and (now - self._client_version_ts) < self._CLIENT_VERSION_TTL:
            return self._client_version_cache
        try:
            response = self.session.get("https://valorant-api.com/v1/version", timeout=5)
            if response.status_code == 200:
                version = response.json()["data"]["riotClientVersion"]
                self._client_version_cache = version
                self._client_version_ts = now
                return version
        except Exception:
            pass
        # Return stale cache if available rather than the hardcoded fallback
        return self._client_version_cache or "release-09.00-shipping-27-2548652"

    def _get_local_player_info(self):
        session = self._request("/chat/v1/session")
        if session:
            self.puuid = session.get("puuid")

        if not self.puuid:
            entitlements = self._request("/entitlements/v1/token") or {}
            self.puuid = self._extract_puuid_from_access_token(entitlements.get("accessToken", ""))

        product_session = self._request("/product-session/v1/external-sessions")
        if product_session:
            for key, value in product_session.items():
                if "valorant" not in key.lower():
                    continue
                launch_args = value.get("launchConfiguration", {}).get("arguments", [])
                for arg in launch_args:
                    if "-ares-deployment=" in arg:
                        self.region = arg.split("=")[1]
                    if "-config-endpoint=" in arg:
                        endpoint = arg.split("=")[1]
                        if "pbe" in endpoint:
                            self.shard = "pbe"
                        elif ".eu." in endpoint:
                            self.shard = "eu"
                        elif ".ap." in endpoint:
                            self.shard = "ap"
                        elif ".kr." in endpoint:
                            self.shard = "kr"
                        else:
                            self.shard = "na"
                break

        self.region = self.region or "na"
        self.shard = self.shard or "na"

    def _extract_puuid_from_access_token(self, token: str) -> str | None:
        payload = self._decode_jwt_payload(token)
        subject = payload.get("sub")
        return subject if isinstance(subject, str) and subject else None

    def _extract_shard_from_access_token(self, token: str) -> str | None:
        payload = self._decode_jwt_payload(token)
        for parent in ("pp", "dat"):
            candidate = payload.get(parent, {}).get("c")
            if candidate in self.KNOWN_SHARDS:
                return candidate
        return None

    def _decode_jwt_payload(self, token: str) -> dict:
        if not token or token.count(".") < 2:
            return {}

        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        except Exception:
            return {}

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
