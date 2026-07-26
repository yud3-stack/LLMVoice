from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest

from llmvoice.audio.merge import merge_wav_files
from llmvoice.audio.metadata import probe_audio
from llmvoice.audio.reference import prepare_reference
from llmvoice.core.exceptions import AudioToolError, VoiceError
from llmvoice.core.paths import AppPaths
from llmvoice.voices.manager import VoiceManager

pytestmark = pytest.mark.integration

SAMPLE_RATE = 24_000


def _write_segments(path: Path, segments: list[tuple[str, float]]) -> None:
    samples: list[int] = []
    phase = 0
    for kind, seconds in segments:
        count = round(seconds * SAMPLE_RATE)
        for index in range(count):
            if kind == "silence":
                samples.append(0)
            else:
                value = int(12_000 * math.sin(2 * math.pi * 220 * phase / SAMPLE_RATE))
                samples.append(value)
                phase += 1
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def _read_samples(path: Path) -> list[int]:
    with wave.open(str(path), "rb") as source:
        frames = source.readframes(source.getnframes())
    return list(struct.unpack(f"<{len(frames) // 2}h", frames))


def test_endpoint_trim_preserves_middle_silence(tmp_path) -> None:
    source = tmp_path / "reference.wav"
    _write_segments(
        source,
        [
            ("silence", 0.5),
            ("tone", 1.0),
            ("silence", 0.5),
            ("tone", 1.0),
            ("silence", 0.5),
        ],
    )

    prepared = prepare_reference(source, tmp_path / "cache")
    metadata = probe_audio(prepared)
    samples = _read_samples(prepared)

    assert 2.35 <= metadata.duration_seconds <= 2.75
    active = [index for index, value in enumerate(samples) if abs(value) > 500]
    assert active[0] < SAMPLE_RATE * 0.2
    assert len(samples) - active[-1] < SAMPLE_RATE * 0.25
    longest_zero_run = 0
    current_run = 0
    for value in samples[active[0] : active[-1] + 1]:
        if abs(value) < 20:
            current_run += 1
            longest_zero_run = max(longest_zero_run, current_run)
        else:
            current_run = 0
    assert longest_zero_run >= SAMPLE_RATE * 0.4


def test_corrupt_reference_cache_is_rebuilt(tmp_path) -> None:
    source = tmp_path / "reference.wav"
    _write_segments(source, [("tone", 3.2)])
    prepared = prepare_reference(source, tmp_path / "cache")
    prepared.write_bytes(b"corrupt")
    rebuilt = prepare_reference(source, tmp_path / "cache")
    assert probe_audio(rebuilt).duration_seconds >= 3.1


def test_voice_validation_with_real_audio(tmp_path) -> None:
    paths = AppPaths(tmp_path / "data")
    manager = VoiceManager(paths)
    valid = tmp_path / "valid.wav"
    short = tmp_path / "short.wav"
    broken = tmp_path / "broken.wav"
    _write_segments(valid, [("tone", 3.2)])
    _write_segments(short, [("tone", 1.4)])
    broken.write_bytes(b"not audio")

    stored = manager.add("valid", valid)
    assert stored.metadata.duration_seconds >= 3.0
    with pytest.raises(VoiceError, match="too short"):
        manager.add("short", short)
    with pytest.raises(AudioToolError, match="readable audio stream"):
        manager.add("broken", broken)


def test_chunk_pause_is_inserted(tmp_path) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    output = tmp_path / "merged.wav"
    _write_segments(first, [("tone", 0.2)])
    _write_segments(second, [("tone", 0.2)])
    merge_wav_files([first, second], output, pause_ms=100)
    assert 0.47 <= probe_audio(output).duration_seconds <= 0.53
