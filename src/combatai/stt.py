"""Local speech recognition through a pinned whisper.cpp executable."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

from .recording_test import _wav_bytes


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_NAME = "ggml-base.en.bin"


class WhisperCpp:
    def __init__(
        self,
        root: Path = PROJECT_ROOT,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.directory = root / "stt"
        self.executable = self.directory / "whisper-cli.exe"
        self.model = self.directory / MODEL_NAME
        self._runner = runner

    def validate(self) -> None:
        missing = [path for path in (self.executable, self.model) if not path.is_file()]
        if missing:
            raise OSError(
                "Local speech recognition is not installed. Run setup-stt.bat first."
            )

    def transcribe(self, pcm: bytes, *, prompt: str | None = None) -> str:
        self.validate()
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="CombatAI-", suffix=".wav", delete=False
            ) as temporary:
                temporary.write(_wav_bytes(pcm))
                temporary_path = Path(temporary.name)

            threads = min(8, os.cpu_count() or 4)
            command = [
                str(self.executable),
                "--model",
                str(self.model),
                "--file",
                str(temporary_path),
                "--language",
                "en",
                "--threads",
                str(threads),
                "--no-gpu",
                "--no-timestamps",
                "--no-prints",
            ]
            if prompt and prompt.strip():
                command.extend(("--prompt", prompt.strip()))
            result = self._runner(
                command,
                cwd=self.directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if result.returncode != 0:
                detail = result.stderr.strip().splitlines()
                reason = detail[-1] if detail else f"exit code {result.returncode}"
                raise OSError(f"whisper.cpp failed: {reason}")
            return " ".join(result.stdout.split())
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
