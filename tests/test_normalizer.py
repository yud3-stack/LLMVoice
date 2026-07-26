from llmvoice.text.normalizer import normalize_text


def test_normalizes_spaces_and_single_line_breaks() -> None:
    source = "Merhaba     arkadaşlar.\nBugün yeni\nbir konuya başlayacağız."
    assert normalize_text(source) == (
        "Merhaba arkadaşlar. Bugün yeni bir konuya başlayacağız."
    )


def test_preserves_paragraphs_and_utf8() -> None:
    source = "\ufeff  Türkçe  metin. \r\n\r\n  English   text.  "
    assert normalize_text(source) == "Türkçe metin.\n\nEnglish text."

