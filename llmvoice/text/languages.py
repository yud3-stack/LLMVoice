from __future__ import annotations

LANGUAGE_NAMES = {
    "ar": "Arabic",
    "cs": "Czech",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi",
    "hu": "Hungarian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ru": "Russian",
    "tr": "Turkish",
    "zh-cn": "Chinese",
}

SUPPORTED_LANGUAGES = frozenset(LANGUAGE_NAMES)


def language_label(code: str, auto_detected: bool = False) -> str:
    """Return a friendly language label while preserving the engine code."""
    name = LANGUAGE_NAMES.get(code, code.upper())
    suffix = " — auto detected" if auto_detected else ""
    return f"{name} ({code}){suffix}"
