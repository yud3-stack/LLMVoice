from pathlib import Path

from llmvoice.core.config import AppConfig
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
        lambda chunks, destination: destination.write_bytes(b"merged"),
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
    assert output.read_bytes() == b"mp3"
    assert not list(paths.cache_dir.glob("job-*"))

