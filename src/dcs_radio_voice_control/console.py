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
    print("DCS Radio Voice Control radio-menu proof of concept")
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
    attempts = 0
    while client.request_menu_and_wait(timeout=2.0) is None:
        attempts += 1
        if attempts == 1:
            print("DCS is not responding yet. Start DCS and enter a mission; Ctrl+C stops DCS Radio Voice Control.")
        elif attempts % 5 == 0:
            print("Still waiting for an active DCS mission …")

    while True:
        snapshot = client.snapshot
        assert snapshot is not None
        print(f"\nRadio menu revision {snapshot.revision}")
        if not snapshot.items:
            print("  (No in-scope radio actions are currently available.)")
        for number, item in enumerate(snapshot.items, 1):
            suffix = " [display only]" if not item.executable else ""
            print(f"  {number:>2}. {' > '.join(item.path)}{suffix}")
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

        if not item.executable:
            print("Standard radio-command execution is not enabled in this test.")
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
