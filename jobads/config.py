"""config.json and api_key.json (PRD §5)."""

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "low"
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


class ConfigError(Exception):
    """A configuration file is missing or invalid. The message is shown to the user."""


@dataclass
class CommunitySettings:
    display_name: str = ""
    whatsapp_group: str = ""


@dataclass
class Config:
    path: Path
    active_community: str = ""
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    communities: dict[str, CommunitySettings] = field(default_factory=dict)

    def community(self, folder: str) -> CommunitySettings:
        return self.communities.get(folder, CommunitySettings())

    def set_active_community(self, folder: str) -> None:
        """Save the chosen community to config.json, keeping everything else in the file."""
        self.active_community = folder
        self._update_file(lambda raw: raw.__setitem__("active_community", folder))

    def set_whatsapp_group(self, folder: str, group: str) -> None:
        """Save a community's WhatsApp distribution group to config.json."""
        self.communities.setdefault(folder, CommunitySettings()).whatsapp_group = group

        def update(raw: dict) -> None:
            communities = raw.setdefault("communities", {})
            communities.setdefault(folder, {})["whatsapp_group"] = group

        self._update_file(update)

    def _update_file(self, change) -> None:
        """Change config.json, keeping everything else in the file as it is."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            raw = {}
        change(raw)
        self.path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"הקובץ {path.name} חסר.\n{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        raise ConfigError(f"הקובץ {path.name} אינו קובץ JSON תקין:\n{e}") from e
    except OSError as e:
        raise ConfigError(f"לא ניתן לקרוא את הקובץ {path.name}:\n{e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"הקובץ {path.name} צריך להכיל אובייקט JSON ({{...}}).")
    return data


def _str(data: dict, key: str, default: str, file_name: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"בקובץ {file_name}, השדה \"{key}\" צריך להיות טקסט.")
    return value.strip()


def load_config(path: Path) -> Config:
    data = _read_json(path)
    name = path.name
    effort = _str(data, "effort", DEFAULT_EFFORT, name) or DEFAULT_EFFORT
    if effort not in EFFORT_LEVELS:
        raise ConfigError(f"בקובץ {name}, הערך של \"effort\" צריך להיות אחד מ: {', '.join(EFFORT_LEVELS)}.")

    communities_raw = data.get("communities", {})
    if not isinstance(communities_raw, dict):
        raise ConfigError(f"בקובץ {name}, השדה \"communities\" צריך להיות אובייקט.")
    communities = {}
    for folder, entry in communities_raw.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"בקובץ {name}, הקהילה \"{folder}\" צריכה להיות אובייקט.")
        communities[folder] = CommunitySettings(
            display_name=_str(entry, "display_name", "", name),
            whatsapp_group=_str(entry, "whatsapp_group", "", name),
        )

    return Config(
        path=path,
        active_community=_str(data, "active_community", "", name),
        model=_str(data, "model", DEFAULT_MODEL, name) or DEFAULT_MODEL,
        effort=effort,
        communities=communities,
    )


def load_api_key(path: Path) -> str:
    data = _read_json(path)
    key = data.get("api_key")
    if not isinstance(key, str) or not key.strip():
        raise ConfigError(f"בקובץ {path.name} חסר השדה \"api_key\".")
    return key.strip()
