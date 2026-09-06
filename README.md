# CombatAI

CombatAI is intended to remove radio-menu interaction from DCS World mission play in VR.
Its eventual runtime path is HOTAS PTT, local speech recognition, deterministic command
routing, optional Gemini interpretation, DCS execution, and short local speech output.

This repository currently contains only the first technical proof: access to the live,
mission-generated F10 menu over localhost UDP. It does not yet contain STT, Gemini or TTS.

## Current proof of concept

The DCS Lua hook:

- reads `data.menuOther` inside the radio-dialogue environment;
- flattens selectable entries into paths without exporting functions or arbitrary DCS state;
- emits a new snapshot only when the menu changes;
- accepts only an action from the same live menu revision;
- calls `missionCommands.doAction` for that validated action;
- returns an explicit acceptance or rejection;
- binds its receiver to `127.0.0.1` only.

The Python console prints the menu and permits numbered selection. An `accepted` result means
that the Lua call completed; DCS does not expose whether the campaign script subsequently
produced its intended effect.

## Experimental Windows setup

This is a developer proof of concept, not a packaged release. It has passed its automated
protocol tests but has not yet passed the in-game acceptance test below. The procedure is
reversible and does not modify the DCS installation under `Program Files`.

There is no existing "router" to edit. The setup tool takes the radio-panel file that DCS
currently uses, appends the CombatAI hook to a generated copy, and places that copy at the
equivalent path under Saved Games. DCS then loads the Saved Games version.

### Requirements

- Windows 11 x64;
- DCS World;
- a local clone or extracted download of this repository;
- DCS and VAICOM closed while changing the Lua file.

Python does not need to be installed on Windows. Run `setup.bat` once. It downloads the
official CPython 3.13.15 x64 embeddable package into `CombatAI\runtime`, verifies the
published SHA-256 before extraction, and configures it to see only the application source and
standard library. It does not install Python system-wide, alter `PATH`, use the Microsoft
Store, or install `pip`.

```text
setup.bat
```

The pinned archive and checksum come from the
[official Python 3.13.15 release](https://www.python.org/downloads/release/python-31315/).
If an existing private runtime fails validation, setup refuses to overwrite it.

To run the automated checks with the private runtime:

```powershell
runtime\python.exe -m unittest discover -s tests -v
```

### Install the DCS hook

With DCS and VAICOM closed, run:

```powershell
install.bat
```

The installer searches the standard standalone and Steam DCS locations and the normal
`Saved Games\DCS` or `Saved Games\DCS.openbeta` directories. It then chooses its base file:

1. if a Saved Games radio-panel file exists, append CombatAI to that exact file so additions
   made by VAICOM or another mod are retained;
2. otherwise, copy the current DCS installation version and append CombatAI to the copy;
3. never alter the file under `Program Files`.

Before replacing anything, it saves the selected base under
`Saved Games\DCS\Scripts\CombatAI\backups`. It writes the generated panel atomically and
records the original and installed SHA-256 hashes in `Scripts\CombatAI\install.json`.

If automatic discovery finds no installation—or more than one—give the paths explicitly:

```powershell
install.bat `
  --dcs-install "C:\Program Files\Eagle Dynamics\DCS World" `
  --saved-games "$env:USERPROFILE\Saved Games\DCS"
```

For Steam, `--dcs-install` normally points to:

```text
C:\Program Files (x86)\Steam\steamapps\common\DCSWorld
```

CombatAI refuses a second installation, an unrecognised existing CombatAI modification, or
an ambiguous DCS directory. It does not guess which installation the user intended.

Check the installed state at any time:

```powershell
runtime\python.exe tools\install.py status
```

On a VAICOM system this is experimental coexistence. The two projects use different UDP
ports, but their update callbacks have not yet been tested together in DCS. Do not run
VAICOM's repair function during the test because it may regenerate the panel and remove the
CombatAI addition.

### Remove the DCS hook

With DCS and VAICOM closed, run:

```powershell
uninstall.bat
```

If there was an earlier Saved Games override, the installer restores it byte-for-byte. If
there was not, it removes the generated override so DCS returns to its Program Files version.
The backup and an archived removal manifest are retained.

Removal is deliberately refused when the active file has changed since installation. That
prevents CombatAI from overwriting a subsequent DCS, VAICOM, or third-party update. Inspect
or repair the installation manually in that case.

### Run the proof of concept

Start the Windows-side listener before entering a DCS mission:

```powershell
run.bat
```

Then start DCS and load a mission containing F10 options. The console should print the current
menu hierarchy. Enter its displayed number to invoke an item, `R` to request a new snapshot,
or `Q` to stop the console.

If no menu arrives:

1. confirm that a mission is running and the player is in an aircraft;
2. run `runtime\python.exe tools\install.py status` and confirm that `healthy` is `true`;
3. confirm that no other process is using UDP ports `34383` or `34384`;
4. inspect `Saved Games\DCS\Logs\dcs.log` for Lua, socket, JSON, or port-binding errors;
5. run the uninstall command if DCS radio operation behaves differently.

The repository does not distribute Eagle Dynamics' Lua implementation. Every generated
override is built from files already on the user's computer. It must be regenerated when DCS
or VAICOM changes the underlying radio-panel file.

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
2. display the actual current campaign F10 hierarchy;
3. detect a menu change without restarting;
4. reject a selection from the previous revision;
5. invoke a current entry and receive an acknowledgement;
6. recover after DCS or the Python console restarts.

Speech should be added only after this boundary has passed those checks.
