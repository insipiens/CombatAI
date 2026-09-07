# Piper speech in CombatAI

CombatAI uses the pinned standalone Piper Windows executable and the
`en_GB-alan-medium` voice. Setup downloads both from their upstream open-source releases
and verifies them before use.

The live path is entirely in memory:

```text
response text -> piper.exe --output-raw -> PCM memory -> pygame-ce/SDL -> selected output
```

Piper runs once per response so an utterance has an unambiguous end. Synthesis runs on a
background thread. Pressing PTT terminates an active Piper process, stops SDL playback, and
discards the interrupted PCM before microphone capture starts.

The configuration page exposes the output device, a voice test, and Piper's
`--length_scale`. The default is Piper's standard `1.00`; lower values speak faster and higher values speak slower. Configuration schema 5 returns the earlier `0.80` and `0.95` accelerated defaults to standard timing. Sentence silence is
`0.04` seconds for concise cockpit responses.

The model and configuration files remain under `models\piper`; the executable remains
under `tools\piper`. No Python package, cloud request, or temporary WAV is involved.
