from __future__ import annotations

import json
import unittest

from combatai.protocol import (
    MAX_DATAGRAM_BYTES,
    MenuSnapshot,
    ProtocolError,
    decode_message,
    encode_message,
)


class ProtocolTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        payload = encode_message("get_menu", request_id="abc")
        self.assertEqual(
            decode_message(payload),
            {"v": 1, "type": "get_menu", "request_id": "abc"},
        )

    def test_rejects_wrong_version(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "unsupported protocol"):
            decode_message(b'{"v":2,"type":"status"}')

    def test_rejects_oversize_datagram(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "exceeds"):
            decode_message(b"x" * (MAX_DATAGRAM_BYTES + 1))

    def test_rejects_nan(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "not JSON serializable"):
            encode_message("test", value=float("nan"))

    def test_parses_snapshot(self) -> None:
        snapshot = MenuSnapshot.from_message(
            {
                "v": 1,
                "type": "menu_snapshot",
                "revision": 7,
                "items": [
                    {
                        "action_id": "f10.1",
                        "label": "Play recording",
                        "path": ["Briefing", "Play recording"],
                    }
                ],
            }
        )
        self.assertEqual(snapshot.revision, 7)
        self.assertEqual(snapshot.items[0].path[-1], "Play recording")

    def test_rejects_duplicate_actions(self) -> None:
        item = {"action_id": "f10.1", "label": "A", "path": ["A"]}
        with self.assertRaisesRegex(ProtocolError, "unique"):
            MenuSnapshot.from_message(
                {"type": "menu_snapshot", "revision": 1, "items": [item, item]}
            )

    def test_compact_encoding(self) -> None:
        payload = encode_message("status", state="mission_active")
        self.assertNotIn(b" ", payload)
        self.assertEqual(json.loads(payload)["state"], "mission_active")


if __name__ == "__main__":
    unittest.main()
