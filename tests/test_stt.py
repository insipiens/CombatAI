from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from combatai.stt import MODEL_NAME, WhisperCpp


class SttTests(unittest.TestCase):
    def test_installed_model_filename_is_configurable(self) -> None:
        recognizer = WhisperCpp(Path("test-root"), model_name="ggml-small.en.bin")
        self.assertEqual(recognizer.model.name, "ggml-small.en.bin")

    def test_missing_installation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recognizer = WhisperCpp(Path(directory))
            with self.assertRaisesRegex(OSError, "setup-stt.bat"):
                recognizer.validate()

    def test_transcription_uses_pinned_local_files_and_deletes_audio(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stt = root / "stt"
            stt.mkdir()
            (stt / "whisper-cli.exe").write_bytes(b"test")
            (stt / MODEL_NAME).write_bytes(b"test")

            def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append((command, kwargs))
                audio_path = Path(command[command.index("--file") + 1])
                self.assertTrue(audio_path.is_file())
                return subprocess.CompletedProcess(command, 0, " Contact air sea rescue.\n", "")

            transcript = WhisperCpp(root, runner=runner).transcribe(
                b"\x00\x00" * 160,
                prompt="DCS radio vocabulary: Wingman, Biggin Hill.",
            )

        self.assertEqual(transcript, "Contact air sea rescue.")
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertIn("--no-gpu", command)
        self.assertIn("--no-timestamps", command)
        self.assertEqual(
            command[command.index("--prompt") + 1],
            "DCS radio vocabulary: Wingman, Biggin Hill.",
        )
        self.assertEqual(kwargs["cwd"], stt)
        audio_path = Path(command[command.index("--file") + 1])
        self.assertFalse(audio_path.exists())


if __name__ == "__main__":
    unittest.main()
