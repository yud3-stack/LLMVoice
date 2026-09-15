from llmvoice.text.normalizer import normalize_speech_text, normalize_text


def test_normalizes_spaces_and_single_line_breaks() -> None:
    source = "Merhaba     arkadaşlar.\nBugün yeni\nbir konuya başlayacağız."
    assert normalize_text(source) == (
        "Merhaba arkadaşlar. Bugün yeni bir konuya başlayacağız."
    )


def test_preserves_paragraphs_and_utf8() -> None:
    source = "\ufeff  Türkçe  metin. \r\n\r\n  English   text.  "
    assert normalize_text(source) == "Türkçe metin.\n\nEnglish text."


def test_turkish_speech_normalization_expands_numbers_and_abbreviations() -> None:
    source = "Dr. Ayşe 2026'da %15 büyüdü. 12,5 dk. sürdü."
    normalized = normalize_speech_text(source, "tr")
    assert normalized == (
        "doktor Ayşe iki bin yirmi altı'da yüzde on beş büyüdü. "
        "on iki virgül beş dakika sürdü."
    )


def test_speech_normalization_does_not_rewrite_english() -> None:
    source = "The year is 2026 and growth is 15%."
    assert normalize_speech_text(source, "en") == source


def test_turkish_speech_normalization_expands_measurements_and_currency() -> None:
    source = "5 km yol, 2 GB veri ve 125 TL ödeme."
    assert normalize_speech_text(source, "tr") == (
        "beş kilometre yol, iki gigabayt veri ve yüz yirmi beş lira ödeme."
    )
