from pathlib import Path

import pytest

from llmvoice.audio.merge import encode_mp3
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
