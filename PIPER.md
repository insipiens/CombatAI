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
discards the interrupted PCM before microphone capture starts. SDL's logical mixer format is
locked to the voice model's sample rate; SDL converts to the output hardware without
reinterpreting the PCM at a higher rate and changing Alan's pitch.

The configuration page exposes the output device, a voice test, and Piper's
`--length_scale`. The default is `0.95`; lower values speak faster. Configuration schema 4 migrates the earlier `0.80` default once because it made Alan sound unnaturally accelerated. Sentence silence is
`0.04` seconds for concise cockpit responses.

The model and configuration files remain under `models\piper`; the executable remains
under `tools\piper`. No Python package, cloud request, or temporary WAV is involved.
