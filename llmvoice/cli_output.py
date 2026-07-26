from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from llmvoice.audio.metadata import AudioMetadata
from llmvoice.core.storage import format_bytes
from llmvoice.text.languages import language_label
from llmvoice.voices.manager import StoredVoice


def details_table(rows: list[tuple[str, str]]) -> Table:
    """Build a compact two-column table for CLI details."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()
    for label, value in rows:
        table.add_row(label, value)
    return table


def status_symbol(console: Console, status: str) -> str:
    """Return a status marker supported by the active terminal encoding."""
    unicode_symbols = {"ok": "✓", "warning": "!", "error": "✗"}
    ascii_symbols = {"ok": "OK", "warning": "!", "error": "X"}
    symbol = unicode_symbols[status]
    try:
        symbol.encode(console.encoding or "utf-8")
        return symbol
    except (LookupError, UnicodeEncodeError):
        return ascii_symbols[status]


def render_voice_added(console: Console, voice: StoredVoice) -> None:
    console.print("\n[bold]LLMVoice[/bold]\n")
    console.print("[green]Voice added successfully.[/green]\n")
    console.print(
        details_table(
            [
                ("Name", voice.name),
                ("Duration", f"{voice.metadata.duration_seconds:.1f} sec"),
                ("Format", voice.path.suffix.lstrip(".").upper()),
                ("Sample rate", f"{voice.metadata.sample_rate} Hz"),
                ("Channels", voice.metadata.channel_label),
            ]
        )
    )
    console.print(f"\n[dim]Stored at:[/dim]\n{voice.path}")


def render_voice_list(console: Console, voices: list[StoredVoice]) -> None:
    if not voices:
        console.print(
            "\nNo voices have been added yet.\n\n"
            "Add one with:\n\n"
            "llmvoice voice add friday reference.wav"
        )
        return
    table = Table(title="Stored voices", box=None, header_style="bold")
    table.add_column("NAME")
    table.add_column("DURATION", justify="right")
    table.add_column("FORMAT")
    for voice in voices:
        table.add_row(
            voice.name,
            f"{voice.metadata.duration_seconds:.1f} sec",
            voice.path.suffix.lstrip(".").upper(),
        )
    console.print()
    console.print(table)


def render_voice_info(console: Console, voice: StoredVoice) -> None:
    console.print(f"\n[bold]Voice: {voice.name}[/bold]\n")
    console.print(
        details_table(
            [
                ("File", voice.path.name),
                ("Duration", f"{voice.metadata.duration_seconds:.1f} sec"),
                ("Sample rate", f"{voice.metadata.sample_rate} Hz"),
                ("Channels", voice.metadata.channel_label),
                ("Codec", voice.metadata.codec),
                ("Format", voice.path.suffix.lstrip(".").upper()),
            ]
        )
    )
    console.print(f"\n[dim]Stored at:[/dim]\n{voice.path}")


def render_start_summary(
    console: Console,
    *,
    version: str,
    input_path: Path,
    voice: str,
    voice_is_default: bool,
    language: str,
    auto_detected: bool,
    device: str,
    engine: str,
    output_path: Path,
    characters: int,
    chunks: int,
    estimated_seconds: float,
    dry_run: bool,
) -> None:
    title = "LLMVoice dry run" if dry_run else f"LLMVoice v{version}"
    voice_label = f"{voice} (default)" if voice_is_default else voice
    console.print(f"\n[bold]{title}[/bold]\n")
    console.print(
        details_table(
            [
                ("Input", input_path.name),
                ("Voice", voice_label),
                ("Language", language_label(language, auto_detected)),
                ("Device", device),
                ("Engine", engine),
                ("Output", output_path.name),
                ("Characters", f"{characters:,}"),
                ("Chunks", f"{chunks:,}"),
                ("Estimated speech", f"~{format_duration(estimated_seconds)}"),
            ]
        )
    )
    console.print()


def render_created(
    console: Console,
    output_path: Path,
    metadata: AudioMetadata,
) -> None:
    console.print("\n[bold green]Created successfully[/bold green]\n")
    console.print(
        details_table(
            [
                ("Output", str(output_path)),
                ("Duration", format_duration(metadata.duration_seconds)),
                ("Size", format_bytes(output_path.stat().st_size)),
            ]
        )
    )


def format_duration(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
