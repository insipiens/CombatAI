"""Capture, match, and execute one tightly gated live DCS voice command."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Sequence

from .dcs_client import DcsMenuClient
from .matcher import MatchResult, RankedMatch, match_catalogue
from .matching_test import _print_result
from .microphone import WinMmAudioInput, load_selection, resolve_selection
from .recording_test import WindowsKeys, capture_while_space
from .stt import WhisperCpp


MINIMUM_EXECUTION_SCORE = 0.90


def execution_candidate(result: MatchResult) -> RankedMatch | None:
    if result.status != "matched" or result.best is None:
        return None
    if result.best.score < MINIMUM_EXECUTION_SCORE:
        return None
    if not result.best.item.executable:
        return None
    return result.best


def wait_for_catalogue(client: DcsMenuClient) -> None:
    attempts = 0
    while client.request_menu_and_wait(timeout=2.0) is None:
        attempts += 1
        if attempts == 1:
            print("DCS is not responding yet. Start DCS and enter a mission; Ctrl+C stops CombatAI.")
        elif attempts % 5 == 0:
            print("Still waiting for an active DCS mission ...")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute one unambiguous spoken command from the live DCS catalogue"
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

        print("CombatAI live voice-command test")
        print(f"Microphone: {microphone.name}")
        print("Waiting for the live DCS radio catalogue...", flush=True)
        with DcsMenuClient() as client:
            wait_for_catalogue(client)
            while True:
                snapshot = client.snapshot
                assert snapshot is not None
                print(f"\nCatalogue revision {snapshot.revision}: {len(snapshot.items)} commands")
                print("Hold SPACE and speak. Release SPACE to execute a safe match.")
                print("Press ESC while waiting to stop.\n")
                pcm = capture_while_space(
                    audio, microphone, keys, maximum_seconds=args.maximum_seconds
                )

                print("Transcribing locally...", flush=True)
                started = time.monotonic()
                transcript = recognizer.transcribe(pcm)
                elapsed = time.monotonic() - started
                if not transcript:
                    print("\nNo speech was recognised. Nothing was sent to DCS.")
                    continue
                print(f"\nHeard: {transcript}")
                print(f"Transcription time: {elapsed:.2f} seconds")
                match = match_catalogue(transcript, snapshot.items)
                _print_result(match)
                candidate = execution_candidate(match)
                if candidate is None:
                    if match.status == "matched" and match.best is not None:
                        print(
                            f"Match is below the {MINIMUM_EXECUTION_SCORE:.0%} execution threshold."
                        )
                    print("Nothing was sent to DCS.")
                    continue

                request_id = client.execute(candidate.item.action_id, snapshot.revision)
                result = client.wait_for_result(request_id)
                if result is None:
                    print("DCS did not acknowledge the command; execution state is unknown.")
                    continue
                if not result.accepted:
                    print(f"DCS rejected the command: {result.code}: {result.detail}")
                    continue
                print("DCS accepted the voice command.")
                wait_for_catalogue(client)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except OSError as exc:
        print(f"Voice-command test failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
