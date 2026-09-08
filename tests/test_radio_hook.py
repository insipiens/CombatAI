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
            r"local included_slots = \{1, 2, 3, 5, 8, 10\}",
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

    def test_submenus_are_exported_as_non_executable_navigation_nodes(self) -> None:
        self.assertIn('action_id = menu_id', self.source)
        self.assertIn('executable = false', self.source)
        self.assertIn('["menu.root"] = {indexes = {}}', self.source)

    def test_open_menu_uses_a_separate_revision_checked_operation(self) -> None:
        self.assertIn('message.type ~= "execute"', self.source)
        self.assertIn('message.type ~= "open_menu"', self.source)
        self.assertIn('message.type ~= "menu_control"', self.source)
        self.assertIn('local menu = cai_state.menus[message.menu_id]', self.source)
        self.assertIn('accepted_code = "menu_opened"', self.source)
        self.assertIn("setShowMenu(true)", self.source)
        capture = self.source.index("cai_capture_menu(false)", self.source.index('message.type ~= "execute"'))
        validation = self.source.index("message.revision ~= cai_state.revision")
        lookup = self.source.index("cai_state.menus[message.menu_id]")
        self.assertLess(capture, validation)
        self.assertLess(validation, lookup)

    def test_menu_controls_use_dcs_navigation_without_executable_actions(self) -> None:
        self.assertIn('message.type == "menu_control"', self.source)
        self.assertIn('message.operation ~= "previous"', self.source)
        self.assertIn('message.operation ~= "exit"', self.source)
        self.assertIn("commandDialogsPanel.selectMenuItem(self, 11)", self.source)
        self.assertIn("setShowMenu(false)", self.source)
        self.assertIn('"previous_menu"', self.source)
        self.assertIn('"menu_closed"', self.source)

    def test_catalogue_is_recaptured_before_revision_validation(self) -> None:
        capture = self.source.index("cai_capture_menu(false)", self.source.index('message.type ~= "execute"'))
        validation = self.source.index("message.revision ~= cai_state.revision")
        self.assertLess(capture, validation)


if __name__ == "__main__":
    unittest.main()
