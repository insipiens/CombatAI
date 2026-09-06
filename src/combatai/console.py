"""Human-observable F10 proof-of-concept console."""

from __future__ import annotations

import logging
import sys

from .dcs_client import DcsMenuClient


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    print("CombatAI F10 proof of concept")
    print("Waiting for DCS on 127.0.0.1:34383 …")

    try:
        with DcsMenuClient() as client:
            return _run(client)
    except OSError as exc:
        print(f"Cannot start UDP listener: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130


def _run(client: DcsMenuClient) -> int:
    if client.request_menu_and_wait(timeout=5.0) is None:
        print("No reply from DCS. Is a mission running with the CombatAI hook installed?")
        return 1

    while True:
        snapshot = client.snapshot
        assert snapshot is not None
        print(f"\nF10 menu revision {snapshot.revision}")
        if not snapshot.items:
            print("  (No selectable F10 actions are currently available.)")
        for number, item in enumerate(snapshot.items, 1):
            print(f"  {number:>2}. {' > '.join(item.path)}")
        print("\nEnter a number, R to refresh, or Q to quit.")
        choice = input("> ").strip().lower()
        if choice == "q":
            return 0
        if choice == "r":
            if client.request_menu_and_wait() is None:
                print("DCS did not return a menu snapshot.")
            continue
        try:
            index = int(choice) - 1
            item = snapshot.items[index]
        except (ValueError, IndexError):
            print("Invalid selection.")
            continue

        request_id = client.execute(item.action_id, snapshot.revision)
        result = client.wait_for_result(request_id)
        if result is None:
            print("No acknowledgement from DCS; execution state is unknown.")
        elif result.accepted:
            print("DCS accepted the current action (the mission's downstream effect is not observable).")
        else:
            print(f"DCS rejected the action: {result.code}: {result.detail}")
            if result.code == "stale_revision":
                client.request_menu_and_wait()


if __name__ == "__main__":
    raise SystemExit(main())
