from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def test_runtime_is_pinned_and_hash_verified(self) -> None:
        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn('$PythonVersion = "3.13.15"', setup)
        self.assertIn("https://www.python.org/ftp/python/3.13.15/", setup)
        match = re.search(r'\$PythonSha256 = "([0-9a-f]+)"', setup)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(len(match.group(1)), 64)
        self.assertIn("Get-FileHash", setup)
        self.assertNotIn("get-pip", setup.lower())

    def test_entry_points_use_only_private_python(self) -> None:
        for filename in (
            "install.bat",
            "configuration.bat",
            "microphone.bat",
            "recording-test.bat",
            "run.bat",
            "transcription-test.bat",
            "uninstall.bat",
        ):
            content = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("runtime\\python.exe", content, filename)
            self.assertNotIn("py -", content.lower(), filename)

    def test_sdl_controller_runtime_is_pinned_and_hash_verified(self) -> None:
        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn('$PygameVersion = "2.5.8"', setup)
        self.assertIn("pygame_ce-2.5.8-cp313-cp313-win_amd64.whl", setup)
        match = re.search(r'\$PygameSha256 = "([0-9a-f]+)"', setup)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(len(match.group(1)), 64)
        self.assertIn("pygame.version.ver", setup)

    def test_stt_setup_pins_worker_and_supported_models(self) -> None:
        setup = (ROOT / "setup-stt.ps1").read_text(encoding="utf-8")
        self.assertIn('$WhisperVersion = "b4938"', setup)
        self.assertIn("whisper-bin-x64.zip", setup)
        self.assertIn("whisper-cublas-12.4.0-bin-x64.zip", setup)
        self.assertIn('[ValidateSet("cpu", "cuda12")]', setup)
        self.assertIn("combatai-whisper.exe", setup)
        self.assertIn("whisper-server.exe", setup)
        self.assertIn("ggml-base.en.bin", setup)
        self.assertIn("ggml-small.en.bin", setup)
        self.assertIn("ggml-medium.en.bin", setup)
        self.assertGreaterEqual(setup.count("Get-FileHash"), 3)
        self.assertIn("System.Diagnostics.ProcessStartInfo", setup)
        self.assertEqual(setup.count("ReadToEndAsync()"), 2)
        self.assertNotIn("pip install", setup.lower())

    def test_installer_elevates_only_mutating_commands(self) -> None:
        installer = (ROOT / "tools" / "install.py").read_text(encoding="utf-8")
        self.assertIn('info.lpVerb = "runas"', installer)
        self.assertIn('args.command in ("install", "uninstall")', installer)

    def test_installer_starts_with_isolated_python_path(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(ROOT / "tools" / "install.py"), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
