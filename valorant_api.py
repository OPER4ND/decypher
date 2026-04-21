"""Minimal Valorant local/GLZ API client used by Decypher."""

import base64
import binascii
import json
import os

import requests
import urllib3

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
        try:
            _cached_volume.GetMute()  # probe — raises if handle is stale
            return _cached_volume
        except Exception:
            _cached_volume = None

    try:
        for session in AudioUtilities.GetAllSessions():
            if _is_valorant_audio_process(session):
                _cached_volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                return _cached_volume
    except Exception:
        pass
    return None


def mute_valorant(mute: bool = True) -> bool:
    """Mute or unmute the VALORANT audio session in the Windows volume mixer."""
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
    AGENT_CATALOG_URL = "https://valorant-api.com/v1/agents?isPlayableCharacter=true"
    ROLE_ORDER = ("Duelists", "Initiators", "Controllers", "Sentinels")
    ROLE_LABELS = {
        "duelist": "Duelists",
        "initiator": "Initiators",
        "controller": "Controllers",
        "sentinel": "Sentinels",
    }
    FALLBACK_AGENT_ROLES = {
        "Iso": "Duelists",
        "Jett": "Duelists",
        "Neon": "Duelists",
        "Phoenix": "Duelists",
        "Raze": "Duelists",
        "Reyna": "Duelists",
        "Waylay": "Duelists",
        "Yoru": "Duelists",
        "Breach": "Initiators",
        "Fade": "Initiators",
        "Gekko": "Initiators",
        "KAY/O": "Initiators",
        "Skye": "Initiators",
        "Sova": "Initiators",
        "Tejo": "Initiators",
        "Astra": "Controllers",
        "Brimstone": "Controllers",
        "Clove": "Controllers",
        "Harbor": "Controllers",
        "Miks": "Controllers",
        "Omen": "Controllers",
        "Viper": "Controllers",
        "Chamber": "Sentinels",
        "Cypher": "Sentinels",
        "Deadlock": "Sentinels",
        "Killjoy": "Sentinels",
        "Sage": "Sentinels",
        "Veto": "Sentinels",
        "Vyse": "Sentinels",
    }

    # Agent UUIDs used by pregame select/lock.
    AGENTS = {
        "Iso": "0e38b510-41a8-5780-5e8f-568b2a4f2d6c",
        "Jett": "add6443a-41bd-e414-f6ad-e58d267f4e95",
        "Neon": "bb2a4828-46eb-8cd1-e765-15848195d751",
        "Phoenix": "eb93336a-449b-9c1b-0a54-a891f7921d69",
        "Raze": "f94c3b30-42be-e959-889c-5aa313dba261",
        "Reyna": "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc",
        "Waylay": "df1cb487-4902-002e-5c17-d28e83e78588",
        "Yoru": "7f94d92c-4234-0a36-9646-3a87eb8b5c89",
        "Breach": "5f8d3a7f-467b-97f3-062c-13acf203c006",
        "Fade": "dade69b4-4f5a-8528-247b-219e5a1facd6",
        "Gekko": "e370fa57-4757-3604-3648-499e1f642d3f",
        "KAY/O": "601dbbe7-43ce-be57-2a40-4abd24953621",
        "Skye": "6f2a04ca-43e0-be17-7f36-b3908627744d",
        "Sova": "320b2a48-4d9b-a075-30f1-1f93a9b638fa",
        "Tejo": "b444168c-4e35-8076-db47-ef9bf368f384",
        "Astra": "41fb69c1-4189-7b37-f117-bcaf1e96f1bf",
        "Brimstone": "9f0d8ba9-4140-b941-57d3-a7ad57c6b417",
        "Clove": "1dbf2edd-4729-0984-3115-daa5eed44993",
        "Harbor": "95b78ed7-4637-86d9-7e41-71ba8c293152",
        "Miks": "7c8a4701-4de6-9355-b254-e09bc2a34b72",
        "Omen": "8e253930-4c05-31dd-1b6c-968525494517",
        "Viper": "707eab51-4836-f488-046a-cda6bf494859",
        "Chamber": "22697a3d-45bf-8dd7-4fec-84a9e28c69d7",
        "Cypher": "117ed9e3-49f3-6512-3ccf-0cada7e3823b",
        "Deadlock": "cc8b64c8-4b25-4ff9-6e7f-37b4da43d235",
        "Killjoy": "1e58de9c-4950-5125-93e9-a0aee9f98746",
        "Sage": "569fdd95-4d10-43ab-ca70-79becc718b46",
        "Veto": "92eeef5d-43b5-1d4a-8d03-b3927a09034b",
        "Vyse": "efba5359-4016-a1e5-7626-b1ae76895940",
    }

    _CLIENT_VERSION_TTL  = 3600.0   # re-fetch at most once per hour
    _REMOTE_HEADERS_TTL  = 60.0    # access token valid for minutes; refresh every 60s

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
        self.agent_catalog_loaded = False
        self.agent_catalog_source = "fallback"
        self.agent_catalog = self._build_agent_catalog_from_map(self.AGENTS, self.FALLBACK_AGENT_ROLES)
        self.agents_by_name = dict(self.AGENTS)
        self.agents_by_uuid = {v.lower(): k for k, v in self.AGENTS.items()}

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
            self._get_local_player_info()
            return True
        except Exception:
            self._lockfile_mtime = None
            return False

    def _agent_icon_url(self, agent_id: str) -> str:
        return f"https://media.valorant-api.com/agents/{agent_id}/displayicon.png"

    def _build_agent_catalog_from_map(self, agents_by_name: dict, roles_by_name: dict) -> dict:
        grouped = {role: [] for role in self.ROLE_ORDER}
        for name, agent_id in sorted(agents_by_name.items()):
            role = roles_by_name.get(name)
            if role not in grouped:
                continue
            grouped[role].append(
                {
                    "name": name,
                    "uuid": agent_id,
                    "role": role,
                    "icon_url": self._agent_icon_url(agent_id),
                }
            )

        return {
            "roles": [
                {"name": role, "agents": grouped[role]}
                for role in self.ROLE_ORDER
                if grouped[role]
            ],
            "agents_by_name": dict(agents_by_name),
            "source": "fallback",
        }

    def _normalize_role_name(self, role_name: str | None) -> str | None:
        if not role_name:
            return None
        return self.ROLE_LABELS.get(role_name.strip().lower())

    def _build_agent_catalog_from_api(self, agents: list) -> dict | None:
        grouped = {role: [] for role in self.ROLE_ORDER}
        agents_by_name = {}

        for agent in agents:
            name = agent.get("displayName")
            agent_id = agent.get("uuid")
            role = self._normalize_role_name(agent.get("role", {}).get("displayName"))
            if not name or not agent_id or role not in grouped:
                continue

            agents_by_name[name] = agent_id
            grouped[role].append(
                {
                    "name": name,
                    "uuid": agent_id,
                    "role": role,
                    "icon_url": agent.get("displayIcon") or self._agent_icon_url(agent_id),
                }
            )

        if not agents_by_name:
            return None

        for role_agents in grouped.values():
            role_agents.sort(key=lambda item: item["name"].lower())

        return {
            "roles": [
                {"name": role, "agents": grouped[role]}
                for role in self.ROLE_ORDER
                if grouped[role]
            ],
            "agents_by_name": agents_by_name,
            "source": "valorant-api",
        }

    def load_agent_catalog_once(self, force: bool = False) -> dict:
        if self.agent_catalog_loaded and not force:
            return self.agent_catalog

        self.agent_catalog_loaded = True
        try:
            response = self.session.get(self.AGENT_CATALOG_URL, timeout=8)
            response.raise_for_status()
            catalog = self._build_agent_catalog_from_api(response.json().get("data", []))
            if catalog:
                self.agent_catalog = catalog
                self.agent_catalog_source = catalog["source"]
                self.agents_by_name = dict(catalog["agents_by_name"])
                self.agents_by_uuid = {v.lower(): k for k, v in self.agents_by_name.items()}
                return self.agent_catalog
        except Exception:
            pass

        self.agent_catalog_source = "fallback"
        self.agent_catalog = self._build_agent_catalog_from_map(self.AGENTS, self.FALLBACK_AGENT_ROLES)
        self.agents_by_name = dict(self.AGENTS)
        self.agents_by_uuid = {v.lower(): k for k, v in self.AGENTS.items()}
        return self.agent_catalog

    def get_agent_catalog(self) -> dict:
        return self.agent_catalog

    def get_agent_uuid(self, agent_name: str) -> str | None:
        return self.agents_by_name.get(agent_name) or self.AGENTS.get(agent_name)

    def get_agent_name(self, agent_id: str) -> str | None:
        if not agent_id:
            return None
        return self.agents_by_uuid.get(str(agent_id).lower())

    def _request(self, endpoint: str, method: str = "GET") -> dict | None:
        if not self.base_url or not self.headers:
            return None

        try:
            response = self.session.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=self.headers,
                verify=False,
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            return None
        return None

    def _glz_request(self, endpoint: str, method: str = "GET", data: dict = None) -> dict | None:
        try:
            headers = self._get_remote_headers()
            url = f"https://glz-{self.region}-1.{self.shard}.a.pvp.net{endpoint}"
            response = self.session.request(method, url, headers=headers, json=data, verify=False)
            if response.status_code in {200, 204}:
                return response.json() if response.text else {"success": True}
        except Exception:
            return None
        return None

    def _get_remote_headers(self) -> dict:
        import time
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
        import time
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
        for presence in self.get_presences():
            if presence.get("puuid") != self.puuid:
                continue

            private_b64 = presence.get("private")
            if not private_b64:
                continue

            try:
                decoded = base64.b64decode(private_b64).decode("utf-8", errors="ignore")
                private_data = json.loads(decoded)
            except (ValueError, binascii.Error, UnicodeDecodeError):
                continue

            ally = private_data.get("partyOwnerMatchScoreAllyTeam")
            enemy = private_data.get("partyOwnerMatchScoreEnemyTeam")
            if isinstance(ally, int) and isinstance(enemy, int):
                return ally + enemy

        return None

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
