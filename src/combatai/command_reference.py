"""Application-side spoken queries over the live DCS menu hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata

from .protocol import MenuItem

_REPEAT = {"repeat", "repeat please", "say again", "say again please"}
_F10_ROOT_LABELS = {"f10", "f10other", "other"}
_F10_REQUESTS = {"f10", "f10other", "otherf10", "other"}
_KNOWN_ROOTS = {
    "wingman": "Wingman",
    "flight": "Flight",
    "secondelement": "Second Element",
    "atc": "ATC",
    "groundcrew": "Ground Crew",
}
_TOP_LEVEL_REQUESTS = {"", "all", "categories", "category", "toplevel"}
_COMMAND_WORDS = {"command", "commands", "cabans"}
_MINIMUM_NODE_SCORE = 0.72
_MINIMUM_NODE_LEAD = 0.10


@dataclass(frozen=True, slots=True)
class MetaCommand:
    kind: str
    node: str | None = None


@dataclass(frozen=True, slots=True)
class NodeListing:
    status: str
    node: str | None
    children: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _compact(text: str) -> str:
    return _normalise(text).replace(" ", "")


def parse_meta_command(transcript: str) -> MetaCommand | None:
    normalised = _normalise(transcript)
    if normalised in _REPEAT:
        return MetaCommand("repeat")

    words = normalised.split()
    if not words:
        return None

    # Treat every utterance beginning with "list" as informational.  A
    # malformed list request must never fall through to live action matching.
    if words[0] == "list":
        words = words[1:]
    elif words[-1] in _COMMAND_WORDS:
        # Safe cockpit shorthand: "F10 commands" or "ATC commands".
        pass
    else:
        return None

    if words and words[-1] in _COMMAND_WORDS:
        words = words[:-1]
    node = " ".join(words)
    if _compact(node) in _TOP_LEVEL_REQUESTS:
        node = ""
    return MetaCommand("list", node=node or None)


def _menu_nodes(items: tuple[MenuItem, ...]) -> dict[tuple[str, ...], tuple[str, ...]]:
    children_by_path: dict[tuple[str, ...], list[str]] = {}
    for item in items:
        for depth in range(1, len(item.path)):
            path = item.path[:depth]
            child = item.path[depth]
            children = children_by_path.setdefault(path, [])
            if _normalise(child) not in {_normalise(value) for value in children}:
                children.append(child)
    return {path: tuple(children) for path, children in children_by_path.items()}


def _display_path(path: tuple[str, ...]) -> str:
    return " ".join(path)


def _resolve_node(
    nodes: dict[tuple[str, ...], tuple[str, ...]], requested_node: str
) -> tuple[str, tuple[str, ...] | None, tuple[str, ...]]:
    wanted = _compact(requested_node)

    if wanted in _F10_REQUESTS:
        matches = [
            path
            for path in nodes
            if len(path) == 1 and _compact(path[0]) in _F10_ROOT_LABELS
        ]
        if matches:
            return "found", matches[0], ()
        return "unavailable", None, ()

    full_matches = [path for path in nodes if _compact(_display_path(path)) == wanted]
    if len(full_matches) == 1:
        return "found", full_matches[0], ()
    if len(full_matches) > 1:
        choices = tuple(_display_path(path) for path in full_matches)
        return "ambiguous", None, choices

    label_matches = [path for path in nodes if _compact(path[-1]) == wanted]
    if len(label_matches) == 1:
        return "found", label_matches[0], ()
    if len(label_matches) > 1:
        choices = tuple(_display_path(path) for path in label_matches)
        return "ambiguous", None, choices

    if wanted in _KNOWN_ROOTS:
        return "unavailable", (_KNOWN_ROOTS[wanted],), ()

    ranked: list[tuple[float, tuple[str, ...]]] = []
    normalised_wanted = _normalise(requested_node)
    for path in nodes:
        scores = (
            SequenceMatcher(None, normalised_wanted, _normalise(_display_path(path))).ratio(),
            SequenceMatcher(None, normalised_wanted, _normalise(path[-1])).ratio(),
        )
        ranked.append((max(scores), path))
    ranked.sort(key=lambda candidate: candidate[0], reverse=True)
    if not ranked or ranked[0][0] < _MINIMUM_NODE_SCORE:
        return "not_found", None, ()

    best_score = ranked[0][0]
    contenders = [path for score, path in ranked if best_score - score < _MINIMUM_NODE_LEAD]
    if len(contenders) > 1:
        choices = tuple(_display_path(path) for path in contenders)
        return "ambiguous", None, choices
    return "found", ranked[0][1], ()


def list_node_children(
    items: tuple[MenuItem, ...], requested_node: str | None
) -> NodeListing:
    """Return immediate children of a live menu node reconstructed from flattened paths."""
    if requested_node is None:
        roots: list[str] = []
        seen: set[str] = set()
        for item in items:
            root = item.path[0]
            key = _normalise(root)
            if key not in seen:
                seen.add(key)
                roots.append(root)
        return NodeListing("found", None, tuple(roots))

    nodes = _menu_nodes(items)
    status, path, choices = _resolve_node(nodes, requested_node)
    if status == "found" and path is not None:
        return NodeListing("found", _display_path(path), nodes[path])
    if status == "unavailable":
        display = path[0] if path is not None else "F10"
        return NodeListing("unavailable", display)
    return NodeListing(status, requested_node, choices=choices)


def spoken_listing(listing: NodeListing) -> str:
    """Format a deliberately terse cockpit response."""
    if listing.status == "ambiguous":
        return "Which menu? " + ". ".join(listing.choices) + "."
    if listing.status == "not_found":
        return "I didn't recognise that menu."
    if listing.status == "unavailable" or not listing.children:
        return f"No {listing.node} commands are currently available."
    return ". ".join(listing.children) + "."
