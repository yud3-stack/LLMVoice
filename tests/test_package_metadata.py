from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_and_build_exclusions() -> None:
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    assert project["version"] == "0.1.1"
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]

    wheel = metadata["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["packages"] == ["llmvoice"]
    assert (PROJECT_ROOT / "README.md").is_file()
    assert (PROJECT_ROOT / "LICENSE").is_file()
    assert (PROJECT_ROOT / "THIRD_PARTY_LICENSES.md").is_file()


def test_tts_constraints_do_not_override_pytorch() -> None:
    constraints = (PROJECT_ROOT / "constraints.txt").read_text(encoding="utf-8").casefold()
    constrained_packages = {
        line.split("==", maxsplit=1)[0].strip()
        for line in constraints.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert constrained_packages.isdisjoint({"torch", "torchaudio", "torchcodec"})


def test_samples_contain_no_audio_or_model_artifacts() -> None:
    forbidden_suffixes = {".wav", ".mp3", ".flac", ".m4a", ".ckpt", ".pth", ".safetensors"}
    artifacts = [
        path
        for path in (PROJECT_ROOT / "samples").rglob("*")
        if path.is_file() and path.suffix.casefold() in forbidden_suffixes
    ]
    assert artifacts == []
