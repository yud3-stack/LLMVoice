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
schema-version = 2
repository = "yud3-stack/LLMVoice"

[[tool.llmvoice.release.runtime-profiles.cuda.groups]]
name = "compute"
index-url = "https://download.pytorch.org/whl/cu130"
packages = ["torch==2.11.0+cu130", "torchaudio==2.11.0+cu130"]
no-dependencies = false

[[tool.llmvoice.release.runtime-profiles.cuda.groups]]
name = "codec"
index-url = "https://download.pytorch.org/whl/cpu"
packages = ["torchcodec==0.13.0+cpu"]
no-dependencies = true

[[tool.llmvoice.release.runtime-profiles.cpu.groups]]
name = "runtime"
index-url = "https://download.pytorch.org/whl/cpu"
packages = ["torch==2.11.0+cpu", "torchaudio==2.11.0+cpu", "torchcodec==0.13.0+cpu"]
no-dependencies = false
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
    assert manifest["schemaVersion"] == 2
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


def test_runtime_profile_indexes_are_explicit_and_deterministic(tmp_path) -> None:
    _project(tmp_path)
    wheel, sdist = _artifacts(tmp_path)
    config = load_project_config(tmp_path)
    manifest = build_manifest(config, wheel, sdist)
    second_manifest = build_manifest(config, wheel, sdist)

    assert manifest == second_manifest
    cuda_groups = {
        group["name"]: group
        for group in manifest["runtimeProfiles"]["cuda"]["groups"]
    }
    assert cuda_groups["compute"] == {
        "name": "compute",
        "indexUrl": "https://download.pytorch.org/whl/cu130",
        "packages": [
            "torch==2.11.0+cu130",
            "torchaudio==2.11.0+cu130",
        ],
        "noDependencies": False,
    }
    assert cuda_groups["codec"] == {
        "name": "codec",
        "indexUrl": "https://download.pytorch.org/whl/cpu",
        "packages": ["torchcodec==0.13.0+cpu"],
        "noDependencies": True,
    }
    cpu_groups = manifest["runtimeProfiles"]["cpu"]["groups"]
    assert cpu_groups == [
        {
            "name": "runtime",
            "indexUrl": "https://download.pytorch.org/whl/cpu",
            "packages": [
                "torch==2.11.0+cpu",
                "torchaudio==2.11.0+cpu",
                "torchcodec==0.13.0+cpu",
            ],
            "noDependencies": False,
        }
    ]


def test_unsafe_or_misassigned_runtime_indexes_are_rejected(tmp_path) -> None:
    _project(tmp_path)
    metadata = tmp_path / "pyproject.toml"
    original = metadata.read_text(encoding="utf-8")

    metadata.write_text(
        original.replace(
            "https://download.pytorch.org/whl/cu130",
            "https://packages.example.invalid/cu130",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseError, match="Unsafe PyTorch index"):
        load_project_config(tmp_path)

    metadata.write_text(
        original.replace(
            'name = "codec"\nindex-url = "https://download.pytorch.org/whl/cpu"',
            'name = "codec"\nindex-url = "https://download.pytorch.org/whl/cu130"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseError, match="TorchCodec"):
        load_project_config(tmp_path)


def test_forbidden_audio_or_model_artifact_is_rejected(tmp_path) -> None:
    _project(tmp_path)
    config = load_project_config(tmp_path)
    wheel = tmp_path / "llmvoice-1.2.3-py3-none-any.whl"
    _wheel(wheel, "1.2.3", "voices/reference.wav")

    with pytest.raises(ReleaseError, match="Forbidden"):
        validate_wheel(wheel, config)


def test_wheel_package_identity_must_match_project(tmp_path) -> None:
    _project(tmp_path)
    config = load_project_config(tmp_path)
    wheel = tmp_path / "llmvoice-1.2.3-py3-none-any.whl"
    _wheel(wheel, "1.2.3")
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("llmvoice/__init__.py", "")
        archive.writestr("llmvoice/voices/manager.py", "")
        archive.writestr(
            "llmvoice-1.2.3.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: OtherPackage\nVersion: 1.2.3\n",
        )
        archive.writestr("llmvoice-1.2.3.dist-info/licenses/LICENSE", "MIT License")
    with pytest.raises(ReleaseError, match="package name"):
        validate_wheel(wheel, config)


def test_unsafe_archive_paths_are_rejected(tmp_path) -> None:
    _project(tmp_path)
    config = load_project_config(tmp_path)
    wheel = tmp_path / "llmvoice-1.2.3-py3-none-any.whl"
    _wheel(wheel, "1.2.3", "../outside.txt")

    with pytest.raises(ReleaseError, match="Unsafe path"):
        validate_wheel(wheel, config)


def test_duplicate_archive_paths_are_rejected(tmp_path) -> None:
    _project(tmp_path)
    config = load_project_config(tmp_path)
    wheel = tmp_path / "llmvoice-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("llmvoice/__init__.py", "")
        archive.writestr("LLMVOICE/__init__.py", "duplicate")

    with pytest.raises(ReleaseError, match="Duplicate path"):
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
    assert "Runtime package version mismatch for $packageName" in installer
    assert "import torchcodec" in installer
    assert "AudioDecoder" in installer
    bootstrap_position = installer.index("ffmpeg_bootstrap.require_ffmpeg()")
    torchcodec_import_position = installer.index(
        "    import torchcodec",
        bootstrap_position,
    )
    assert bootstrap_position < torchcodec_import_position
    assert "dllDirectoryRegistered" in installer
    assert "LLMVOICE_RUNTIME_DIAGNOSTICS=" in installer
    assert 'if ($ProfileName -eq "cuda" -and -not [bool]$Probe.cuda)' in installer
    assert "CUDA-enabled PyTorch was installed" in installer
    assert "silent fallback" not in installer.lower()
    assert 'tags:' in workflow
    assert '"v*"' in workflow
    assert "contents: write" in workflow
    assert "validate-tag" in workflow
    assert "python -m pytest" in workflow
    assert "python -m pytest -m integration" in workflow
    assert "gh release create" in workflow
