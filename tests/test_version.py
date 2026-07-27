from importlib.metadata import version

from typer.testing import CliRunner

import llmvoice
from llmvoice.cli import app
from pathlib import Path
import tomllib


def test_package_and_cli_versions_match() -> None:
    package_version = version("llmvoice")
    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    result = CliRunner().invoke(app, ["--version"])

    assert package_version == project["project"]["version"]
    assert llmvoice.__version__ == package_version
    assert result.exit_code == 0
    assert result.output.strip() == f"LLMVoice {package_version}"
