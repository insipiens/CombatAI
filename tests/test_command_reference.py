from __future__ import annotations

import unittest

from combatai.command_reference import (
    MetaCommand,
    list_node_children,
    parse_meta_command,
    spoken_listing,
)
from combatai.protocol import MenuItem


ITEMS = (
    MenuItem("1", "Startup", ("ATC", "Ford", "Startup")),
    MenuItem("2", "Taxi", ("ATC", "Ford", "Taxi")),
    MenuItem("3", "Inbound", ("ATC", "Tangmere", "Inbound")),
    MenuItem("4", "Engage", ("Wingman", "Engage", "Bandits")),
    MenuItem("5", "Rescue", ("Other", "Contact Air Sea Rescue")),
    MenuItem("6", "Cover", ("Flight", "Cover Me")),
    MenuItem("7", "Bandits", ("Flight", "Engage", "Engage Bandits")),
    MenuItem("8", "Bandits", ("Second Element", "Engage", "Engage Bandits")),
)


class CommandReferenceTests(unittest.TestCase):
    def test_parses_list_query(self) -> None:
        command = parse_meta_command("List ATC commands.")
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command.kind, "list")
        self.assertEqual(command.node, "atc")

    def test_normalises_whisper_punctuation_and_singular_command(self) -> None:
        command = parse_meta_command("List, Second Element, Command.")
        self.assertEqual(command, MetaCommand("list", "second element"))

    def test_parses_safe_list_shorthand(self) -> None:
        self.assertEqual(parse_meta_command("F10 commands."), MetaCommand("list", "f10"))

    def test_every_list_prefix_is_a_meta_command(self) -> None:
        self.assertEqual(parse_meta_command("List of a Command."), MetaCommand("list", "of a"))

    def test_parses_top_level_list_aliases(self) -> None:
        for phrase in (
            "List commands",
            "List all commands",
            "List categories",
            "List top-level commands",
            "List, Cabans.",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_meta_command(phrase), MetaCommand("list"))

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

    def test_lists_full_nested_path(self) -> None:
        listing = list_node_children(ITEMS, "Second Element Engage")
        self.assertEqual(listing.children, ("Engage Bandits",))

    def test_lists_top_level_nodes(self) -> None:
        listing = list_node_children(ITEMS, None)
        self.assertEqual(listing.children, ("ATC", "Wingman", "Other", "Flight", "Second Element"))

    def test_duplicate_node_label_is_ambiguous(self) -> None:
        listing = list_node_children(ITEMS, "Engage")
        self.assertEqual(listing.status, "ambiguous")
        self.assertEqual(listing.choices, ("Wingman Engage", "Flight Engage", "Second Element Engage"))

    def test_f10_alias_resolves_dcs_other_root(self) -> None:
        listing = list_node_children(ITEMS, "F10")
        self.assertEqual(listing.status, "found")
        self.assertEqual(listing.node, "Other")
        self.assertEqual(listing.children, ("Contact Air Sea Rescue",))

    def test_f10_alias_does_not_match_nested_other(self) -> None:
        nested = ITEMS + (MenuItem("6", "Nested", ("ATC", "Other", "Nested")),)
        listing = list_node_children(nested, "F10")
        self.assertEqual(listing.children, ("Contact Air Sea Rescue",))

    def test_unknown_node_is_terse(self) -> None:
        listing = list_node_children(ITEMS, "carrier")
        self.assertEqual(spoken_listing(listing), "I didn't recognise that menu.")

    def test_known_f10_node_can_be_temporarily_empty(self) -> None:
        no_other = tuple(item for item in ITEMS if item.path[0] != "Other")
        listing = list_node_children(no_other, "F10")
        self.assertEqual(listing.status, "unavailable")
        self.assertEqual(spoken_listing(listing), "No F10 commands are currently available.")

    def test_known_radio_root_can_be_temporarily_empty(self) -> None:
        no_ground_crew = tuple(item for item in ITEMS if item.path[0] != "Ground Crew")
        listing = list_node_children(no_ground_crew, "Ground Crew")
        self.assertEqual(listing.status, "unavailable")
        self.assertEqual(
            spoken_listing(listing),
            "No Ground Crew commands are currently available.",
        )


if __name__ == "__main__":
    unittest.main()
