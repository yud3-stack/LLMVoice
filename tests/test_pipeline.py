from pathlib import Path

import pytest

from llmvoice.core.config import AppConfig
from llmvoice.core.exceptions import EngineError, SpeechGenerationError
from llmvoice.core.paths import AppPaths
from llmvoice.service import SynthesisPlan, SynthesisRequest, VoiceService
from llmvoice.tts.base import TTSEngine


class FakeEngine(TTSEngine):
    def __init__(self) -> None:
        self.loaded = False
        self.calls: list[str] = []

    @property
    def display_name(self) -> str:
        return "Fake"

    def load(self) -> None:
        self.loaded = True

    def synthesize(
        self,
        text: str,
        voice_path: Path,
        language: str,
        output_path: Path,
    ) -> None:
        self.calls.append(text)
        output_path.write_bytes(b"wav")


def test_pipeline_is_engine_mockable(tmp_path, monkeypatch) -> None:
    paths = AppPaths(tmp_path / "data")
    paths.ensure()
    reference = tmp_path / "voice.wav"
    reference.write_bytes(b"voice")
    output = tmp_path / "output.mp3"
    engine = FakeEngine()
    stages: list[str] = []
    progress: list[tuple[int, int]] = []

    monkeypatch.setattr(
        "llmvoice.service.prepare_reference",
        lambda source, cache: source,
    )
    monkeypatch.setattr(
        "llmvoice.service.merge_wav_files",
        lambda chunks, destination, pause_ms=0, crossfade_ms=0: destination.write_bytes(b"merged"),
    )
    monkeypatch.setattr(
        "llmvoice.service.encode_mp3",
        lambda source, destination, speed: destination.write_bytes(b"mp3"),
    )

    VoiceService(engine, paths, AppConfig()).run(
        SynthesisRequest(
            input_path=tmp_path / "input.txt",
            output_path=output,
            voice_path=reference,
            language="tr",
            speed=1.0,
        ),
        SynthesisPlan(text="Bir. İki.", chunks=["Bir.", "İki."], language="tr"),
        progress=lambda current, total: progress.append((current, total)),
        stage=stages.append,
    )

    assert engine.loaded
    assert engine.calls == ["Bir.", "İki."]
    assert progress == [(1, 2), (2, 2)]
    assert stages == [
        "preparing_reference",
        "reference_ready",
        "loading_model",
        "model_ready",
        "merging",
        "merge_done",
        "encoding",
        "encoding_done",
    ]
    assert output.read_bytes() == b"mp3"
    assert not list(paths.cache_dir.glob("job-*"))


class FailingEngine(FakeEngine):
    def __init__(self, failure: BaseException) -> None:
        super().__init__()
        self.failure = failure

    def synthesize(
        self,
        text: str,
        voice_path: Path,
        language: str,
        output_path: Path,
    ) -> None:
        if len(self.calls) == 1:
            raise self.failure
        super().synthesize(text, voice_path, language, output_path)


def _run_failing_pipeline(tmp_path, monkeypatch, failure: BaseException) -> AppPaths:
    paths = AppPaths(tmp_path / "data")
    paths.ensure()
    reference = tmp_path / "voice.wav"
    reference.write_bytes(b"voice")
    monkeypatch.setattr("llmvoice.service.prepare_reference", lambda source, cache: source)
    engine = FailingEngine(failure)
    service = VoiceService(engine, paths, AppConfig())
    service.run(
        SynthesisRequest(
            input_path=tmp_path / "input.txt",
            output_path=tmp_path / "output.mp3",
            voice_path=reference,
            language="en",
            speed=1.0,
        ),
        SynthesisPlan("One. Two.", ["One.", "Two."], "en"),
        progress=lambda current, total: None,
        stage=lambda name: None,
    )
    return paths


def test_chunk_failure_has_context_and_cleans_temp(tmp_path, monkeypatch) -> None:
    with pytest.raises(SpeechGenerationError, match="Chunk: 2 / 2"):
        _run_failing_pipeline(tmp_path, monkeypatch, EngineError("technical detail"))
    assert not list((tmp_path / "data" / "cache").glob("job-*"))
    assert not (tmp_path / "output.mp3").exists()


def test_keyboard_interrupt_cleans_temp_and_partial_output(tmp_path, monkeypatch) -> None:
    with pytest.raises(KeyboardInterrupt):
        _run_failing_pipeline(tmp_path, monkeypatch, KeyboardInterrupt())
    assert not list((tmp_path / "data" / "cache").glob("job-*"))
    assert not (tmp_path / "output.mp3").exists()


def test_resume_reuses_completed_chunks(tmp_path, monkeypatch) -> None:
    paths = AppPaths(tmp_path / "data")
    paths.ensure()
    reference = tmp_path / "voice.wav"
    reference.write_bytes(b"voice")
    (tmp_path / "input.txt").write_text("One. Two. Three.", encoding="utf-8")
    output = tmp_path / "output.mp3"
    monkeypatch.setattr("llmvoice.service.prepare_reference", lambda source, cache: source)
    monkeypatch.setattr(
        "llmvoice.service.merge_wav_files",
        lambda chunks, destination, pause_ms=0, crossfade_ms=0: destination.write_bytes(b"merged"),
    )
    monkeypatch.setattr(
        "llmvoice.service.encode_mp3",
        lambda source, destination, speed: destination.write_bytes(b"mp3"),
    )

    class InterruptingEngine(FakeEngine):
        def synthesize(self, text, voice_path, language, output_path) -> None:
            if text == "Two.":
                raise EngineError("interrupted")
            super().synthesize(text, voice_path, language, output_path)

    request = SynthesisRequest(
        input_path=tmp_path / "input.txt",
        output_path=output,
        voice_path=reference,
        language="en",
        speed=1.0,
    )
    plan = SynthesisPlan("One. Two. Three.", ["One.", "Two.", "Three."], "en")

    with pytest.raises(SpeechGenerationError, match="Chunk: 2 / 3"):
        VoiceService(InterruptingEngine(), paths, AppConfig()).run(
            request,
            plan,
            progress=lambda current, total: None,
            stage=lambda name: None,
            resume=True,
        )

    checkpoint_dirs = list((paths.cache_dir / "checkpoints").iterdir())
    assert len(checkpoint_dirs) == 1
    assert (checkpoint_dirs[0] / "chunk-00001.wav").exists()

    resumed = FakeEngine()
    VoiceService(resumed, paths, AppConfig()).run(
        request,
        plan,
        progress=lambda current, total: None,
        stage=lambda name: None,
        resume=True,
    )

    assert resumed.calls == ["Two.", "Three."]
    assert output.read_bytes() == b"mp3"
    assert not list((paths.cache_dir / "checkpoints").iterdir())
