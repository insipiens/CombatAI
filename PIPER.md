# Piper development patch

This branch adds short local speech output and application-side spoken queries over the live DCS radio hierarchy.

## Setup

Run:

```bat
setup-tts.bat
```

The development setup downloads the pinned standalone Windows Piper build from the archived MIT-licensed `rhasspy/piper` release `2023.11.14-2`, plus the `en_GB-alan-medium` voice and config from `rhasspy/piper-voices` v1.0.0. The published voice-file MD5 values are checked after download.

The Piper release itself did not publish a digest for the Windows ZIP, so the binary archive cannot currently receive the same checksum verification used by CombatAI's Python and pygame bootstrap. This is acceptable for the development patch but should be resolved before packaging a release.

Then run the existing live voice-command test:

```bat
voice-command-test.bat
```

## Spoken application commands

These commands are handled by CombatAI and do not select anything in DCS:

- `List ATC commands`
- `List wingman commands`
- `List F10 commands`
- `List <any known menu node> commands`
- `Repeat`
- `Repeat please`
- `Say again`
- `Say again please`

A list query reconstructs the hierarchy from the flattened live DCS paths and speaks only the immediate children of the requested node. Responses are intentionally terse.

Pressing the configured HOTAS PTT (or Space in the development test) stops current Piper playback immediately before recording the new utterance.

Rejected near-matches with a plausible candidate are added to `%LOCALAPPDATA%\CombatAI\pending_aliases.json` as null mappings for later human review. They are never activated automatically.

Existing JSONL event logging records the meta-command, resolved node, children and spoken response during development.
