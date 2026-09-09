from __future__ import annotations

import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dcs_radio_voice_control.audio_output import AudioOutput


class FakeSound:
    def set_volume(self, volume: float) -> None:
        self.volume = volume

    def play(self) -> object:
        return object()


class FakeMixer:
    def __init__(self, *, forced_frequency: int | None = None) -> None:
        self.actual: tuple[int, int, int] | None = None
        self.forced_frequency = forced_frequency
        self.init_arguments: dict[str, object] = {}
        self.sound_created = False

    def get_init(self) -> tuple[int, int, int] | None:
        return self.actual

    def quit(self) -> None:
        self.actual = None

    def init(self, **arguments: object) -> None:
        self.init_arguments = arguments
        frequency = self.forced_frequency or int(arguments["frequency"])
        self.actual = (frequency, int(arguments["size"]), int(arguments["channels"]))

    def Sound(self, *, buffer: bytes) -> FakeSound:
        self.sound_created = True
        return FakeSound()

    def stop(self) -> None:
        pass


class AudioOutputTests(unittest.TestCase):
    def test_pcm_rate_cannot_be_changed_by_sdl(self) -> None:
        mixer = FakeMixer()
        pygame = SimpleNamespace(mixer=mixer)
        with patch.dict(sys.modules, {"pygame": pygame}):
            AudioOutput().play_pcm(b"\x00\x00", sample_rate=22_050)

        self.assertEqual(mixer.init_arguments["allowedchanges"], 0)
        self.assertEqual(mixer.actual, (22_050, -16, 1))
        self.assertTrue(mixer.sound_created)

    def test_unexpected_mixer_format_is_rejected_before_playback(self) -> None:
        mixer = FakeMixer(forced_frequency=48_000)
        pygame = SimpleNamespace(mixer=mixer)
        with patch.dict(sys.modules, {"pygame": pygame}):
            with self.assertRaisesRegex(OSError, "changed the requested PCM format"):
                AudioOutput().play_pcm(b"\x00\x00", sample_rate=22_050)

        self.assertFalse(mixer.sound_created)


if __name__ == "__main__":
    unittest.main()
