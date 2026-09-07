"""Application-side spoken queries over the live DCS menu hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from .protocol import MenuItem

_LIST_RE = re.compile(r"^\s*list\s+(.+?)\s+commands?\s*[.!?]*\s*$", re.IGNORECASE)
_REPEAT = {"repeat", "repeat please", "say again", "say again please"}


@dataclass(frozen=True, slots=True)
class MetaCommand:
    kind: str
    node: str | None = None


@dataclass(frozen=True, slots=True)
class NodeListing:
    status: str
    node: str
    children: tuple[str, ...] = ()


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _compact(text: str) -> str:
    return _normalise(text).replace(" ", "")


def parse_meta_command(transcript: str) -> MetaCommand | None:
    normalised = _normalise(transcript)
    if normalised in _REPEAT:
        return MetaCommand("repeat")
    match = _LIST_RE.match(transcript)
    if match:
        node = match.group(1).strip()
        if node:
            return MetaCommand("list", node=node)
    return None


def list_node_children(items: tuple[MenuItem, ...], requested_node: str) -> NodeListing:
    """Return immediate children of a named node reconstructed from flattened paths."""
    wanted = _compact(requested_node)
    occurrences: list[tuple[str, tuple[str, ...]]] = []

    for item in items:
        for index, label in enumerate(item.path):
            if _compact(label) != wanted:
                continue
            child = item.path[index + 1] if index + 1 < len(item.path) else None
            if child is not None:
                occurrences.append((label, (child,)))

    if not occurrences:
        return NodeListing("not_found", requested_node)

    display_node = occurrences[0][0]
    children: list[str] = []
    seen: set[str] = set()
    for _, child_tuple in occurrences:
        child = child_tuple[0]
        key = _normalise(child)
        if key not in seen:
            seen.add(key)
            children.append(child)

    return NodeListing("found", display_node, tuple(children))


def spoken_listing(listing: NodeListing) -> str:
    """Format a deliberately terse cockpit response."""
    if listing.status != "found" or not listing.children:
        return f"No {listing.node} commands."
    return ". ".join(listing.children) + "."
