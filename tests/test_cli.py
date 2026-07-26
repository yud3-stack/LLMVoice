from typer.testing import CliRunner

from llmvoice.audio.metadata import AudioMetadata
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


def test_voice_list_empty_state_has_quick_start(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    result = runner.invoke(app, ["voice", "list"])
    assert result.exit_code == 0
    assert "No voices have been added yet" in result.output
    assert "llmvoice voice add friday reference.wav" in result.output


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


def test_dry_run_does_not_generate_audio(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLMVOICE_DATA_DIR", str(tmp_path / "data"))
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("This is a short transcript.", encoding="utf-8")
    voice_dir = tmp_path / "data" / "voices"
    voice_dir.mkdir(parents=True)
    (voice_dir / "friday.wav").write_bytes(b"voice")
    ConfigStore(AppPaths(tmp_path / "data")).set("default_voice", "friday")
    monkeypatch.setattr("llmvoice.cli.resolve_device", lambda requested: DeviceInfo("cpu", "CPU"))

    class Engine:
        display_name = "XTTS-v2"

    monkeypatch.setattr("llmvoice.cli.create_engine", lambda *args: Engine())
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
    monkeypatch.setattr("llmvoice.cli.check_disk_space", lambda *args: (1, 1))
    monkeypatch.setattr("llmvoice.cli.probe_audio", lambda path: metadata)

    class Engine:
        display_name = "XTTS-v2"
        is_model_installed = True

    monkeypatch.setattr("llmvoice.cli.create_engine", lambda *args: Engine())

    def fake_run(self, request, plan, progress, stage):
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
