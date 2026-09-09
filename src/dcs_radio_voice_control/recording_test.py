"""Capture while Space is held, then play the audio back once."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from io import BytesIO
import math
import sys
import time
from typing import Protocol, Sequence
import wave

from .microphone import (
    Microphone,
    WinMmAudioInput,
    _pcm16_level,
    load_selection,
    resolve_selection,
)


VK_ESCAPE = 0x1B
VK_SPACE = 0x20
STD_INPUT_HANDLE = -10
SAMPLE_RATE = 16_000


class WindowsKeys:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("The recording test is available only on Windows.")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self._user32.GetAsyncKeyState.restype = ctypes.c_short
        self._kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        self._kernel32.GetStdHandle.restype = wintypes.HANDLE
        self._kernel32.FlushConsoleInputBuffer.argtypes = [wintypes.HANDLE]
        self._kernel32.FlushConsoleInputBuffer.restype = wintypes.BOOL

    def is_down(self, virtual_key: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(virtual_key) & 0x8000)

    def wait_for_space(self) -> None:
        while not self.is_down(VK_SPACE):
            if self.is_down(VK_ESCAPE):
                raise KeyboardInterrupt
            time.sleep(0.01)

    def flush_console_input(self) -> None:
        handle = self._kernel32.GetStdHandle(STD_INPUT_HANDLE)
        if handle and handle != wintypes.HANDLE(-1).value:
            self._kernel32.FlushConsoleInputBuffer(handle)


class PushToTalk(Protocol):
    label: str

    def wait_for_press(self) -> None: ...
    def is_down(self) -> bool: ...
    def flush(self) -> None: ...


class SpacePushToTalk:
    label = "SPACE"

    def __init__(self, keys: WindowsKeys) -> None:
        self.keys = keys

    def wait_for_press(self) -> None:
        self.keys.wait_for_space()

    def is_down(self) -> bool:
        return self.keys.is_down(VK_SPACE)

    def flush(self) -> None:
        self.keys.flush_console_input()


class SpaceOrHotasPushToTalk:
    """Use Space or one learned HOTAS button, latching the source per utterance."""

    def __init__(self, keys: WindowsKeys, hotas: object) -> None:
        self.keys = keys
        self.hotas = hotas
        self._active = ""
        self.label = f"SPACE or {getattr(hotas, 'label')}"

    def wait_for_press(self) -> None:
        self._active = ""
        while True:
            if self.keys.is_down(VK_ESCAPE):
                raise KeyboardInterrupt
            if self.keys.is_down(VK_SPACE):
                self._active = "space"
                return
            if getattr(self.hotas, "is_down")():
                self._active = "hotas"
                return
            time.sleep(0.01)

    def is_down(self) -> bool:
        if self._active == "space":
            return self.keys.is_down(VK_SPACE)
        if self._active == "hotas":
            return bool(getattr(self.hotas, "is_down")())
        return False

    def flush(self) -> None:
        self.keys.flush_console_input()


def _wav_bytes(pcm: bytes) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(SAMPLE_RATE)
        recording.writeframes(pcm)
    return output.getvalue()


def _play(pcm: bytes) -> None:
    import winsound

    # PlaySound is synchronous unless SND_ASYNC is explicitly supplied.
    winsound.PlaySound(_wav_bytes(pcm), winsound.SND_MEMORY)


def capture_while_space(
    audio: WinMmAudioInput,
    microphone: Microphone,
    keys: WindowsKeys,
    *,
    maximum_seconds: float,
) -> bytes:
    return capture_while_ptt(
        audio,
        microphone,
        SpacePushToTalk(keys),
        maximum_seconds=maximum_seconds,
    )


def capture_while_ptt(
    audio: WinMmAudioInput,
    microphone: Microphone,
    ptt: PushToTalk,
    *,
    maximum_seconds: float,
) -> bytes:
    ptt.wait_for_press()
    deadline = time.monotonic() + maximum_seconds
    chunks: list[bytes] = []
    captured_bytes = 0

    def keep_recording() -> bool:
        return ptt.is_down() and time.monotonic() < deadline

    for payload in audio.pcm_chunks(microphone.device_id, keep_recording):
        chunks.append(payload)
        captured_bytes += len(payload)
        duration = captured_bytes / (SAMPLE_RATE * 2)
        print(f"\rRecording... {duration:4.1f} seconds", end="", flush=True)

    ptt.flush()
    pcm = b"".join(chunks)
    duration = len(pcm) / (SAMPLE_RATE * 2)
    if duration < 0.1:
        raise OSError(f"No usable audio was captured; hold {ptt.label} for longer and try again.")
    level = _pcm16_level(pcm)
    dbfs = 20 * math.log10(level) if level > 0 else -math.inf
    print(f"\rCaptured {duration:.1f} seconds; average {dbfs:.1f} dBFS.          ")
    return pcm


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record from the selected DCS Radio Voice Control microphone and play it back"
    )
    parser.add_argument("--maximum-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if args.maximum_seconds <= 0:
        parser.error("--maximum-seconds must be greater than zero")

    try:
        audio = WinMmAudioInput()
        microphone = resolve_selection(audio.microphones(), load_selection())
        keys = WindowsKeys()
        print("DCS Radio Voice Control microphone recording test")
        print(f"Microphone: {microphone.name}")
        print("\nHold SPACE and speak. Release SPACE to hear the recording.")
        print("Press ESC before recording to cancel.\n")
        pcm = capture_while_space(
            audio, microphone, keys, maximum_seconds=args.maximum_seconds
        )
        print("Playing through the current Windows default output...\n")
        _play(pcm)
        print("Playback complete.")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except OSError as exc:
        print(f"Recording test failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
