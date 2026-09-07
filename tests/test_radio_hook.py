from __future__ import annotations

from pathlib import Path
import re
import unittest


HOOK = Path(__file__).parents[1] / "dcs" / "CombatAI.radio_hook.lua"


class RadioHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = HOOK.read_text(encoding="utf-8")

    def test_reads_dynamic_root_and_limits_top_level_scope(self) -> None:
        self.assertIn("cai_submenu(data.rootItem)", self.source)
        self.assertRegex(
            self.source,
            r"local included_slots = \{1, 2, 3, 5, 10\}",
        )

    def test_sparse_menu_slots_are_sorted_before_traversal(self) -> None:
        self.assertIn("cai_numeric_keys(menu.items)", self.source)
        self.assertIn("cai_base.table.sort(keys)", self.source)
        self.assertNotIn("for index = 1, #menu.items do", self.source)

    def test_only_f10_action_indexes_enter_execution_map(self) -> None:
        executable_block = re.search(
            r'local executable = scope == "f10".*?items\[#items \+ 1\]',
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(executable_block)
        assert executable_block is not None
        self.assertIn("if executable then", executable_block.group())
        self.assertIn("actions[action_id] = item.command.actionIndex", executable_block.group())
        self.assertNotRegex(self.source, r"item\.command\s*:\s*perform")
        self.assertNotRegex(self.source, r"item\.command\.perform\s*\(")

    def test_execution_remains_mission_action_only(self) -> None:
        self.assertEqual(self.source.count("missionCommands.doAction(action)"), 1)


if __name__ == "__main__":
    unittest.main()
