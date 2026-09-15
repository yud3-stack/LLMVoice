from __future__ import annotations

import re

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])(?:[\"'”’)\]]*)\s+")
_SOFT_BOUNDARY = re.compile(r"(?<=[,;:])\s+")
_ABBREVIATIONS = {
    "dr.", "mr.", "mrs.", "ms.", "prof.", "doç.", "örn.", "vb.", "vs.",
    "e.g.", "i.e.",
}


def _split_hard(text: str, limit: int) -> list[str]:
    parts: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        window = remaining[: limit + 1]
        candidates = [match.end() for match in _SOFT_BOUNDARY.finditer(window)]
        split_at = candidates[-1] if candidates else window.rfind(" ")
        if split_at < max(1, limit // 2):
            split_at = limit
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def _sentences(paragraph: str, limit: int) -> list[str]:
    raw_sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(paragraph.strip()) if part.strip()]
    result: list[str] = []
    for sentence in raw_sentences:
        # The punctuation in abbreviations is not a spoken sentence boundary.
        if result and _ends_with_abbreviation(result[-1]):
            sentence = f"{result.pop()} {sentence}"
        if result and _is_initial(result[-1]):
            sentence = f"{result.pop()} {sentence}"
        result.append(sentence)
    chunks: list[str] = []
    for sentence in result:
        chunks.extend(_split_hard(sentence, limit) if len(sentence) > limit else [sentence])
    return chunks


def _ends_with_abbreviation(text: str) -> bool:
    token = text.rsplit(maxsplit=1)[-1].casefold()
    return token in _ABBREVIATIONS


def _is_initial(text: str) -> bool:
    token = text.rsplit(maxsplit=1)[-1]
    return len(token) == 2 and token[0].isalpha() and token[1] == "."


def _combine_short(chunks: list[str], limit: int, minimum: int) -> list[str]:
    if minimum <= 0:
        return chunks
    combined: list[str] = []
    for chunk in chunks:
        if combined and len(combined[-1]) < minimum and len(combined[-1]) + 1 + len(chunk) <= limit:
            combined[-1] = f"{combined[-1]} {chunk}"
        else:
            combined.append(chunk)
    return combined


def chunk_text(text: str, max_chars: int = 220, min_chars: int = 0) -> list[str]:
    """Create bounded chunks while avoiding awkward short synthesis jobs."""
    if max_chars < 40:
        raise ValueError("max_chars must be at least 40")
    if min_chars < 0 or min_chars > max_chars:
        raise ValueError("min_chars must be between 0 and max_chars")
    chunks: list[str] = []
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences = _sentences(paragraph, max_chars)
        chunks.extend(_combine_short(sentences, max_chars, min_chars))
    return chunks
