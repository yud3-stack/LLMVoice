from pathlib import Path

import pytest

from llmvoice.core.exceptions import EngineError
from llmvoice.tts.xtts import XTTSEngine


class FakeXttsApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def tts_to_file(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_reuses_cloned_speaker_embedding(tmp_path) -> None:
    engine = XTTSEngine("cpu", tmp_path / "models")
    api = FakeXttsApi()
    engine._model = api
    voice = tmp_path / "voice-hash.wav"
    voice.write_bytes(b"voice")

    engine.synthesize("Bir.", voice, "tr", tmp_path / "one.wav")
    engine.synthesize("İki.", voice, "tr", tmp_path / "two.wav")

    assert api.calls[0]["speaker_wav"] == str(voice)
    assert api.calls[1]["speaker_wav"] is None
    assert api.calls[0]["speaker"] == api.calls[1]["speaker"]


def test_rejects_unsupported_language_before_model_call(tmp_path) -> None:
    engine = XTTSEngine("cpu", tmp_path / "models")
    engine._model = FakeXttsApi()
    with pytest.raises(EngineError, match="does not support"):
        engine.synthesize("Hej.", Path("voice.wav"), "sv", tmp_path / "out.wav")


def test_same_filename_in_different_directories_has_distinct_speaker_id(tmp_path) -> None:
    engine = XTTSEngine("cpu", tmp_path / "models")
    api = FakeXttsApi()
    engine._model = api
    first = tmp_path / "one" / "voice.wav"
    second = tmp_path / "two" / "voice.wav"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    engine.synthesize("One.", first, "en", tmp_path / "one.wav")
    engine.synthesize("Two.", second, "en", tmp_path / "two.wav")
    assert api.calls[0]["speaker"] != api.calls[1]["speaker"]
    assert api.calls[1]["speaker_wav"] == str(second)


def test_model_installation_detection(tmp_path) -> None:
    engine = XTTSEngine("cpu", tmp_path / "models")
    assert not engine.is_model_installed
    (tmp_path / "models" / "tts_models--multilingual--multi-dataset--xtts_v2").mkdir(
        parents=True
    )
    assert engine.is_model_installed
