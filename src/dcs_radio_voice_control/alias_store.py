"""Pending recognition aliases for later human review."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re


def pending_alias_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".dcs_radio_voice_control"
    return base / "DCSRadioVoiceControl" / "pending_aliases.json"


def pending_meta_alias_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".dcs_radio_voice_control"
    return base / "DCSRadioVoiceControl" / "pending_meta_aliases.json"


def _key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold())).strip()


def reviewed_aliases(path: Path | None = None) -> dict[str, str]:
    """Return all non-null, human-reviewed alias mappings."""
    target = path or pending_alias_path()
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        _key(str(name)): value.strip()
        for name, value in loaded.items()
        if _key(str(name)) and isinstance(value, str) and value.strip()
    }


def reviewed_alias(transcript: str, path: Path | None = None) -> str | None:
    """Return an exact, human-reviewed alias mapping; ignore null candidates."""
    return reviewed_aliases(path).get(_key(transcript))


def reviewed_meta_alias(transcript: str, path: Path | None = None) -> str | None:
    """Return a reviewed alias for an application-side spoken command."""
    return reviewed_alias(transcript, path or pending_meta_alias_path())


def record_pending_alias(transcript: str, path: Path | None = None) -> bool:
    """Add a phrase with a null mapping; never overwrite a reviewed mapping."""
    key = _key(transcript)
    if not key:
        return False
    target = path or pending_alias_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, str | None] = {}
    if target.exists():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = {
                    str(name): value
                    for name, value in loaded.items()
                    if value is None or isinstance(value, str)
                }
        except (OSError, json.JSONDecodeError):
            return False
    if key in data:
        return False
    data[key] = None
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    return True


def record_pending_meta_alias(transcript: str, path: Path | None = None) -> bool:
    """Record an unresolved application command separately from DCS action aliases."""
    return record_pending_alias(transcript, path or pending_meta_alias_path())
