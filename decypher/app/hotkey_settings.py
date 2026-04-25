"""Hotkey settings persistence for Decypher."""

from __future__ import annotations

import json

from decypher.app.hotkeys import DEFAULT_HOTKEYS, normalize_hotkey


class HotkeySettings:
    def __init__(self, config_path: str, defaults: dict[str, str] | None = None):
        self.config_path = config_path
        self.defaults = dict(defaults or DEFAULT_HOTKEYS)
        self.hotkeys = self._load()

    def _load(self) -> dict[str, str]:
        hotkeys = dict(self.defaults)
        try:
            with open(self.config_path, "r", encoding="utf-8") as config_file:
                config = json.load(config_file)
        except FileNotFoundError:
            return hotkeys
        except Exception:
            return hotkeys

        if isinstance(config, dict):
            for name, fallback in self.defaults.items():
                hotkeys[name] = normalize_hotkey(config.get(name), fallback)
        return hotkeys

    def get(self, name: str) -> str:
        return self.hotkeys[name]

    def has_conflict(self, name: str, hotkey: str) -> bool:
        return any(
            other_name != name and other_hotkey == hotkey
            for other_name, other_hotkey in self.hotkeys.items()
        )

    def set(self, name: str, hotkey: str) -> Exception | None:
        self.hotkeys[name] = hotkey
        return self.save()

    def save(self) -> Exception | None:
        config = {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as config_file:
                loaded_config = json.load(config_file)
            if isinstance(loaded_config, dict):
                config.update(loaded_config)
        except FileNotFoundError:
            pass
        except Exception:
            pass

        config.update(self.hotkeys)
        try:
            with open(self.config_path, "w", encoding="utf-8") as config_file:
                json.dump(config, config_file, indent=2)
                config_file.write("\n")
        except Exception as exc:
            return exc
        return None
