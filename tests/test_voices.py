from pathlib import Path

import pytest

from llmvoice.core.exceptions import VoiceError
from llmvoice.core.paths import AppPaths
from llmvoice.voices.manager import VoiceManager


def _audio(path: Path) -> Path:
    path.write_bytes(b"test audio placeholder")
    return path


def test_add_list_resolve_and_remove_voice(tmp_path) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    source = _audio(tmp_path / "friday.wav")
    stored = manager.add("friday", source)

    assert stored.read_bytes() == source.read_bytes()
    assert manager.list() == ["friday"]
    assert manager.resolve("friday") == stored

    manager.remove("friday")
    assert manager.list() == []


def test_resolves_direct_audio_path(tmp_path) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    source = _audio(tmp_path / "reference.mp3")
    assert manager.resolve(str(source)) == source.resolve()


def test_missing_voice_has_actionable_message(tmp_path) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    with pytest.raises(VoiceError, match="llmvoice voice list"):
        manager.resolve("missing")


def test_rejects_wildcard_voice_lookup(tmp_path) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    _audio(manager.paths.voices_dir / "private.wav")
    with pytest.raises(VoiceError, match="Voice name"):
        manager.resolve("*")


@pytest.mark.parametrize("name", ["../escape", "has space", ".hidden", "a" * 65])
def test_rejects_unsafe_voice_names(tmp_path, name: str) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    with pytest.raises(VoiceError):
        manager.add(name, _audio(tmp_path / "voice.wav"))
