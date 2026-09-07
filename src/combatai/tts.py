"""Short local speech output through the standalone Piper executable."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading


class PiperSpeech:
    """Synthesize short responses and play them asynchronously on Windows."""

    def __init__(self, executable: Path | None = None, model: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.executable = executable or Path(
            os.environ.get("COMBATAI_PIPER_EXE", root / "tools" / "piper" / "piper" / "piper.exe")
        )
        self.model = model or Path(
            os.environ.get(
                "COMBATAI_PIPER_MODEL",
                root / "models" / "piper" / "en_GB-alan-medium.onnx",
            )
        )
        self._last_text: str | None = None
        self._last_wave: Path | None = None
        self._lock = threading.Lock()

    def validate(self) -> None:
        if sys.platform != "win32":
            raise OSError("Piper speech output is available only on Windows in this build.")
        if not self.executable.is_file():
            raise OSError(f"Piper executable not found: {self.executable}. Run setup-tts.bat.")
        if not self.model.is_file():
            raise OSError(f"Piper voice model not found: {self.model}. Run setup-tts.bat.")
        config = Path(str(self.model) + ".json")
        if not config.is_file():
            raise OSError(f"Piper voice configuration not found: {config}. Run setup-tts.bat.")

    @property
    def last_text(self) -> str | None:
        return self._last_text

    def speak(self, text: str) -> None:
        """Synthesize text, then begin asynchronous playback."""
        text = text.strip()
        if not text:
            return
        self.validate()
        self.stop()
        fd, filename = tempfile.mkstemp(prefix="combatai-tts-", suffix=".wav")
        os.close(fd)
        wave_path = Path(filename)
        try:
            completed = subprocess.run(
                [
                    str(self.executable),
                    "--model",
                    str(self.model),
                    "--output_file",
                    str(wave_path),
                    "--sentence_silence",
                    "0.08",
                    "--quiet",
                ],
                input=text + "\n",
                text=True,
                capture_output=True,
                timeout=15.0,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0 or not wave_path.is_file() or wave_path.stat().st_size < 44:
                detail = completed.stderr.strip() or f"exit code {completed.returncode}"
                raise OSError(f"Piper synthesis failed: {detail}")
            import winsound

            with self._lock:
                self._last_text = text
                self._last_wave = wave_path
                winsound.PlaySound(
                    str(wave_path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
        except Exception:
            wave_path.unlink(missing_ok=True)
            raise

    def repeat(self) -> bool:
        text = self.last_text
        if not text:
            return False
        self.speak(text)
        return True

    def stop(self) -> None:
        """Stop current playback immediately and retire its temporary WAV."""
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(None, 0)
        with self._lock:
            old_wave = self._last_wave
            self._last_wave = None
        if old_wave is not None:
            try:
                old_wave.unlink(missing_ok=True)
            except OSError:
                pass


class InterruptingPushToTalk:
    """Delegate PTT input while stopping speech at the instant PTT is pressed."""

    def __init__(self, ptt: object, speech: PiperSpeech) -> None:
        self._ptt = ptt
        self._speech = speech
        self.label = getattr(ptt, "label")

    def wait_for_press(self) -> None:
        getattr(self._ptt, "wait_for_press")()
        self._speech.stop()

    def is_down(self) -> bool:
        return bool(getattr(self._ptt, "is_down")())

    def flush(self) -> None:
        getattr(self._ptt, "flush")()
