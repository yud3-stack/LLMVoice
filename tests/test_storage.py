import pytest

from llmvoice.core.exceptions import DiskSpaceError
from llmvoice.core.storage import (
    MIN_DISK_RESERVE_BYTES,
    check_disk_space,
    estimate_speech_seconds,
    required_disk_bytes,
)


def test_speech_and_disk_estimates_are_conservative() -> None:
    seconds = estimate_speech_seconds("word " * 150)
    assert seconds == pytest.approx(60.0)
    assert required_disk_bytes(seconds) > MIN_DISK_RESERVE_BYTES


def test_low_disk_space_is_rejected(tmp_path, monkeypatch) -> None:
    usage = type("Usage", (), {"free": 1, "total": 2, "used": 1})()
    monkeypatch.setattr("llmvoice.core.storage.shutil.disk_usage", lambda path: usage)
    with pytest.raises(DiskSpaceError, match="Not enough free disk space"):
        check_disk_space(tmp_path / "output.mp3", estimated_seconds=600)
