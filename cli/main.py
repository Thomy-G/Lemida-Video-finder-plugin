"""
cli/main.py - Lemida Video Finder CLI Entrypoint
"""

from __future__ import annotations
import sys
from typing import Optional
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .auth import (
    create_requests_session,
    interactive_browser_login,
    check_session_status,
    clear_session,
    LEMIDA_BASE_URL,
)
from .parser import (
    parse_videos_from_html,
    extract_course_info,
    find_activity_links,
    VideoItem,
)
from .exporter import (
    print_videos_table,
    export_plain_links,
    export_to_json,
    export_to_m3u,
    export_to_ytdlp,
    save_to_file,
)

app = typer.Typer(
    help="Lemida Video Finder - Extract video links from Bar-Ilan University Moodle courses.",
    no_args_is_help=True,
)
console = Console()


def resolve_course_url(course_input: str) -> str:
    """Normalizes course ID or URL to a full Lemida course URL."""
    course_input = course_input.strip()
    if course_input.startswith("http://") or course_input.startswith("https://"):
        return course_input
    if course_input.isdigit():
        return f"{LEMIDA_BASE_URL}/course/view.php?id={course_input}"
    return f"{LEMIDA_BASE_URL}/course/view.php?id={course_input}"


@app.command()
def login(
    cookie: Optional[str] = typer.Option(
        None, "--cookie", "-c", help="Save MoodleSession cookie directly without opening browser"
    ),
    headless: bool = typer.Option(
        False, "--headless", help="Run browser in headless mode"
    )
):
    """
    Log in to Bar-Ilan University Lemida via Microsoft SSO or by pasting cookie.
    """
    if cookie:
        from .auth import save_cookie_string
        cookies = save_cookie_string(cookie)
        if cookies:
            console.print("[bold green]✓ Cookie saved successfully to session![/bold green]")
            return
        else:
            console.print("[bold red]Failed to parse provided cookie.[/bold red]")
            sys.exit(1)

    cookies = interactive_browser_login(headless=headless)
    if cookies:
        console.print("[bold green]Login completed successfully![/bold green]")
        console.print("[dim]You can now run 'fetch <course_id_or_url>' without logging in again.[/dim]")
    else:
        console.print("[bold red]Login failed or was cancelled.[/bold red]")
        sys.exit(1)


@app.command()
def status():
    """
    Check current Lemida session status.
    """
    session, is_auth = create_requests_session()
    if not is_auth:
        console.print("[yellow]No active session stored.[/yellow]")
        console.print("Run [cyan]uv run lemida-cli login[/cyan] to authenticate.")
        return

    with console.status("[cyan]Verifying session with Lemida BIU...[/cyan]"):
        valid, msg = check_session_status(session)

    if valid:
        console.print(f"[bold green]✓ Session is valid and active![/bold green] ({msg})")
    else:
        console.print(f"[bold red]✗ Session invalid:[/bold red] {msg}")
        console.print("Run [cyan]uv run lemida-cli login[/cyan] to re-authenticate.")


@app.command()
def logout():
    """
    Log out and remove stored session cookies.
    """
    clear_session()


@app.command()
def fetch(
    course: str = typer.Argument(
        ...,
        help="Course ID (e.g. 108883) or full course URL (e.g. https://lemida.biu.ac.il/course/view.php?id=108883)",
    ),
    deep: bool = typer.Option(
        False, "--deep", "-d", help="Deep scan linked activities and subpages for videos"
    ),
    xpath: Optional[str] = typer.Option(
        None, "--xpath", "-x", help="Custom XPath expression to extract video sources"
    ),
    cookie: Optional[str] = typer.Option(
        None, "--cookie", "-c", help="Pass MoodleSession cookie directly"
    ),
    force_login: bool = typer.Option(
        False, "--login", help="Prompt interactive browser login if not authenticated"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output results in JSON format"
    ),
    links_only: bool = typer.Option(
        False, "--links-only", "-l", help="Output only raw video URLs (one per line)"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Save results to file (.txt, .json, .m3u)"
    ),
    ytdlp: bool = typer.Option(
        False, "--ytdlp", help="Output yt-dlp batch download commands"
    ),
):
    """
    Fetch and extract all video links from a Lemida course.
    """
    course_url = resolve_course_url(course)
    session, is_auth = create_requests_session(cookie_override=cookie)

    if not is_auth:
        if force_login:
            console.print("[yellow]Not logged in. Starting interactive browser login...[/yellow]")
            cookies = interactive_browser_login(headless=False)
            if not cookies:
                console.print("[red]Login failed.[/red]")
                sys.exit(1)
            session, _ = create_requests_session()
        else:
            console.print(
                "[yellow]Notice: No stored session found. Attempting guest/public access...[/yellow]\n"
                "[dim]If the course requires login, run:[/dim] [cyan]uv run lemida-cli login[/cyan] "
                "[dim]or pass[/dim] [cyan]--cookie \"MoodleSession=...\"[/cyan]"
            )

    # 1. Fetch course & videos using Chrome crawler (handles Radware and video subpages)
    try:
        from .crawler import crawl_course_videos
        course_info, videos = crawl_course_videos(
            course_url=course_url,
            cookie_override=cookie,
            custom_xpath=xpath,
        )
    except PermissionError as pe:
        if force_login:
            console.print("[yellow]Starting interactive login...[/yellow]")
            interactive_browser_login(headless=False)
            from .crawler import crawl_course_videos
            course_info, videos = crawl_course_videos(
                course_url=course_url,
                cookie_override=cookie,
                custom_xpath=xpath,
            )
        else:
            console.print(f"[bold red]{pe}[/bold red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Failed to fetch course:[/bold red] {e}")
        sys.exit(1)

    # 3. Output Formatting
    if json_output:
        print(export_to_json(course_info, videos))
    elif links_only:
        print(export_plain_links(videos))
    elif ytdlp:
        print(export_to_ytdlp(videos))
    else:
        print_videos_table(course_info, videos)

    # 4. Save to file if requested
    if output:
        out_lower = output.lower()
        if out_lower.endswith(".json"):
            content = export_to_json(course_info, videos)
        elif out_lower.endswith(".m3u"):
            content = export_to_m3u(course_info, videos)
        elif out_lower.endswith(".sh") or out_lower.endswith(".bat"):
            content = export_to_ytdlp(videos)
        else:
            # Default text
            lines = [f"{v.title} [{v.section}]\n{v.url}\n" for v in videos]
            content = f"Course: {course_info.title} ({course_url})\n\n" + "\n".join(lines)
        save_to_file(content, output)


def main():
    app()


if __name__ == "__main__":
    main()
