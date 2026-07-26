from importlib.metadata import version

from typer.testing import CliRunner

import llmvoice
from llmvoice.cli import app


def test_package_and_cli_versions_match() -> None:
    package_version = version("llmvoice")
    result = CliRunner().invoke(app, ["--version"])

    assert package_version == "0.1.1"
    assert llmvoice.__version__ == package_version
    assert result.exit_code == 0
    assert result.output.strip() == f"LLMVoice {package_version}"
