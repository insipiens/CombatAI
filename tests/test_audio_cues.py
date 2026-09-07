from __future__ import annotations

from io import BytesIO
import unittest
import wave

from combatai.audio_cues import _cue_wave, play_cue


class AudioCueTests(unittest.TestCase):
    def test_accepted_and_rejected_cues_are_short_mono_waves(self) -> None:
        accepted = _cue_wave("accepted", 0.25)
        rejected = _cue_wave("rejected", 0.25)
        with wave.open(BytesIO(accepted), "rb") as recording:
            self.assertEqual(recording.getnchannels(), 1)
            self.assertEqual(recording.getframerate(), 16_000)
            self.assertLess(recording.getnframes(), 3_200)
        self.assertGreater(len(rejected), len(accepted))

    def test_player_receives_generated_wave(self) -> None:
        payloads: list[bytes] = []
        self.assertTrue(play_cue("accepted", volume=0.4, player=payloads.append))
        self.assertEqual(payloads[0][:4], b"RIFF")

    def test_invalid_outcome_and_volume_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            play_cue("maybe")
        with self.assertRaises(ValueError):
            play_cue("accepted", volume=2.0)


if __name__ == "__main__":
    unittest.main()
