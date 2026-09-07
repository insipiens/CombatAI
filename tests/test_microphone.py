from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from combatai.microphone import (
    Microphone,
    _meter_fraction,
    _pcm16_level,
    display_labels,
    load_selection,
    save_selection,
)


class MicrophoneTests(unittest.TestCase):
    def test_pcm_silence_and_known_level(self) -> None:
        self.assertEqual(_pcm16_level(b"\x00\x00" * 8), 0.0)
        sample = (16384).to_bytes(2, "little", signed=True)
        self.assertAlmostEqual(_pcm16_level(sample * 8), 0.5)

    def test_meter_maps_decibels_to_visible_range(self) -> None:
        self.assertEqual(_meter_fraction(0.0), 0.0)
        self.assertAlmostEqual(_meter_fraction(0.001), 0.0)
        self.assertAlmostEqual(_meter_fraction(0.1), 2 / 3)
        self.assertEqual(_meter_fraction(1.0), 1.0)

    def test_duplicate_names_include_stable_device_id(self) -> None:
        devices = [
            Microphone(2, "Headset Microphone", 1),
            Microphone(7, "Headset Microphone", 2),
            Microphone(9, "Webcam", 1),
        ]
        self.assertEqual(
            display_labels(devices),
            [
                "Headset Microphone (Windows device 2)",
                "Headset Microphone (Windows device 7)",
                "Webcam",
            ],
        )

    def test_selection_round_trip_preserves_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"schema": 1, "future_setting": true}\n', encoding="utf-8")
            microphone = Microphone(4, "VR Headset", 1)
            self.assertEqual(save_selection(microphone, path), path)
            self.assertEqual(
                load_selection(path),
                {
                    "device_id": 4,
                    "name": "VR Headset",
                    "channels": 1,
                },
            )
            self.assertTrue(json.loads(path.read_text(encoding="utf-8"))["future_setting"])

    def test_unreadable_configuration_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("not json", encoding="utf-8")
            with self.assertRaisesRegex(OSError, "Refusing to overwrite"):
                save_selection(Microphone(0, "Mic", 1), path)
            self.assertEqual(path.read_text(encoding="utf-8"), "not json")


if __name__ == "__main__":
    unittest.main()
