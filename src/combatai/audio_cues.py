"""Brief non-verbal acknowledgement cues through the Windows default output."""

from __future__ import annotations

from array import array
from io import BytesIO
import math
import sys
from typing import Callable
import wave


SAMPLE_RATE = 16_000


def play_cue(
    outcome: str,
    *,
    volume: float = 0.25,
    player: Callable[[bytes], None] | None = None,
) -> bool:
    if outcome not in {"accepted", "rejected"}:
        raise ValueError("Cue outcome must be accepted or rejected")
    if not 0.0 <= volume <= 1.0:
        raise ValueError("Cue volume must be between zero and one")
    payload = _cue_wave(outcome, volume)
    try:
        if player is not None:
            player(payload)
        else:
            if sys.platform != "win32":
                return False
            import winsound

            winsound.PlaySound(payload, winsound.SND_MEMORY)
        return True
    except (OSError, RuntimeError):
        return False


def _cue_wave(outcome: str, volume: float) -> bytes:
    samples = array("h")
    if outcome == "accepted":
        _append_tone(samples, frequency=880.0, seconds=0.09, volume=volume)
    else:
        _append_tone(samples, frequency=330.0, seconds=0.07, volume=volume)
        samples.extend([0] * round(SAMPLE_RATE * 0.05))
        _append_tone(samples, frequency=330.0, seconds=0.07, volume=volume)
    output = BytesIO()
    with wave.open(output, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(SAMPLE_RATE)
        recording.writeframes(samples.tobytes())
    return output.getvalue()


def _append_tone(
    samples: array[int], *, frequency: float, seconds: float, volume: float
) -> None:
    count = round(SAMPLE_RATE * seconds)
    fade = max(1, round(SAMPLE_RATE * 0.008))
    amplitude = 32767 * volume
    for index in range(count):
        envelope = min(1.0, index / fade, (count - 1 - index) / fade)
        value = amplitude * envelope * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)
        samples.append(round(value))
