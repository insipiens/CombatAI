"""Windows microphone selection and a dependency-free input level meter."""

from __future__ import annotations

from array import array
import argparse
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Iterator, Protocol, Sequence


MMSYSERR_NOERROR = 0
WAVE_FORMAT_PCM = 1
WHDR_DONE = 0x00000001


@dataclass(frozen=True, slots=True)
class Microphone:
    device_id: int
    name: str
    channels: int


class AudioInput(Protocol):
    def microphones(self) -> list[Microphone]: ...

    def levels(self, device_id: int, seconds: float) -> Iterator[float]: ...


class WAVEINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * 32),
        ("dwFormats", wintypes.DWORD),
        ("wChannels", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
    ]


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    pass


WAVEHDR._fields_ = [
    ("lpData", ctypes.c_void_p),
    ("dwBufferLength", wintypes.DWORD),
    ("dwBytesRecorded", wintypes.DWORD),
    ("dwUser", ctypes.c_size_t),
    ("dwFlags", wintypes.DWORD),
    ("dwLoops", wintypes.DWORD),
    ("lpNext", ctypes.POINTER(WAVEHDR)),
    ("reserved", ctypes.c_size_t),
]


class WinMmAudioInput:
    """Small wrapper around the Windows waveform-audio input API."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Microphone setup is available only on Windows.")
        self._api = ctypes.WinDLL("winmm", use_last_error=True)
        self._declare_functions()

    def _declare_functions(self) -> None:
        self._api.waveInGetNumDevs.restype = wintypes.UINT
        self._api.waveInGetDevCapsW.argtypes = [
            ctypes.c_size_t,
            ctypes.POINTER(WAVEINCAPSW),
            wintypes.UINT,
        ]
        self._api.waveInGetDevCapsW.restype = wintypes.UINT
        self._api.waveInOpen.argtypes = [
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.UINT,
            ctypes.POINTER(WAVEFORMATEX),
            ctypes.c_size_t,
            ctypes.c_size_t,
            wintypes.DWORD,
        ]
        self._api.waveInOpen.restype = wintypes.UINT
        for name in ("waveInPrepareHeader", "waveInUnprepareHeader"):
            function = getattr(self._api, name)
            function.argtypes = [wintypes.HANDLE, ctypes.POINTER(WAVEHDR), wintypes.UINT]
            function.restype = wintypes.UINT
        self._api.waveInAddBuffer.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(WAVEHDR),
            wintypes.UINT,
        ]
        self._api.waveInAddBuffer.restype = wintypes.UINT
        for name in ("waveInStart", "waveInReset", "waveInClose"):
            function = getattr(self._api, name)
            function.argtypes = [wintypes.HANDLE]
            function.restype = wintypes.UINT

    def microphones(self) -> list[Microphone]:
        devices: list[Microphone] = []
        for device_id in range(self._api.waveInGetNumDevs()):
            caps = WAVEINCAPSW()
            result = self._api.waveInGetDevCapsW(
                device_id, ctypes.byref(caps), ctypes.sizeof(caps)
            )
            if result == MMSYSERR_NOERROR:
                devices.append(Microphone(device_id, caps.szPname, caps.wChannels))
        return devices

    def levels(self, device_id: int, seconds: float) -> Iterator[float]:
        sample_rate = 16_000
        samples_per_buffer = 1_600
        byte_count = samples_per_buffer * 2
        wave_format = WAVEFORMATEX(
            WAVE_FORMAT_PCM, 1, sample_rate, sample_rate * 2, 2, 16, 0
        )
        handle = wintypes.HANDLE()
        self._check(
            self._api.waveInOpen(
                ctypes.byref(handle),
                device_id,
                ctypes.byref(wave_format),
                0,
                0,
                0,
            ),
            "open microphone",
        )

        buffers = [ctypes.create_string_buffer(byte_count) for _ in range(4)]
        headers = [
            WAVEHDR(ctypes.addressof(buffer), byte_count, 0, 0, 0, 0, None, 0)
            for buffer in buffers
        ]
        prepared: list[WAVEHDR] = []
        try:
            for header in headers:
                self._check(
                    self._api.waveInPrepareHeader(
                        handle, ctypes.byref(header), ctypes.sizeof(header)
                    ),
                    "prepare capture buffer",
                )
                prepared.append(header)
                self._check(
                    self._api.waveInAddBuffer(
                        handle, ctypes.byref(header), ctypes.sizeof(header)
                    ),
                    "queue capture buffer",
                )
            self._check(self._api.waveInStart(handle), "start microphone")
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                emitted = False
                for buffer, header in zip(buffers, headers):
                    if header.dwFlags & WHDR_DONE:
                        emitted = True
                        payload = bytes(buffer[: header.dwBytesRecorded])
                        yield _pcm16_level(payload)
                        header.dwBytesRecorded = 0
                        self._check(
                            self._api.waveInAddBuffer(
                                handle, ctypes.byref(header), ctypes.sizeof(header)
                            ),
                            "requeue capture buffer",
                        )
                if not emitted:
                    time.sleep(0.01)
        finally:
            self._api.waveInReset(handle)
            for header in prepared:
                self._api.waveInUnprepareHeader(
                    handle, ctypes.byref(header), ctypes.sizeof(header)
                )
            self._api.waveInClose(handle)

    @staticmethod
    def _check(result: int, action: str) -> None:
        if result != MMSYSERR_NOERROR:
            raise OSError(f"Windows could not {action} (winmm error {result}).")


def _pcm16_level(payload: bytes) -> float:
    if len(payload) < 2:
        return 0.0
    samples = array("h")
    samples.frombytes(payload[: len(payload) - (len(payload) % 2)])
    if sys.byteorder != "little":
        samples.byteswap()
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    return min(1.0, math.sqrt(mean_square) / 32768.0)


def _meter_fraction(level: float) -> float:
    """Map -60..0 dBFS onto a visible 0..1 meter."""
    if level <= 0:
        return 0.0
    return max(0.0, min(1.0, (20 * math.log10(level) + 60) / 60))


def config_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise OSError("Windows LOCALAPPDATA is not available.")
    return Path(root) / "CombatAI" / "config.json"


def load_selection(path: Path | None = None) -> dict[str, object] | None:
    target = path or config_path()
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OSError(f"Cannot read microphone configuration {target}: {exc}") from exc
    microphone = document.get("microphone")
    return microphone if isinstance(microphone, dict) else None


def save_selection(microphone: Microphone, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, object] = {"schema": 1}
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                document.update(existing)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OSError(
                f"Refusing to overwrite unreadable configuration {target}: {exc}"
            ) from exc
    document["microphone"] = asdict(microphone)
    temporary = target.with_suffix(target.suffix + ".new")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return target


def display_labels(devices: Sequence[Microphone]) -> list[str]:
    counts: dict[str, int] = {}
    for device in devices:
        counts[device.name.casefold()] = counts.get(device.name.casefold(), 0) + 1
    return [
        f"{device.name} (Windows device {device.device_id})"
        if counts[device.name.casefold()] > 1
        else device.name
        for device in devices
    ]


def choose_microphone(
    devices: Sequence[Microphone], current: dict[str, object] | None
) -> Microphone:
    labels = display_labels(devices)
    current_identity = (
        (current.get("device_id"), current.get("name")) if current else (None, None)
    )
    print("\nWindows recording devices:\n")
    for index, (device, label) in enumerate(zip(devices, labels), 1):
        marker = (
            " [current]" if (device.device_id, device.name) == current_identity else ""
        )
        print(f"  {index}. {label}{marker}")
    while True:
        raw = input("\nChoose a microphone number, or Q to cancel: ").strip().lower()
        if raw == "q":
            raise KeyboardInterrupt
        try:
            return devices[int(raw) - 1]
        except (ValueError, IndexError):
            print("Enter one of the displayed numbers.")


def show_meter(audio: AudioInput, microphone: Microphone, seconds: float) -> None:
    print(f"\nInput level — {microphone.name}")
    print("Speak normally. The meter will run for " + f"{seconds:g} seconds.\n")
    width = 40
    for level in audio.levels(microphone.device_id, seconds):
        filled = round(_meter_fraction(level) * width)
        dbfs = 20 * math.log10(level) if level > 0 else -math.inf
        reading = f"{dbfs:6.1f} dBFS" if math.isfinite(dbfs) else "silence    "
        print(
            "\r[" + "#" * filled + "-" * (width - filled) + f"] {reading}",
            end="",
            flush=True,
        )
    print("\n")


def main(argv: Sequence[str] | None = None, *, audio: AudioInput | None = None) -> int:
    parser = argparse.ArgumentParser(description="Choose and test the CombatAI microphone")
    parser.add_argument(
        "--list", action="store_true", help="list devices without changing the selection"
    )
    parser.add_argument("--meter-seconds", type=float, default=8.0)
    args = parser.parse_args(argv)
    if args.meter_seconds <= 0:
        parser.error("--meter-seconds must be greater than zero")

    try:
        source = audio or WinMmAudioInput()
        devices = source.microphones()
        if not devices:
            print("Windows reported no recording devices.", file=sys.stderr)
            return 2
        current = load_selection()
        if args.list:
            for index, label in enumerate(display_labels(devices), 1):
                marker = (
                    " [current]"
                    if current
                    and (devices[index - 1].device_id, devices[index - 1].name)
                    == (current.get("device_id"), current.get("name"))
                    else ""
                )
                print(f"{index}. {label}{marker}")
            return 0
        selected = choose_microphone(devices, current)
        saved_to = save_selection(selected)
        print(f"\nSaved microphone: {selected.name}")
        print(f"Configuration: {saved_to}")
        show_meter(source, selected, args.meter_seconds)
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except OSError as exc:
        print(f"Microphone setup failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
