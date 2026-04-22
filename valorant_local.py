"""Local Riot Client request support."""

from __future__ import annotations

import base64
import os


LOCAL_REQUEST_TIMEOUT = 2.0


class ValorantLocalClient:
    def __init__(self, session):
        self.session = session
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
        self.lockfile_mtime = None
        self.connection_generation = 0

    def is_game_running(self) -> bool:
        return os.path.exists(self.lockfile_path)

    def has_current_connection(self) -> bool:
        if not self.base_url or not self.headers or self.lockfile_mtime is None:
            return False
        try:
            return os.path.getmtime(self.lockfile_path) == self.lockfile_mtime
        except OSError:
            return False

    def connect(self) -> bool:
        if not self.is_game_running():
            self.lockfile_mtime = None
            return False

        try:
            mtime = os.path.getmtime(self.lockfile_path)
            if self.base_url and mtime == self.lockfile_mtime:
                return True

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
            self.lockfile_mtime = mtime
            self.connection_generation += 1
            return True
        except Exception:
            self.lockfile_mtime = None
            return False

    def request(self, endpoint: str, method: str = "GET") -> dict | None:
        if not self.base_url or not self.headers:
            return None

        try:
            response = self.session.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=self.headers,
                verify=False,
                timeout=LOCAL_REQUEST_TIMEOUT,
            )
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None
