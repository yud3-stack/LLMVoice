from __future__ import annotations

import re

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])(?:[\"'”’)\]]*)\s+")
_SOFT_BOUNDARY = re.compile(r"(?<=[,;:])\s+")


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
    result: list[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(paragraph.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        result.extend(_split_hard(sentence, limit) if len(sentence) > limit else [sentence])
    return result


def chunk_text(text: str, max_chars: int = 220) -> list[str]:
    """Create natural, bounded chunks, preferring paragraphs then sentences."""
    if max_chars < 40:
        raise ValueError("max_chars must be at least 40")
    chunks: list[str] = []
    current = ""
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences = _sentences(paragraph, max_chars)
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            chunks.append(current)
            current = ""
    return chunks

