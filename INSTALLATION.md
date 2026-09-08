# CombatAI installation guide

This guide assumes no programming knowledge. It covers installation, configuration, the
first test in DCS, updates, and safe removal.

## What CombatAI installs

CombatAI adds a small hook to DCS's radio-menu file and keeps the rest of the software in the
CombatAI folder. It downloads its own private Python runtime, local Whisper speech recognition,
and the Alan speech voice. It does not require a separate Python installation, does not change
the Windows `PATH`, and does not send recorded speech to a cloud service.

## Before you begin

You need:

- Windows 11 on a 64-bit PC;
- DCS World already installed;
- an internet connection for the first setup;
- a microphone;
- a HOTAS button if you want one for push-to-talk (the Space key also works); and
- permission to approve a Windows administrator prompt when the DCS hook is installed.

Launch DCS at least once before installing CombatAI. This creates the DCS folder under
`Saved Games`, which the installer needs. Then close DCS before continuing.

## 1. Download and extract CombatAI

1. Download the CombatAI ZIP supplied for the version you want to install.
2. Open your Downloads folder in File Explorer.
3. Right-click the ZIP and select **Extract All**.
4. Choose a permanent, easy-to-find location, such as `C:\CombatAI`.
5. Open the extracted folder and check that it contains `install.bat`, `configuration.bat`,
   and `run.bat`.

Do not run CombatAI from inside the ZIP preview. Do not put it in `Program Files`. Keep the
extracted folder after installation: it contains the program and is also needed for safe
updates and removal.

If Windows shows an **Unblock** checkbox in the ZIP's **Properties** window, select it before
extracting. This can prevent Windows from marking every extracted script as downloaded from
the internet.

## 2. Open PowerShell in the CombatAI folder

The easiest method is:

1. Open the extracted CombatAI folder in File Explorer.
2. Click the address bar at the top of the window.
3. Type `powershell` and press Enter.

A blue or black PowerShell window will open. Its prompt should end with the name of your
CombatAI folder, for example:

```text
PS C:\CombatAI>
```

Leave this window open for the following commands. You can paste a command into PowerShell
and press Enter to run it.

## 3. Install CombatAI

Make sure DCS is closed, then run:

```powershell
.\install.bat
```

The first run downloads and verifies the private runtime, SDL controller support, Whisper's
`base.en` model, and the Alan voice. The speech model alone is about 142 MiB, so this stage can
take several minutes. Later runs reuse files that are already valid.

Windows will ask whether the installer may make changes to the computer. Approve this prompt.
Administrator access is used to update the DCS program file; the other CombatAI files remain
in the extracted folder or your own user folders.

When installation succeeds, PowerShell prints JSON containing an `outcome`. On a first install
this describes the installed DCS panel. When applying a later CombatAI patch it may instead say
`updated_active_dcs_panel` or `already_current`.

### If DCS is in the usual location

No path is normally needed. CombatAI checks these locations:

- `C:\Program Files\Eagle Dynamics\DCS World`
- `C:\Program Files\Eagle Dynamics\DCS World OpenBeta`
- `C:\Program Files (x86)\Steam\steamapps\common\DCSWorld`

### If DCS is elsewhere, including another Steam library

Run the installer with the actual DCS folder. The correct folder is the one containing DCS's
`bin` and `Scripts` folders.

For a Steam installation, open Steam's **Library**, right-click **DCS World Steam Edition**,
select **Manage > Browse local files**, and copy the folder path from File Explorer's address
bar. For a standalone installation, right-click the DCS shortcut, select **Properties**, and
use the installation folder shown in the **Target** field rather than the path to the `.exe`
itself.

For example:

```powershell
.\install.bat `
  --dcs-install "D:\SteamLibrary\steamapps\common\DCSWorld" `
  --saved-games "$env:USERPROFILE\Saved Games\DCS"
```

The backtick at the end of the first two lines tells PowerShell that the command continues on
the next line. You may instead put the whole command on one line:

```powershell
.\install.bat --dcs-install "D:\SteamLibrary\steamapps\common\DCSWorld" --saved-games "$env:USERPROFILE\Saved Games\DCS"
```

Use `DCS.openbeta` instead of `DCS` in the Saved Games path if that is the folder DCS created.
Providing both paths is also the solution if CombatAI reports that it found more than one DCS
installation or more than one Saved Games DCS folder.

## 4. Verify the DCS hook

Run:

```powershell
.\runtime\python.exe .\tools\install.py status
```

A healthy installation includes these values:

```json
{
  "healthy": true,
  "installed": true,
  "recorded_file_intact": true,
  "target_matches_selected_install": true
}
```

There will be additional path and hash fields; that is normal. If `healthy` is `false`, do not
manually replace the DCS Lua file. Keep the complete status output for troubleshooting.

If you used explicit paths while installing, use the same options when checking status:

```powershell
.\runtime\python.exe .\tools\install.py status --dcs-install "D:\SteamLibrary\steamapps\common\DCSWorld" --saved-games "$env:USERPROFILE\Saved Games\DCS"
```

## 5. Configure your microphone, sound, and push-to-talk

Run:

```powershell
.\configuration.bat
```

Your browser should open the local configuration page. If it does not, open
`http://127.0.0.1:34385/` yourself. The page exists only on your PC while the configuration
window is running.

On the page:

1. Select your recording device and click **Run three-second level test**. Speak at your normal
   cockpit volume and confirm that the test reports a signal rather than silence.
2. Select the playback device on which you want to hear Alan and the accepted/rejected cues.
   Use **Test Alan voice** and the two cue-test buttons.
3. Under **Push to talk**, click **Learn a HOTAS button**, then press and release the button you
   want. If you do not want to use a controller, click **Use Space only**.
4. Leave the default `base.en`, CPU, and command-matching settings selected for the first test.
5. Click **Save configuration** and wait for the message **Configuration saved.**

You can now close the browser tab and press Ctrl+C in the configuration PowerShell window.
Configuration is stored at `%LOCALAPPDATA%\CombatAI\config.json` and is kept when you update
the source files.

## 6. Run CombatAI in DCS

1. In PowerShell, from the CombatAI folder, run:

   ```powershell
   .\run.bat
   ```

2. Leave that PowerShell window open.
3. Start DCS and enter a mission in which the radio menu is available. CombatAI will wait for a
   live DCS command catalogue.
4. Hold your configured HOTAS button, or Space, speak a command, and then release the button.

For the first flight, start with commands that are easy to observe and do not trigger an
aircraft action:

```text
List commands
List ATC commands
Show F10
```

`List` makes Alan speak the immediate choices without changing the on-screen DCS menu. `Show`
opens the requested DCS menu without speaking its choices. You can use another `Show` command
to move into a displayed submenu, then say a displayed leaf command to execute it.

For example:

```text
Show ATC
```

Opens the DCS **F5 ATC** menu.

```text
Show Biggin Hill
```

Opens the **Biggin Hill** submenu within ATC.

```text
Request Start-Up
```

Executes the displayed command.

To move back up or close the displayed menu:

```text
Previous Menu
```

Selects DCS's displayed **F11 Previous Menu** control.

```text
Exit Menu
```

Selects DCS's **F12 Exit** behaviour and closes the radio menu. You may also say `F11`, `Back`,
`F12`, or `Close Menu` respectively.

`Repeat` only says Alan's last spoken response again, principally after a `List` request. It
never sends or repeats a DCS action. If Alan has not spoken, CombatAI reports `Nothing spoken
to repeat.`

CombatAI sends a command only when the recognition result passes both configured safety gates.
An accepted response confirms that DCS ran the menu action; a mission script can still decide
what gameplay effect follows.

To stop CombatAI, return to its PowerShell window and press Ctrl+C.

## Everyday use

For each session:

1. Run `.\run.bat` from the CombatAI folder.
2. Start DCS and enter the mission.
3. Leave the CombatAI window open while flying.
4. Press Ctrl+C in that window when finished.

Only one CombatAI test or runner can listen to DCS at a time. Close any earlier CombatAI
PowerShell window before starting another one.

## Applying a CombatAI update or patch

You normally do **not** need to uninstall CombatAI first.

1. Close DCS and CombatAI.
2. Extract the new ZIP to a temporary folder and open it. If the ZIP created an extra outer
   folder, open that too, until you can see `install.bat`.
3. Select everything in that folder, copy it, and paste it into your existing CombatAI folder.
   Choose **Replace the files in the destination** when Windows asks. Do not delete the old
   folder first; this preserves the downloaded runtime and models.
4. Open PowerShell in the existing CombatAI folder.
5. Run `.\install.bat` again, using the same explicit path options as before if you needed them.
6. Run the status command from step 4 of this guide and confirm that `healthy` is `true`.

The installer checks hashes before changing anything. If DCS, VAICOM, another mod, or a DCS
update changed the radio-panel file after CombatAI was installed, the update is deliberately
refused. In that case, do not force-copy the hook and do not uninstall immediately: an old
backup may no longer be the correct file for the updated DCS version. Keep the error and status
output and resolve the changed base file before continuing.

## Optional speech models

The default `base.en` model is the right starting point. Larger models require more disk space,
memory, and recognition time. To install one for comparison:

```powershell
.\setup-stt.bat small.en
.\setup-stt.bat medium.en
```

`small.en` is about 466 MiB and `medium.en` about 1.5 GiB. After installation, select the model
on the configuration page and save the change.

An experimental NVIDIA CUDA 12 worker can be installed with:

```powershell
.\setup-stt.bat base.en cuda12
```

CPU mode remains the recommended baseline until testing on your PC shows that GPU recognition
improves the overall result without interfering with DCS.

## Troubleshooting

| What you see | What to do |
|---|---|
| `install.bat` is not found | PowerShell is not in the extracted CombatAI folder. Repeat step 2 and check the prompt. |
| CombatAI cannot locate DCS | Use `--dcs-install` and `--saved-games` as shown in step 3. This is expected for a Steam library on another drive. |
| More than one DCS or Saved Games folder was found | Supply both explicit paths so the installer cannot choose the wrong one. |
| A download fails | Check the internet connection, VPN/proxy, and antivirus history, then run the same batch file again. Setup safely reuses downloads that already passed verification. |
| The browser configuration page does not open | Leave `configuration.bat` running and browse to `http://127.0.0.1:34385/`. If the port is already in use, close the older configuration window first. |
| The microphone test reports silence | Select a different recording device and check Windows **Settings > System > Sound > Input** and microphone privacy permissions. |
| The HOTAS is not listed | Connect and power it before opening the configuration page, then restart `configuration.bat`. Use **Space only** as a fallback. |
| CombatAI waits for DCS indefinitely | Enter an active mission, confirm the installation status is healthy, and make sure only one CombatAI runner is open. |
| DCS has no CombatAI catalogue | Check `Saved Games\DCS\Logs\dcs.log`. Advanced checks: DCS should own UDP port `34383`, and CombatAI should own `34384`. |
| `Previous Menu` or `Exit Menu` is rejected as an ordinary command | Rerun `install.bat`; these controls require both the current Windows application and the current DCS hook. |
| The installer refuses because the panel changed | Stop. Do not overwrite it manually. Preserve the full error/status output; the safety check is protecting a DCS update or another modification. |

Text and JSONL diagnostic logs are stored under `%LOCALAPPDATA%\CombatAI\logs`. Recorded audio
is not retained.

## Uninstalling

Close DCS and CombatAI, open PowerShell in the CombatAI folder, and run:

```powershell
.\uninstall.bat
```

Approve the administrator prompt. A successful uninstall restores the exact DCS file that was
backed up during installation and removes CombatAI's Saved Games state, local configuration,
logs, private runtime, speech models, and Alan voice. The extracted source folder is retained;
after the uninstaller reports success, you may delete that folder yourself.

Removal is refused if the installed DCS panel changed after installation or if the backup
cannot be verified. This is intentional: it prevents an older backup from overwriting a DCS
update or another modification. Do not manually replace the panel when this happens.

## Files CombatAI uses

| Purpose | Location |
|---|---|
| Program, private runtime, Whisper, and Alan | The extracted CombatAI folder |
| Settings | `%LOCALAPPDATA%\CombatAI\config.json` |
| Logs | `%LOCALAPPDATA%\CombatAI\logs` |
| Installation record and backups | `Saved Games\DCS\Scripts\CombatAI` |
| DCS hook target | The active DCS installation's `Scripts\UI\RadioCommandDialogPanel\RadioCommandDialogsPanel.lua` |
