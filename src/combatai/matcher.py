"""Deterministic matching of speech transcripts to the live DCS catalogue."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata

from .protocol import MenuItem


MINIMUM_SCORE = 0.72
AMBIGUITY_MARGIN = 0.02
MAX_PROMPT_CHARACTERS = 1_500
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


def build_vocabulary_prompt(
    items: tuple[MenuItem, ...], *, maximum_characters: int = MAX_PROMPT_CHARACTERS
) -> str:
    prefix = "DCS radio command vocabulary: "
    if maximum_characters <= len(prefix) + 1:
        return ""

    labels: list[str] = []
    seen: set[str] = set()
    maximum_depth = max((len(item.path) for item in items), default=0)
    for depth in range(maximum_depth):
        for item in items:
            if depth >= len(item.path):
                continue
            label = " ".join(item.path[depth].split())
            key = label.casefold()
            if not label or key in seen:
                continue
            candidate = prefix + ", ".join((*labels, label)) + "."
            if len(candidate) > maximum_characters:
                return prefix + ", ".join(labels) + "." if labels else ""
            labels.append(label)
            seen.add(key)
    return prefix + ", ".join(labels) + "." if labels else ""


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
        score = max(
            _similarity(spoken, form, contextual=contextual)
            for form, contextual in _spoken_forms(item)
        )
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


def _spoken_forms(item: MenuItem) -> tuple[tuple[str, bool], ...]:
    path = tuple(normalize_phrase(part) for part in item.path)
    forms = {" ".join(path): True, path[-1]: False}
    if len(path) > 1:
        tail = " ".join(path[1:])
        forms[tail] = forms.get(tail, False) or len(path) > 2 or path[0] == "other"
        root_and_leaf = f"{path[0]} {path[-1]}"
        forms[root_and_leaf] = True
    return tuple((form, contextual) for form, contextual in forms.items() if form)


def _similarity(spoken: str, candidate: str, *, contextual: bool) -> float:
    if spoken == candidate:
        return 1.0
    spoken_words = spoken.split()
    candidate_words = candidate.split()
    sequence_score = SequenceMatcher(None, spoken, candidate).ratio()
    if contextual and _is_subsequence(candidate_words, spoken_words):
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
