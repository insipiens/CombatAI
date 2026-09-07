from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from combatai.configuration_store import (
    DEFAULT_MINIMUM_LEAD,
    DEFAULT_MINIMUM_SCORE,
    load_document,
    save_document,
)


class ConfigurationStoreTests(unittest.TestCase):
    def test_legacy_microphone_configuration_gets_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"schema": 1, "microphone": {"device_id": 3, "name": "VR", "channels": 1}}),
                encoding="utf-8",
            )
            document = load_document(path)
        self.assertEqual(document["schema"], 2)
        self.assertEqual(document["microphone"]["name"], "VR")
        self.assertEqual(document["matching"]["minimum_score"], DEFAULT_MINIMUM_SCORE)
        self.assertEqual(document["matching"]["minimum_lead"], DEFAULT_MINIMUM_LEAD)
        self.assertEqual(document["ptt"], {"mode": "keyboard"})
        self.assertEqual(document["feedback"], {"audio_cues": True, "cue_volume": 0.25})

    def test_hotas_binding_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            document = load_document(path)
            document["ptt"] = {
                "mode": "hotas",
                "device_id": 7,
                "name": "Throttle",
                "guid": "0300abcd",
                "button": 47,
            }
            save_document(document, path)
            self.assertEqual(load_document(path)["ptt"]["button"], 47)

    def test_match_settings_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            document = load_document(path)
            document["matching"]["minimum_score"] = 0.20
            with self.assertRaisesRegex(ValueError, "between"):
                save_document(document, path)


if __name__ == "__main__":
    unittest.main()
