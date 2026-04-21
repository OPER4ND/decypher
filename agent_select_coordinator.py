"""Coordinator for the agent-select overlay lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable

from agent_select import AgentSelectOverlay
from presence import get_local_player


@dataclass(frozen=True)
class AgentSelection:
    agent_id: str | None
    agent_name: str | None


class AgentSelectCoordinator:
    def __init__(self, api, root, can_preload: Callable[[], bool]):
        self.api = api
        self.root = root
        self.can_preload = can_preload
        self.overlay: AgentSelectOverlay | None = None
        self.catalog_load_started = False

    def ensure_overlay(self) -> AgentSelectOverlay:
        if self.overlay is None:
            self.overlay = AgentSelectOverlay(self.api, master=self.root)
        return self.overlay

    def show(self):
        overlay = self.ensure_overlay()
        self.root.after(0, overlay.show)

    def hide(self):
        if self.overlay:
            self.root.after(0, self.overlay.hide)

    def destroy(self):
        if not self.overlay:
            return

        overlay = self.overlay
        self.overlay = None
        self.root.after(0, overlay.close)

    def ensure_catalog_loading(self):
        if self.catalog_load_started:
            return
        self.catalog_load_started = True

        def load_catalog():
            self.api.load_agent_catalog_once()
            self.root.after(0, self.preload_if_allowed)

        threading.Thread(target=load_catalog, daemon=True).start()

    def preload_if_allowed(self):
        if not self.can_preload():
            return
        overlay = self.ensure_overlay()
        overlay._refresh_agent_grid()
        overlay.preload_agent_images()

    def sync_from_players(self, players: list) -> AgentSelection | None:
        if not self.overlay:
            return None

        local_player = get_local_player(players)
        if not local_player:
            return None

        agent_id = local_player.get("agent")
        agent_name = self.api.get_agent_name(agent_id) if agent_id else None
        selection_state = local_player.get("selection_state")
        overlay = self.overlay
        self.root.after(
            0,
            lambda o=overlay, a=agent_id, s=selection_state: o.sync_from_game(a, s),
        )
        return AgentSelection(agent_id, agent_name)
