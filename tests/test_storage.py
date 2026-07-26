from pathlib import Path

import pytest

from llmvoice.core.exceptions import DiskSpaceError
from llmvoice.core.storage import (
    MIN_DISK_RESERVE_BYTES,
    check_disk_space,
    check_synthesis_disk_space,
    estimate_speech_seconds,
    required_disk_bytes,
    required_output_bytes,
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


def _usage(free: int):
    return type("Usage", (), {"free": free, "total": free * 2, "used": free})()


def test_cache_drive_insufficient(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    output_dir = tmp_path / "output"
    cache.mkdir()
    output_dir.mkdir()
    monkeypatch.setattr(
        "llmvoice.core.storage._volume_key",
        lambda path: "cache" if Path(path) == cache else "output",
    )
    monkeypatch.setattr(
        "llmvoice.core.storage.shutil.disk_usage",
        lambda path: _usage(1) if Path(path) == cache else _usage(10**12),
    )

    with pytest.raises(DiskSpaceError, match="temporary audio") as error:
        check_synthesis_disk_space(cache, output_dir / "speech.mp3", 600)
    assert "LLMVOICE_DATA_DIR" in str(error.value)


def test_output_drive_insufficient(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    output_dir = tmp_path / "output"
    cache.mkdir()
    output_dir.mkdir()
    monkeypatch.setattr(
        "llmvoice.core.storage._volume_key",
        lambda path: "cache" if Path(path) == cache else "output",
    )
    monkeypatch.setattr(
        "llmvoice.core.storage.shutil.disk_usage",
        lambda path: _usage(10**12) if Path(path) == cache else _usage(1),
    )

    with pytest.raises(DiskSpaceError, match="for output"):
        check_synthesis_disk_space(cache, output_dir / "speech.mp3", 600)


def test_same_drive_is_checked_once_with_combined_requirement(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    output_dir = tmp_path / "output"
    cache.mkdir()
    output_dir.mkdir()
    calls: list[Path] = []
    required = required_disk_bytes(600) + required_output_bytes(600)
    monkeypatch.setattr("llmvoice.core.storage._volume_key", lambda path: "same")

    def disk_usage(path):
        calls.append(Path(path))
        return _usage(required)

    monkeypatch.setattr("llmvoice.core.storage.shutil.disk_usage", disk_usage)
    available, reported_required = check_synthesis_disk_space(
        cache, output_dir / "speech.mp3", 600
    )
    assert available == required
    assert reported_required == required
    assert calls == [cache]


def test_same_drive_failure_is_reported_once(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    output_dir = tmp_path / "output"
    cache.mkdir()
    output_dir.mkdir()
    calls: list[Path] = []
    required = required_disk_bytes(600) + required_output_bytes(600)
    monkeypatch.setattr("llmvoice.core.storage._volume_key", lambda path: "same")

    def disk_usage(path):
        calls.append(Path(path))
        return _usage(required - 1)

    monkeypatch.setattr("llmvoice.core.storage.shutil.disk_usage", disk_usage)
    with pytest.raises(DiskSpaceError, match="temporary audio and output"):
        check_synthesis_disk_space(cache, output_dir / "speech.mp3", 600)
    assert calls == [cache]


def test_both_drives_sufficient(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    output_dir = tmp_path / "output"
    cache.mkdir()
    output_dir.mkdir()
    monkeypatch.setattr(
        "llmvoice.core.storage._volume_key",
        lambda path: "cache" if Path(path) == cache else "output",
    )
    monkeypatch.setattr(
        "llmvoice.core.storage.shutil.disk_usage",
        lambda path: _usage(10**12),
    )
    available, required = check_synthesis_disk_space(
        cache, output_dir / "speech.mp3", 600
    )
    assert available == 10**12
    assert required == required_disk_bytes(600) + required_output_bytes(600)
