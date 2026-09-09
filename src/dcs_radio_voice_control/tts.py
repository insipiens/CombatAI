"""Interruptible local speech output through Piper raw PCM and SDL."""

from __future__ import annotations

import json
from pathlib import Path
import os
import subprocess
import sys
import threading

from .audio_output import AudioOutput


class PiperSpeech:
    """Synthesize responses off-thread and play PCM without temporary files."""

    def __init__(
        self,
        executable: Path | None = None,
        model: Path | None = None,
        *,
        output_device: str | None = None,
        output: AudioOutput | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        self.executable = executable or Path(
            os.environ.get("DCS_RADIO_VOICE_CONTROL_PIPER_EXE", root / "tools" / "piper" / "piper" / "piper.exe")
        )
        self.model = model or Path(
            os.environ.get("DCS_RADIO_VOICE_CONTROL_PIPER_MODEL", root / "models" / "piper" / "en_GB-alan-medium.onnx")
        )
        self.output = output or AudioOutput(output_device)
        self._last_text: str | None = None
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._generation = 0

    def validate(self) -> None:
        if sys.platform != "win32":
            raise OSError("Piper speech output is available only on Windows in this build.")
        if not self.executable.is_file():
            raise OSError(f"Piper executable not found: {self.executable}. Run setup-tts.bat.")
        if not self.model.is_file():
            raise OSError(f"Piper voice model not found: {self.model}. Run setup-tts.bat.")
        if not Path(str(self.model) + ".json").is_file():
            raise OSError("Piper voice configuration is missing. Run setup-tts.bat.")

    @property
    def last_text(self) -> str | None:
        return self._last_text

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.validate()
        self.stop()
        with self._lock:
            self._last_text = text
            self._generation += 1
            generation = self._generation
        threading.Thread(
            target=self._synthesize,
            args=(text, generation),
            name="DCS Radio Voice Control-Piper",
            daemon=True,
        ).start()

    def _synthesize(self, text: str, generation: int) -> None:
        process = subprocess.Popen(
            [
                str(self.executable),
                "--model", str(self.model),
                "--output-raw",
                "--quiet",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with self._lock:
            if generation != self._generation:
                process.terminate()
                return
            self._process = process
        pcm, error = process.communicate((text + "\n").encode("utf-8"))
        with self._lock:
            active = generation == self._generation
            if self._process is process:
                self._process = None
        if not active:
            return
        if process.returncode != 0:
            detail = error.decode("utf-8", "replace").strip() or f"exit code {process.returncode}"
            raise OSError(f"Piper synthesis failed: {detail}")
        self.output.play_pcm(pcm, sample_rate=self._sample_rate())

    def _sample_rate(self) -> int:
        config = json.loads(Path(str(self.model) + ".json").read_text(encoding="utf-8"))
        return int(config["audio"]["sample_rate"])

    def repeat(self) -> bool:
        text = self.last_text
        if not text:
            return False
        self.speak(text)
        return True

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            process = self._process
            self._process = None
        if process is not None and process.poll() is None:
            process.terminate()
        self.output.stop()


class InterruptingPushToTalk:
    """Delegate PTT input while stopping speech and synthesis on press."""

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
