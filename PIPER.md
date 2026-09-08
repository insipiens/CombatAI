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

CombatAI does not override Piper's length scale, sentence silence, or other voice controls;
Alan uses the model's native synthesis settings. SDL's logical mixer format is locked to the
model's sample rate, and SDL converts to the output hardware without reinterpreting the PCM
at a higher rate.

The configuration page exposes the output device and a voice test. The model and
configuration files remain under `models\piper`; the executable remains under
`tools\piper`. No Python package, cloud request, or temporary WAV is involved.
