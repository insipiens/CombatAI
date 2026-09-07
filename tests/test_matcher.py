from __future__ import annotations

from pathlib import Path
import unittest

from combatai.matcher import MatchResult, RankedMatch, match_catalogue, normalize_phrase
from combatai.protocol import MenuItem
from combatai.voice_command_test import MINIMUM_EXECUTION_SCORE, execution_candidate


ITEMS = (
    MenuItem("radio.1.4.1", "Break Right", ("Wingman", "Maneuvers", "Break Right")),
    MenuItem("radio.1.4.2", "Break Left", ("Wingman", "Maneuvers", "Break Left")),
    MenuItem("radio.2.4.1", "Break Right", ("Flight", "Maneuvers", "Break Right")),
    MenuItem("radio.2.4.2", "Break Left", ("Flight", "Maneuvers", "Break Left")),
    MenuItem(
        "radio.3.4.2",
        "Break Left",
        ("Second Element", "Maneuvers", "Break Left"),
    ),
    MenuItem(
        "radio.5.1.1",
        "Request Start-Up",
        ("ATC", "Biggin Hill", "Request Start-Up"),
    ),
    MenuItem(
        "radio.5.2.1",
        "Request Start-Up",
        ("ATC", "Kenley", "Request Start-Up"),
    ),
    MenuItem("f10.10.1", "Contact Air Sea Rescue", ("Other", "Contact Air Sea Rescue")),
)


class MatcherTests(unittest.TestCase):
    def test_normalizes_punctuation_and_common_compounds(self) -> None:
        self.assertEqual(normalize_phrase("Request start-up!"), "request start up")
        self.assertEqual(normalize_phrase("Wing man"), "wingman")

    def test_recipient_and_leaf_select_unique_command(self) -> None:
        result = match_catalogue("Wingman, break left", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "radio.1.4.2")  # type: ignore[union-attr]

    def test_framed_recipient_command_matches(self) -> None:
        result = match_catalogue("Please tell the wingman to break right", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "radio.1.4.1")  # type: ignore[union-attr]

    def test_leaf_without_recipient_is_ambiguous(self) -> None:
        result = match_catalogue("Break left", ITEMS)
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(len(result.candidates), 3)

    def test_atc_location_disambiguates_repeated_command(self) -> None:
        result = match_catalogue("Biggin Hill request startup", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "radio.5.1.1")  # type: ignore[union-attr]

    def test_f10_leaf_matches_without_saying_other(self) -> None:
        result = match_catalogue("Contact air-sea rescue", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "f10.10.1")  # type: ignore[union-attr]

    def test_unrelated_speech_does_not_match(self) -> None:
        result = match_catalogue("What is the weather tomorrow", ITEMS)
        self.assertEqual(result.status, "no_match")

    def test_matching_test_contains_no_execution_call(self) -> None:
        source = (
            Path(__file__).parents[1] / "src" / "combatai" / "matching_test.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(".execute(", source)

    def test_exact_unique_match_is_eligible_for_execution(self) -> None:
        result = match_catalogue("Wingman break left", ITEMS)
        candidate = execution_candidate(result)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.item.action_id, "radio.1.4.2")  # type: ignore[union-attr]

    def test_weaker_match_is_not_eligible_for_execution(self) -> None:
        result = MatchResult(
            "matched",
            (RankedMatch(ITEMS[0], MINIMUM_EXECUTION_SCORE - 0.01),),
        )
        self.assertIsNone(execution_candidate(result))

    def test_ambiguous_match_is_not_eligible_for_execution(self) -> None:
        result = match_catalogue("Break left", ITEMS)
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(execution_candidate(result))

    def test_display_only_item_is_not_eligible_for_execution(self) -> None:
        item = MenuItem("legacy.1", "Test", ("Test",), executable=False)
        result = MatchResult("matched", (RankedMatch(item, 1.0),))
        self.assertIsNone(execution_candidate(result))


if __name__ == "__main__":
    unittest.main()
