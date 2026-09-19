from pathlib import Path

import pytest

from llmvoice.audio.merge import encode_mp3, encode_wav
from llmvoice.core.exceptions import AudioToolError


def test_failed_encoding_leaves_no_partial_output(tmp_path, monkeypatch) -> None:
    source = tmp_path / "merged.wav"
    source.write_bytes(b"wav")
    output = tmp_path / "output.mp3"
    monkeypatch.setattr("llmvoice.audio.merge.require_ffmpeg", lambda: ("ffmpeg", "ffprobe"))

    def fail_after_partial(arguments: list[str], purpose: str) -> None:
        Path(arguments[-1]).write_bytes(b"partial")
        raise AudioToolError("encoding failed")

    monkeypatch.setattr("llmvoice.audio.merge.run_tool", fail_after_partial)
    with pytest.raises(AudioToolError, match="encoding failed"):
        encode_mp3(source, output, speed=1.0)
    assert not output.exists()
    assert not list(tmp_path.glob(".output.llmvoice-*.mp3"))


def test_failed_forced_encoding_preserves_existing_output(tmp_path, monkeypatch) -> None:
    source = tmp_path / "merged.wav"
    source.write_bytes(b"wav")
    output = tmp_path / "output.mp3"
    output.write_bytes(b"known-good-output")
    monkeypatch.setattr("llmvoice.audio.merge.require_ffmpeg", lambda: ("ffmpeg", "ffprobe"))

    def fail_after_partial(arguments: list[str], purpose: str) -> None:
        Path(arguments[-1]).write_bytes(b"partial")
        raise AudioToolError("disk full")

    monkeypatch.setattr("llmvoice.audio.merge.run_tool", fail_after_partial)
    with pytest.raises(AudioToolError, match="disk full"):
        encode_mp3(source, output, speed=1.0)
    assert output.read_bytes() == b"known-good-output"
    assert not list(tmp_path.glob(".output.llmvoice-*.mp3"))


def test_encoding_normalizes_loudness_and_applies_speed(tmp_path, monkeypatch) -> None:
    source = tmp_path / "merged.wav"
    source.write_bytes(b"wav")
    output = tmp_path / "output.mp3"
    arguments_seen: list[str] = []
    monkeypatch.setattr("llmvoice.audio.merge.require_ffmpeg", lambda: ("ffmpeg", "ffprobe"))

    def capture(arguments: list[str], purpose: str) -> None:
        arguments_seen.extend(arguments)
        Path(arguments[-1]).write_bytes(b"mp3")

    monkeypatch.setattr("llmvoice.audio.merge.run_tool", capture)

    encode_mp3(source, output, speed=0.95)

    assert arguments_seen[arguments_seen.index("-filter:a") + 1] == (
        "atempo=0.9500,loudnorm=I=-16:TP=-1.5:LRA=11"
    )


def test_wav_encoding_uses_pcm_and_atomic_wav_output(tmp_path, monkeypatch) -> None:
    source = tmp_path / "merged.wav"
    source.write_bytes(b"wav")
    output = tmp_path / "output.wav"
    arguments_seen: list[str] = []
    monkeypatch.setattr("llmvoice.audio.merge.require_ffmpeg", lambda: ("ffmpeg", "ffprobe"))

    def capture(arguments: list[str], purpose: str) -> None:
        arguments_seen.extend(arguments)
        Path(arguments[-1]).write_bytes(b"wav")

    monkeypatch.setattr("llmvoice.audio.merge.run_tool", capture)

    encode_wav(source, output, speed=1.0)

    assert output.read_bytes() == b"wav"
    assert arguments_seen[arguments_seen.index("-c:a") + 1] == "pcm_s16le"
    assert not list(tmp_path.glob(".output.llmvoice-*.wav"))
