"""Small rotating human and JSONL logs for field diagnosis."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any


MAX_LOG_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3
_lock = threading.Lock()


def log_directory() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise OSError("Windows LOCALAPPDATA is not available.")
    return Path(root) / "CombatAI" / "logs"


def write_event(event: str, **fields: Any) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    document = {"timestamp": timestamp, "event": event, **fields}
    summary = fields.get("message") or _summary(event, fields)
    try:
        directory = log_directory()
        directory.mkdir(parents=True, exist_ok=True)
        with _lock:
            _rotate(directory / "events.jsonl")
            _rotate(directory / "combatai.log")
            with (directory / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(document, ensure_ascii=False) + "\n")
            with (directory / "combatai.log").open("a", encoding="utf-8") as stream:
                stream.write(f"{timestamp} {event}: {summary}\n")
    except OSError:
        # Diagnostics must never prevent a radio command from operating.
        return


def recent_events(limit: int = 100) -> list[dict[str, Any]]:
    path = log_directory() / "events.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except FileNotFoundError:
        return []
    except OSError:
        return []
    result: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def _rotate(path: Path) -> None:
    try:
        if path.stat().st_size < MAX_LOG_BYTES:
            return
    except FileNotFoundError:
        return
    oldest = path.with_name(path.name + f".{BACKUP_COUNT}")
    oldest.unlink(missing_ok=True)
    for index in range(BACKUP_COUNT - 1, 0, -1):
        source = path.with_name(path.name + f".{index}")
        if source.exists():
            os.replace(source, path.with_name(path.name + f".{index + 1}"))
    os.replace(path, path.with_name(path.name + ".1"))


def _summary(event: str, fields: dict[str, Any]) -> str:
    useful = ("transcript", "action", "reason", "revision", "command_count")
    parts = [f"{key}={fields[key]!r}" for key in useful if key in fields]
    return ", ".join(parts) if parts else event
