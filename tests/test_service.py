from pathlib import Path

import pytest

from llmvoice.core.exceptions import InputFileError
from llmvoice.service import output_path_for, read_and_plan


def test_default_output_is_next_to_input(tmp_path) -> None:
    transcript = tmp_path / "episode.txt"
    assert output_path_for(transcript, None) == tmp_path / "episode.mp3"


def test_explicit_output_is_resolved(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert output_path_for(tmp_path / "input.txt", Path("custom.mp3")) == (
        tmp_path / "custom.mp3"
    )


def test_invalid_input_missing(tmp_path) -> None:
    with pytest.raises(InputFileError, match="Input file not found"):
        read_and_plan(tmp_path / "missing.txt", "tr", 220)


def test_invalid_input_extension(tmp_path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("Merhaba.", encoding="utf-8")
    with pytest.raises(InputFileError, match=r"\.txt"):
        read_and_plan(source, "tr", 220)


def test_empty_input(tmp_path) -> None:
    source = tmp_path / "empty.txt"
    source.write_text(" \n\n ", encoding="utf-8")
    with pytest.raises(InputFileError, match="contains no text"):
        read_and_plan(source, "tr", 220)


def test_auto_language_and_chunks(tmp_path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("This is an English sentence. This is another one.", encoding="utf-8")
    plan = read_and_plan(source, "auto", 40)
    assert plan.language == "en"
    assert len(plan.chunks) == 2

