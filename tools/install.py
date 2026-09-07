#!/usr/bin/env python3
"""Install, inspect, or remove the experimental CombatAI DCS radio hook."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from uuid import uuid4

if not __package__:
    # The embeddable runtime uses an explicit _pth file and therefore does not add
    # this script's directory automatically. Establish the repository root before
    # importing the tools package.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.build_radio_overlay import BEGIN_MARKER, build_overlay

RELATIVE_PANEL = Path("Scripts/UI/RadioCommandDialogPanel/RadioCommandDialogsPanel.lua")
STATE_DIRECTORY = Path("Scripts/CombatAI")
MANIFEST_NAME = "install.json"


class InstallError(RuntimeError):
    """A safe installation or removal could not be completed."""


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def install_hook(dcs_install: Path, saved_games: Path, hook: Path) -> dict[str, Any]:
    """Append CombatAI to the radio panel DCS actually loads from its installation."""

    dcs_install = dcs_install.resolve()
    saved_games = saved_games.resolve()
    hook = hook.resolve()
    core_panel = dcs_install / RELATIVE_PANEL
    state_directory = saved_games / STATE_DIRECTORY
    manifest_path = state_directory / MANIFEST_NAME

    if not core_panel.is_file():
        raise InstallError(f"DCS radio-panel file was not found: {core_panel}")
    if not hook.is_file() or BEGIN_MARKER not in hook.read_bytes():
        raise InstallError(f"CombatAI hook is missing or invalid: {hook}")

    migrated: dict[str, Any] | None = None
    if manifest_path.exists():
        existing = _read_manifest(manifest_path)
        if _is_legacy_saved_games_install(existing, saved_games):
            migrated = _remove_legacy_saved_games_install(saved_games, existing)
        else:
            raise InstallError(f"CombatAI already has an active installation manifest: {manifest_path}")

    if BEGIN_MARKER in core_panel.read_bytes():
        raise InstallError(
            "The active radio-panel file already contains CombatAI but has no usable manifest; "
            "manual inspection is required"
        )

    state_directory.mkdir(parents=True, exist_ok=True)
    backup_directory = state_directory / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / f"RadioCommandDialogsPanel.{uuid4().hex}.lua"
    shutil.copy2(core_panel, backup_path)

    staged_path = core_panel.with_name(core_panel.name + f".{uuid4().hex}.combatai-new")
    installed = False
    try:
        base_sha256 = build_overlay(core_panel, hook, staged_path)
        installed_sha256 = file_hash(staged_path)
        os.replace(staged_path, core_panel)
        installed = True

        manifest: dict[str, Any] = {
            "schema": 2,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "dcs_install": str(dcs_install),
            "saved_games": str(saved_games),
            "target": str(core_panel),
            "base_kind": "active_dcs_panel",
            "base_sha256": base_sha256,
            "installed_sha256": installed_sha256,
            "backup": str(backup_path),
        }
        if migrated is not None:
            manifest["migrated_legacy_install"] = migrated["manifest_archive"]
        _write_json_atomic(manifest_path, manifest)
        return manifest
    except BaseException:
        if staged_path.exists():
            staged_path.unlink()
        if installed:
            _copy_atomic(backup_path, core_panel)
        raise


def uninstall_hook(dcs_install: Path, saved_games: Path) -> dict[str, Any]:
    dcs_install = dcs_install.resolve()
    saved_games = saved_games.resolve()
    state_directory = saved_games / STATE_DIRECTORY
    manifest_path = state_directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise InstallError(f"No active CombatAI installation manifest was found: {manifest_path}")

    manifest = _read_manifest(manifest_path)
    if _is_legacy_saved_games_install(manifest, saved_games):
        return _remove_legacy_saved_games_install(saved_games, manifest)

    target = Path(manifest["target"])
    backup = Path(manifest["backup"])
    expected_target = dcs_install / RELATIVE_PANEL
    if target.resolve() != expected_target.resolve():
        raise InstallError("Manifest target does not belong to the selected DCS installation")
    _validate_backup_location(backup, state_directory)
    if not target.is_file():
        raise InstallError(f"Installed radio-panel file is missing: {target}")
    if file_hash(target) != manifest["installed_sha256"]:
        raise InstallError(
            "The installed radio-panel file has changed since CombatAI was installed; "
            "refusing to overwrite changes made by DCS, VAICOM, or another mod"
        )
    if not backup.is_file() or file_hash(backup) != manifest["base_sha256"]:
        raise InstallError(f"The recorded backup is missing or altered: {backup}")
    if manifest["base_kind"] != "active_dcs_panel":
        raise InstallError(f"Unknown base kind in manifest: {manifest['base_kind']!r}")

    _copy_atomic(backup, target)
    archive = _archive_manifest(manifest_path, state_directory, "removed")
    return {
        "outcome": "restored_active_dcs_panel",
        "manifest_archive": str(archive),
        "backup": str(backup),
    }


def installation_status(dcs_install: Path, saved_games: Path) -> dict[str, Any]:
    dcs_install = dcs_install.resolve()
    saved_games = saved_games.resolve()
    manifest_path = saved_games / STATE_DIRECTORY / MANIFEST_NAME
    active_target = dcs_install / RELATIVE_PANEL
    if not manifest_path.is_file():
        return {
            "installed": False,
            "target_exists": active_target.is_file(),
            "target": str(active_target),
        }

    manifest = _read_manifest(manifest_path)
    recorded_target = Path(manifest["target"])
    legacy_install = _is_legacy_saved_games_install(manifest, saved_games)
    target_matches = recorded_target.resolve() == active_target.resolve()
    actual_hash = file_hash(recorded_target) if recorded_target.is_file() else None
    recorded_file_intact = actual_hash == manifest["installed_sha256"]
    return {
        "installed": True,
        "healthy": not legacy_install and target_matches and recorded_file_intact,
        "legacy_install": legacy_install,
        "recorded_file_intact": recorded_file_intact,
        "target_matches_selected_install": target_matches,
        "target": str(recorded_target),
        "active_target": str(active_target),
        "base_kind": manifest["base_kind"],
        "installed_at": manifest["installed_at"],
        "expected_sha256": manifest["installed_sha256"],
        "actual_sha256": actual_hash,
    }


def discover_saved_games(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    candidates = [
        Path.home() / "Saved Games" / name
        for name in ("DCS", "DCS.openbeta")
        if (Path.home() / "Saved Games" / name).is_dir()
    ]
    return _require_one(candidates, "Saved Games DCS directory", "--saved-games")


def discover_dcs_install(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    candidates: list[Path] = []
    configured = os.environ.get("DCS_INSTALL_DIR")
    if configured:
        candidates.append(Path(configured))
    for environment_name, suffix in (
        ("ProgramFiles", Path("Eagle Dynamics/DCS World")),
        ("ProgramFiles", Path("Eagle Dynamics/DCS World OpenBeta")),
        ("ProgramFiles(x86)", Path("Steam/steamapps/common/DCSWorld")),
    ):
        root = os.environ.get(environment_name)
        if root:
            candidates.append(Path(root) / suffix)
    valid = []
    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen and (resolved / RELATIVE_PANEL).is_file():
            valid.append(resolved)
            seen.add(resolved)
    return _require_one(valid, "DCS installation", "--dcs-install")


def _require_one(candidates: list[Path], description: str, option: str) -> Path:
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise InstallError(f"Could not locate the {description}; specify it with {option}")
    choices = "\n  ".join(str(candidate) for candidate in candidates)
    raise InstallError(f"More than one {description} was found; use {option}:\n  {choices}")


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"Cannot read installation manifest {path}: {exc}") from exc
    required = {
        "schema",
        "installed_at",
        "target",
        "base_kind",
        "base_sha256",
        "installed_sha256",
        "backup",
    }
    if (
        not isinstance(value, dict)
        or value.get("schema") not in (1, 2)
        or not required <= value.keys()
    ):
        raise InstallError(f"Installation manifest is invalid: {path}")
    for field in ("target", "base_kind", "backup", "installed_at"):
        if not isinstance(value[field], str) or not value[field]:
            raise InstallError(f"Installation manifest field {field!r} is invalid: {path}")
    for field in ("base_sha256", "installed_sha256"):
        digest = value[field]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise InstallError(f"Installation manifest field {field!r} is invalid: {path}")
    return value


def _is_legacy_saved_games_install(manifest: dict[str, Any], saved_games: Path) -> bool:
    if manifest.get("schema") != 1:
        return False
    return Path(manifest["target"]).resolve() == (saved_games.resolve() / RELATIVE_PANEL).resolve()


def _remove_legacy_saved_games_install(
    saved_games: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Safely remove the inactive Saved Games overlay produced by early CombatAI builds."""

    saved_games = saved_games.resolve()
    state_directory = saved_games / STATE_DIRECTORY
    manifest_path = state_directory / MANIFEST_NAME
    target = saved_games / RELATIVE_PANEL
    backup = Path(manifest["backup"])

    if Path(manifest["target"]).resolve() != target.resolve():
        raise InstallError("Legacy manifest target is not the expected Saved Games panel")
    _validate_backup_location(backup, state_directory)
    if not target.is_file() or file_hash(target) != manifest["installed_sha256"]:
        raise InstallError(
            "The legacy Saved Games radio-panel file has changed; refusing automatic migration"
        )
    if not backup.is_file() or file_hash(backup) != manifest["base_sha256"]:
        raise InstallError(f"The recorded backup is missing or altered: {backup}")

    if manifest["base_kind"] == "saved_games_override":
        _copy_atomic(backup, target)
        outcome = "restored_legacy_saved_games_override"
    elif manifest["base_kind"] == "dcs_core":
        target.unlink()
        outcome = "removed_legacy_generated_override"
    else:
        raise InstallError(f"Unknown legacy base kind: {manifest['base_kind']!r}")

    archive = _archive_manifest(manifest_path, state_directory, "migrated")
    return {"outcome": outcome, "manifest_archive": str(archive), "backup": str(backup)}


def _validate_backup_location(backup: Path, state_directory: Path) -> None:
    expected = (state_directory / "backups").resolve()
    if backup.resolve().parent != expected:
        raise InstallError("Manifest backup does not belong to the CombatAI backup directory")


def _archive_manifest(manifest_path: Path, state_directory: Path, action: str) -> Path:
    archive = state_directory / (
        f"install.{action}."
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "."
        + uuid4().hex
        + ".json"
    )
    os.replace(manifest_path, archive)
    return archive


def _write_json_atomic(destination: Path, value: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".tmp",
        dir=destination.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _copy_atomic(source: Path, destination: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".restore",
        dir=destination.parent,
    )
    os.close(descriptor)
    try:
        shutil.copy2(source, temporary_name)
        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _windows_command_line(arguments: list[str]) -> str:
    """Quote arguments according to the Windows CommandLineToArgvW convention."""

    return subprocess.list2cmdline(arguments)


def _is_windows_administrator() -> bool:
    if os.name != "nt":
        return False
    import ctypes

    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def _run_elevated(arguments: list[str]) -> int:
    """Relaunch this installer through UAC and return the child exit code."""

    if os.name != "nt":
        raise InstallError("Administrator elevation is available only on Windows")

    import ctypes
    from ctypes import wintypes

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", wintypes.LPVOID),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    parameters = _windows_command_line(
        [str(Path(__file__).resolve()), *arguments, "--elevated"]
    )
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = sys.executable
    info.lpParameters = parameters
    info.lpDirectory = str(Path(__file__).resolve().parents[1])
    info.nShow = 1  # SW_SHOWNORMAL

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == 1223:
            raise InstallError("Administrator permission was cancelled")
        raise InstallError(f"Could not request administrator permission (Windows error {error})")

    try:
        kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
            error = ctypes.get_last_error()
            raise InstallError(f"Could not read elevated installer result (Windows error {error})")
        return int(exit_code.value)
    finally:
        kernel32.CloseHandle(info.hProcess)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    install_parser = commands.add_parser("install", help="safely append and install the hook")
    install_parser.add_argument("--dcs-install", type=Path)
    install_parser.add_argument("--saved-games", type=Path)
    install_parser.add_argument(
        "--hook",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dcs" / "CombatAI.radio_hook.lua",
    )
    install_parser.add_argument("--elevated", action="store_true", help=argparse.SUPPRESS)

    for name in ("status", "uninstall"):
        command_parser = commands.add_parser(name)
        command_parser.add_argument("--dcs-install", type=Path)
        command_parser.add_argument("--saved-games", type=Path)
        if name == "uninstall":
            command_parser.add_argument("--elevated", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()
    try:
        if args.command in ("install", "uninstall") and os.name == "nt":
            if not args.elevated:
                if not _is_windows_administrator():
                    return _run_elevated(sys.argv[1:])
            elif not _is_windows_administrator():
                raise InstallError("The elevated installer did not receive administrator rights")
        saved_games = discover_saved_games(args.saved_games)
        dcs_install = discover_dcs_install(args.dcs_install)
        if args.command == "install":
            result = install_hook(dcs_install, saved_games, args.hook)
        elif args.command == "uninstall":
            result = uninstall_hook(dcs_install, saved_games)
        else:
            result = installation_status(dcs_install, saved_games)
    except (InstallError, FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"CombatAI: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
