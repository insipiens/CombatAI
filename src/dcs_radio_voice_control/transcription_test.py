"""Capture one held-key utterance and transcribe it locally."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Sequence

from .configuration_store import load_document
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
        stt_settings = load_document()["stt"]
        recognizer = WhisperCpp(
            model_name=str(stt_settings["model"]),
            use_gpu=bool(stt_settings["use_gpu"]),
        )
        recognizer.start()

        print("DCS Radio Voice Control local transcription test")
        print(f"Microphone: {microphone.name}")
        print(
            f"Model: {recognizer.model.name} "
            f"({'GPU' if recognizer.use_gpu else 'CPU'})"
        )
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
        metrics = recognizer.last_metrics
        print(f"Real-time factor: {metrics['real_time_factor']:.3f}")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except OSError as exc:
        print(f"Transcription test failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
