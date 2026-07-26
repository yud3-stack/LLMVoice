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
