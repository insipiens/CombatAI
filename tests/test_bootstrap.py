from __future__ import annotations

from pathlib import Path
import re
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
        for filename in ("install.bat", "run.bat", "uninstall.bat"):
            content = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("runtime\\python.exe", content, filename)
            self.assertNotIn("py -", content.lower(), filename)


if __name__ == "__main__":
    unittest.main()
