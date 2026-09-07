"""Capture one utterance and propose a match from the live DCS catalogue."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Sequence

from .dcs_client import DcsMenuClient
from .matcher import MatchResult, build_vocabulary_prompt, match_catalogue
from .microphone import WinMmAudioInput, load_selection, resolve_selection
from .recording_test import WindowsKeys, capture_while_space
from .stt import WhisperCpp


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe one utterance and match it against the live DCS radio catalogue"
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

        print("CombatAI live command-matching test")
        print(f"Microphone: {microphone.name}")
        print("Waiting for the live DCS radio catalogue...", flush=True)
        with DcsMenuClient() as client:
            snapshot = client.request_menu_and_wait(timeout=3.0)
            if snapshot is None:
                raise OSError(
                    "DCS did not return a radio catalogue. Start DCS, enter a mission, "
                    "and close any other CombatAI console."
                )
            print(f"Catalogue revision {snapshot.revision}: {len(snapshot.items)} commands")
            print("\nHold SPACE and speak. Release SPACE to transcribe and match.")
            print("Press ESC before recording to cancel.\n")
            pcm = capture_while_space(
                audio, microphone, keys, maximum_seconds=args.maximum_seconds
            )

        print("Transcribing locally...", flush=True)
        started = time.monotonic()
        transcript = recognizer.transcribe(
            pcm,
            prompt=build_vocabulary_prompt(snapshot.items),
        )
        elapsed = time.monotonic() - started
        if not transcript:
            print("\nNo speech was recognised.")
            return 1
        print(f"\nHeard: {transcript}")
        print(f"Transcription time: {elapsed:.2f} seconds")
        _print_result(match_catalogue(transcript, snapshot.items))
        print("No command was sent to DCS.")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except OSError as exc:
        print(f"Command-matching test failed: {exc}", file=sys.stderr)
        return 2


def _print_result(result: MatchResult) -> None:
    if result.status == "matched":
        assert result.best is not None
        print(f"Matched: {' > '.join(result.best.item.path)}")
        print(f"Match score: {result.best.score:.0%}")
        return
    if result.status == "ambiguous":
        print("Ambiguous; possible matches:")
        for candidate in result.candidates:
            print(f"  - {' > '.join(candidate.item.path)} ({candidate.score:.0%})")
        return
    print("No sufficiently close live command was found.")


if __name__ == "__main__":
    raise SystemExit(main())
