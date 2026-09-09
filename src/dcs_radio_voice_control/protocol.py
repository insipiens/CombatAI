"""Versioned, deliberately small UDP protocol used by DCS Radio Voice Control and DCS."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Final

PROTOCOL_VERSION: Final = 1
MAX_DATAGRAM_BYTES: Final = 60_000
MAX_TEXT_LENGTH: Final = 512


class ProtocolError(ValueError):
    """Raised when a datagram is malformed or outside the accepted protocol."""


@dataclass(frozen=True, slots=True)
class MenuItem:
    action_id: str
    label: str
    path: tuple[str, ...]
    executable: bool = True
    slot: int | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> "MenuItem":
        if not isinstance(value, dict):
            raise ProtocolError("menu item must be an object")

        action_id = _short_string(value.get("action_id"), "action_id", 128)
        label = _short_string(value.get("label"), "label", MAX_TEXT_LENGTH)
        raw_path = value.get("path")
        if not isinstance(raw_path, list) or not raw_path or len(raw_path) > 16:
            raise ProtocolError("path must contain between 1 and 16 labels")
        path = tuple(_short_string(part, "path label", MAX_TEXT_LENGTH) for part in raw_path)
        executable = value.get("executable", True)
        if not isinstance(executable, bool):
            raise ProtocolError("executable must be boolean")
        slot = value.get("slot")
        if slot is not None and (
            not isinstance(slot, int)
            or isinstance(slot, bool)
            or not 1 <= slot <= 12
        ):
            raise ProtocolError("slot must be an integer from 1 to 12")
        return cls(
            action_id=action_id,
            label=label,
            path=path,
            executable=executable,
            slot=slot,
        )


@dataclass(frozen=True, slots=True)
class MenuSnapshot:
    revision: int
    items: tuple[MenuItem, ...]

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> "MenuSnapshot":
        if message.get("type") != "menu_snapshot":
            raise ProtocolError("message is not a menu snapshot")
        revision = message.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise ProtocolError("revision must be a non-negative integer")
        raw_items = message.get("items")
        if not isinstance(raw_items, list) or len(raw_items) > 1_000:
            raise ProtocolError("items must be a list containing at most 1000 entries")
        items = tuple(MenuItem.from_mapping(item) for item in raw_items)
        if len({item.action_id for item in items}) != len(items):
            raise ProtocolError("action_id values must be unique")
        return cls(revision=revision, items=items)


def encode_message(message_type: str, **fields: Any) -> bytes:
    """Encode one protocol message, enforcing the UDP payload limit."""
    message_type = _short_string(message_type, "message type", 64)
    message = {"v": PROTOCOL_VERSION, "type": message_type, **fields}
    try:
        payload = json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"message is not JSON serializable: {exc}") from exc
    if len(payload) > MAX_DATAGRAM_BYTES:
        raise ProtocolError(f"message exceeds {MAX_DATAGRAM_BYTES} bytes")
    return payload


def decode_message(payload: bytes) -> dict[str, Any]:
    """Decode and validate the common envelope of one received datagram."""
    if not payload:
        raise ProtocolError("empty datagram")
    if len(payload) > MAX_DATAGRAM_BYTES:
        raise ProtocolError(f"datagram exceeds {MAX_DATAGRAM_BYTES} bytes")
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("datagram is not valid UTF-8 JSON") from exc
    if not isinstance(message, dict):
        raise ProtocolError("message must be an object")
    if message.get("v") != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version: {message.get('v')!r}")
    _short_string(message.get("type"), "message type", 64)
    return message


def _short_string(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ProtocolError(f"{name} must be a non-empty string of at most {maximum} characters")
    return value
