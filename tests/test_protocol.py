from __future__ import annotations

import json
import unittest

from dcs_radio_voice_control.protocol import (
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
                        "slot": 7,
                    }
                ],
            }
        )
        self.assertEqual(snapshot.revision, 7)
        self.assertEqual(snapshot.items[0].path[-1], "Play recording")
        self.assertTrue(snapshot.items[0].executable)
        self.assertEqual(snapshot.items[0].slot, 7)

    def test_rejects_invalid_function_key_slot(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "slot"):
            MenuSnapshot.from_message(
                {
                    "type": "menu_snapshot",
                    "revision": 1,
                    "items": [
                        {
                            "action_id": "radio.1",
                            "label": "Invalid",
                            "path": ["Invalid"],
                            "slot": 13,
                        }
                    ],
                }
            )

    def test_parses_display_only_standard_radio_item(self) -> None:
        snapshot = MenuSnapshot.from_message(
            {
                "v": 1,
                "type": "menu_snapshot",
                "revision": 8,
                "items": [
                    {
                        "action_id": "radio.1.4.2",
                        "label": "Break Left",
                        "path": ["Wingman", "Maneuvers", "Break Left"],
                        "executable": False,
                    }
                ],
            }
        )
        self.assertFalse(snapshot.items[0].executable)

    def test_rejects_non_boolean_executable_flag(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "executable"):
            MenuSnapshot.from_message(
                {
                    "type": "menu_snapshot",
                    "revision": 1,
                    "items": [
                        {
                            "action_id": "radio.1",
                            "label": "Break Left",
                            "path": ["Wingman", "Break Left"],
                            "executable": "no",
                        }
                    ],
                }
            )

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
