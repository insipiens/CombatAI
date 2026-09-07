from __future__ import annotations

import unittest

from combatai.configuration_ui import PAGE


class ConfigurationUiTests(unittest.TestCase):
    def test_page_exposes_required_setup_controls(self) -> None:
        for label in (
            "Audio devices",
            "Microphone input",
            "Speech and cue output",
            "Recording device",
            "Learn a HOTAS button",
            "Minimum match",
            "Minimum lead over runner-up",
            "Installed Whisper model",
            "Use GPU acceleration",
            "Playback device",
            "Speech pace",
            "Test Alan voice",
            "Recent activity",
            "Audio feedback",
            "Test accepted cue",
            "__TOKEN__",
        ):
            self.assertIn(label, PAGE)


if __name__ == "__main__":
    unittest.main()
