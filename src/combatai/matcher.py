"""Deterministic matching of speech transcripts to the live DCS catalogue."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata

from .protocol import MenuItem


MINIMUM_SCORE = 0.72
AMBIGUITY_MARGIN = 0.02
_SCOPES = ("second element", "wingman", "flight", "atc")
_LEADING_POLITENESS = {"please"}
_RECIPIENT_VERBS = {"ask", "order", "tell"}
_RECIPIENT_ARTICLES = {"my", "the"}


@dataclass(frozen=True, slots=True)
class RankedMatch:
    item: MenuItem
    score: float


@dataclass(frozen=True, slots=True)
class MatchResult:
    status: str
    candidates: tuple[RankedMatch, ...]

    @property
    def best(self) -> RankedMatch | None:
        return self.candidates[0] if self.candidates else None


def normalize_phrase(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(character for character in decomposed if not unicodedata.combining(character))
    words = re.findall(r"[a-z0-9]+", ascii_text)
    normalized = " ".join(words)
    substitutions = {
        "wing man": "wingman",
        "startup": "start up",
        "airsea": "air sea",
        "r t b": "rtb",
    }
    for source, replacement in substitutions.items():
        normalized = re.sub(rf"\b{re.escape(source)}\b", replacement, normalized)
    return normalized


def match_catalogue(
    transcript: str,
    items: tuple[MenuItem, ...],
    *,
    minimum_score: float = MINIMUM_SCORE,
    ambiguity_margin: float = AMBIGUITY_MARGIN,
) -> MatchResult:
    spoken = normalize_phrase(transcript)
    if not spoken or not items:
        return MatchResult("no_match", ())

    scope = _explicit_scope(spoken)
    ranked: list[RankedMatch] = []
    for item in items:
        item_scope = normalize_phrase(item.path[0])
        if scope is not None and item_scope != scope:
            continue
        score = max(_similarity(spoken, form) for form in _spoken_forms(item))
        if score >= minimum_score:
            ranked.append(RankedMatch(item, score))

    ranked.sort(key=lambda match: (-match.score, match.item.action_id))
    if not ranked:
        return MatchResult("no_match", ())

    best_score = ranked[0].score
    contenders = tuple(
        match for match in ranked if best_score - match.score <= ambiguity_margin
    )
    if len(contenders) > 1:
        return MatchResult("ambiguous", contenders[:5])
    return MatchResult("matched", (ranked[0],))


def _spoken_forms(item: MenuItem) -> tuple[str, ...]:
    path = tuple(normalize_phrase(part) for part in item.path)
    forms = {
        " ".join(path),
        path[-1],
    }
    if len(path) > 1:
        forms.add(" ".join(path[1:]))
        forms.add(f"{path[0]} {path[-1]}")
    return tuple(form for form in forms if form)


def _similarity(spoken: str, candidate: str) -> float:
    if spoken == candidate:
        return 1.0
    spoken_words = spoken.split()
    candidate_words = candidate.split()
    sequence_score = SequenceMatcher(None, spoken, candidate).ratio()
    if _is_subsequence(candidate_words, spoken_words):
        coverage = len(candidate_words) / len(spoken_words)
        sequence_score = max(sequence_score, 0.92 + 0.08 * coverage)
    return sequence_score


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    position = 0
    for word in haystack:
        if position < len(needle) and word == needle[position]:
            position += 1
    return position == len(needle)


def _explicit_scope(spoken: str) -> str | None:
    words = spoken.split()
    while words and words[0] in _LEADING_POLITENESS:
        words.pop(0)
    if words and words[0] in _RECIPIENT_VERBS:
        words.pop(0)
        if words and words[0] in _RECIPIENT_ARTICLES:
            words.pop(0)
    prefix = " ".join(words)
    for scope in _SCOPES:
        if prefix == scope or prefix.startswith(scope + " "):
            return scope
    return None
