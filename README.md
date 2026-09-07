# CombatAI

CombatAI is a local, deterministic voice-control layer for DCS World. It lets a pilot hold a
HOTAS push-to-talk button, speak a command from the live DCS radio catalogue, and execute it
only when the match clears explicit safety thresholds.

The working path is:

```text
HOTAS PTT -> microphone PCM -> local whisper.cpp -> deterministic matcher
          -> revision-checked DCS action -> local Piper/SDL feedback
```

No cloud service or generative command interpretation is used. Audio stays on the machine,
and the live path does not write captured speech or synthesized responses to temporary files.

## Current behaviour

CombatAI currently provides:

- live command discovery from DCS over localhost UDP;
- standard radio and mission-generated commands from the active menu;
- guarded execution against the same live catalogue revision;
- safe recovery when the DCS menu changes during recognition;
- Windows microphone selection and SDL HOTAS push-to-talk;
- a persistent native whisper.cpp worker with the selected model kept resident;
- local `base.en`, `small.en`, and `medium.en` model choices;
- catalogue-derived Whisper vocabulary prompting;
- deterministic scoring with a configurable floor and runner-up lead;
- Piper's Alan voice as raw PCM, played from memory through SDL;
- selectable audio output, interruptible speech, and configurable speech pace;
- concise accepted/rejected cues through the same output device;
- rotating text and JSONL development logs.

An accepted result means the Lua action completed. DCS does not expose whether a mission
script subsequently produced its intended gameplay effect.

## Requirements

- Windows 11 x64;
- DCS World;
- a local clone or extracted download of this repository.

Python does not need to be installed. `setup.bat` downloads the official CPython 3.13
embeddable runtime, the pinned pygame-ce wheel, whisper.cpp, the selected Whisper model, and
Piper. Each downloaded artifact is verified before it is installed. Nothing is installed
system-wide, `PATH` is not changed, and `pip` is not required.

```powershell
.\setup.bat
```

The default speech-recognition model is `base.en`. Install another supported model only
when you want to compare it:

```powershell
.\setup-stt.bat small.en
.\setup-stt.bat medium.en

# Optional NVIDIA CUDA 12 worker; CPU remains the default
.\setup-stt.bat base.en cuda12
```

Only the requested model is downloaded. Installed models appear in the configuration page.

## Install the DCS hook

Close DCS before changing its radio-panel file, then run:

```powershell
.\install.bat
```

The installer requests administrator permission only for the DCS installation directory. It
finds standard standalone and Steam locations, backs up the exact active radio-panel file
under `Saved Games\DCS\Scripts\CombatAI\backups`, appends the CombatAI hook atomically,
and records hashes in `Scripts\CombatAI\install.json`.

If discovery finds no installation or more than one, provide both paths:

```powershell
.\install.bat `
  --dcs-install "C:\Program Files\Eagle Dynamics\DCS World" `
  --saved-games "$env:USERPROFILE\Saved Games\DCS"
```

CombatAI refuses an ambiguous installation, an unrecognised existing modification, or a
second active installation. Check the installed state with:

```powershell
.\runtime\python.exe tools\install.py status
```

To restore the exact file backed up during installation:

```powershell
.\uninstall.bat
```

Removal is refused if the active file changed after installation. This prevents CombatAI
from overwriting a DCS update or another later modification.

## Configure and run

Open the local configuration page:

```powershell
.\configuration.bat
```

The page is served only on `127.0.0.1:34385`. It configures and tests the microphone,
audio output, Alan speech pace, accepted/rejected cues, installed Whisper model, matching
thresholds, and HOTAS PTT binding. GPU recognition becomes available only after the pinned CUDA 12 worker is installed. It is
experimental so its latency and DCS resource impact can be measured on the target machine;
CPU remains the default.

Settings are stored in `%LOCALAPPDATA%\CombatAI\config.json`. Logs are stored beneath
`%LOCALAPPDATA%\CombatAI\logs`. JSONL recognition events include the model, CPU/GPU
mode, audio duration, inference time, real-time factor, model-load time, transcript, ranked
candidates, best and runner-up scores, acceptance or rejection, and DCS acknowledgement.
Captured audio is neither logged nor retained.

Start CombatAI before entering a DCS mission:

```powershell
.\voice-command-test.bat
```

Hold Space or the configured HOTAS button, speak, and release. A command is sent immediately
only when it clears both configured matching gates. PTT stops active SDL playback, terminates
Piper if synthesis is still running, discards that response, and starts microphone capture.

Useful local spoken commands include:

```text
List flight commands
List ATC commands
List mission commands
Repeat
```

List and repeat commands do not send a DCS action.

## Diagnostics

The individual diagnostics remain available:

```powershell
.\microphone.bat
.\recording-test.bat
.\transcription-test.bat
.\matching-test.bat
.\run.bat
```

Only one Windows process can own CombatAI's UDP listener. Close `run.bat` before starting a
matching or live voice-command test.

If no catalogue arrives, confirm that a mission is active, check installer status, verify
that DCS owns UDP port `34383` and CombatAI owns `34384`, then inspect
`Saved Games\DCS\Logs\dcs.log`.

The repository does not distribute Eagle Dynamics' Lua implementation. The installed panel
is generated from the file already present on the user's computer and must be reinstalled
after DCS replaces that file.

## Development

Developers with Python 3.11 or newer can install the project locally:

```powershell
py -3 -m pip install -e .
```

Protocol ports are:

| Direction | Address |
|---|---|
| Python to DCS | `127.0.0.1:34383` |
| DCS to Python | `127.0.0.1:34384` |

## Future work

Items 1-11 of the audio and recognition architecture plan are implemented in this revision.
The following work remains deliberately deferred until field measurements show that the new
pipeline is stable:

12. Add a light, configurable radio/intercom DSP effect to Alan while preserving
    intelligibility.
13. Carry explicit command provenance from Lua and search nested DCS menu nodes by normalized
    name, including the semantic mission-command source and its spoken `F10`/`Other`
    aliases.
14. Use the JSONL measurements from real sorties to decide whether GPU recognition and larger
    models improve command accuracy enough to justify their latency, RAM/VRAM use, and DCS
    contention.
15. Package the proven worker/runtime combination into a simpler end-user release after the
    in-cockpit acceptance pass.
