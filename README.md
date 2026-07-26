# LLMVoice

LLMVoice is a Windows CLI that converts UTF-8 text transcripts into MP3 audio
using a fully local voice-cloning model.

```text
TXT -> normalize -> natural chunks -> XTTS-v2 -> audio merge -> MP3
```

No cloud API, telemetry, or file upload is used. The first synthesis may
download model weights; after that, synthesis can run offline.

> [!IMPORTANT]
> XTTS-v2 model weights use the Coqui Public Model License (CPML), which permits
> **non-commercial use only**. The MIT license of the LLMVoice source code does
> not change the model license. Use a differently licensed engine before using
> LLMVoice or its output commercially.
>
> See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for the explicit
> separation between source-code and model licensing.

## Requirements

- Windows 10/11, 64-bit
- Python 3.11-3.14
- FFmpeg **shared build** and FFprobe
- Approximately 4 GB of model/disk space
- NVIDIA GPU recommended; CPU fallback is supported but significantly slower
- A clean, single-speaker voice reference; approximately 6-30 seconds recommended

XTTS-v2 supports English (`en`), Turkish (`tr`), and other documented languages.

## Installation

Create and activate a virtual environment:

```cmd
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
```

Install the shared FFmpeg build required by TorchCodec:

```cmd
winget install --id Gyan.FFmpeg.Shared
```

Reopen the terminal and verify:

```cmd
ffmpeg -version
ffprobe -version
```

Install PyTorch before LLMVoice so that pip does not select an unsuitable CPU
wheel. Obtain the current command from the
[PyTorch installation selector](https://pytorch.org/get-started/locally/).
The verified Windows CUDA 13.0 combination used during development is:

```cmd
python -m pip install torch==2.11.0+cu130 torchaudio==2.11.0+cu130 torchcodec==0.13.0+cu130 --index-url https://download.pytorch.org/whl/cu130
```

CPU-only alternative:

```cmd
python -m pip install torch torchaudio torchcodec --index-url https://download.pytorch.org/whl/cpu
```

Install LLMVoice and XTTS:

```cmd
python -m pip install -e ".[tts]"
```

Development dependencies:

```cmd
python -m pip install -c constraints.txt -e ".[tts,dev]"
```

The TTS extra pins `coqui-tts` to the compatible 0.27 release and keeps
Transformers below 5. It intentionally does not select or replace the user's
PyTorch CUDA/CPU build. `constraints.txt` makes development and release
validation more repeatable but deliberately does not constrain `torch`,
`torchaudio`, or `torchcodec`.

## Quick start

Check the local installation without downloading a model:

```cmd
llmvoice doctor
```

Add and inspect a voice:

```cmd
llmvoice voice add friday reference.wav
llmvoice voice info friday
llmvoice voice list
```

Set it as the default:

```cmd
llmvoice config set default_voice friday
```

Generate speech:

```cmd
llmvoice start transcript.txt --language en
```

The default output is `transcript.mp3` in the transcript directory.

## Start options

Show the plan without loading XTTS or generating audio:

```cmd
llmvoice start transcript.txt --voice friday --language en --dry-run
```

Choose a custom output, speed, and direct reference path:

```cmd
llmvoice start transcript.txt --voice "C:\Voices\friday.mp3" --language en --speed 0.95 -o narration.mp3
```

Existing outputs are protected. Overwrite only when intentional:

```cmd
llmvoice start transcript.txt --force
llmvoice start transcript.txt -o narration.mp3 --force
```

Automatic English/Turkish detection is available:

```cmd
llmvoice start transcript.txt --language auto
```

This is a lightweight heuristic, not a confidence-scored language model. Pass
`--language en` or `--language tr` when accuracy matters.

Use `--debug` to show exception chains and subprocess diagnostics:

```cmd
llmvoice start transcript.txt --debug
```

Normal application errors never print a traceback. `Ctrl+C` exits with code 130,
cleans the temporary job directory, and leaves no partial MP3.

## Voice management

Supported reference formats include WAV, MP3, FLAC, M4A, AAC, OGG, and Opus.
`voice add` validates the audio stream, duration, sample rate, channel count,
codec, and container before copying it.

```cmd
llmvoice voice add friday reference.mp3
llmvoice voice info friday
llmvoice voice list
llmvoice voice remove friday
llmvoice voice remove friday --yes
```

References shorter than 3 seconds are rejected. References longer than 30
seconds are accepted with a warning. LLMVoice never modifies the original.
It prepares a trimmed mono 24 kHz WAV under the reference cache.

Endpoint trimming removes silence only from the beginning and end. Natural
pauses inside the recording are preserved.

## Configuration

```cmd
llmvoice config show
llmvoice config get default_voice
llmvoice config set default_voice friday
llmvoice config set default_language en
llmvoice config set device auto
llmvoice config set chunk_pause_ms 80
```

Unknown fields and invalid values are rejected through `AppConfig` validation.
Use `none` to clear the default voice:

```cmd
llmvoice config set default_voice none
```

Default configuration:

```json
{
  "default_voice": null,
  "default_language": "tr",
  "default_speed": 1.0,
  "output_format": "mp3",
  "device": "auto",
  "engine": "xtts",
  "chunk_size": 220,
  "chunk_pause_ms": 80
}
```

Application data is stored below the Windows local application-data directory:

```text
LLMVoice/
|-- voices/
|-- models/
|-- cache/
|   |-- references/
|   `-- job-.../
`-- config.json
```

Processed reference cache keys include the source path, size, modification
timestamp, and processing version. Cache hits are probed; corrupt entries are
rebuilt. Temporary `job-*` directories are always removed.

## Long transcripts

The text is normalized without rewriting its meaning. Paragraph and sentence
boundaries are preferred when creating bounded chunks. Each chunk is synthesized
separately, and an 80 ms pause is inserted between chunks by default. Configure
the pause from 0 to 500 ms using `chunk_pause_ms`.

XTTS voice conditioning is computed from `speaker_wav` on the first chunk and
reused by internal speaker ID for later chunks. The ID is derived from the
processed reference path, size, and modification timestamp to avoid collisions.

Before synthesis, LLMVoice estimates speech duration and checks free space
separately for the application cache and output volumes. If both paths use the
same volume, one combined check accounts for temporary PCM and atomic MP3
storage. Chunk WAV files are merged in a secure job directory. MP3 is written
to a temporary sibling file and atomically replaces the destination only after
successful encoding. A failed encode never replaces an existing output.

## Architecture

```text
Typer CLI
  -> VoiceService
      -> TTSEngine
          -> XTTSEngine
```

The CLI does not import or call Coqui directly. Text processing, audio metadata,
voice storage, rendering, diagnostics, synthesis, and encoding remain separate.
New engines implement `llmvoice.tts.base.TTSEngine` and are registered in the
engine factory.

## Development and validation

Install the same development tools used by CI:

```cmd
python -m pip install -c constraints.txt -e ".[tts,dev]"
```

Fast unit and mocked CLI/service tests:

```cmd
python -m pytest
```

FFmpeg integration tests:

```cmd
python -m pytest -m integration
```

Run the remaining release checks:

```cmd
python -m compileall llmvoice
python -m pip check
python -m build
```

Integration tests generate small synthetic WAV files and verify:

- leading and trailing silence are trimmed;
- middle silence is preserved;
- corrupt reference cache is rebuilt;
- valid/broken/short voice validation;
- configurable inter-chunk pause.

The default test run never downloads XTTS or performs GPU synthesis.

GitHub Actions runs the unit suite, compilation, dependency validation, package
build, and a separate FFmpeg integration job on Python 3.11. It does not install
or download XTTS model weights.

Before a release, manually validate the locally installed GPU stack with a
non-personal test reference that is not committed:

```cmd
llmvoice doctor
llmvoice start samples\transcript.txt --voice testvoice --language en --force
```

## Licensing

LLMVoice source code is licensed under the [MIT License](LICENSE). XTTS-v2
weights are licensed separately under CPML; MIT does not grant commercial model
rights. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) before
redistributing or using model-backed output.

## Troubleshooting

### FFmpeg was not found

Install the shared build, reopen the terminal, and verify it:

```cmd
winget install --id Gyan.FFmpeg.Shared
ffmpeg -version
```

The static `Gyan.FFmpeg` build provides executables but not the DLLs required by
TorchCodec. Use `Gyan.FFmpeg.Shared`.

### CUDA is unavailable

Run:

```cmd
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

Install a CUDA-enabled PyTorch wheel compatible with the NVIDIA driver. CPU
fallback remains available but is much slower for long-form work.

### XTTS cannot load

- Confirm `llmvoice doctor` reports PyTorch, CUDA/CPU, FFmpeg, and XTTS.
- Allow internet access for the first model download.
- Read and answer the CPML license prompt.
- Check free disk space.
- Run again with `--debug` for technical details.

### Reference audio is rejected

Check that FFprobe can read it:

```cmd
ffprobe reference.wav
```

Use a clean, single-speaker segment with no music or heavy effects. Six to
thirty seconds is generally preferable.

### Chunk transitions sound abrupt

Try a pause between 50 and 150 ms:

```cmd
llmvoice config set chunk_pause_ms 100
```

Also review transcript punctuation and try a `chunk_size` between 160 and 300.
XTTS output is not deterministic, so small tonal differences can remain.
