from pathlib import Path

import pytest

from llmvoice.audio.metadata import AudioMetadata
from llmvoice.core.exceptions import VoiceError
from llmvoice.core.paths import AppPaths
from llmvoice.voices.manager import VoiceManager


def _audio(path: Path) -> Path:
    path.write_bytes(b"test audio placeholder")
    return path


@pytest.fixture()
def audio_metadata(monkeypatch) -> AudioMetadata:
    metadata = AudioMetadata(12.5, 44100, 1, "pcm_s16le", "wav")
    monkeypatch.setattr("llmvoice.voices.manager.probe_audio", lambda path: metadata)
    return metadata


def test_add_list_resolve_and_remove_voice(tmp_path, audio_metadata) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    source = _audio(tmp_path / "friday.wav")
    stored = manager.add("friday", source)

    assert stored.path.read_bytes() == source.read_bytes()
    assert [voice.name for voice in manager.list()] == ["friday"]
    assert manager.resolve("friday") == stored.path

    manager.remove("friday")
    assert manager.list() == []


def test_list_keeps_voice_names_that_end_in_a_number(tmp_path, audio_metadata) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    source = _audio(tmp_path / "voice-2.wav")

    manager.add("voice-2", source)

    assert [voice.name for voice in manager.list()] == ["voice-2"]


def test_list_hides_only_references_with_an_existing_primary(tmp_path, audio_metadata) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    manager.add("voice", _audio(tmp_path / "voice.wav"), (_audio(tmp_path / "extra.wav"),))

    assert [voice.name for voice in manager.list()] == ["voice"]


def test_list_and_info_include_metadata(tmp_path, audio_metadata) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    manager.add("friday", _audio(tmp_path / "friday.wav"))
    listed = manager.list()
    info = manager.info("friday")
    assert listed[0].metadata.duration_seconds == 12.5
    assert info.metadata.sample_rate == 44100


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
def test_rejects_unsafe_voice_names(tmp_path, name: str, audio_metadata) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    with pytest.raises(VoiceError):
        manager.add(name, _audio(tmp_path / "voice.wav"))


def test_broken_audio_is_rejected_before_copy(tmp_path, monkeypatch) -> None:
    from llmvoice.core.exceptions import AudioToolError

    manager = VoiceManager(AppPaths(tmp_path / "data"))
    source = _audio(tmp_path / "broken.wav")
    monkeypatch.setattr(
        "llmvoice.voices.manager.probe_audio",
        lambda path: (_ for _ in ()).throw(AudioToolError("unreadable")),
    )
    with pytest.raises(AudioToolError, match="unreadable"):
        manager.add("broken", source)
    assert not (manager.paths.voices_dir / "broken.wav").exists()


def test_too_short_audio_is_rejected(tmp_path, monkeypatch) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    source = _audio(tmp_path / "short.wav")
    monkeypatch.setattr(
        "llmvoice.voices.manager.probe_audio",
        lambda path: AudioMetadata(1.4, 24000, 1, "pcm_s16le", "wav"),
    )
    with pytest.raises(VoiceError, match="too short"):
        manager.add("short", source)


def test_add_rejects_short_additional_reference_before_copy(tmp_path, monkeypatch) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    first = _audio(tmp_path / "first.wav")
    second = _audio(tmp_path / "second.wav")

    def metadata_for(path: Path) -> AudioMetadata:
        duration = 12.0 if path == first else 1.0
        return AudioMetadata(duration, 24000, 1, "pcm_s16le", "wav")

    monkeypatch.setattr("llmvoice.voices.manager.probe_audio", metadata_for)

    with pytest.raises(VoiceError, match="too short"):
        manager.add("friday", first, (second,))
    assert not (manager.paths.voices_dir / "friday.wav").exists()
    assert not (manager.paths.voices_dir / "friday-2.wav").exists()


def test_add_reference_rejects_unreadable_audio_before_copy(tmp_path, monkeypatch, audio_metadata) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    manager.add("friday", _audio(tmp_path / "first.wav"))
    second = _audio(tmp_path / "second.wav")

    from llmvoice.core.exceptions import AudioToolError

    monkeypatch.setattr(
        "llmvoice.voices.manager.probe_audio",
        lambda path: (_ for _ in ()).throw(AudioToolError("unreadable")),
    )
    with pytest.raises(AudioToolError, match="unreadable"):
        manager.add_reference("friday", second)
    assert not (manager.paths.voices_dir / "friday-2.wav").exists()


def test_add_reference_uses_first_available_number(tmp_path, audio_metadata) -> None:
    manager = VoiceManager(AppPaths(tmp_path / "data"))
    manager.add("friday", _audio(tmp_path / "first.wav"))
    (manager.paths.voices_dir / "friday-3.wav").write_bytes(b"existing")

    added = manager.add_reference("friday", _audio(tmp_path / "second.wav"))

    assert added.reference_paths[-1].name == "friday-2.wav"
