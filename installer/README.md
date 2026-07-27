# LLMVoice bootstrap installer

`install.ps1` is the canonical Windows bootstrap installer published with each
GitHub Release. It installs a release wheel; it never clones the repository or
uses an editable package.

## Installation flow

1. Require PowerShell 5.1+, 64-bit Windows, supported 64-bit Python, FFmpeg, and
   FFprobe.
2. Download `install-manifest.json` from the latest or explicitly selected
   GitHub Release over HTTPS.
3. Select the CUDA profile when `nvidia-smi` detects an NVIDIA GPU, otherwise
   select CPU. `-Runtime cuda` and `-Runtime cpu` override automatic selection.
4. Download the exact wheel named by the manifest and verify its SHA-256 hash.
5. Build an isolated versioned virtual environment, install the selected
   PyTorch profile, pinned TTS dependencies, and the LLMVoice wheel.
6. Validate imports, require CUDA availability for the CUDA profile, verify the
   CLI version, and run `llmvoice doctor`.
7. Atomically update the launcher and installer state, then add the per-user
   `bin` directory to the user PATH without duplicates.

No administrator privileges, machine PATH changes, registry edits, telemetry,
or arbitrary downloaded script execution are used.

## Runtime layout

```text
%LOCALAPPDATA%\LLMVoice\
|-- runtime\
|   |-- install-state.json
|   `-- versions\
|       `-- 0.1.2-cuda-<id>\
|           `-- venv\
|-- bin\
|   `-- llmvoice.cmd
|-- voices\
|-- models\
|-- cache\
`-- config.json
```

Versioned runtime directories allow a new installation to be fully verified
before the launcher is switched. Upgrades replace only `runtime`/`bin` state.
Voices, models, reference cache, and `config.json` are never deleted.

## Usage

Download `install.ps1` from a GitHub Release, inspect it, then run:

```powershell
Unblock-File .\install.ps1
.\install.ps1
```

If Windows PowerShell is configured with the `Restricted` execution policy,
run the inspected script with a process-only override:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

This does not modify the persisted user or machine execution policy.

Options:

```powershell
.\install.ps1 -Runtime auto
.\install.ps1 -Runtime cuda
.\install.ps1 -Runtime cpu
.\install.ps1 -Version 0.1.2
.\install.ps1 -Force
.\install.ps1 -Debug
```

The default version is `latest`. Re-running an installed version is a no-op
unless `-Force` is supplied.

## Python and FFmpeg

Python compatibility comes from the release manifest generated from
`project.requires-python`. The installer searches the Windows `py` launcher,
then `python.exe` and `python3.exe`, and validates the real interpreter version,
path, and 64-bit architecture. It does not install Python automatically.

FFmpeg and FFprobe must already be available. The recommended shared build is:

```powershell
winget install --id Gyan.FFmpeg.Shared
```

Reopen the terminal after installing prerequisites.

## CUDA and CPU profiles

Runtime package versions and official PyTorch index URLs are generated from
`pyproject.toml`; the installer contains no package-version constants. Automatic
selection uses `nvidia-smi`, but a detected GPU is not considered sufficient:
the isolated runtime must also report `torch.cuda.is_available() == True`.
There is no silent fallback from CUDA to CPU.

## Upgrade and recovery

A candidate runtime is installed and diagnosed before `llmvoice.cmd` or
`install-state.json` changes. A failed download, checksum, dependency install,
CUDA validation, or doctor run leaves the active launcher unchanged. After a
successful switch the prior runtime is removed when possible; failure to remove
it is a warning and does not affect user data.

## Manual uninstall

To remove only the executable runtime:

1. Delete `%LOCALAPPDATA%\LLMVoice\runtime`.
2. Delete `%LOCALAPPDATA%\LLMVoice\bin`.
3. Remove `%LOCALAPPDATA%\LLMVoice\bin` from the user PATH.

Do not delete the whole `%LOCALAPPDATA%\LLMVoice` directory unless you also
intend to remove voices, downloaded models, caches, and configuration.

## Troubleshooting

- Run with `-Debug` for PowerShell failure details.
- A checksum mismatch always aborts installation.
- If CUDA validation fails, update the NVIDIA driver or install the CPU profile
  explicitly.
- If final diagnostics fail, run the installed runtime executable under
  `runtime\versions\<id>\venv\Scripts\llmvoice.exe doctor`.
- XTTS model weights are not release assets. They retain their separate CPML
  terms and are downloaded by the model library on first use.
