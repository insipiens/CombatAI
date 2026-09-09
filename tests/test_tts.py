from __future__ import annotations

import unittest

from dcs_radio_voice_control.tts import InterruptingPushToTalk


class FakePtt:
    label = "TEST"

    def __init__(self) -> None:
        self.waited = False
        self.flushed = False

    def wait_for_press(self) -> None:
        self.waited = True

    def is_down(self) -> bool:
        return True

    def flush(self) -> None:
        self.flushed = True


class FakeSpeech:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class TtsTests(unittest.TestCase):
    def test_ptt_press_interrupts_speech_before_capture(self) -> None:
        ptt = FakePtt()
        speech = FakeSpeech()
        wrapped = InterruptingPushToTalk(ptt, speech)  # type: ignore[arg-type]
        wrapped.wait_for_press()
        self.assertTrue(ptt.waited)
        self.assertTrue(speech.stopped)
        self.assertTrue(wrapped.is_down())
        wrapped.flush()
        self.assertTrue(ptt.flushed)


if __name__ == "__main__":
    unittest.main()
