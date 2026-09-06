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

## Development check

The Windows-side proof has no third-party Python dependencies:

```powershell
py -3.13 -m pip install -e .
py -3.13 -m unittest discover -s tests -v
py -3.13 -m combatai
```

## DCS integration status

The hook is designed to be appended to the user's own installed
`Scripts\UI\RadioCommandDialogPanel\RadioCommandDialogsPanel.lua`. The generated file then
shadows that same relative path under `Saved Games\DCS\Scripts`.

`tools\build_radio_overlay.py` performs this composition atomically and refuses to overwrite
an existing Saved Games override. This refusal is intentional: VAICOM currently owns that
path on systems where it is installed. The first in-game test therefore requires an explicit
test profile or a separately agreed migration procedure; the tool will not silently replace
VAICOM or any other mod.

The repository does not distribute Eagle Dynamics' Lua implementation. A generated override
must be built from the user's locally installed DCS version, and it must be regenerated after
the source file changes.

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
