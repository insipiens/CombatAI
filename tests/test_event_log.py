from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dcs_radio_voice_control.event_log import recent_events, write_event


class EventLogTests(unittest.TestCase):
    def test_writes_human_and_structured_logs_under_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"LOCALAPPDATA": directory}
        ):
            write_event(
                "command_rejected",
                transcript="Wingman great left",
                reason="insufficient_lead",
                candidates=[{"score": 0.89}],
            )
            root = Path(directory) / "DCSRadioVoiceControl" / "logs"
            self.assertIn("command_rejected", (root / "dcs_radio_voice_control.log").read_text(encoding="utf-8"))
            document = json.loads((root / "events.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(document["transcript"], "Wingman great left")
            self.assertEqual(recent_events()[0]["reason"], "insufficient_lead")


if __name__ == "__main__":
    unittest.main()
