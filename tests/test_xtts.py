from pathlib import Path

import pytest

from llmvoice.core.exceptions import EngineError
from llmvoice.tts.xtts import XTTSEngine


class FakeXttsApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def tts_to_file(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_uses_reference_for_each_chunk(tmp_path) -> None:
    engine = XTTSEngine("cpu", tmp_path / "models")
    api = FakeXttsApi()
    engine._model = api
    voice = tmp_path / "voice-hash.wav"
    voice.write_bytes(b"voice")

    engine.synthesize("Bir.", voice, "tr", tmp_path / "one.wav")
    engine.synthesize("İki.", voice, "tr", tmp_path / "two.wav")

    assert api.calls[0]["speaker_wav"] == str(voice)
    assert api.calls[1]["speaker_wav"] == str(voice)
    assert api.calls[0]["speaker"] == api.calls[1]["speaker"]


def test_quality_profile_controls_sampling_and_sentence_splitting(tmp_path) -> None:
    engine = XTTSEngine("cpu", tmp_path / "models")
    api = FakeXttsApi()
    engine._model = api
    engine.set_quality_profile("natural")
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice")

    engine.synthesize("Bir.", voice, "tr", tmp_path / "one.wav")

    assert api.calls[0]["split_sentences"] is False
    assert api.calls[0]["temperature"] == 0.85
    assert api.calls[0]["top_p"] == 0.90


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


def test_uses_multiple_references_when_provided(tmp_path) -> None:
    engine = XTTSEngine("cpu", tmp_path / "models")
    api = FakeXttsApi()
    engine._model = api
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    engine.synthesize("Bir.", [first, second], "tr", tmp_path / "one.wav")

    assert api.calls[0]["speaker_wav"] == [str(first), str(second)]


def test_model_installation_detection(tmp_path) -> None:
    engine = XTTSEngine("cpu", tmp_path / "models")
    assert not engine.is_model_installed
    (tmp_path / "models" / "tts_models--multilingual--multi-dataset--xtts_v2").mkdir(
        parents=True
    )
    assert engine.is_model_installed
