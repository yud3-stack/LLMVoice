from typer.testing import CliRunner

from llmvoice.cli import app

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

    added = runner.invoke(app, ["voice", "add", "friday", str(reference)])
    listed = runner.invoke(app, ["voice", "list"])
    removed = runner.invoke(app, ["voice", "remove", "friday"])

    assert added.exit_code == 0
    assert "Voice 'friday' added" in added.output
    assert listed.exit_code == 0
    assert "friday" in listed.output
    assert removed.exit_code == 0
    assert "Voice 'friday' removed" in removed.output
