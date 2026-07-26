from __future__ import annotations

import re

_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)
_TR_MARKERS = {"bir", "bu", "ve", "ile", "için", "çok", "de", "da", "mi", "ama", "gibi"}
_EN_MARKERS = {"the", "and", "is", "to", "of", "in", "for", "this", "that", "with", "but"}


def detect_language(text: str) -> str:
    """Distinguish Turkish and English using a dependency-free heuristic."""
    lowered = text.casefold()
    if any(character in lowered for character in "çğıöşü"):
        return "tr"
    words = {word.casefold() for word in _WORDS.findall(lowered)}
    tr_score = len(words & _TR_MARKERS)
    en_score = len(words & _EN_MARKERS)
    return "en" if en_score > tr_score else "tr"


def resolve_language(requested: str, text: str) -> str:
    language = requested.strip().casefold()
    return detect_language(text) if language == "auto" else language

