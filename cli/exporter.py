"""
cli/exporter.py - Output formatters & exporters (Rich Table, JSON, M3U, TXT, yt-dlp)
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from .parser import VideoItem, CourseInfo

console = Console()


def print_videos_table(course: CourseInfo, videos: List[VideoItem]) -> None:
    """Renders a beautiful Rich table summarizing the found videos."""
    header_panel = Panel(
        f"[bold white]{course.title}[/bold white]\n"
        f"[dim]Course ID:[/dim] [cyan]{course.course_id}[/cyan]  •  "
        f"[dim]Total Videos:[/dim] [bold green]{len(videos)}[/bold green]\n"
        f"[dim]URL:[/dim] [link={course.url}]{course.url}[/link]",
        title="[bold green]Lemida BIU - Video Finder[/bold green]",
        border_style="green",
    )
    console.print(header_panel)

    if not videos:
        console.print("[yellow]No video links were found on this course page.[/yellow]")
        console.print("[dim]Tip: Use --deep to scan linked activity subpages.[/dim]")
        return

    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        row_styles=["none", "dim"],
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Section", style="magenta", max_width=20)
    table.add_column("Title", style="white", max_width=40)
    table.add_column("Video URL", style="cyan", overflow="fold")
    table.add_column("Type", style="green", width=12)

    for idx, vid in enumerate(videos, 1):
        type_badge = "iframe" if vid.source_type == "iframe" else vid.video_type
        table.add_row(
            str(idx),
            vid.section,
            vid.title,
            vid.url,
            type_badge,
        )

    console.print(table)


def export_plain_links(videos: List[VideoItem]) -> str:
    """Returns newline separated URLs."""
    return "\n".join(v.url for v in videos)


def export_to_json(course: CourseInfo, videos: List[VideoItem]) -> str:
    """Returns JSON representation."""
    data = {
        "course": {
            "title": course.title,
            "id": course.course_id,
            "url": course.url,
        },
        "total": len(videos),
        "videos": [v.to_dict() for v in videos],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_to_m3u(course: CourseInfo, videos: List[VideoItem]) -> str:
    """Generates an M3U playlist file for VLC or media players."""
    lines = ["#EXTM3U", f"#PLAYLIST:{course.title}"]
    for v in videos:
        clean_title = v.title.replace(",", " - ")
        lines.append(f'#EXTINF:-1 group-title="{v.section}",{clean_title}')
        lines.append(v.url)
    return "\n".join(lines)


def export_to_ytdlp(videos: List[VideoItem]) -> str:
    """Generates yt-dlp shell download commands."""
    commands = []
    for v in videos:
        safe_title = v.title.replace('"', "").replace("\\", "").replace("/", "-")
        commands.append(f'yt-dlp "{v.url}" -o "{safe_title}.%(ext)s"')
    return "\n".join(commands)


def save_to_file(content: str, filepath: str | Path) -> None:
    """Saves string content to a target file path."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    console.print(f"[bold green]✓ Saved output to {path}[/bold green]")
