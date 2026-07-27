from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_powershell_installer_parses_without_errors() -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not installed.")
    installer = Path(__file__).resolve().parents[1] / "installer" / "install.ps1"
    escaped_installer = str(installer).replace("'", "''")
    command = (
        "$tokens=$null; $errors=$null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{escaped_installer}',"
        "[ref]$tokens,[ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_powershell_python_candidate_regressions() -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not installed.")
    project_root = Path(__file__).resolve().parents[1]
    installer = project_root / "installer" / "install.ps1"
    test_script = project_root / "tests" / "powershell" / "test_python_detection.ps1"
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(test_script),
            "-InstallerPath",
            str(installer),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PYTHON_DETECTION_CASES_PASSED=13" in result.stdout


@pytest.mark.integration
def test_powershell_native_invocation_regressions() -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not installed.")
    project_root = Path(__file__).resolve().parents[1]
    installer = project_root / "installer" / "install.ps1"
    test_script = project_root / "tests" / "powershell" / "test_native_invocation.ps1"
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(test_script),
            "-InstallerPath",
            str(installer),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NATIVE_STDERR_WARNING_EXIT_0=PASSED" in result.stdout
    assert "NATIVE_INVOCATION_CASES_PASSED=10" in result.stdout


@pytest.mark.integration
def test_powershell_runtime_profile_regressions() -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not installed.")
    project_root = Path(__file__).resolve().parents[1]
    installer = project_root / "installer" / "install.ps1"
    test_script = project_root / "tests" / "powershell" / "test_runtime_profiles.ps1"
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(test_script),
            "-InstallerPath",
            str(installer),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RUNTIME_PROFILE_CASES_PASSED=6" in result.stdout
