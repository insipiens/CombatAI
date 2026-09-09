from __future__ import annotations

import unittest

from dcs_radio_voice_control.audio_cues import _cue_pcm, play_cue


class AudioCueTests(unittest.TestCase):
    def test_accepted_and_rejected_cues_are_short_mono_pcm(self) -> None:
        accepted = _cue_pcm("accepted", 0.25)
        rejected = _cue_pcm("rejected", 0.25)
        self.assertLess(len(accepted), 6_400)
        self.assertGreater(len(rejected), len(accepted))
        self.assertEqual(len(accepted) % 2, 0)

    def test_player_receives_generated_pcm(self) -> None:
        payloads: list[bytes] = []
        self.assertTrue(play_cue("accepted", volume=0.4, player=payloads.append))
        self.assertTrue(payloads[0])
        self.assertNotEqual(payloads[0][:4], b"RIFF")

    def test_invalid_outcome_and_volume_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            play_cue("maybe")
        with self.assertRaises(ValueError):
            play_cue("accepted", volume=2.0)


if __name__ == "__main__":
    unittest.main()
