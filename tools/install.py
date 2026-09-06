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
import sys
import tempfile
from typing import Any
from uuid import uuid4

if __package__:
    from .build_radio_overlay import BEGIN_MARKER, build_overlay
else:  # Executed directly as `py tools\install.py`.
    from build_radio_overlay import BEGIN_MARKER, build_overlay

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
    dcs_install = dcs_install.resolve()
    saved_games = saved_games.resolve()
    hook = hook.resolve()
    core_panel = dcs_install / RELATIVE_PANEL
    saved_panel = saved_games / RELATIVE_PANEL
    state_directory = saved_games / STATE_DIRECTORY
    manifest_path = state_directory / MANIFEST_NAME

    if manifest_path.exists():
        raise InstallError(f"CombatAI already has an active installation manifest: {manifest_path}")
    if not core_panel.is_file():
        raise InstallError(f"DCS radio-panel file was not found: {core_panel}")
    if not hook.is_file() or BEGIN_MARKER not in hook.read_bytes():
        raise InstallError(f"CombatAI hook is missing or invalid: {hook}")

    had_saved_override = saved_panel.is_file()
    base_panel = saved_panel if had_saved_override else core_panel
    if BEGIN_MARKER in base_panel.read_bytes():
        raise InstallError(
            "The active radio-panel file already contains CombatAI but has no usable manifest; "
            "manual inspection is required"
        )

    state_directory.mkdir(parents=True, exist_ok=True)
    backup_directory = state_directory / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / f"RadioCommandDialogsPanel.{uuid4().hex}.lua"
    shutil.copy2(base_panel, backup_path)

    saved_panel.parent.mkdir(parents=True, exist_ok=True)
    staged_path = saved_panel.with_name(saved_panel.name + f".{uuid4().hex}.combatai-new")
    installed = False
    try:
        base_sha256 = build_overlay(base_panel, hook, staged_path)
        installed_sha256 = file_hash(staged_path)
        os.replace(staged_path, saved_panel)
        installed = True

        manifest: dict[str, Any] = {
            "schema": 1,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "dcs_install": str(dcs_install),
            "saved_games": str(saved_games),
            "target": str(saved_panel),
            "base_kind": "saved_games_override" if had_saved_override else "dcs_core",
            "base_sha256": base_sha256,
            "installed_sha256": installed_sha256,
            "backup": str(backup_path),
        }
        _write_json_atomic(manifest_path, manifest)
        return manifest
    except BaseException:
        if staged_path.exists():
            staged_path.unlink()
        if installed:
            if had_saved_override:
                shutil.copy2(backup_path, saved_panel)
            elif saved_panel.exists():
                saved_panel.unlink()
        raise


def uninstall_hook(saved_games: Path) -> dict[str, Any]:
    saved_games = saved_games.resolve()
    state_directory = saved_games / STATE_DIRECTORY
    manifest_path = state_directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise InstallError(f"No active CombatAI installation manifest was found: {manifest_path}")

    manifest = _read_manifest(manifest_path)
    target = Path(manifest["target"])
    backup = Path(manifest["backup"])
    expected_target = saved_games / RELATIVE_PANEL
    if target.resolve() != expected_target.resolve():
        raise InstallError("Manifest target does not belong to the selected Saved Games directory")
    expected_backup_directory = (state_directory / "backups").resolve()
    if backup.resolve().parent != expected_backup_directory:
        raise InstallError("Manifest backup does not belong to the CombatAI backup directory")
    if not target.is_file():
        raise InstallError(f"Installed radio-panel file is missing: {target}")
    if file_hash(target) != manifest["installed_sha256"]:
        raise InstallError(
            "The installed radio-panel file has changed since CombatAI was installed; "
            "refusing to overwrite changes made by DCS, VAICOM, or another mod"
        )
    if not backup.is_file() or file_hash(backup) != manifest["base_sha256"]:
        raise InstallError(f"The recorded backup is missing or altered: {backup}")

    if manifest["base_kind"] == "saved_games_override":
        _copy_atomic(backup, target)
        outcome = "restored_saved_games_override"
    elif manifest["base_kind"] == "dcs_core":
        target.unlink()
        outcome = "removed_generated_override"
    else:
        raise InstallError(f"Unknown base kind in manifest: {manifest['base_kind']!r}")

    archive = state_directory / (
        "install.removed."
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "."
        + uuid4().hex
        + ".json"
    )
    os.replace(manifest_path, archive)
    return {"outcome": outcome, "manifest_archive": str(archive), "backup": str(backup)}


def installation_status(saved_games: Path) -> dict[str, Any]:
    saved_games = saved_games.resolve()
    manifest_path = saved_games / STATE_DIRECTORY / MANIFEST_NAME
    target = saved_games / RELATIVE_PANEL
    if not manifest_path.is_file():
        return {
            "installed": False,
            "target_exists": target.is_file(),
            "target": str(target),
        }
    manifest = _read_manifest(manifest_path)
    actual_hash = file_hash(target) if target.is_file() else None
    return {
        "installed": True,
        "healthy": actual_hash == manifest["installed_sha256"],
        "target": str(target),
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
    if not isinstance(value, dict) or value.get("schema") != 1 or not required <= value.keys():
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

    for name in ("status", "uninstall"):
        command_parser = commands.add_parser(name)
        command_parser.add_argument("--saved-games", type=Path)

    args = parser.parse_args()
    try:
        saved_games = discover_saved_games(args.saved_games)
        if args.command == "install":
            result = install_hook(discover_dcs_install(args.dcs_install), saved_games, args.hook)
        elif args.command == "uninstall":
            result = uninstall_hook(saved_games)
        else:
            result = installation_status(saved_games)
    except (InstallError, FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"CombatAI: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
