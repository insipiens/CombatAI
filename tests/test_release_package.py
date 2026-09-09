from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.package_release import build_release


ROOT = Path(__file__).parents[1]


class ReleasePackageTests(unittest.TestCase):
    def test_release_has_stable_root_layout_without_developer_utilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "DCS-Radio-Voice-Control.zip"
            build_release(ROOT, output)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()

        self.assertEqual(len(names), len(set(names)))
        for required in (
            "INSTALLATION.md",
            "configuration.bat",
            "dcs/DCSRadioVoiceControl.radio_hook.lua",
            "install.bat",
            "run.bat",
            "setup.bat",
            "src/dcs_radio_voice_control/launcher.py",
            "tools/install.py",
            "uninstall.bat",
        ):
            self.assertIn(required, names)
        self.assertFalse(any(name.startswith("DCS-Radio-Voice-Control/") for name in names))
        self.assertFalse(any(name.startswith("tests/") for name in names))
        self.assertNotIn("tools/package_release.py", names)
        for diagnostic in (
            "matching-test.bat",
            "microphone.bat",
            "radio-menu-test.bat",
            "recording-test.bat",
            "transcription-test.bat",
            "voice-command-test.bat",
        ):
            self.assertNotIn(diagnostic, names)


if __name__ == "__main__":
    unittest.main()
