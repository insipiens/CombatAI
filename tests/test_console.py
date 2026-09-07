from __future__ import annotations

from contextlib import redirect_stdout
import io
from unittest import mock
import unittest

from combatai.console import _run
from combatai.protocol import MenuItem, MenuSnapshot


class _DisplayOnlyClient:
    def __init__(self) -> None:
        self.snapshot = MenuSnapshot(
            revision=3,
            items=(
                MenuItem(
                    action_id="radio.1.4.2",
                    label="Break Left",
                    path=("Wingman", "Maneuvers", "Break Left"),
                    executable=False,
                ),
            ),
        )
        self.execute_calls = 0

    def request_menu_and_wait(self, timeout: float = 2.0) -> MenuSnapshot:
        return self.snapshot

    def execute(self, action_id: str, revision: int) -> str:
        self.execute_calls += 1
        return "unexpected"


class ConsoleTests(unittest.TestCase):
    def test_display_only_item_never_reaches_dcs_execution(self) -> None:
        client = _DisplayOnlyClient()
        output = io.StringIO()
        with mock.patch("builtins.input", side_effect=["1", "q"]), redirect_stdout(output):
            result = _run(client)  # type: ignore[arg-type]

        self.assertEqual(result, 0)
        self.assertEqual(client.execute_calls, 0)
        self.assertIn("[display only]", output.getvalue())
        self.assertIn("execution is not enabled", output.getvalue())


if __name__ == "__main__":
    unittest.main()
