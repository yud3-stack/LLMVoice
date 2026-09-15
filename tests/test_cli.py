import json

from typer.testing import CliRunner

from llmvoice.audio.metadata import AudioMetadata
from llmvoice.audio.quality import AudioQualityReport
from llmvoice.cli import app
from llmvoice.core.config import ConfigStore
from llmvoice.core.paths import AppPaths
from llmvoice.doctor import DiagnosticCheck
from llmvoice.tts.device import DeviceInfo

runner = CliRunner()


def test_start_reports_missing_input_without_traceback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    result = runner.invoke(app, ["start", str(tmp_path / "missing.txt")])
    assert result.exit_code == 1
    assert "Error: Input file not found" in result.output
    assert "Traceback" not in result.output


def test_voice_commands_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    reference = tmp_path / "voice.wav"
    reference.write_bytes(b"placeholder")
    metadata = AudioMetadata(12.5, 44100, 1, "pcm_s16le", "wav")
    monkeypatch.setattr("llmvoice.voices.manager.probe_audio", lambda path: metadata)

    added = runner.invoke(app, ["voice", "add", "friday", str(reference)])
    listed = runner.invoke(app, ["voice", "list"])
    info = runner.invoke(app, ["voice", "info", "friday"])
    removed = runner.invoke(app, ["voice", "remove", "friday", "--yes"])

    assert added.exit_code == 0
    assert "Voice added successfully" in added.output
    assert listed.exit_code == 0
    assert "friday" in listed.output
    assert "12.5 sec" in listed.output
    assert info.exit_code == 0
    assert "44100 Hz" in info.output
    assert removed.exit_code == 0
    assert "Voice 'friday' removed" in removed.output


def test_voice_add_accepts_optional_additional_references(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    metadata = AudioMetadata(10.0, 24000, 1, "pcm_s16le", "wav")
    monkeypatch.setattr("llmvoice.voices.manager.probe_audio", lambda path: metadata)
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    result = runner.invoke(
        app,
        ["voice", "add", "friday", str(first), "--reference", str(second)],
    )

    assert result.exit_code == 0
    assert (tmp_path / "data" / "voices" / "friday.wav").exists()
    assert (tmp_path / "data" / "voices" / "friday-2.wav").exists()
    listed = runner.invoke(app, ["voice", "list", "--json"])
    assert json.loads(listed.output)[0]["reference_count"] == 2


def test_voice_list_empty_state_has_quick_start(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    result = runner.invoke(app, ["voice", "list"])
    assert result.exit_code == 0
    assert "No voices have been added yet" in result.output
    assert "llmvoice voice add friday reference.wav" in result.output


def test_voice_list_json_is_machine_readable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    metadata = AudioMetadata(10.0, 24000, 1, "pcm_s16le", "wav")
    monkeypatch.setattr("llmvoice.voices.manager.probe_audio", lambda path: metadata)
    source = tmp_path / "voice.wav"
    source.write_bytes(b"placeholder")
    runner.invoke(app, ["voice", "add", "friday", str(source)])

    result = runner.invoke(app, ["voice", "list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload[0]["name"] == "friday"
    assert payload[0]["duration_seconds"] == 10.0


def test_voice_inspect_json_reports_quality(tmp_path, monkeypatch) -> None:
    source = tmp_path / "voice.wav"
    source.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "llmvoice.cli.inspect_audio",
        lambda path: AudioQualityReport(
            duration_seconds=10.0,
            sample_rate=24000,
            channels=1,
            mean_volume_db=-18.0,
            max_volume_db=-2.0,
            clipping_risk=False,
            quality="good",
            recommendations=[],
        ),
    )

    result = runner.invoke(app, ["voice", "inspect", str(source), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["quality"] == "good"


def test_voice_references_reports_each_reference(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    metadata = AudioMetadata(10.0, 24000, 1, "pcm_s16le", "wav")
    monkeypatch.setattr("llmvoice.voices.manager.probe_audio", lambda path: metadata)
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    runner.invoke(app, ["voice", "add", "friday", str(first), "--reference", str(second)])
    monkeypatch.setattr(
        "llmvoice.cli.inspect_audio",
        lambda path: AudioQualityReport(
            duration_seconds=10.0,
            sample_rate=24000,
            channels=1,
            mean_volume_db=-18.0,
            max_volume_db=-2.0,
            clipping_risk=False,
            quality="good",
            recommendations=[],
            silence_ratio=0.02,
            score=94,
        ),
    )

    result = runner.invoke(app, ["voice", "references", "friday", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert len(payload["references"]) == 2
    assert payload["references"][0]["score"] == 94


def test_voice_remove_confirmation_defaults_to_no(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    metadata = AudioMetadata(10.0, 24000, 1, "pcm_s16le", "wav")
    monkeypatch.setattr("llmvoice.voices.manager.probe_audio", lambda path: metadata)
    source = tmp_path / "voice.wav"
    source.write_bytes(b"placeholder")
    runner.invoke(app, ["voice", "add", "friday", str(source)])

    result = runner.invoke(app, ["voice", "remove", "friday"], input="\n")

    assert result.exit_code == 0
    assert "Voice was not removed" in result.output
    assert (tmp_path / "data" / "voices" / "friday.wav").exists()


def test_config_get_set_and_invalid_field(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    set_result = runner.invoke(app, ["config", "set", "device", "cpu"])
    get_result = runner.invoke(app, ["config", "get", "device"])
    invalid = runner.invoke(app, ["config", "set", "unknown", "value"])
    assert set_result.exit_code == 0
    assert get_result.output.strip() == "cpu"
    assert invalid.exit_code == 1
    assert "Unknown config field" in invalid.output


def test_config_json_outputs_are_parseable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))

    set_result = runner.invoke(app, ["config", "set", "device", "cpu", "--json"])
    get_result = runner.invoke(app, ["config", "get", "device", "--json"])
    show_result = runner.invoke(app, ["config", "show", "--json"])

    assert set_result.exit_code == 0
    assert json.loads(set_result.output) == {"field": "device", "value": "cpu"}
    assert json.loads(get_result.output) == {"field": "device", "value": "cpu"}
    assert json.loads(show_result.output)["device"] == "cpu"


def test_doctor_renders_mocked_checks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        "llmvoice.cli.run_diagnostics",
        lambda paths: [
            DiagnosticCheck("Python", "ok", "3.13.0"),
            DiagnosticCheck("CUDA", "warning", "Not available", "CPU is slower."),
        ],
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "LLMVoice Doctor" in result.output
    assert "CPU is slower" in result.output


def test_doctor_returns_nonzero_for_critical_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        "llmvoice.cli.run_diagnostics",
        lambda paths: [
            DiagnosticCheck("LLMVoice", "ok", "0.1.1"),
            DiagnosticCheck("FFmpeg", "error", "Not found"),
        ],
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "System needs attention" in result.output


def test_doctor_json_is_parseable_and_preserves_failure_exit_code(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        "llmvoice.cli.run_diagnostics",
        lambda paths: [DiagnosticCheck("FFmpeg", "error", "Not found")],
    )

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert payload["checks"] == [
        {"name": "FFmpeg", "status": "error", "detail": "Not found", "hint": None}
    ]


def test_model_status_json_reports_installation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))

    class Engine:
        display_name = "XTTS-v2"
        is_model_installed = False

    monkeypatch.setattr("llmvoice.cli.create_engine", lambda *args: Engine())

    result = runner.invoke(app, ["model", "status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["installed"] is False
    assert payload["engine"] == "XTTS-v2"
    assert payload["model"] == "tts_models/multilingual/multi-dataset/xtts_v2"


def test_model_download_json_loads_engine(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("llmvoice.cli.resolve_device", lambda requested: DeviceInfo("cpu", "CPU"))
    events: list[str] = []

    class Engine:
        display_name = "XTTS-v2"
        is_model_installed = True

        def load(self) -> None:
            events.append("load")

    monkeypatch.setattr("llmvoice.cli.create_engine", lambda *args: Engine())

    result = runner.invoke(app, ["model", "download", "--json"])

    assert result.exit_code == 0
    assert events == ["load"]
    assert json.loads(result.output)["ok"] is True


def test_dry_run_does_not_generate_audio(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("This is a short transcript.", encoding="utf-8")
    voice_dir = tmp_path / "data" / "voices"
    voice_dir.mkdir(parents=True)
    (voice_dir / "friday.wav").write_bytes(b"voice")
    ConfigStore(AppPaths(tmp_path / "data")).set("default_voice", "friday")
    monkeypatch.setattr("llmvoice.cli.resolve_device", lambda requested: DeviceInfo("cpu", "CPU"))

    monkeypatch.setattr(
        "llmvoice.cli.require_ffmpeg",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run used FFmpeg")),
    )
    monkeypatch.setattr(
        "llmvoice.cli.create_engine",
        lambda *args: (_ for _ in ()).throw(AssertionError("dry-run created engine")),
    )
    result = runner.invoke(
        app,
        ["start", str(transcript), "--language", "en", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "LLMVoice dry run" in result.output
    assert "English (en)" in result.output
    assert "friday (default)" in result.output
    assert "No audio was generated" in result.output
    assert not transcript.with_suffix(".mp3").exists()


def test_start_json_dry_run_is_single_machine_readable_result(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("This is a short transcript.", encoding="utf-8")
    voice_dir = tmp_path / "data" / "voices"
    voice_dir.mkdir(parents=True)
    (voice_dir / "friday.wav").write_bytes(b"voice")
    ConfigStore(AppPaths(tmp_path / "data")).set("default_voice", "friday")
    monkeypatch.setattr("llmvoice.cli.resolve_device", lambda requested: DeviceInfo("cpu", "CPU"))

    result = runner.invoke(
        app,
        ["start", str(transcript), "--language", "en", "--dry-run", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["voice"] == "friday"
    assert payload["language"] == "en"


def test_start_json_error_is_single_machine_readable_result(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))

    result = runner.invoke(app, ["start", str(tmp_path / "missing.txt"), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"] == "InputFileError"
    assert "Input file not found" in payload["message"]


def test_compare_generates_all_quality_profiles(tmp_path, monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_start(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("llmvoice.cli.start", fake_start)

    result = runner.invoke(
        app,
        [
            "compare",
            str(tmp_path / "transcript.txt"),
            "--voice",
            "friday",
            "--output-dir",
            str(tmp_path / "compare"),
        ],
    )

    assert result.exit_code == 0
    assert [call["quality"] for call in calls] == ["natural", "balanced", "stable"]
    assert all(call["force"] is True for call in calls)


def test_force_controls_overwrite(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("This is a short transcript.", encoding="utf-8")
    output = transcript.with_suffix(".mp3")
    output.write_bytes(b"old")
    voice_dir = tmp_path / "data" / "voices"
    voice_dir.mkdir(parents=True)
    (voice_dir / "friday.wav").write_bytes(b"voice")
    metadata = AudioMetadata(4.0, 24000, 1, "mp3", "mp3")
    monkeypatch.setattr("llmvoice.cli.resolve_device", lambda requested: DeviceInfo("cpu", "CPU"))
    monkeypatch.setattr("llmvoice.cli.require_ffmpeg", lambda: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr("llmvoice.cli.check_synthesis_disk_space", lambda *args: (1, 1))
    monkeypatch.setattr("llmvoice.cli.probe_audio", lambda path: metadata)

    class Engine:
        display_name = "XTTS-v2"
        is_model_installed = True

    monkeypatch.setattr("llmvoice.cli.create_engine", lambda *args: Engine())

    def fake_run(self, request, plan, progress, stage, resume=False):
        request.output_path.write_bytes(b"new")

    monkeypatch.setattr("llmvoice.cli.VoiceService.run", fake_run)
    rejected = runner.invoke(app, ["start", str(transcript), "--voice", "friday"])
    accepted = runner.invoke(
        app,
        ["start", str(transcript), "--voice", "friday", "--force"],
    )
    assert rejected.exit_code == 1
    assert "Use --force" in rejected.output
    assert accepted.exit_code == 0
    assert output.read_bytes() == b"new"


def test_ffmpeg_bootstrap_precedes_engine_creation(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("This is a short transcript.", encoding="utf-8")
    voice_dir = tmp_path / "data" / "voices"
    voice_dir.mkdir(parents=True)
    (voice_dir / "friday.wav").write_bytes(b"voice")
    events: list[str] = []
    metadata = AudioMetadata(4.0, 24000, 1, "mp3", "mp3")

    monkeypatch.setattr(
        "llmvoice.cli.resolve_device",
        lambda requested: DeviceInfo("cpu", "CPU"),
    )
    monkeypatch.setattr(
        "llmvoice.cli.require_ffmpeg",
        lambda: events.append("ffmpeg") or ("ffmpeg", "ffprobe"),
    )
    monkeypatch.setattr(
        "llmvoice.cli.check_synthesis_disk_space",
        lambda *args: (1, 1),
    )
    monkeypatch.setattr("llmvoice.cli.probe_audio", lambda path: metadata)

    class Engine:
        display_name = "XTTS-v2"
        is_model_installed = True

    monkeypatch.setattr(
        "llmvoice.cli.create_engine",
        lambda *args: events.append("engine") or Engine(),
    )

    def fake_run(self, request, plan, progress, stage, resume=False):
        events.append("service")
        request.output_path.write_bytes(b"audio")

    monkeypatch.setattr("llmvoice.cli.VoiceService.run", fake_run)
    result = runner.invoke(
        app,
        ["start", str(transcript), "--voice", "friday"],
    )

    assert result.exit_code == 0
    assert events == ["ffmpeg", "engine", "service"]


def test_ctrl_c_uses_exit_130_without_traceback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        "llmvoice.cli.read_and_plan",
        lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    result = runner.invoke(app, ["start", str(tmp_path / "input.txt")])
    assert result.exit_code == 130
    assert "Generation cancelled" in result.output
    assert "Traceback" not in result.output


def test_debug_mode_prints_traceback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        "llmvoice.cli.read_and_plan",
        lambda *args: (_ for _ in ()).throw(RuntimeError("debug boom")),
    )
    result = runner.invoke(app, ["start", str(tmp_path / "input.txt"), "--debug"])
    assert result.exit_code == 1
    assert "Traceback" in result.output
    assert "debug boom" in result.output
