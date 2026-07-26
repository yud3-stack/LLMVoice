from importlib.metadata import PackageNotFoundError

from llmvoice.core.exceptions import AudioToolError
from llmvoice.core.paths import AppPaths
from llmvoice.doctor import run_diagnostics


def test_doctor_detects_missing_dependencies_without_model_load(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "llmvoice.doctor.require_ffmpeg",
        lambda: (_ for _ in ()).throw(AudioToolError("missing")),
    )
    monkeypatch.setattr("llmvoice.doctor.importlib.util.find_spec", lambda name: None)
    monkeypatch.setattr(
        "llmvoice.doctor.version",
        lambda name: (_ for _ in ()).throw(PackageNotFoundError(name)),
    )
    checks = run_diagnostics(AppPaths(tmp_path / "data"))
    by_name = {check.name: check for check in checks}
    assert by_name["LLMVoice"].detail == "0.1.1"
    assert by_name["FFmpeg"].status == "error"
    assert by_name["CUDA"].status == "warning"
    assert by_name["XTTS"].status == "error"
    assert by_name["Voices"].detail == "0 stored"
