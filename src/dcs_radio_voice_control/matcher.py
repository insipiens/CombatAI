"""Deterministic matching of speech transcripts to the live DCS catalogue."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata

from .protocol import MenuItem


MINIMUM_SCORE = 0.60
AMBIGUITY_MARGIN = 0.02
MAX_PROMPT_CHARACTERS = 1_500
_SCOPES = ("second element", "wingman", "flight", "atc")
_LEADING_POLITENESS = {"please"}
_RECIPIENT_VERBS = {"ask", "order", "tell"}
_RECIPIENT_ARTICLES = {"my", "the"}
_EXCLUSIVE_TERMS = (
    frozenset({"start", "stop"}),
    frozenset({"on", "off"}),
    frozenset({"open", "close"}),
    frozenset({"enable", "disable"}),
    frozenset({"left", "right"}),
    frozenset({"increase", "decrease"}),
    frozenset({"extend", "retract"}),
)


@dataclass(frozen=True, slots=True)
class RankedMatch:
    item: MenuItem
    score: float
    exact: bool = False


@dataclass(frozen=True, slots=True)
class MatchResult:
    status: str
    candidates: tuple[RankedMatch, ...]
    ranked: tuple[RankedMatch, ...] = ()

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
    for label in (
        "Show Menu",
        "Previous Menu",
        "Exit Menu",
        "F11",
        "F12",
        "Back",
        "Close Menu",
    ):
        candidate = prefix + ", ".join((*labels, label)) + "."
        if len(candidate) > maximum_characters:
            return prefix + ", ".join(labels) + "." if labels else ""
        labels.append(label)
        seen.add(label.casefold())
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
    all_ranked: list[RankedMatch] = []
    for item in items:
        item_scope = normalize_phrase(item.path[0])
        if scope is not None and item_scope != scope:
            continue
        forms = _spoken_forms(item)
        score = max(
            _similarity(spoken, form, contextual=contextual)
            for form, contextual in forms
        )
        score = max(score, _hierarchical_similarity(spoken, item))
        exact = any(spoken == form for form, _ in forms)
        all_ranked.append(RankedMatch(item, score, exact=exact))

    all_ranked.sort(key=lambda match: (-match.score, match.item.action_id))
    ranked = [match for match in all_ranked if match.score >= minimum_score]
    diagnostic = tuple(all_ranked[:5])
    if not ranked:
        return MatchResult("no_match", (), diagnostic)

    best_score = ranked[0].score
    contenders = tuple(
        match for match in ranked if best_score - match.score <= ambiguity_margin
    )
    if len(contenders) > 1:
        return MatchResult("ambiguous", contenders[:5], diagnostic)
    return MatchResult("matched", (ranked[0],), diagnostic)


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
    if not critical_terms_compatible(spoken, candidate):
        return 0.0
    if spoken == candidate:
        return 1.0
    spoken_words = spoken.split()
    candidate_words = candidate.split()
    sequence_score = SequenceMatcher(None, spoken, candidate).ratio()
    if contextual and _is_subsequence(candidate_words, spoken_words):
        coverage = len(candidate_words) / len(spoken_words)
        sequence_score = max(sequence_score, 0.92 + 0.08 * coverage)
    return sequence_score


def _hierarchical_similarity(spoken: str, item: MenuItem) -> float:
    """Score the action phrase and its menu context as separate evidence."""
    path = tuple(normalize_phrase(part) for part in item.path)
    if not path or not critical_terms_compatible(spoken, " ".join(path)):
        return 0.0

    leaf_score = _best_window_similarity(path[-1], spoken)
    spoken_words = spoken.split()
    leaf_words = path[-1].split()
    if len(spoken_words) <= len(leaf_words):
        return leaf_score

    # For deeper paths, the middle menu node is discriminating evidence while
    # the root is shared by every command in that radio scope.
    context = path[1:-1] if len(path) > 2 else path[:-1]
    context_score = max(
        (_best_window_similarity(segment, spoken) for segment in context),
        default=0.0,
    )
    if context_score < 0.65:
        return 0.70 * leaf_score
    return 0.75 * leaf_score + 0.25 * context_score


def _best_window_similarity(needle: str, haystack: str) -> float:
    needle_words = needle.split()
    haystack_words = haystack.split()
    if not needle_words or not haystack_words:
        return 0.0
    best = 0.0
    for width in range(max(1, len(needle_words) - 1), len(needle_words) + 2):
        for start in range(0, len(haystack_words) - width + 1):
            window = " ".join(haystack_words[start : start + width])
            best = max(best, SequenceMatcher(None, needle, window).ratio())
    return best


def critical_terms_compatible(spoken: str, candidate: str) -> bool:
    """Reject a match when either side adds or contradicts an operational qualifier."""
    spoken_words = set(normalize_phrase(spoken).split())
    candidate_words = set(normalize_phrase(candidate).split())
    for group in _EXCLUSIVE_TERMS:
        spoken_terms = spoken_words & group
        candidate_terms = candidate_words & group
        if (spoken_terms or candidate_terms) and spoken_terms != candidate_terms:
            return False
    return True


def strong_semantic_match(transcript: str, item: MenuItem) -> bool:
    """Allow stale-menu recovery only when the refreshed action retains explicit intent."""
    spoken = normalize_phrase(transcript)
    leaf = normalize_phrase(item.path[-1])
    if not critical_terms_compatible(spoken, leaf):
        return False
    if any(spoken == form for form, _ in _spoken_forms(item)):
        return True
    return len(leaf.split()) >= 2 and _is_subsequence(leaf.split(), spoken.split())


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
