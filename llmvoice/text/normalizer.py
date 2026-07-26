from __future__ import annotations

import re

_HORIZONTAL_SPACE = re.compile(r"[^\S\r\n]+")
_LINE_BREAK = re.compile(r"\s*\n\s*")
_PARAGRAPH_BREAK = re.compile(r"\n{2,}")


def normalize_text(text: str) -> str:
    """Normalize whitespace without rewriting words or punctuation."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    paragraphs = _PARAGRAPH_BREAK.split(text)
    normalized: list[str] = []
    for paragraph in paragraphs:
        lines = [_HORIZONTAL_SPACE.sub(" ", line).strip() for line in paragraph.split("\n")]
        joined = _LINE_BREAK.sub(" ", "\n".join(line for line in lines if line))
        if joined:
            normalized.append(joined.strip())
    return "\n\n".join(normalized)

