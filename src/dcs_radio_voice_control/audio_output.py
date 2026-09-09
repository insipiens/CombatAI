"""Low-latency in-memory audio playback through pygame-ce/SDL."""

from __future__ import annotations

import os
import threading


class AudioOutput:
    def __init__(self, device_name: str | None = None, *, buffer_size: int = 512) -> None:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        self.device_name = device_name or None
        self.buffer_size = buffer_size
        self._lock = threading.Lock()
        self._channel: object | None = None
        self._format: tuple[int, int, int] | None = None

    @staticmethod
    def devices() -> list[str]:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        from pygame._sdl2 import audio

        try:
            return list(audio.get_audio_device_names(False))
        except RuntimeError:
            return []

    def play_pcm(self, pcm: bytes, *, sample_rate: int, volume: float = 1.0) -> None:
        if not pcm:
            return
        import pygame

        with self._lock:
            wanted = (sample_rate, -16, 1)
            if self._format != wanted or pygame.mixer.get_init() != wanted:
                pygame.mixer.quit()
                pygame.mixer.init(
                    frequency=sample_rate,
                    size=-16,
                    channels=1,
                    buffer=self.buffer_size,
                    devicename=self.device_name,
                    allowedchanges=0,
                )
                actual = pygame.mixer.get_init()
                if actual != wanted:
                    pygame.mixer.quit()
                    raise OSError(
                        f"SDL changed the requested PCM format from {wanted} to {actual}"
                    )
                self._format = wanted
            sound = pygame.mixer.Sound(buffer=pcm)
            sound.set_volume(volume)
            self._channel = sound.play()

    def stop(self) -> None:
        import pygame

        with self._lock:
            channel = self._channel
            self._channel = None
            if channel is not None:
                getattr(channel, "stop")()
            elif pygame.mixer.get_init():
                pygame.mixer.stop()
