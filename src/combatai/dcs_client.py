"""Reliable-enough request handling over local UDP.

UDP remains intentionally connectionless. Reliability comes from idempotent request IDs,
explicit replies, periodic menu requests, and rejecting stale menu selections.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import secrets
import socket
import time
from typing import Any

from .protocol import MenuSnapshot, ProtocolError, decode_message, encode_message

LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ActionResult:
    request_id: str
    accepted: bool
    code: str
    detail: str


class DcsMenuClient:
    """Owns the Windows side of the CombatAI localhost protocol."""

    def __init__(
        self,
        *,
        listen_host: str = "127.0.0.1",
        listen_port: int = 34384,
        dcs_host: str = "127.0.0.1",
        dcs_port: int = 34383,
    ) -> None:
        if listen_host != "127.0.0.1" or dcs_host != "127.0.0.1":
            raise ValueError("CombatAI v1 is restricted to localhost")
        self._dcs_address = (dcs_host, dcs_port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((listen_host, listen_port))
        self._socket.settimeout(0.25)
        self.snapshot: MenuSnapshot | None = None
        self.last_seen_monotonic: float | None = None
        self._results: dict[str, ActionResult] = {}
        self._pending: dict[str, bytes] = {}

    def close(self) -> None:
        self._socket.close()

    def __enter__(self) -> "DcsMenuClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request_menu(self) -> str:
        request_id = self._request_id()
        self._send("get_menu", request_id=request_id)
        return request_id

    def request_menu_and_wait(self, timeout: float = 2.0) -> MenuSnapshot | None:
        """Request a snapshot and wait until that response is actually observed."""
        self.request_menu()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.receive_once()
            if message is not None and message["type"] == "menu_snapshot":
                return self.snapshot
        return None

    def execute(self, action_id: str, revision: int) -> str:
        request_id = self._request_id()
        payload = self._send(
            "execute",
            request_id=request_id,
            action_id=action_id,
            revision=revision,
        )
        self._pending[request_id] = payload
        return request_id

    def receive_once(self) -> dict[str, Any] | None:
        try:
            payload, address = self._socket.recvfrom(65_535)
        except socket.timeout:
            return None
        if address[0] != "127.0.0.1":
            LOG.warning("Discarding non-local datagram from %s", address)
            return None
        try:
            message = decode_message(payload)
            self._consume(message)
        except ProtocolError as exc:
            LOG.warning("Discarding invalid DCS message: %s", exc)
            return None
        self.last_seen_monotonic = time.monotonic()
        return message

    def wait_for_result(
        self,
        request_id: str,
        timeout: float = 2.0,
        retry_interval: float = 0.4,
    ) -> ActionResult | None:
        deadline = time.monotonic() + timeout
        next_retry = time.monotonic() + retry_interval
        while time.monotonic() < deadline:
            existing = self._results.pop(request_id, None)
            if existing is not None:
                self._pending.pop(request_id, None)
                return existing
            self.receive_once()
            now = time.monotonic()
            if now >= next_retry:
                payload = self._pending.get(request_id)
                if payload is not None:
                    self._socket.sendto(payload, self._dcs_address)
                next_retry = now + retry_interval
        self._pending.pop(request_id, None)
        return self._results.pop(request_id, None)

    def _consume(self, message: dict[str, Any]) -> None:
        message_type = message["type"]
        if message_type == "menu_snapshot":
            self.snapshot = MenuSnapshot.from_message(message)
            return
        if message_type == "result":
            request_id = message.get("request_id")
            accepted = message.get("accepted")
            code = message.get("code")
            detail = message.get("detail", "")
            if not isinstance(request_id, str) or not request_id:
                raise ProtocolError("result has no valid request_id")
            if not isinstance(accepted, bool):
                raise ProtocolError("result accepted must be boolean")
            if not isinstance(code, str) or not code:
                raise ProtocolError("result has no valid code")
            if not isinstance(detail, str):
                raise ProtocolError("result detail must be a string")
            self._results[request_id] = ActionResult(request_id, accepted, code, detail)

    def _send(self, message_type: str, **fields: Any) -> bytes:
        payload = encode_message(message_type, **fields)
        self._socket.sendto(payload, self._dcs_address)
        return payload

    @staticmethod
    def _request_id() -> str:
        return secrets.token_hex(8)
