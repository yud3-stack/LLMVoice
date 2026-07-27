from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


TAG_PATTERN = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.-]+)?$")
PINNED_REQUIREMENT = re.compile(r"^[A-Za-z0-9_.+-]+==[A-Za-z0-9_.+-]+$")
FORBIDDEN_SUFFIXES = {
    ".aac",
    ".bin",
    ".ckpt",
    ".env",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".p12",
    ".pem",
    ".pfx",
    ".pt",
    ".pth",
    ".key",
    ".safetensors",
    ".wav",
}
FORBIDDEN_PARTS = {"cache", "runtime", "venv"}
FORBIDDEN_FILENAMES = {
    ".env",
    "config.json",
    "credentials.json",
    "secrets.json",
}


class ReleaseError(ValueError):
    """Raised when release metadata or artifacts are unsafe or inconsistent."""


@dataclass(frozen=True)
class ProjectReleaseConfig:
    name: str
    version: str
    requires_python: str
    python_minimum: str
    python_maximum_exclusive: str
    schema_version: int
    repository: str
    runtime_profiles: dict[str, dict[str, Any]]
    application_dependencies: list[str]

    @property
    def tag(self) -> str:
        return f"v{self.version}"

    @property
    def normalized_name(self) -> str:
        return re.sub(r"[-_.]+", "-", self.name).lower()


@dataclass(frozen=True)
class ReleaseArtifacts:
    wheel: Path
    sdist: Path


def _python_bounds(requires_python: str) -> tuple[str, str]:
    minimum: str | None = None
    maximum: str | None = None
    for item in (part.strip() for part in requires_python.split(",")):
        if item.startswith(">="):
            minimum = item[2:].strip()
        elif item.startswith("<"):
            maximum = item[1:].strip()
    if not minimum or not maximum:
        raise ReleaseError(
            "project.requires-python must contain >=minimum and <maximum bounds."
        )
    if not re.fullmatch(r"[0-9]+\.[0-9]+", minimum) or not re.fullmatch(
        r"[0-9]+\.[0-9]+", maximum
    ):
        raise ReleaseError("Python compatibility bounds must use major.minor values.")
    return minimum, maximum


def _read_constraints(path: Path) -> list[str]:
    dependencies: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not PINNED_REQUIREMENT.fullmatch(line):
            raise ReleaseError(f"Installer constraint is not exactly pinned: {line}")
        dependencies.append(line)
    if not dependencies:
        raise ReleaseError("constraints.txt contains no installer dependencies.")
    return dependencies


def load_project_config(project_root: Path) -> ProjectReleaseConfig:
    """Load all release inputs from project metadata and constraints."""
    root = project_root.resolve()
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = payload["project"]
    release = payload["tool"]["llmvoice"]["release"]
    minimum, maximum = _python_bounds(project["requires-python"])
    profiles = release["runtime-profiles"]
    schema_version = int(release["schema-version"])
    repository = str(release["repository"])
    if schema_version != 1:
        raise ReleaseError("Only installer manifest schemaVersion 1 is supported.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ReleaseError("Release repository must be a safe owner/name GitHub slug.")
    if set(profiles) != {"cuda", "cpu"}:
        raise ReleaseError("Runtime profiles must contain exactly cuda and cpu.")
    for profile_name in ("cuda", "cpu"):
        if profile_name not in profiles:
            raise ReleaseError(f"Missing runtime profile: {profile_name}")
        profile = profiles[profile_name]
        index_url = str(profile.get("index-url", ""))
        if not index_url.startswith("https://download.pytorch.org/whl/"):
            raise ReleaseError(f"Unsafe PyTorch index URL for profile {profile_name}.")
        packages = list(profile.get("packages", []))
        if not packages or any(not PINNED_REQUIREMENT.fullmatch(item) for item in packages):
            raise ReleaseError(f"Runtime profile {profile_name} must use exact pins.")
    return ProjectReleaseConfig(
        name=str(project["name"]),
        version=str(project["version"]),
        requires_python=str(project["requires-python"]),
        python_minimum=minimum,
        python_maximum_exclusive=maximum,
        schema_version=schema_version,
        repository=repository,
        runtime_profiles={
            name: {
                "indexUrl": str(profile["index-url"]),
                "packages": list(profile["packages"]),
            }
            for name, profile in profiles.items()
        },
        application_dependencies=_read_constraints(root / "constraints.txt"),
    )


def validate_tag(tag: str, package_version: str) -> None:
    """Require a safe v-prefixed tag that exactly matches package metadata."""
    if not TAG_PATTERN.fullmatch(tag):
        raise ReleaseError(
            f"Invalid release tag '{tag}'. Expected a tag such as v{package_version}."
        )
    expected = f"v{package_version}"
    if tag != expected:
        raise ReleaseError(
            "Release tag/package version mismatch.\n"
            f"Tag             : {tag}\n"
            f"Package metadata: {package_version}\n"
            f"Expected tag    : {expected}"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_release_artifacts(
    dist_dir: Path,
    config: ProjectReleaseConfig,
) -> ReleaseArtifacts:
    wheel_candidates = sorted(
        dist_dir.glob(f"{config.normalized_name}-{config.version}-*.whl")
    )
    sdist_candidates = sorted(
        path
        for path in dist_dir.glob(f"{config.normalized_name}-{config.version}.*")
        if path.name.endswith(".tar.gz")
    )
    if len(wheel_candidates) != 1:
        raise ReleaseError(
            f"Expected exactly one wheel for {config.version}; found {len(wheel_candidates)}."
        )
    if len(sdist_candidates) != 1:
        raise ReleaseError(
            f"Expected exactly one sdist for {config.version}; found {len(sdist_candidates)}."
        )
    return ReleaseArtifacts(wheel_candidates[0], sdist_candidates[0])


def _validate_member_names(names: Sequence[str]) -> None:
    for raw_name in names:
        path = PurePosixPath(raw_name.replace("\\", "/"))
        lowered_parts = {part.casefold() for part in path.parts}
        filename = path.name.casefold()
        if lowered_parts & FORBIDDEN_PARTS:
            raise ReleaseError(f"Forbidden user/runtime directory in artifact: {raw_name}")
        if filename in FORBIDDEN_FILENAMES or path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            raise ReleaseError(f"Forbidden file in release artifact: {raw_name}")


def validate_wheel(path: Path, config: ProjectReleaseConfig) -> None:
    """Inspect wheel metadata and reject user data, models, audio, or secrets."""
    if not path.is_file():
        raise ReleaseError(f"Wheel does not exist: {path}")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        _validate_member_names(names)
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ReleaseError("Wheel must contain exactly one METADATA file.")
        metadata = Parser().parsestr(
            archive.read(metadata_names[0]).decode("utf-8", errors="strict")
        )
        if metadata.get("Version") != config.version:
            raise ReleaseError(
                f"Wheel version {metadata.get('Version')} does not match {config.version}."
            )
        if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
            raise ReleaseError("Wheel does not contain the MIT LICENSE.")
        if not any(name.startswith("llmvoice/") for name in names):
            raise ReleaseError("Wheel does not contain the llmvoice package.")
        if "llmvoice/voices/manager.py" not in names:
            raise ReleaseError("Wheel does not contain the voice-management package.")


def validate_sdist(path: Path, config: ProjectReleaseConfig) -> None:
    """Inspect the source distribution for required and forbidden content."""
    if not path.is_file():
        raise ReleaseError(f"Source distribution does not exist: {path}")
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
    _validate_member_names(names)
    required = ("README.md", "LICENSE", "THIRD_PARTY_LICENSES.md", "pyproject.toml")
    for filename in required:
        if not any(name.endswith(f"/{filename}") for name in names):
            raise ReleaseError(f"Source distribution is missing {filename}.")
    expected_root = f"{config.normalized_name}-{config.version}/"
    if not any(name.startswith(expected_root) for name in names):
        raise ReleaseError("Source distribution root does not match package version.")
    if f"{expected_root}llmvoice/voices/manager.py" not in names:
        raise ReleaseError("Source distribution is missing voice-management sources.")


def build_manifest(
    config: ProjectReleaseConfig,
    wheel: Path,
    sdist: Path,
) -> dict[str, Any]:
    """Create the versioned installer manifest without writing it."""
    return {
        "schemaVersion": config.schema_version,
        "version": config.version,
        "tag": config.tag,
        "repository": config.repository,
        "wheel": {
            "file": wheel.name,
            "sha256": sha256_file(wheel),
            "size": wheel.stat().st_size,
        },
        "sdist": {
            "file": sdist.name,
            "sha256": sha256_file(sdist),
            "size": sdist.stat().st_size,
        },
        "python": {
            "requires": config.requires_python,
            "minimum": config.python_minimum,
            "maximumExclusive": config.python_maximum_exclusive,
            "architecture": "x64",
        },
        "application": {
            "extras": ["tts"],
            "dependencies": config.application_dependencies,
        },
        "runtimeProfiles": config.runtime_profiles,
    }


def _copy_file(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return destination


def prepare_release(
    project_root: Path,
    tag: str,
    dist_dir: Path,
    installer: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Validate build output and assemble all GitHub Release assets."""
    config = load_project_config(project_root)
    validate_tag(tag, config.version)
    artifacts = find_release_artifacts(dist_dir, config)
    validate_wheel(artifacts.wheel, config)
    validate_sdist(artifacts.sdist, config)

    output_dir.mkdir(parents=True, exist_ok=True)
    wheel = _copy_file(artifacts.wheel, output_dir / artifacts.wheel.name)
    sdist = _copy_file(artifacts.sdist, output_dir / artifacts.sdist.name)
    installer_asset = _copy_file(installer, output_dir / "install.ps1")
    manifest = build_manifest(config, wheel, sdist)
    manifest_path = output_dir / "install-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    checksummed = (wheel, sdist, installer_asset, manifest_path)
    sums_path = output_dir / "SHA256SUMS.txt"
    sums_path.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksummed),
        encoding="ascii",
    )
    validate_release_assets(project_root, tag, output_dir)
    return manifest


def validate_release_assets(project_root: Path, tag: str, assets_dir: Path) -> None:
    """Validate the complete five-file GitHub Release asset set."""
    config = load_project_config(project_root)
    validate_tag(tag, config.version)
    expected_names = {
        f"{config.normalized_name}-{config.version}-py3-none-any.whl",
        f"{config.normalized_name}-{config.version}.tar.gz",
        "install.ps1",
        "install-manifest.json",
        "SHA256SUMS.txt",
    }
    actual_names = {path.name for path in assets_dir.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise ReleaseError(
            "Release asset set is incomplete or contains unexpected files.\n"
            f"Expected: {sorted(expected_names)}\n"
            f"Actual  : {sorted(actual_names)}"
        )

    artifacts = find_release_artifacts(assets_dir, config)
    validate_wheel(artifacts.wheel, config)
    validate_sdist(artifacts.sdist, config)
    manifest_path = assets_dir / "install-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_manifest = build_manifest(config, artifacts.wheel, artifacts.sdist)
    if manifest.get("wheel", {}).get("sha256") != expected_manifest["wheel"]["sha256"]:
        raise ReleaseError("Manifest wheel checksum is incorrect.")
    if manifest.get("sdist", {}).get("sha256") != expected_manifest["sdist"]["sha256"]:
        raise ReleaseError("Manifest source distribution checksum is incorrect.")
    if manifest != expected_manifest:
        raise ReleaseError(
            "Manifest content does not exactly match package metadata and artifacts."
        )

    expected_sums: dict[str, str] = {}
    for line in (assets_dir / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        checksum, separator, filename = line.partition("  ")
        if not separator or filename in expected_sums:
            raise ReleaseError("SHA256SUMS.txt is malformed.")
        expected_sums[filename] = checksum
    checksummed_names = expected_names - {"SHA256SUMS.txt"}
    if set(expected_sums) != checksummed_names:
        raise ReleaseError("SHA256SUMS.txt does not cover the expected release assets.")
    for filename, expected in expected_sums.items():
        actual = sha256_file(assets_dir / filename)
        if actual != expected:
            raise ReleaseError(f"Checksum mismatch for release asset: {filename}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and validate LLMVoice releases.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version")
    tag_parser = subparsers.add_parser("validate-tag")
    tag_parser.add_argument("--tag", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--tag", required=True)
    prepare.add_argument("--dist-dir", type=Path, required=True)
    prepare.add_argument("--installer", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--tag", required=True)
    validate.add_argument("--assets-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_project_config(args.project_root)
        if args.command == "version":
            print(config.version)
        elif args.command == "validate-tag":
            validate_tag(args.tag, config.version)
            print(f"Release tag {args.tag} matches package version {config.version}.")
        elif args.command == "prepare":
            prepare_release(
                args.project_root,
                args.tag,
                args.dist_dir,
                args.installer,
                args.output_dir,
            )
            print(f"Release assets prepared in {args.output_dir.resolve()}.")
        elif args.command == "validate":
            validate_release_assets(args.project_root, args.tag, args.assets_dir)
            print(f"Release assets in {args.assets_dir.resolve()} are valid.")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
