from pathlib import Path

from llmvoice.audio.recording import list_audio_devices, record_audio


def test_lists_audio_devices_from_ffmpeg_output(monkeypatch) -> None:
    class Result:
        stderr = '[dshow @ 1] "USB Microphone" (audio)\n[dshow @ 1] "Webcam" (video)\n'
        returncode = 1

    monkeypatch.setattr("llmvoice.audio.recording.require_ffmpeg", lambda: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr("llmvoice.audio.recording.subprocess.run", lambda *args, **kwargs: Result())

    assert list_audio_devices() == ["USB Microphone"]


def test_record_audio_replaces_destination_atomically(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "recording.wav"
    calls: list[list[str]] = []

    monkeypatch.setattr("llmvoice.audio.recording.require_ffmpeg", lambda: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr(
        "llmvoice.audio.recording.list_audio_devices",
        lambda: ["USB Microphone"],
    )

    class Result:
        returncode = 0
        stderr = ""

    def fake_run(arguments, **kwargs):
        calls.append(arguments)
        Path(arguments[-1]).write_bytes(b"wav")
        return Result()

    monkeypatch.setattr("llmvoice.audio.recording.subprocess.run", fake_run)

    record_audio(destination, 5, "USB Microphone")

    assert destination.read_bytes() == b"wav"
    assert "dshow" in calls[0]
    assert "audio=USB Microphone" in calls[0]
    assert not list(tmp_path.glob(".*.llmvoice-*.wav"))
