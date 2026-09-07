# CombatAI

CombatAI is intended to remove radio-menu interaction from DCS World mission play in VR.
Its eventual runtime path is HOTAS PTT, local speech recognition, deterministic command
routing, optional Gemini interpretation, DCS execution, and short local speech output.

This repository contains the first working vertical slice: access to selected live DCS
radio-menu branches over localhost UDP, Windows microphone capture, local speech recognition,
deterministic matching, guarded execution, and SDL HOTAS push-to-talk. It does not yet contain
Gemini or TTS.

## Current proof of concept

The DCS Lua hook currently exports the live Wingman, Flight, Second Element, ATC, and
mission-generated F10 branches. It:

- reads the already-instantiated `data.rootItem` inside the radio-dialogue environment;
- flattens selectable entries into paths without exporting functions or arbitrary DCS state;
- emits a new snapshot only when the menu changes;
- accepts only a validated action from the same live menu revision;
- drives standard commands through DCS's own menu-selection implementation;
- calls `missionCommands.doAction` for validated F10 actions;
- returns an explicit acceptance or rejection;
- binds its receiver to `127.0.0.1` only.

The Python console prints all in-scope branches and permits numbered selection. An `accepted`
result means that the Lua call completed; DCS does not expose whether the campaign script
subsequently produced its intended effect.

## Experimental Windows setup

This is a developer proof of concept, not a packaged release. It has passed its automated
protocol tests but has not yet passed the in-game acceptance test below. The procedure is
reversible, but it necessarily modifies one Lua file in the DCS installation under
`Program Files`.

There is no existing "router" to edit. Testing established that DCS does not load a
`Saved Games\DCS\Scripts\UI` copy of the radio panel. The setup tool therefore appends the
CombatAI hook to the active DCS installation file. Administrator permission is requested
only while installing or removing that hook; running CombatAI does not require elevation.

### Requirements

- Windows 11 x64;
- DCS World;
- a local clone or extracted download of this repository;
- DCS and VAICOM closed while changing the Lua file.

Python does not need to be installed on Windows. Run `setup.bat` once. It downloads the
official CPython 3.13.15 x64 embeddable package into `CombatAI\runtime`, verifies the
published SHA-256 before extraction, and configures it to see only the application source,
standard library, and a pinned pygame-ce wheel. pygame-ce supplies SDL controller access for
DirectInput/XInput HOTAS devices and is also checksum-verified. Setup does not install Python
system-wide, alter `PATH`, use the Microsoft Store, or install `pip`.

```text
.\setup.bat
```

The pinned archive and checksum come from the
[official Python 3.13.15 release](https://www.python.org/downloads/release/python-31315/).
If an existing private runtime fails validation, setup refuses to overwrite it.

To run the automated checks with the private runtime:

```powershell
.\runtime\python.exe -m unittest discover -s tests -v
```

### Install the DCS hook

With DCS and VAICOM closed, run:

```powershell
.\install.bat
```

Windows displays a User Account Control prompt because the active file is normally beneath
`Program Files`. The installer searches standard standalone and Steam locations and the
normal `Saved Games\DCS` or `Saved Games\DCS.openbeta` directories. It appends CombatAI to
the active radio-panel file exactly as found, so existing VAICOM additions are retained.

Before replacing anything, it saves that exact active file under
`Saved Games\DCS\Scripts\CombatAI\backups`. It writes the generated panel atomically and
records the original and installed SHA-256 hashes in `Scripts\CombatAI\install.json`.

Early CombatAI builds incorrectly generated an inactive Saved Games radio-panel override.
When its intact version-1 manifest is present, the corrected installer restores that file
from its recorded backup, archives the old manifest, and then performs the active
installation. It refuses migration if either the old target or backup has changed.

If automatic discovery finds no installation—or more than one—give the paths explicitly:

```powershell
.\install.bat `
  --dcs-install "C:\Program Files\Eagle Dynamics\DCS World" `
  --saved-games "$env:USERPROFILE\Saved Games\DCS"
```

For Steam, `--dcs-install` normally points to:

```text
C:\Program Files (x86)\Steam\steamapps\common\DCSWorld
```

CombatAI refuses a second active installation, an unrecognised existing CombatAI
modification, or an ambiguous DCS directory. It does not guess which installation the user
intended.

Check the installed state at any time:

```powershell
.\runtime\python.exe tools\install.py status
```

On a VAICOM system this is experimental coexistence. CombatAI backs up and extends the
VAICOM-modified active panel rather than replacing it with a stock DCS copy. The projects use
different UDP ports, but their update callbacks have not yet been tested together in DCS.
Do not run VAICOM's reset or repair function while CombatAI is installed because it will
regenerate the active panel and remove CombatAI's addition.

### Remove the DCS hook

With DCS and VAICOM closed, run:

```powershell
.\uninstall.bat
```

The uninstaller requests administrator permission and restores the exact active panel that
was backed up during installation. The backup and an archived removal manifest are retained.

Removal is deliberately refused when the active file has changed since installation. That
prevents CombatAI from overwriting a subsequent DCS, VAICOM, or third-party update. A DCS
update or VAICOM reset may therefore require inspection or repair rather than automatic
restoration.

### Run the proof of concept

Open the local configuration front end:

```powershell
.\configuration.bat
```

It opens `127.0.0.1:34385` in the default browser. The page selects and tests the recording
device, configures the command-match floor and required lead over the runner-up, chooses among
installed Whisper models, and learns a HOTAS button. HOTAS learning snapshots every attached
SDL controller and assigns the first newly pressed button after setup starts; controls already
held are ignored. Release completes the assignment, after which the page shows its live state.
Space remains available alongside a configured HOTAS button.

Settings remain under `%LOCALAPPDATA%\CombatAI\config.json`. The initial execution gate is a
70% text-similarity score with a 10-point lead over the next candidate. These are similarity
scores, not calibrated probabilities. The front end constrains both settings to bounded ranges.

CombatAI writes a readable rotating log and structured JSONL events beneath
`%LOCALAPPDATA%\CombatAI\logs`. Voice events include the transcript, top candidates, scores,
timings, selected action, menu revision, rejection reason, and DCS acknowledgement. Captured
audio is not logged or retained.

Choose the microphone CombatAI will use:

```powershell
.\microphone.bat
```

The command lists Windows recording inputs, saves the selected device under the current
Windows user's local application-data folder, and displays an eight-second live level meter.
It captures only the short-lived audio needed to calculate the meter; it does not save or
play back audio. Run it again whenever the desired device changes. To inspect devices without
changing the saved choice, use `.\microphone.bat --list`.

Test capture from the saved microphone:

```powershell
.\recording-test.bat
```

Hold the space bar while speaking and release it to hear the captured audio once through the
current Windows default output. The test keeps the recording only in memory and imposes a
30-second maximum. It does not yet recognise speech or invoke DCS actions.

Install the pinned local speech-recognition engine and English model, then test one utterance:

```powershell
.\transcription-test.bat
```

The first run downloads and verifies the official whisper.cpp Windows x64 build and the
`base.en` model (approximately 150 MiB combined). Hold the space bar while speaking and
release it to print the locally recognised text and elapsed transcription time. The temporary
WAV passed to the separate whisper.cpp process is deleted immediately afterward.

Speech recognition and the numbered radio console remain available as separate diagnostic
tests.

Test one spoken phrase against the current live catalogue:

```powershell
.\matching-test.bat
```

Close `run.bat` first because only one process can own CombatAI's UDP listener. The test
retrieves the current catalogue, records while Space is held, transcribes after release, and
prints either one proposed path, an ambiguity, or no match. It never sends an execution
request to DCS. Recipient names are significant: `break left` is ambiguous when the same
command exists under Wingman, Flight, and Second Element, while `wingman break left` is not.

Execute one tightly gated voice command against the live catalogue:

```powershell
.\voice-command-test.bat
```

Only an unambiguous match passing both configured gates is sent. DCS rebuilds and revalidates
the catalogue revision immediately before dispatch; a changed menu, ambiguity, weak or closely
competing match, or missing action is refused. The process waits for a mission, then remains
active for repeated commands until Escape or Ctrl+C. Each accepted command executes immediately
after recognition without asking for confirmation. Hold either the configured HOTAS button or
Space while speaking and release it to transcribe.

Before each transcription, CombatAI supplies whisper.cpp with a bounded, deduplicated vocabulary
prompt generated from the current live catalogue. This biases recognition toward current
recipient, airfield, command, and F10 names without rewriting particular transcription mistakes.

Start the Windows-side listener before entering a DCS mission:

```powershell
.\run.bat
```

Then start DCS and load a mission. The console should print the current Wingman, Flight,
Second Element, ATC, and F10 hierarchy. Enter an entry's number to invoke it, `R` to request
a new snapshot, or `Q` to stop the console.

If no menu arrives:

1. confirm that a mission is running and the player is in an aircraft;
2. run `.\runtime\python.exe tools\install.py status` and confirm that `healthy` is `true`;
3. confirm that DCS owns UDP port `34383` and CombatAI owns `34384`;
4. inspect `Saved Games\DCS\Logs\dcs.log` for Lua, socket, JSON, or port-binding errors;
5. run the uninstall command if DCS radio operation behaves differently.

The repository does not distribute Eagle Dynamics' Lua implementation. Every installed panel
is generated from the file already on the user's computer. CombatAI must be reinstalled after
DCS or VAICOM regenerates the underlying radio-panel file.

## Development check

Developers who already have Python 3.11 or newer can use it instead of the private runtime:

```powershell
py -3 -m pip install -e .
py -3 -m unittest discover -s tests -v
```

Default protocol ports are:

| Direction | Address |
|---|---|
| Python to DCS | `127.0.0.1:34383` |
| DCS to Python | `127.0.0.1:34384` |

These deliberately avoid the existing DCS Shaker port (`34382`) and VAICOM's ports.

## Immediate acceptance test

The proof is successful only when it can:

1. report that a mission is active;
2. display the current in-scope standard radio and campaign F10 hierarchy;
3. detect a menu change without restarting;
4. reject a selection from the previous revision;
5. invoke a current entry and receive an acknowledgement;
6. recover after DCS or the Python console restarts.

Speech should be added only after this boundary has passed those checks.
