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
