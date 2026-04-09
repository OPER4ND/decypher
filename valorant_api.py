"""
Valorant Local API Client
Connects to the game's local API to fetch player data
"""

import os
import base64
import json
import binascii
import requests
import urllib3

# Disable SSL warnings for self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Audio control (Windows)
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

VALORANT_AUDIO_PROCESSES = {
    "valorant.exe",
    "valorant-win64-shipping.exe",
}


def _is_valorant_audio_process(session) -> bool:
    process = getattr(session, "Process", None)
    if not process:
        return False

    try:
        name = process.name().lower()
    except Exception:
        return False

    return name in VALORANT_AUDIO_PROCESSES or name.startswith("valorant")


def mute_valorant(mute: bool = True) -> bool:
    """Mute or unmute VALORANT.exe via Windows audio mixer"""
    if not AUDIO_AVAILABLE:
        return False

    try:
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            if _is_valorant_audio_process(session):
                volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                volume.SetMute(1 if mute else 0, None)
                return True
    except:
        pass
    return False


def is_valorant_muted() -> bool:
    """Check if VALORANT.exe is muted"""
    if not AUDIO_AVAILABLE:
        return False

    try:
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            if _is_valorant_audio_process(session):
                volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                return volume.GetMute() == 1
    except:
        pass
    return False


class ValorantLocalAPI:
    KNOWN_SHARDS = {"na", "latam", "br", "eu", "ap", "kr", "pbe"}

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False  # Ignore broken global proxy env vars
        self.lockfile_path = os.path.join(
            os.environ["LOCALAPPDATA"],
            "Riot Games",
            "Riot Client",
            "Config",
            "lockfile"
        )
        self.port = None
        self.password = None
        self.headers = None
        self.base_url = None
        self.puuid = None
        self.region = None
        self.shard = None
        self._name_cache = {}

    def is_game_running(self) -> bool:
        """Check if Valorant is running by checking lockfile existence"""
        return os.path.exists(self.lockfile_path)

    def connect(self) -> bool:
        """Read lockfile and setup connection"""
        if not self.is_game_running():
            return False

        try:
            with open(self.lockfile_path, "r") as f:
                data = f.read().split(":")
                # Format: name:pid:port:password:protocol
                self.port = data[2]
                self.password = data[3]

            self.base_url = f"https://127.0.0.1:{self.port}"
            auth = base64.b64encode(f"riot:{self.password}".encode()).decode()
            self.headers = {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json"
            }

            # Get local player info
            self._get_local_player_info()
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def _request(self, endpoint: str, method: str = "GET") -> dict | None:
        """Make a request to local API"""
        try:
            url = f"{self.base_url}{endpoint}"
            resp = self.session.request(method, url, headers=self.headers, verify=False)
            if resp.status_code == 200:
                return resp.json()
            return None
        except:
            return None

    def _pd_request(self, endpoint: str) -> dict | None:
        """Make request to PD (Player Data) API"""
        try:
            headers = self._get_remote_headers()
            url = f"https://pd.{self.shard}.a.pvp.net{endpoint}"
            resp = self.session.get(url, headers=headers, verify=False)
            if resp.status_code == 200:
                return resp.json()
            return None
        except:
            return None

    def _glz_request(self, endpoint: str, method: str = "GET", data: dict = None) -> dict | None:
        """Make request to GLZ (Game Logic) API"""
        try:
            headers = self._get_remote_headers()
            url = f"https://glz-{self.region}-1.{self.shard}.a.pvp.net{endpoint}"
            resp = self.session.request(
                method, url,
                headers=headers,
                json=data,
                verify=False
            )
            if resp.status_code in [200, 204]:
                if resp.text:
                    return resp.json()
                return {"success": True}
            return None
        except:
            return None

    def _get_remote_headers(self) -> dict:
        """Get headers for remote API calls"""
        entitlements = self._request("/entitlements/v1/token") or {}
        access_token = entitlements.get("accessToken", "")
        inferred_shard = self._extract_shard_from_access_token(access_token)
        if inferred_shard:
            if self.shard != inferred_shard:
                self.shard = inferred_shard
            if (not self.region) or self.region == "na":
                self.region = inferred_shard

        return {
            "Authorization": f"Bearer {access_token}",
            "X-Riot-Entitlements-JWT": entitlements.get("token", ""),
            "X-Riot-ClientPlatform": "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9",
            "X-Riot-ClientVersion": self._get_client_version(),
            "Content-Type": "application/json"
        }

    def current_game_match_debug(self) -> dict:
        """Grab the /current-game/match response so it can be logged externally."""
        headers = self._get_remote_headers()
        url = f"https://pd.{self.shard}.a.pvp.net/current-game/match"

        try:
            resp = self.session.get(url, headers=headers, verify=False)
        except Exception as exc:
            return {
                "url": url,
                "headers": headers,
                "error": str(exc),
            }

        body = None
        if resp.text:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text

        return {
            "url": url,
            "status": resp.status_code,
            "headers": headers,
            "body": body,
        }

    def _get_client_version(self) -> str:
        """Get current client version"""
        try:
            resp = self.session.get("https://valorant-api.com/v1/version")
            if resp.status_code == 200:
                return resp.json()["data"]["riotClientVersion"]
        except:
            pass
        return "release-09.00-shipping-27-2548652"

    def _get_local_player_info(self):
        """Get local player's PUUID and region"""
        # Get PUUID
        session = self._request("/chat/v1/session")
        if session:
            self.puuid = session.get("puuid")

        # Fallback: infer local player PUUID from access token when chat session is unavailable.
        if not self.puuid:
            entitlements = self._request("/entitlements/v1/token") or {}
            self.puuid = self._extract_puuid_from_access_token(entitlements.get("accessToken", ""))

        # Get region/shard from product session
        product_session = self._request("/product-session/v1/external-sessions")
        if product_session:
            for key, value in product_session.items():
                if "valorant" in key.lower():
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

        # Default fallback
        if not self.region:
            self.region = "na"
        if not self.shard:
            self.shard = "na"

    def _extract_puuid_from_access_token(self, token: str) -> str | None:
        """Infer local player's PUUID from JWT access token subject claim."""
        if not token or token.count(".") < 2:
            return None

        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
            subject = data.get("sub")
            if isinstance(subject, str) and subject:
                return subject
        except Exception:
            return None

        return None

    def _extract_shard_from_access_token(self, token: str) -> str | None:
        """Infer shard from the JWT payload when launch args are unavailable."""
        if not token or token.count(".") < 2:
            return None

        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())

            pp = data.get("pp", {})
            candidate = pp.get("c")
            if candidate in self.KNOWN_SHARDS:
                return candidate

            dat = data.get("dat", {})
            candidate = dat.get("c")
            if candidate in self.KNOWN_SHARDS:
                return candidate
        except Exception:
            return None

        return None

    def get_presences(self) -> list:
        """Get all player presences (reveals hidden names)"""
        data = self._request("/chat/v4/presences")
        if data:
            return data.get("presences", [])
        return []

    def get_party_members(self) -> dict:
        """Get party IDs for all players from presences. Returns {puuid: party_id}"""
        import json
        parties = {}
        presences = self.get_presences()

        for presence in presences:
            puuid = presence.get("puuid")
            private_b64 = presence.get("private")

            if puuid and private_b64:
                try:
                    private_json = base64.b64decode(private_b64).decode("utf-8")
                    private_data = json.loads(private_json)
                    party_id = private_data.get("partyId")
                    if party_id:
                        parties[puuid] = party_id
                except:
                    pass

        return parties

    def get_coregame_match(self) -> dict | None:
        """Get current live match data"""
        # Check if in a match
        match_info = self._glz_request(f"/core-game/v1/players/{self.puuid}")
        if not match_info:
            return None

        match_id = match_info.get("MatchID")
        if not match_id:
            return None

        # Get full match data
        return self._glz_request(f"/core-game/v1/matches/{match_id}")

    def get_pregame_match(self) -> dict | None:
        """Get agent select (pregame) match data"""
        match_info = self._glz_request(f"/pregame/v1/players/{self.puuid}")
        if not match_info:
            return None

        match_id = match_info.get("MatchID")
        if not match_id:
            return None

        return self._glz_request(f"/pregame/v1/matches/{match_id}")

    def get_player_names(self, puuids: list) -> dict:
        """Get player names from PUUIDs"""
        if not puuids:
            return {}

        # Resolve shard from fresh token headers first, then build PD URL.
        headers = self._get_remote_headers()
        shard_primary = self.shard or "na"
        shard_fallback = self._extract_shard_from_access_token(
            (headers.get("Authorization") or "").replace("Bearer ", "", 1)
        )

        def fetch_on_shard(shard: str) -> dict:
            out = {}
            try:
                url = f"https://pd.{shard}.a.pvp.net/name-service/v2/players"
                resp = self.session.put(url, headers=headers, json=puuids, verify=False)
                if resp.status_code != 200:
                    return out
                for player in resp.json():
                    subject = player.get("Subject")
                    if not subject:
                        continue
                    game_name = player.get("GameName") or ""
                    tag_line = player.get("TagLine") or ""
                    if game_name and tag_line:
                        out[subject] = f"{game_name}#{tag_line}"
            except Exception:
                return out
            return out

        names = fetch_on_shard(shard_primary)

        # Retry once on token-inferred shard if we got partial/empty resolution.
        if len(names) < len(puuids) and shard_fallback and shard_fallback != shard_primary:
            retry_names = fetch_on_shard(shard_fallback)
            if retry_names:
                names.update(retry_names)
                self.shard = shard_fallback

        # Never overwrite known names with empty values.
        for puuid in puuids:
            resolved = names.get(puuid)
            if resolved:
                self._name_cache[puuid] = resolved
            elif puuid in self._name_cache:
                names[puuid] = self._name_cache[puuid]
            else:
                names[puuid] = "Unknown"

        return names

    RANK_NAMES = [
        "Unranked", "Unused1", "Unused2",
        "Iron 1", "Iron 2", "Iron 3",
        "Bronze 1", "Bronze 2", "Bronze 3",
        "Silver 1", "Silver 2", "Silver 3",
        "Gold 1", "Gold 2", "Gold 3",
        "Platinum 1", "Platinum 2", "Platinum 3",
        "Diamond 1", "Diamond 2", "Diamond 3",
        "Ascendant 1", "Ascendant 2", "Ascendant 3",
        "Immortal 1", "Immortal 2", "Immortal 3",
        "Radiant"
    ]

    def _tier_to_rank(self, tier: int) -> str:
        """Convert tier number to rank name"""
        if 0 <= tier < len(self.RANK_NAMES):
            return self.RANK_NAMES[tier]
        return "Unknown"

    def get_player_ranks(self, puuids: list) -> tuple[dict, dict]:
        """Get player current and peak ranks. Returns (current_ranks, peak_ranks)"""
        current_ranks = {}
        peak_ranks = {}

        for puuid in puuids:
            try:
                data = self._pd_request(f"/mmr/v1/players/{puuid}")
                if data:
                    # Current rank (Riot now often omits QueueSkills.competitive.CompetitiveTier)
                    current_data = data.get("QueueSkills", {}).get("competitive", {})
                    current_tier = current_data.get("CompetitiveTier")
                    if not isinstance(current_tier, int):
                        current_tier = 0

                    if current_tier <= 0:
                        latest = data.get("LatestCompetitiveUpdate", {})
                        if isinstance(latest, dict) and latest.get("QueueID") == "competitive":
                            after = latest.get("TierAfterUpdate")
                            before = latest.get("TierBeforeUpdate")
                            if isinstance(after, int) and after > 0:
                                current_tier = after
                            elif isinstance(before, int) and before > 0:
                                current_tier = before

                    current_ranks[puuid] = self._tier_to_rank(current_tier)

                    # Lifetime peak rank
                    peak_tier = 0
                    seasonal_info = data.get("QueueSkills", {}).get("competitive", {}).get("SeasonalInfoBySeasonID", {})
                    for season_data in seasonal_info.values():
                        season_tier = season_data.get("CompetitiveTier", 0)
                        wins_by_tier = season_data.get("WinsByTier", {})
                        if isinstance(wins_by_tier, dict):
                            for key in wins_by_tier.keys():
                                try:
                                    tier_key = int(key)
                                    if tier_key > season_tier:
                                        season_tier = tier_key
                                except (ValueError, TypeError):
                                    continue
                        if season_tier > peak_tier:
                            peak_tier = season_tier

                    # Strict lifetime peak only from seasonal history, not current-rank fallback.
                    peak_ranks[puuid] = self._tier_to_rank(peak_tier) if peak_tier > 0 else "-"
                else:
                    current_ranks[puuid] = "Unknown"
                    peak_ranks[puuid] = "-"
            except:
                current_ranks[puuid] = "Unknown"
                peak_ranks[puuid] = "-"

        return current_ranks, peak_ranks

    def get_current_match_id(self) -> str | None:
        """Get active core-game match id for the local player."""
        if not self.puuid:
            return None
        match_info = self._glz_request(f"/core-game/v1/players/{self.puuid}")
        if not match_info:
            return None
        return match_info.get("MatchID")

    def get_local_death_count(self, match_id: str | None = None) -> int | None:
        """
        Get local player's death count from live match-details payload.
        Returns None if unavailable.
        """
        match_id = match_id or self.get_current_match_id()
        if not match_id or not self.puuid:
            return None

        details = self._pd_request(f"/match-details/v1/matches/{match_id}")
        if not isinstance(details, dict):
            return None

        players = details.get("players") or details.get("Players") or []
        if not isinstance(players, list):
            return None

        for p in players:
            if not isinstance(p, dict):
                continue
            subject = p.get("subject") or p.get("Subject") or p.get("puuid") or p.get("Puuid")
            if subject != self.puuid:
                continue

            stats = p.get("stats") or p.get("Stats") or {}
            if not isinstance(stats, dict):
                return None

            deaths = stats.get("deaths")
            if deaths is None:
                deaths = stats.get("Deaths")
            if isinstance(deaths, int):
                return deaths

            try:
                return int(deaths)
            except Exception:
                return None

        return None

    def get_local_death_count_info(self, match_id: str | None = None) -> tuple[int | None, str]:
        """Return (death_count, reason) for easier debugging in UI."""
        if not self.puuid:
            return None, "no_puuid"

        match_id = match_id or self.get_current_match_id()
        if not match_id:
            return None, "no_match_id"

        details = self._pd_request(f"/match-details/v1/matches/{match_id}")
        if not isinstance(details, dict):
            return None, "match_details_unavailable"

        players = details.get("players") or details.get("Players")
        if not isinstance(players, list):
            return None, "players_missing"

        for p in players:
            if not isinstance(p, dict):
                continue
            subject = p.get("subject") or p.get("Subject") or p.get("puuid") or p.get("Puuid")
            if subject != self.puuid:
                continue

            stats = p.get("stats") or p.get("Stats")
            if not isinstance(stats, dict):
                return None, "stats_missing"

            deaths = stats.get("deaths")
            if deaths is None:
                deaths = stats.get("Deaths")
            if isinstance(deaths, int):
                return deaths, "ok"
            try:
                return int(deaths), "ok"
            except Exception:
                return None, "deaths_parse_failed"

        return None, "player_not_found"

    def get_round_score_total(self) -> int | None:
        """
        Use local presence private payload to get current round score sum.
        Returns ally+enemy score when available.
        """
        for presence in self.get_presences():
            if presence.get("puuid") != self.puuid:
                continue

            private_b64 = presence.get("private")
            if not private_b64:
                continue

            try:
                decoded = base64.b64decode(private_b64).decode("utf-8", errors="ignore")
                pdata = json.loads(decoded)
            except (ValueError, binascii.Error, UnicodeDecodeError):
                continue

            ally = pdata.get("partyOwnerMatchScoreAllyTeam")
            enemy = pdata.get("partyOwnerMatchScoreEnemyTeam")
            if isinstance(ally, int) and isinstance(enemy, int):
                return ally + enemy

        return None

    # === AGENT SELECT ACTIONS ===

    def get_pregame_match_id(self) -> str | None:
        """Get current pregame match ID"""
        match_info = self._glz_request(f"/pregame/v1/players/{self.puuid}")
        if match_info:
            return match_info.get("MatchID")
        return None

    def select_agent(self, agent_id: str) -> bool:
        """Select an agent (doesn't lock)"""
        match_id = self.get_pregame_match_id()
        if not match_id:
            return False
        result = self._glz_request(
            f"/pregame/v1/matches/{match_id}/select/{agent_id}",
            method="POST"
        )
        return result is not None

    def lock_agent(self, agent_id: str) -> bool:
        """Lock in an agent (instalock)"""
        match_id = self.get_pregame_match_id()
        if not match_id:
            return False
        result = self._glz_request(
            f"/pregame/v1/matches/{match_id}/lock/{agent_id}",
            method="POST"
        )
        return result is not None

    def dodge_match(self) -> bool:
        """Dodge the current match (quit pregame)"""
        match_id = self.get_pregame_match_id()
        if not match_id:
            return False
        result = self._glz_request(
            f"/pregame/v1/matches/{match_id}/quit",
            method="POST"
        )
        return result is not None

    def is_player_alive(self) -> bool | None:
        """Check if local player is alive in current match. Returns None if not in match."""
        if not self.puuid:
            return None

        player_state = self._glz_request(f"/core-game/v1/players/{self.puuid}")
        if not player_state:
            return None
        if "IsAlive" in player_state:
            return bool(player_state.get("IsAlive"))

        coregame = self.get_coregame_match()
        if not coregame:
            return None

        for player in coregame.get("Players", []):
            if player.get("Subject") == self.puuid:
                if "IsAlive" in player:
                    return bool(player.get("IsAlive"))
                # Newer payloads omit IsAlive entirely.
                return None

        return None

    # Agent UUIDs (from valorant-api.com)
    AGENTS = {
        # Duelists
        "Iso": "0e38b510-41a8-5780-5e8f-568b2a4f2d6c",
        "Jett": "add6443a-41bd-e414-f6ad-e58d267f4e95",
        "Neon": "bb2a4828-46eb-8cd1-e765-15848195d751",
        "Phoenix": "eb93336a-449b-9c1b-0a54-a891f7921d69",
        "Raze": "f94c3b30-42be-e959-889c-5aa313dba261",
        "Reyna": "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc",
        "Waylay": "df1cb487-4902-002e-5c17-d28e83e78588",
        "Yoru": "7f94d92c-4234-0a36-9646-3a87eb8b5c89",
        # Initiators
        "Breach": "5f8d3a7f-467b-97f3-062c-13acf203c006",
        "Fade": "dade69b4-4f5a-8528-247b-219e5a1facd6",
        "Gekko": "e370fa57-4757-3604-3648-499e1f642d3f",
        "KAY/O": "601dbbe7-43ce-be57-2a40-4abd24953621",
        "Skye": "6f2a04ca-43e0-be17-7f36-b3908627744d",
        "Sova": "320b2a48-4d9b-a075-30f1-1f93a9b638fa",
        "Tejo": "b444168c-4e35-8076-db47-ef9bf368f384",
        # Controllers
        "Astra": "41fb69c1-4189-7b37-f117-bcaf1e96f1bf",
        "Brimstone": "9f0d8ba9-4140-b941-57d3-a7ad57c6b417",
        "Clove": "1dbf2edd-4729-0984-3115-daa5eed44993",
        "Harbor": "95b78ed7-4637-86d9-7e41-71ba8c293152",
        "Miks": "7c8a4701-4de6-9355-b254-e09bc2a34b72",
        "Omen": "8e253930-4c05-31dd-1b6c-968525494517",
        "Viper": "707eab51-4836-f488-046a-cda6bf494859",
        # Sentinels
        "Chamber": "22697a3d-45bf-8dd7-4fec-84a9e28c69d7",
        "Cypher": "117ed9e3-49f3-6512-3ccf-0cada7e3823b",
        "Deadlock": "cc8b64c8-4b25-4ff9-6e7f-37b4da43d235",
        "Killjoy": "1e58de9c-4950-5125-93e9-a0aee9f98746",
        "Sage": "569fdd95-4d10-43ab-ca70-79becc718b46",
        "Veto": "92eeef5d-43b5-1d4a-8d03-b3927a09034b",
        "Vyse": "efba5359-4016-a1e5-7626-b1ae76895940",
    }
