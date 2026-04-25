"""Agent catalog loading and fallback data."""

from __future__ import annotations


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


def agent_icon_url(agent_id: str) -> str:
    return f"https://media.valorant-api.com/agents/{agent_id}/displayicon.png"


def normalize_role_name(role_name: str | None) -> str | None:
    if not role_name:
        return None
    return ROLE_LABELS.get(role_name.strip().lower())


def build_agent_catalog_from_map(agents_by_name: dict, roles_by_name: dict) -> dict:
    grouped = {role: [] for role in ROLE_ORDER}
    for name, agent_id in sorted(agents_by_name.items()):
        role = roles_by_name.get(name)
        if role not in grouped:
            continue
        grouped[role].append(
            {
                "name": name,
                "uuid": agent_id,
                "role": role,
                "icon_url": agent_icon_url(agent_id),
            }
        )

    return {
        "roles": [
            {"name": role, "agents": grouped[role]}
            for role in ROLE_ORDER
            if grouped[role]
        ],
        "agents_by_name": dict(agents_by_name),
        "source": "fallback",
    }


def build_agent_catalog_from_api(agents: list) -> dict | None:
    grouped = {role: [] for role in ROLE_ORDER}
    agents_by_name = {}

    for agent in agents:
        name = agent.get("displayName")
        agent_id = agent.get("uuid")
        role = normalize_role_name(agent.get("role", {}).get("displayName"))
        if not name or not agent_id or role not in grouped:
            continue

        agents_by_name[name] = agent_id
        grouped[role].append(
            {
                "name": name,
                "uuid": agent_id,
                "role": role,
                "icon_url": agent.get("displayIcon") or agent_icon_url(agent_id),
            }
        )

    if not agents_by_name:
        return None

    for role_agents in grouped.values():
        role_agents.sort(key=lambda item: item["name"].lower())

    return {
        "roles": [
            {"name": role, "agents": grouped[role]}
            for role in ROLE_ORDER
            if grouped[role]
        ],
        "agents_by_name": agents_by_name,
        "source": "valorant-api",
    }


class AgentCatalog:
    def __init__(self):
        self.loaded = False
        self.source = "fallback"
        self.catalog = build_agent_catalog_from_map(AGENTS, FALLBACK_AGENT_ROLES)
        self.agents_by_name = dict(AGENTS)
        self.agents_by_uuid = {value.lower(): name for name, value in AGENTS.items()}

    def load_once(self, session, force: bool = False) -> dict:
        if self.loaded and not force:
            return self.catalog

        self.loaded = True
        try:
            response = session.get(AGENT_CATALOG_URL, timeout=8)
            response.raise_for_status()
            catalog = build_agent_catalog_from_api(response.json().get("data", []))
            if catalog:
                self._apply_catalog(catalog)
                return self.catalog
        except Exception:
            pass

        self._apply_fallback()
        return self.catalog

    def get_catalog(self) -> dict:
        return self.catalog

    def get_uuid(self, agent_name: str) -> str | None:
        return self.agents_by_name.get(agent_name) or AGENTS.get(agent_name)

    def get_name(self, agent_id: str) -> str | None:
        if not agent_id:
            return None
        return self.agents_by_uuid.get(str(agent_id).lower())

    def _apply_catalog(self, catalog: dict):
        self.catalog = catalog
        self.source = catalog["source"]
        self.agents_by_name = dict(catalog["agents_by_name"])
        self.agents_by_uuid = {value.lower(): name for name, value in self.agents_by_name.items()}

    def _apply_fallback(self):
        self.source = "fallback"
        self.catalog = build_agent_catalog_from_map(AGENTS, FALLBACK_AGENT_ROLES)
        self.agents_by_name = dict(AGENTS)
        self.agents_by_uuid = {value.lower(): name for name, value in AGENTS.items()}
