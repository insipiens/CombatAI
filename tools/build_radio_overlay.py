#!/usr/bin/env python3
"""Generate a DCS Saved Games radio-panel override from the user's installed file."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile

BEGIN_MARKER = b"-- COMBATAI RADIO HOOK BEGIN"


def build_overlay(source: Path, hook: Path, destination: Path) -> str:
    source = source.resolve()
    hook = hook.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("source and destination must be different files")

    source_bytes = source.read_bytes()
    hook_bytes = hook.read_bytes()
    if BEGIN_MARKER in source_bytes:
        raise ValueError("source already contains the CombatAI hook")
    if BEGIN_MARKER not in hook_bytes:
        raise ValueError("hook does not contain the CombatAI marker")
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite {destination}; remove or relocate the existing override explicitly"
        )

    source_hash = hashlib.sha256(source_bytes).hexdigest()
    header = (
        b"\n-- Generated locally by CombatAI; do not distribute this DCS-derived file.\n"
        + f"-- Source SHA-256: {source_hash}\n".encode("ascii")
    )
    payload = source_bytes.rstrip() + header + hook_bytes.lstrip()
    destination.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".tmp",
        dir=destination.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return source_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="current DCS RadioCommandDialogsPanel.lua")
    parser.add_argument("destination", type=Path, help="new Saved Games override path")
    parser.add_argument(
        "--hook",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dcs" / "CombatAI.radio_hook.lua",
    )
    args = parser.parse_args()
    source_hash = build_overlay(args.source, args.hook, args.destination)
    print(f"Created {args.destination}")
    print(f"Source SHA-256: {source_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
