"""Capture, match, and execute one tightly gated live DCS voice command."""

from __future__ import annotations

import argparse
import math
import sys
import time
from typing import Sequence

from .dcs_client import DcsMenuClient
from .configuration_store import load_document
from .event_log import write_event
from .hotas import HotasButton, SdlHotasInput, resolve_binding
from .matcher import MatchResult, RankedMatch, build_vocabulary_prompt, match_catalogue
from .matching_test import _print_result
from .microphone import WinMmAudioInput, load_selection, resolve_selection
from .recording_test import (
    SAMPLE_RATE,
    SpaceOrHotasPushToTalk,
    SpacePushToTalk,
    WindowsKeys,
    capture_while_ptt,
)
from .microphone import _pcm16_level
from .stt import WhisperCpp


MINIMUM_EXECUTION_SCORE = 0.70
MINIMUM_EXECUTION_LEAD = 0.10


def execution_candidate(
    result: MatchResult,
    *,
    minimum_score: float = MINIMUM_EXECUTION_SCORE,
    minimum_lead: float = MINIMUM_EXECUTION_LEAD,
) -> RankedMatch | None:
    if result.status != "matched" or result.best is None:
        return None
    if result.best.score < minimum_score:
        return None
    ranked = result.ranked or result.candidates
    if len(ranked) > 1 and result.best.score - ranked[1].score < minimum_lead:
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
        settings = load_document()
        microphone = resolve_selection(audio.microphones(), load_selection())
        keys = WindowsKeys()
        stt_settings = settings["stt"]
        matching_settings = settings["matching"]
        ptt_settings = settings["ptt"]
        minimum_score = float(matching_settings["minimum_score"])
        minimum_lead = float(matching_settings["minimum_lead"])
        recognizer = WhisperCpp(model_name=str(stt_settings["model"]))
        recognizer.validate()
        if ptt_settings["mode"] == "hotas":
            hotas_source = SdlHotasInput()
            binding = resolve_binding(hotas_source.devices(), ptt_settings)
            ptt = SpaceOrHotasPushToTalk(keys, HotasButton(hotas_source, binding))
        else:
            ptt = SpacePushToTalk(keys)

        print("CombatAI live voice-command test")
        print(f"Microphone: {microphone.name}")
        print(f"Push to talk: {ptt.label}")
        print(f"Execution gate: {minimum_score:.0%} match, {minimum_lead:.0%} lead")
        print("Waiting for the live DCS radio catalogue...", flush=True)
        write_event(
            "session_started",
            microphone=microphone.name,
            ptt=ptt.label,
            model=str(stt_settings["model"]),
            minimum_score=minimum_score,
            minimum_lead=minimum_lead,
        )
        with DcsMenuClient() as client:
            wait_for_catalogue(client)
            while True:
                snapshot = client.snapshot
                assert snapshot is not None
                print(f"\nCatalogue revision {snapshot.revision}: {len(snapshot.items)} commands")
                print(f"Hold {ptt.label} and speak. Release it to execute a safe match.")
                print("Press ESC while waiting to stop.\n")
                pcm = capture_while_ptt(
                    audio, microphone, ptt, maximum_seconds=args.maximum_seconds
                )

                print("Transcribing locally...", flush=True)
                started = time.monotonic()
                transcript = recognizer.transcribe(
                    pcm,
                    prompt=build_vocabulary_prompt(snapshot.items),
                )
                elapsed = time.monotonic() - started
                duration = len(pcm) / (SAMPLE_RATE * 2)
                level = _pcm16_level(pcm)
                dbfs = 20 * math.log10(level) if level > 0 else None
                if not transcript:
                    print("\nNo speech was recognised. Nothing was sent to DCS.")
                    write_event(
                        "command_rejected",
                        reason="no_speech",
                        revision=snapshot.revision,
                        duration_seconds=round(duration, 3),
                        average_dbfs=round(dbfs, 2) if dbfs is not None else None,
                        transcription_seconds=round(elapsed, 3),
                    )
                    continue
                print(f"\nHeard: {transcript}")
                print(f"Transcription time: {elapsed:.2f} seconds")
                match = match_catalogue(transcript, snapshot.items)
                _print_result(match)
                candidate = execution_candidate(
                    match,
                    minimum_score=minimum_score,
                    minimum_lead=minimum_lead,
                )
                ranked = [
                    {
                        "action_id": ranked_match.item.action_id,
                        "path": list(ranked_match.item.path),
                        "score": round(ranked_match.score, 4),
                    }
                    for ranked_match in match.ranked[:5]
                ]
                if candidate is None:
                    if match.status == "matched" and match.best is not None:
                        if match.best.score < minimum_score:
                            reason = "below_minimum_score"
                            print(f"Match is below the configured {minimum_score:.0%} score.")
                        elif len(match.ranked) > 1:
                            lead = match.best.score - match.ranked[1].score
                            reason = "insufficient_lead"
                            runner_up = match.ranked[1]
                            print(
                                f"Best match leads the runner-up by {lead:.0%}; "
                                f"configured minimum is {minimum_lead:.0%}."
                            )
                            print(
                                "Runner-up: "
                                + " > ".join(runner_up.item.path)
                                + f" ({runner_up.score:.0%})"
                            )
                        else:
                            reason = "not_executable"
                    else:
                        reason = match.status
                    print("Nothing was sent to DCS.")
                    write_event(
                        "command_rejected",
                        reason=reason,
                        transcript=transcript,
                        revision=snapshot.revision,
                        candidates=ranked,
                        duration_seconds=round(duration, 3),
                        average_dbfs=round(dbfs, 2) if dbfs is not None else None,
                        transcription_seconds=round(elapsed, 3),
                    )
                    continue

                write_event(
                    "command_sent",
                    transcript=transcript,
                    action=" > ".join(candidate.item.path),
                    action_id=candidate.item.action_id,
                    score=round(candidate.score, 4),
                    revision=snapshot.revision,
                    candidates=ranked,
                    duration_seconds=round(duration, 3),
                    average_dbfs=round(dbfs, 2) if dbfs is not None else None,
                    transcription_seconds=round(elapsed, 3),
                )
                request_id = client.execute(candidate.item.action_id, snapshot.revision)
                result = client.wait_for_result(request_id)
                if result is None:
                    print("DCS did not acknowledge the command; execution state is unknown.")
                    write_event("dcs_result", reason="timeout", action_id=candidate.item.action_id)
                    continue
                if not result.accepted:
                    print(f"DCS rejected the command: {result.code}: {result.detail}")
                    write_event(
                        "dcs_result",
                        reason=result.code,
                        message=result.detail,
                        action_id=candidate.item.action_id,
                    )
                    continue
                print("DCS accepted the voice command.")
                write_event("dcs_result", action_id=candidate.item.action_id, accepted=True)
                wait_for_catalogue(client)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except OSError as exc:
        print(f"Voice-command test failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
