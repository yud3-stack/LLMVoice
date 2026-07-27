from __future__ import annotations

import io
import json
import tarfile
import zipfile
from importlib.metadata import version
from pathlib import Path

import pytest

from scripts.release import (
    ReleaseError,
    build_manifest,
    find_release_artifacts,
    load_project_config,
    prepare_release,
    sha256_file,
    validate_release_assets,
    validate_tag,
    validate_wheel,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _project(root: Path, release_version: str = "1.2.3") -> None:
    (root / "pyproject.toml").write_text(
        f"""
[project]
name = "LLMVoice"
version = "{release_version}"
requires-python = ">=3.11,<3.15"

[tool.llmvoice.release]
schema-version = 1
repository = "yud3-stack/LLMVoice"

[tool.llmvoice.release.runtime-profiles.cuda]
index-url = "https://download.pytorch.org/whl/cu130"
packages = ["torch==2.11.0+cu130", "torchaudio==2.11.0+cu130", "torchcodec==0.13.0+cu130"]

[tool.llmvoice.release.runtime-profiles.cpu]
index-url = "https://download.pytorch.org/whl/cpu"
packages = ["torch==2.11.0", "torchaudio==2.11.0", "torchcodec==0.13.0"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "constraints.txt").write_text(
        "coqui-tts==0.27.5\ntransformers==4.57.6\n",
        encoding="utf-8",
    )


def _wheel(path: Path, release_version: str, extra_name: str | None = None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("llmvoice/__init__.py", "")
        archive.writestr("llmvoice/voices/__init__.py", "")
        archive.writestr("llmvoice/voices/manager.py", "")
        archive.writestr(
            f"llmvoice-{release_version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: LLMVoice\nVersion: {release_version}\n",
        )
        archive.writestr(
            f"llmvoice-{release_version}.dist-info/licenses/LICENSE",
            "MIT License",
        )
        if extra_name:
            archive.writestr(extra_name, b"unsafe")


def _sdist(path: Path, release_version: str) -> None:
    root = f"llmvoice-{release_version}"
    with tarfile.open(path, "w:gz") as archive:
        for name, content in {
            f"{root}/README.md": b"# LLMVoice\n",
            f"{root}/LICENSE": b"MIT License\n",
            f"{root}/THIRD_PARTY_LICENSES.md": b"XTTS CPML\n",
            f"{root}/pyproject.toml": b"[project]\n",
            f"{root}/llmvoice/__init__.py": b"",
            f"{root}/llmvoice/voices/__init__.py": b"",
            f"{root}/llmvoice/voices/manager.py": b"",
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def _artifacts(root: Path, release_version: str = "1.2.3") -> tuple[Path, Path]:
    dist = root / "dist"
    dist.mkdir()
    wheel = dist / f"llmvoice-{release_version}-py3-none-any.whl"
    sdist = dist / f"llmvoice-{release_version}.tar.gz"
    _wheel(wheel, release_version)
    _sdist(sdist, release_version)
    return wheel, sdist


def test_real_package_cli_and_manifest_versions_share_metadata(tmp_path) -> None:
    config = load_project_config(PROJECT_ROOT)
    wheel = tmp_path / f"llmvoice-{config.version}-py3-none-any.whl"
    sdist = tmp_path / f"llmvoice-{config.version}.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    manifest = build_manifest(config, wheel, sdist)

    assert config.version == version("llmvoice")
    assert config.tag == f"v{config.version}"
    assert manifest["version"] == version("llmvoice")
    assert manifest["tag"] == config.tag
    assert config.python_minimum == "3.11"
    assert config.python_maximum_exclusive == "3.15"


def test_tag_validation_accepts_exact_match_and_rejects_mismatch() -> None:
    validate_tag("v1.2.3", "1.2.3")
    with pytest.raises(ReleaseError, match="mismatch"):
        validate_tag("v1.2.4", "1.2.3")
    with pytest.raises(ReleaseError, match="Invalid release tag"):
        validate_tag("release-1.2.3", "1.2.3")


def test_wheel_detection_checksum_and_manifest_schema(tmp_path) -> None:
    _project(tmp_path)
    wheel, sdist = _artifacts(tmp_path)
    config = load_project_config(tmp_path)
    found = find_release_artifacts(tmp_path / "dist", config)
    manifest = build_manifest(config, found.wheel, found.sdist)

    assert found.wheel == wheel
    assert found.sdist == sdist
    assert manifest["schemaVersion"] == 1
    assert manifest["version"] == "1.2.3"
    assert manifest["tag"] == "v1.2.3"
    assert manifest["wheel"]["sha256"] == sha256_file(wheel)
    assert manifest["python"]["minimum"] == "3.11"
    assert manifest["python"]["maximumExclusive"] == "3.15"
    assert set(manifest["runtimeProfiles"]) == {"cuda", "cpu"}
    assert manifest["application"]["dependencies"] == [
        "coqui-tts==0.27.5",
        "transformers==4.57.6",
    ]


def test_forbidden_audio_or_model_artifact_is_rejected(tmp_path) -> None:
    _project(tmp_path)
    config = load_project_config(tmp_path)
    wheel = tmp_path / "llmvoice-1.2.3-py3-none-any.whl"
    _wheel(wheel, "1.2.3", "voices/reference.wav")

    with pytest.raises(ReleaseError, match="Forbidden"):
        validate_wheel(wheel, config)


def test_missing_release_artifact_is_rejected(tmp_path) -> None:
    _project(tmp_path)
    (tmp_path / "dist").mkdir()
    config = load_project_config(tmp_path)
    with pytest.raises(ReleaseError, match="exactly one wheel"):
        find_release_artifacts(tmp_path / "dist", config)


def test_prepare_and_validate_complete_release_asset_set(tmp_path) -> None:
    _project(tmp_path)
    wheel, _ = _artifacts(tmp_path)
    installer = tmp_path / "install.ps1"
    installer.write_text("Write-Host 'installer'\n", encoding="utf-8")
    output = tmp_path / "release-assets"

    manifest = prepare_release(
        tmp_path,
        "v1.2.3",
        tmp_path / "dist",
        installer,
        output,
    )
    assert {path.name for path in output.iterdir()} == {
        "llmvoice-1.2.3-py3-none-any.whl",
        "llmvoice-1.2.3.tar.gz",
        "install.ps1",
        "install-manifest.json",
        "SHA256SUMS.txt",
    }
    on_disk = json.loads((output / "install-manifest.json").read_text(encoding="utf-8"))
    assert on_disk == manifest
    assert manifest["wheel"]["sha256"] == sha256_file(wheel)
    validate_release_assets(tmp_path, "v1.2.3", output)

    with (output / "llmvoice-1.2.3-py3-none-any.whl").open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(ReleaseError, match="checksum"):
        validate_release_assets(tmp_path, "v1.2.3", output)


def test_installer_and_release_workflow_security_invariants() -> None:
    installer = (PROJECT_ROOT / "installer" / "install.ps1").read_text(encoding="utf-8")
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")

    assert "Invoke-Expression" not in installer
    assert '"Machine"' not in installer
    assert "Get-FileHash" in installer
    assert "releases/latest/download/install-manifest.json" in installer
    assert "& llmvoice" not in installer
    assert 'Invoke-Native -FilePath $llmvoiceExe -Arguments @("doctor")' in installer
    assert 'tags:' in workflow
    assert '"v*"' in workflow
    assert "contents: write" in workflow
    assert "validate-tag" in workflow
    assert "python -m pytest" in workflow
    assert "python -m pytest -m integration" in workflow
    assert "gh release create" in workflow
