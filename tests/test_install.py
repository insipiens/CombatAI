from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.install import InstallError, RELATIVE_PANEL, install_hook, installation_status, uninstall_hook


HOOK = b"-- COMBATAI RADIO HOOK BEGIN\nreturn true\n"


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dcs = self.root / "DCS World"
        self.saved = self.root / "Saved Games" / "DCS"
        self.hook = self.root / "hook.lua"
        self.core = self.dcs / RELATIVE_PANEL
        self.target = self.saved / RELATIVE_PANEL
        self.core.parent.mkdir(parents=True)
        self.core.write_bytes(b"-- DCS core\n")
        self.hook.write_bytes(HOOK)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_clean_install_and_uninstall(self) -> None:
        manifest = install_hook(self.dcs, self.saved, self.hook)
        self.assertEqual(manifest["base_kind"], "dcs_core")
        self.assertIn(HOOK, self.target.read_bytes())
        self.assertTrue(installation_status(self.saved)["healthy"])

        result = uninstall_hook(self.saved)
        self.assertEqual(result["outcome"], "removed_generated_override")
        self.assertFalse(self.target.exists())

    def test_preserves_and_restores_existing_override(self) -> None:
        vaicom = b"-- VAICOM server-side script\n"
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(vaicom)

        manifest = install_hook(self.dcs, self.saved, self.hook)
        self.assertEqual(manifest["base_kind"], "saved_games_override")
        self.assertTrue(self.target.read_bytes().startswith(vaicom))
        self.assertIn(HOOK, self.target.read_bytes())

        result = uninstall_hook(self.saved)
        self.assertEqual(result["outcome"], "restored_saved_games_override")
        self.assertEqual(self.target.read_bytes(), vaicom)

    def test_second_install_is_rejected(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        with self.assertRaisesRegex(InstallError, "active installation manifest"):
            install_hook(self.dcs, self.saved, self.hook)

    def test_changed_target_is_not_overwritten_on_uninstall(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        self.target.write_bytes(self.target.read_bytes() + b"-- changed elsewhere\n")
        with self.assertRaisesRegex(InstallError, "has changed"):
            uninstall_hook(self.saved)
        self.assertIn(b"changed elsewhere", self.target.read_bytes())

    def test_manifest_contains_no_file_contents(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        manifest_path = self.saved / "Scripts" / "CombatAI" / "install.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], 1)
        self.assertNotIn("content", manifest)

    def test_uninstall_rejects_redirected_backup(self) -> None:
        install_hook(self.dcs, self.saved, self.hook)
        manifest_path = self.saved / "Scripts" / "CombatAI" / "install.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["backup"] = str(self.core)
        manifest["base_sha256"] = manifest["installed_sha256"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(InstallError, "backup directory"):
            uninstall_hook(self.saved)


if __name__ == "__main__":
    unittest.main()
