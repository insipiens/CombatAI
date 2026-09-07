from __future__ import annotations

import unittest

from combatai.command_reference import list_node_children, parse_meta_command, spoken_listing
from combatai.protocol import MenuItem


ITEMS = (
    MenuItem("1", "Startup", ("ATC", "Ford", "Startup")),
    MenuItem("2", "Taxi", ("ATC", "Ford", "Taxi")),
    MenuItem("3", "Inbound", ("ATC", "Tangmere", "Inbound")),
    MenuItem("4", "Engage", ("Wingman", "Engage", "Bandits")),
    MenuItem("5", "Rescue", ("F10", "Contact Air Sea Rescue")),
)


class CommandReferenceTests(unittest.TestCase):
    def test_parses_list_query(self) -> None:
        command = parse_meta_command("List ATC commands.")
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command.kind, "list")
        self.assertEqual(command.node, "ATC")

    def test_parses_repeat_aliases(self) -> None:
        for phrase in ("repeat", "repeat please", "say again", "say again please"):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_meta_command(phrase).kind, "repeat")  # type: ignore[union-attr]

    def test_lists_immediate_children_only(self) -> None:
        listing = list_node_children(ITEMS, "ATC")
        self.assertEqual(listing.status, "found")
        self.assertEqual(listing.children, ("Ford", "Tangmere"))
        self.assertEqual(spoken_listing(listing), "Ford. Tangmere.")

    def test_compact_initialism_matches(self) -> None:
        listing = list_node_children(ITEMS, "A T C")
        self.assertEqual(listing.children, ("Ford", "Tangmere"))

    def test_lists_nested_node(self) -> None:
        listing = list_node_children(ITEMS, "Ford")
        self.assertEqual(listing.children, ("Startup", "Taxi"))

    def test_unknown_node_is_terse(self) -> None:
        listing = list_node_children(ITEMS, "carrier")
        self.assertEqual(spoken_listing(listing), "No carrier commands.")


if __name__ == "__main__":
    unittest.main()
