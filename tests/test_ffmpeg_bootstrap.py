from __future__ import annotations

import os
from pathlib import Path

from llmvoice.audio import ffmpeg


def test_shared_ffmpeg_registers_dll_directory_and_retains_handle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shared = tmp_path / "FFmpeg shared" / "bin"
    shared.mkdir(parents=True)
    for filename in ("ffmpeg.exe", "ffprobe.exe", "avcodec-62.dll"):
        (shared / filename).write_bytes(b"test")

    events: list[tuple[str, Path]] = []
    handle = object()

    def fake_which(name: str) -> str | None:
        if name == "ffmpeg":
            return str(shared / "ffmpeg.exe")
        if name == "ffprobe":
            return str(shared / "ffprobe.exe")
        return None

    def fake_add_dll_directory(path: str) -> object:
        events.append(("dll", Path(path)))
        return handle

    previous_handles = list(ffmpeg._DLL_DIRECTORY_HANDLES)
    previous_directories = set(ffmpeg._REGISTERED_DLL_DIRECTORIES)
    previous_path = os.environ.get("PATH")
    ffmpeg._DLL_DIRECTORY_HANDLES.clear()
    ffmpeg._REGISTERED_DLL_DIRECTORIES.clear()
    monkeypatch.setattr(ffmpeg.shutil, "which", fake_which)
    monkeypatch.setattr(os, "add_dll_directory", fake_add_dll_directory, raising=False)
    try:
        ffmpeg_path, ffprobe_path = ffmpeg.require_ffmpeg()
        events.append(("torchcodec-import", shared.resolve()))

        assert Path(ffmpeg_path) == shared / "ffmpeg.exe"
        assert Path(ffprobe_path) == shared / "ffprobe.exe"
        assert events == [
            ("dll", shared.resolve()),
            ("torchcodec-import", shared.resolve()),
        ]
        assert ffmpeg._DLL_DIRECTORY_HANDLES == [handle]
        assert ffmpeg._REGISTERED_DLL_DIRECTORIES == {shared.resolve()}
        assert os.environ["PATH"].split(os.pathsep)[0] == str(shared.resolve())
    finally:
        if previous_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = previous_path
        ffmpeg._DLL_DIRECTORY_HANDLES[:] = previous_handles
        ffmpeg._REGISTERED_DLL_DIRECTORIES.clear()
        ffmpeg._REGISTERED_DLL_DIRECTORIES.update(previous_directories)
