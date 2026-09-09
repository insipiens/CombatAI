from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.build_radio_overlay import build_overlay
from tools.install import (
    InstallError,
    RELATIVE_PANEL,
    file_hash,
    install_hook,
    installation_preflight,
    installation_status,
    purge_installation,
    uninstall_hook,
    _windows_command_line,
)


HOOK = b"-- DCS RADIO VOICE CONTROL HOOK BEGIN\nreturn true\n"


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dcs = self.root / "DCS World"
        self.saved = self.root / "Saved Games" / "DCS"
        self.hook = self.root / "hook.lua"
        self.core = self.dcs / RELATIVE_PANEL
        self.saved_panel = self.saved / RELATIVE_PANEL
        self.original_core = b"-- DCS core\n"
        self.core.parent.mkdir(parents=True)
        self.core.write_bytes(self.original_core)
        self.hook.write_bytes(HOOK)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_clean_install_and_uninstall(self) -> None:
        manifest = install_hook(self.dcs, self.saved, self.hook)
        self.assertEqual(manifest["schema"], 2)
        self.assertEqual(manifest["base_kind"], "active_dcs_panel")
        self.assertIn(HOOK, self.core.read_bytes())
        self.assertFalse(self.saved_panel.exists())
        self.assertTrue(installation_status(self.dcs, self.saved)["healthy"])

        result = uninstall_hook(self.dcs, self.saved)
        self.assertEqual(result["outcome"], "restored_active_dcs_panel")
        self.assertEqual(self.core.read_bytes(), self.original_core)

    def test_full_purge_removes_saved_state_and_local_data(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        local_app_data = self.root / "LocalAppData"
        user_state = local_app_data / "DCSRadioVoiceControl"
        user_state.mkdir(parents=True)
        (user_state / "config.json").write_text("{}", encoding="utf-8")

        result = purge_installation(self.dcs, self.saved, local_app_data)

        self.assertEqual(result["outcome"], "restored_active_dcs_panel")
        self.assertEqual(self.core.read_bytes(), self.original_core)
        self.assertFalse((self.saved / "Scripts" / "DCSRadioVoiceControl").exists())
        self.assertFalse(user_state.exists())

    def test_full_purge_refuses_untracked_hook(self) -> None:
        self.core.write_bytes(self.original_core + HOOK)
        with self.assertRaisesRegex(InstallError, "no usable manifest"):
            purge_installation(self.dcs, self.saved, self.root / "LocalAppData")

    def test_install_refuses_the_former_combatai_hook(self) -> None:
        self.core.write_bytes(self.original_core + b"-- COMBATAI RADIO HOOK BEGIN\n")
        with self.assertRaisesRegex(InstallError, "former CombatAI hook"):
            install_hook(self.dcs, self.saved, self.hook)
        self.assertEqual(
            installation_preflight(self.dcs, self.saved, self.hook)["state"],
            "repair_required",
        )

    def test_preserves_and_restores_vaicom_in_active_panel(self) -> None:
        vaicom_core = self.original_core + b"-- VAICOM server-side script\n"
        self.core.write_bytes(vaicom_core)

        install_hook(self.dcs, self.saved, self.hook)
        self.assertTrue(self.core.read_bytes().startswith(vaicom_core.rstrip()))
        self.assertIn(HOOK, self.core.read_bytes())

        uninstall_hook(self.dcs, self.saved)
        self.assertEqual(self.core.read_bytes(), vaicom_core)

    def test_second_install_is_an_idempotent_update(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        result = install_hook(self.dcs, self.saved, self.hook)
        self.assertEqual(result["outcome"], "already_current")

    def test_preflight_distinguishes_install_current_and_update(self) -> None:
        self.assertEqual(
            installation_preflight(self.dcs, self.saved, self.hook)["state"],
            "install_required",
        )
        install_hook(self.dcs, self.saved, self.hook)
        self.assertEqual(
            installation_preflight(self.dcs, self.saved, self.hook)["state"],
            "current",
        )
        self.hook.write_bytes(HOOK + b"-- revised hook\n")
        self.assertEqual(
            installation_preflight(self.dcs, self.saved, self.hook)["state"],
            "update_required",
        )

    def test_preflight_requires_repair_for_changed_installed_panel(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        self.core.write_bytes(self.core.read_bytes() + b"-- external change\n")
        result = installation_preflight(self.dcs, self.saved, self.hook)
        self.assertEqual(result["state"], "repair_required")

    def test_installed_hook_can_be_updated_without_replacing_original_backup(self) -> None:
        first = install_hook(self.dcs, self.saved, self.hook)
        backup = Path(first["backup"])
        original_backup = backup.read_bytes()
        updated_hook = HOOK + b"-- revised hook\n"
        self.hook.write_bytes(updated_hook)

        result = install_hook(self.dcs, self.saved, self.hook)

        self.assertEqual(result["outcome"], "updated_active_dcs_panel")
        self.assertEqual(Path(result["backup"]), backup)
        self.assertEqual(backup.read_bytes(), original_backup)
        self.assertIn(updated_hook, self.core.read_bytes())
        self.assertTrue(installation_status(self.dcs, self.saved)["healthy"])
        uninstall_hook(self.dcs, self.saved)
        self.assertEqual(self.core.read_bytes(), self.original_core)

    def test_update_refuses_an_installed_panel_changed_elsewhere(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        self.core.write_bytes(self.core.read_bytes() + b"-- changed elsewhere\n")
        self.hook.write_bytes(HOOK + b"-- revised hook\n")

        with self.assertRaisesRegex(InstallError, "has changed"):
            install_hook(self.dcs, self.saved, self.hook)

        self.assertIn(b"changed elsewhere", self.core.read_bytes())

    def test_changed_target_is_not_overwritten_on_uninstall(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        self.core.write_bytes(self.core.read_bytes() + b"-- changed elsewhere\n")
        with self.assertRaisesRegex(InstallError, "has changed"):
            uninstall_hook(self.dcs, self.saved)
        self.assertIn(b"changed elsewhere", self.core.read_bytes())

    def test_manifest_contains_no_file_contents(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        manifest_path = self.saved / "Scripts" / "DCSRadioVoiceControl" / "install.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], 2)
        self.assertNotIn("content", manifest)

    def test_uninstall_rejects_redirected_backup(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        manifest_path = self.saved / "Scripts" / "DCSRadioVoiceControl" / "install.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["backup"] = str(self.core)
        manifest["base_sha256"] = manifest["installed_sha256"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(InstallError, "backup directory"):
            uninstall_hook(self.dcs, self.saved)

    def test_uninstall_rejects_different_dcs_install(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        other_dcs = self.root / "Other DCS"
        other_panel = other_dcs / RELATIVE_PANEL
        other_panel.parent.mkdir(parents=True)
        other_panel.write_bytes(self.original_core)

        with self.assertRaisesRegex(InstallError, "selected DCS installation"):
            uninstall_hook(other_dcs, self.saved)

    def test_windows_elevation_preserves_paths_with_spaces(self) -> None:
        command_line = _windows_command_line(
            ["C:\\Combat AI\\tools\\install.py", "install", "--dcs-install", "C:\\DCS World"]
        )
        self.assertIn('"C:\\Combat AI\\tools\\install.py"', command_line)
        self.assertIn('"C:\\DCS World"', command_line)

    def test_legacy_saved_games_install_is_migrated(self) -> None:
        vaicom_saved = b"-- VAICOM server-side script\n"
        self._create_legacy_install(vaicom_saved)

        manifest = install_hook(self.dcs, self.saved, self.hook)

        self.assertEqual(manifest["schema"], 2)
        self.assertEqual(self.saved_panel.read_bytes(), vaicom_saved)
        self.assertIn(HOOK, self.core.read_bytes())
        archives = list((self.saved / "Scripts" / "DCSRadioVoiceControl").glob("install.migrated.*.json"))
        self.assertEqual(len(archives), 1)

    def test_legacy_file_already_restored_by_vaicom_is_migrated(self) -> None:
        vaicom_saved = b"-- VAICOM server-side script\n"
        self._create_legacy_install(vaicom_saved)
        self.saved_panel.write_bytes(vaicom_saved)

        manifest = install_hook(self.dcs, self.saved, self.hook)

        self.assertEqual(manifest["schema"], 2)
        self.assertEqual(self.saved_panel.read_bytes(), vaicom_saved)
        self.assertIn(HOOK, self.core.read_bytes())

    def test_legacy_status_is_not_reported_as_healthy(self) -> None:
        self._create_legacy_install(b"-- VAICOM server-side script\n")

        status = installation_status(self.dcs, self.saved)

        self.assertTrue(status["legacy_install"])
        self.assertTrue(status["recorded_file_intact"])
        self.assertFalse(status["healthy"])
        self.assertFalse(status["target_matches_selected_install"])

    def test_legacy_uninstall_restores_saved_games_file(self) -> None:
        vaicom_saved = b"-- VAICOM server-side script\n"
        self._create_legacy_install(vaicom_saved)

        result = uninstall_hook(self.dcs, self.saved)

        self.assertEqual(result["outcome"], "restored_legacy_saved_games_override")
        self.assertEqual(self.saved_panel.read_bytes(), vaicom_saved)
        self.assertEqual(self.core.read_bytes(), self.original_core)

    def test_legacy_generated_override_is_removed_during_migration(self) -> None:
        self._create_legacy_install(self.original_core, base_kind="dcs_core")

        install_hook(self.dcs, self.saved, self.hook)

        self.assertFalse(self.saved_panel.exists())
        self.assertIn(HOOK, self.core.read_bytes())

    def test_changed_legacy_override_blocks_migration(self) -> None:
        self._create_legacy_install(b"-- VAICOM server-side script\n")
        self.saved_panel.write_bytes(self.saved_panel.read_bytes() + b"-- external change\n")

        with self.assertRaisesRegex(InstallError, "changed"):
            install_hook(self.dcs, self.saved, self.hook)

        self.assertEqual(self.core.read_bytes(), self.original_core)

    def _create_legacy_install(
        self, base: bytes, base_kind: str = "saved_games_override"
    ) -> None:
        state = self.saved / "Scripts" / "DCSRadioVoiceControl"
        backups = state / "backups"
        backups.mkdir(parents=True)
        self.saved_panel.parent.mkdir(parents=True, exist_ok=True)
        backup = backups / "RadioCommandDialogsPanel.legacy.lua"
        backup.write_bytes(base)
        source = self.root / "legacy-source.lua"
        source.write_bytes(base)
        build_overlay(source, self.hook, self.saved_panel)
        manifest = {
            "schema": 1,
            "installed_at": "2026-09-07T00:00:00+00:00",
            "dcs_install": str(self.dcs),
            "saved_games": str(self.saved),
            "target": str(self.saved_panel),
            "base_kind": base_kind,
            "base_sha256": file_hash(backup),
            "installed_sha256": file_hash(self.saved_panel),
            "backup": str(backup),
        }
        (state / "install.json").write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
