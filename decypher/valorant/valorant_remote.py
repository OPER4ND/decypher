"""Remote Valorant GLZ request support."""

from __future__ import annotations

import base64
import json
import time
from typing import Callable


KNOWN_SHARDS = {"na", "latam", "br", "eu", "ap", "kr", "pbe"}
CLIENT_VERSION_TTL = 3600.0
REMOTE_HEADERS_TTL = 60.0
GLZ_REQUEST_TIMEOUT = 4.0
CLIENT_VERSION_FALLBACK = "release-09.00-shipping-27-2548652"
CLIENT_PLATFORM = (
    "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3Mi"
    "LA0KCSJwbGF0Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0Ii"
    "wNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9"
)


def decode_jwt_payload(token: str) -> dict:
    if not token or token.count(".") < 2:
        return {}

    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return {}


def extract_puuid_from_access_token(token: str) -> str | None:
    payload = decode_jwt_payload(token)
    subject = payload.get("sub")
    return subject if isinstance(subject, str) and subject else None


def extract_shard_from_access_token(token: str) -> str | None:
    payload = decode_jwt_payload(token)
    for parent in ("pp", "dat"):
        candidate = payload.get(parent, {}).get("c")
        if candidate in KNOWN_SHARDS:
            return candidate
    return None


class ValorantRemoteClient:
    def __init__(self, session, local_request: Callable[[str], dict | None]):
        self.session = session
        self.local_request = local_request
        self.region = None
        self.shard = None
        self._client_version_cache = None
        self._client_version_ts = 0.0
        self._headers_cache = None
        self._headers_ts = 0.0

    def reset_headers(self):
        self._headers_cache = None
        self._headers_ts = 0.0

    def request(self, endpoint: str, method: str = "GET", data: dict = None) -> dict | None:
        if not self.region or not self.shard:
            return None
        try:
            url = f"https://glz-{self.region}-1.{self.shard}.a.pvp.net{endpoint}"
            response = self.session.request(
                method,
                url,
                headers=self.get_headers(),
                json=data,
                verify=False,
                timeout=GLZ_REQUEST_TIMEOUT,
            )
            if response.status_code in {200, 204}:
                return response.json() if response.text else {"success": True}
        except Exception:
            return None
        return None

    def get_headers(self) -> dict:
        now = time.time()
        if self._headers_cache and (now - self._headers_ts) < REMOTE_HEADERS_TTL:
            return self._headers_cache

        entitlements = self.local_request("/entitlements/v1/token") or {}
        access_token = entitlements.get("accessToken", "")
        inferred_shard = extract_shard_from_access_token(access_token)
        if inferred_shard:
            self.shard = inferred_shard
            if not self.region or self.region == "na":
                self.region = inferred_shard

        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Riot-Entitlements-JWT": entitlements.get("token", ""),
            "X-Riot-ClientPlatform": CLIENT_PLATFORM,
            "X-Riot-ClientVersion": self.get_client_version(),
            "Content-Type": "application/json",
        }
        self._headers_cache = headers
        self._headers_ts = now
        return headers

    def get_client_version(self) -> str:
        now = time.time()
        if self._client_version_cache and (now - self._client_version_ts) < CLIENT_VERSION_TTL:
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
        return self._client_version_cache or CLIENT_VERSION_FALLBACK
