from __future__ import annotations

import unittest

from combatai.configuration_ui import PAGE


class ConfigurationUiTests(unittest.TestCase):
    def test_page_exposes_required_setup_controls(self) -> None:
        self.assertIn("Recording device", PAGE)
        self.assertIn("Learn a HOTAS button", PAGE)
        self.assertIn("Minimum match", PAGE)
        self.assertIn("Minimum lead over runner-up", PAGE)
        self.assertIn("Installed Whisper model", PAGE)
        self.assertIn("Recent activity", PAGE)
        self.assertIn("__TOKEN__", PAGE)


if __name__ == "__main__":
    unittest.main()
