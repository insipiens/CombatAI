"""Small durable status record for the lightweight DCS Radio Voice Control controller."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


def state_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise OSError("Windows LOCALAPPDATA is not available.")
    return Path(root) / "DCSRadioVoiceControl" / "controller-status.json"


def set_state(state: str, message: str = "") -> None:
    target = state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.new")
    document = {
        "state": state,
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def get_state() -> dict[str, Any]:
    try:
        value = json.loads(state_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"state": "Not running", "message": ""}
    if not isinstance(value, dict) or not isinstance(value.get("state"), str):
        return {"state": "Not running", "message": ""}
    return value
