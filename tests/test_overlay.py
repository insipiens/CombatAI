from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.build_radio_overlay import BEGIN_MARKER, build_overlay


class OverlayTests(unittest.TestCase):
    def test_builds_new_overlay_and_records_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.lua"
            hook = root / "hook.lua"
            destination = root / "Saved Games" / "panel.lua"
            source.write_bytes(b"return true\n")
            hook.write_bytes(BEGIN_MARKER + b"\nreturn true\n")

            digest = build_overlay(source, hook, destination)

            output = destination.read_bytes()
            self.assertIn(BEGIN_MARKER, output)
            self.assertIn(digest.encode("ascii"), output)

    def test_refuses_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.lua"
            hook = root / "hook.lua"
            destination = root / "panel.lua"
            source.write_bytes(b"return true\n")
            hook.write_bytes(BEGIN_MARKER + b"\n")
            destination.write_bytes(b"user-owned data")

            with self.assertRaises(FileExistsError):
                build_overlay(source, hook, destination)
            self.assertEqual(destination.read_bytes(), b"user-owned data")

    def test_refuses_already_patched_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.lua"
            hook = root / "hook.lua"
            source.write_bytes(BEGIN_MARKER)
            hook.write_bytes(BEGIN_MARKER)
            with self.assertRaisesRegex(ValueError, "already contains"):
                build_overlay(source, hook, root / "output.lua")


if __name__ == "__main__":
    unittest.main()
