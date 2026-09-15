from __future__ import annotations

import re

_HORIZONTAL_SPACE = re.compile(r"[^\S\r\n]+")
_LINE_BREAK = re.compile(r"\s*\n\s*")
_PARAGRAPH_BREAK = re.compile(r"\n{2,}")
_TURKISH_ABBREVIATIONS = {
    "dr.": "doktor",
    "prof.": "profesör",
    "doç.": "doçent",
    "sn.": "saniye",
    "dk.": "dakika",
    "örn.": "örneğin",
    "vb.": "ve benzeri",
    "vs.": "vesaire",
}
_TURKISH_PERCENT = re.compile(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*%")
_TURKISH_PERCENT_PREFIX = re.compile(r"(?<!\w)%\s*(\d+(?:[.,]\d+)?)")
_TURKISH_DECIMAL = re.compile(r"(?<![\w.])(\d+)[,.](\d+)(?![\w.])")
_TURKISH_INTEGER = re.compile(r"(?<![\w.])\d+(?![\w.])")
_TURKISH_NUMBER_SUFFIX = re.compile(r"(?<![\w.])(\d+)'([A-Za-zÇĞİÖŞÜçğıöşü]+)")
_TURKISH_CURRENCY = re.compile(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(₺|TL|TRY)\b", re.IGNORECASE)
_TURKISH_UNIT = re.compile(
    r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(km|kg|GB|MB|MHz|°C)\b", re.IGNORECASE
)

_ONES = (
    "sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"
)
_TENS = (
    "", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"
)


def _under_thousand(value: int) -> str:
    parts: list[str] = []
    hundreds, remainder = divmod(value, 100)
    if hundreds:
        parts.append("yüz" if hundreds == 1 else f"{_ONES[hundreds]} yüz")
    tens, ones = divmod(remainder, 10)
    if tens:
        parts.append(_TENS[tens])
    if ones:
        parts.append(_ONES[ones])
    return " ".join(parts)


def _turkish_number(value: int) -> str:
    if value < 1000:
        return _under_thousand(value)
    thousands, remainder = divmod(value, 1000)
    parts = []
    if thousands:
        parts.append("bin" if thousands == 1 else f"{_turkish_number(thousands)} bin")
    if remainder:
        parts.append(_under_thousand(remainder))
    return " ".join(parts)


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


def normalize_speech_text(text: str, language: str) -> str:
    """Rewrite common Turkish numeric forms into pronunciation-friendly text."""
    if language.casefold() not in {"tr", "turkish"}:
        return text

    for abbreviation, spoken in _TURKISH_ABBREVIATIONS.items():
        text = re.sub(rf"(?<!\w){re.escape(abbreviation)}(?=\s|$)", spoken, text, flags=re.IGNORECASE)

    def spoken_percent(raw_value: str) -> str:
        value = raw_value.replace(",", ".")
        if "." in value:
            whole, fraction = value.split(".", 1)
            return f"yüzde {_turkish_number(int(whole))} virgül {_turkish_number(int(fraction))}"
        return f"yüzde {_turkish_number(int(value))}"

    def spoken_measurement(match: re.Match[str]) -> str:
        value = match.group(1).replace(",", ".")
        number = (
            f"{_turkish_number(int(value.split('.')[0]))} virgül "
            f"{_turkish_number(int(value.split('.')[1]))}"
            if "." in value
            else _turkish_number(int(value))
        )
        units = {
            "km": "kilometre", "kg": "kilogram", "gb": "gigabayt",
            "mb": "megabayt", "mhz": "megahertz", "°c": "derece",
        }
        unit = units[match.group(2).casefold()]
        return f"{number} {unit}"

    def spoken_currency(match: re.Match[str]) -> str:
        value = match.group(1).replace(",", ".")
        number = (
            f"{_turkish_number(int(value.split('.')[0]))} virgül "
            f"{_turkish_number(int(value.split('.')[1]))}"
            if "." in value
            else _turkish_number(int(value))
        )
        return f"{number} lira"

    text = _TURKISH_PERCENT.sub(lambda match: spoken_percent(match.group(1)), text)
    text = _TURKISH_PERCENT_PREFIX.sub(lambda match: spoken_percent(match.group(1)), text)
    text = _TURKISH_CURRENCY.sub(spoken_currency, text)
    text = _TURKISH_UNIT.sub(spoken_measurement, text)

    def decimal(match: re.Match[str]) -> str:
        return (
            f"{_turkish_number(int(match.group(1)))} virgül "
            f"{_turkish_number(int(match.group(2)))}"
        )

    text = _TURKISH_DECIMAL.sub(decimal, text)
    text = _TURKISH_NUMBER_SUFFIX.sub(
        lambda match: f"{_turkish_number(int(match.group(1)))}'{match.group(2)}", text
    )
    return _TURKISH_INTEGER.sub(lambda match: _turkish_number(int(match.group(0))), text)
