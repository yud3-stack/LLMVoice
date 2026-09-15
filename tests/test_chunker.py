from llmvoice.text.chunker import chunk_text


def test_chunks_at_sentence_boundaries() -> None:
    text = "Birinci cümle burada. İkinci cümle biraz uzundur. Üçüncü cümle."
    chunks = chunk_text(text, max_chars=40)
    assert chunks == [
        "Birinci cümle burada.",
        "İkinci cümle biraz uzundur.",
        "Üçüncü cümle.",
    ]
    assert all(len(chunk) <= 42 for chunk in chunks)


def test_hard_splits_long_sentence_without_losing_text() -> None:
    text = " ".join(f"kelime{i}" for i in range(30))
    chunks = chunk_text(text, max_chars=60)
    assert len(chunks) > 1
    assert " ".join(chunks) == text
    assert all(len(chunk) <= 60 for chunk in chunks)


def test_prefers_paragraph_boundary() -> None:
    assert chunk_text("Kısa paragraf.\n\nİkinci paragraf.", 100) == [
        "Kısa paragraf.",
        "İkinci paragraf.",
    ]


def test_does_not_combine_short_sentences() -> None:
    assert chunk_text("Birinci cümle. İkinci cümle.", 100) == [
        "Birinci cümle.",
        "İkinci cümle.",
    ]


def test_combines_short_sentences_when_minimum_is_requested() -> None:
    assert chunk_text("Bir. İki. Üç.", 40, min_chars=10) == ["Bir. İki. Üç."]


def test_does_not_split_common_abbreviation() -> None:
    assert chunk_text("Dr. Ayşe bugün geldi. Sonra gitti.", 100) == [
        "Dr. Ayşe bugün geldi.",
        "Sonra gitti.",
    ]
