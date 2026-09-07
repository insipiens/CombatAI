"""Capture one held-key utterance and transcribe it locally."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Sequence

from .microphone import WinMmAudioInput, load_selection, resolve_selection
from .recording_test import WindowsKeys, capture_while_space
from .stt import WhisperCpp


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture from the selected microphone and transcribe locally"
    )
    parser.add_argument("--maximum-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if args.maximum_seconds <= 0:
        parser.error("--maximum-seconds must be greater than zero")

    try:
        audio = WinMmAudioInput()
        microphone = resolve_selection(audio.microphones(), load_selection())
        keys = WindowsKeys()
        recognizer = WhisperCpp()
        recognizer.validate()

        print("CombatAI local transcription test")
        print(f"Microphone: {microphone.name}")
        print("Model: Whisper base.en (CPU)")
        print("\nHold SPACE and speak. Release SPACE to transcribe.")
        print("Press ESC before recording to cancel.\n")

        pcm = capture_while_space(
            audio, microphone, keys, maximum_seconds=args.maximum_seconds
        )
        print("Transcribing locally...", flush=True)
        started = time.monotonic()
        transcript = recognizer.transcribe(pcm)
        elapsed = time.monotonic() - started
        if transcript:
            print(f"\nHeard: {transcript}")
        else:
            print("\nNo speech was recognised.")
        print(f"Transcription time: {elapsed:.2f} seconds")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except OSError as exc:
        print(f"Transcription test failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
