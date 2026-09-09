from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from dcs_radio_voice_control.stt import MODEL_NAME, WhisperCpp, _multipart


class SttTests(unittest.TestCase):
    def test_installed_model_filename_is_configurable(self) -> None:
        recognizer = WhisperCpp(Path("test-root"), model_name="ggml-small.en.bin")
        self.assertEqual(recognizer.model.name, "ggml-small.en.bin")

    def test_missing_worker_or_model_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recognizer = WhisperCpp(Path(directory))
            with self.assertRaisesRegex(OSError, "setup-stt.bat"):
                recognizer.validate()

    def test_worker_and_model_are_validated_without_temp_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stt = root / "stt"
            stt.mkdir()
            (stt / "dcs_radio_voice_control-whisper.exe").write_bytes(b"test")
            (stt / MODEL_NAME).write_bytes(b"test")
            WhisperCpp(root).validate()
            self.assertEqual(list(root.glob("**/DCSRadioVoiceControl-*.wav")), [])

    def test_multipart_frames_prompt_and_in_memory_wave(self) -> None:
        body = _multipart(
            "boundary",
            {"response_format": "json", "prompt": "Wingman, Biggin Hill"},
            "audio.wav",
            b"RIFF-test",
        )
        self.assertIn(b'name="prompt"', body)
        self.assertIn(b"Wingman, Biggin Hill", body)
        self.assertIn(b"RIFF-test", body)
        self.assertTrue(body.endswith(b"--boundary--\r\n"))


if __name__ == "__main__":
    unittest.main()
