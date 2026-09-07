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

    def test_only_f10_action_indexes_use_mission_action_execution(self) -> None:
        f10_block = re.search(
            r'if scope == "f10" and item\.command\.actionIndex ~= nil then.*?else',
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(f10_block)
        assert f10_block is not None
        self.assertIn("action_index = item.command.actionIndex", f10_block.group())
        self.assertNotRegex(self.source, r"item\.command\s*:\s*perform")
        self.assertNotRegex(self.source, r"item\.command\.perform\s*\(")

    def test_f10_execution_remains_mission_action_only(self) -> None:
        self.assertEqual(
            self.source.count("missionCommands.doAction(action.action_index)"),
            1,
        )

    def test_standard_execution_uses_dcs_menu_selection(self) -> None:
        self.assertIn("commandDialogsPanel.switchToMainMenu(self)", self.source)
        self.assertIn("commandDialogsPanel.selectMenuItem(self, index)", self.source)

    def test_catalogue_is_recaptured_before_revision_validation(self) -> None:
        capture = self.source.index("cai_capture_menu(false)", self.source.index('message.type ~= "execute"'))
        validation = self.source.index("message.revision ~= cai_state.revision")
        self.assertLess(capture, validation)


if __name__ == "__main__":
    unittest.main()
