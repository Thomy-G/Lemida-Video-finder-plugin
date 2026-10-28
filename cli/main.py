"""
cli/main.py - Lemida Video Finder CLI Entrypoint
"""

from __future__ import annotations
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
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


@app.command()
def tui(
    file: Optional[str] = typer.Option(
        None, "--file", "-f", help="Preload videos from an exported JSON file"
    )
):
    """
    Launch the interactive Terminal User Interface (TUI) to browse, stream, and backup videos.
    """
    from .tui import launch_tui
    launch_tui(initial_json_path=file)


@app.command()
def play(
    target: str = typer.Argument(..., help="Direct video URL or Course ID to play"),
    index: int = typer.Option(1, "--index", "-i", help="Video index to play if Course ID is provided (1-based)"),
    player: Optional[str] = typer.Option(None, "--player", "-p", help="Media player to use (vlc, mpv, ffplay, system)"),
):
    """
    Watch a video lecture directly in your terminal/media player (VLC, MPV, FFplay).
    """
    from .player import play_video, get_default_player

    url_to_play = target.strip()

    # If target is numeric or course URL, crawl course to find the video
    if url_to_play.isdigit() or "/course/" in url_to_play:
        from .crawler import crawl_course_videos
        console.print(f"[cyan]Fetching course {url_to_play} to stream video #{index}...[/cyan]")
        course, videos = crawl_course_videos(url_to_play, headless=True)
        if not videos:
            console.print("[bold red]No direct video streams found in this course.[/bold red]")
            sys.exit(1)
        if index < 1 or index > len(videos):
            console.print(f"[bold red]Invalid video index {index}. Course has {len(videos)} videos.[/bold red]")
            sys.exit(1)
        target_video = videos[index - 1]
        url_to_play = target_video.url
        title = target_video.title
    else:
        title = "Lemida Video Stream"

    chosen_player = player or get_default_player()
    console.print(f"[green]Launching video in {chosen_player.upper()}...[/green]")
    success, msg = play_video(url_to_play, title=title, player_choice=chosen_player)
    if success:
        console.print(f"[bold green]✓ {msg}[/bold green]")
    else:
        console.print(f"[bold red]✗ {msg}[/bold red]")
        sys.exit(1)


# ---------------- Telegram Commands ----------------

telegram_app = typer.Typer(
    help="Backup and upload video lectures to Telegram channels or forum topics.",
    no_args_is_help=True,
)
app.add_typer(telegram_app, name="telegram")


@telegram_app.command("config")
def telegram_config():
    """
    Interactively configure Telegram API credentials and authenticate once.
    """
    import asyncio
    from .telegram_client import load_telegram_config, save_telegram_config, TelegramUploader

    console.print("[bold cyan]Telegram MTProto Configuration[/bold cyan]")
    console.print("[dim]Get your API ID and API Hash from https://my.telegram.org[/dim]\n")

    current = load_telegram_config()

    api_id_str = typer.prompt("Telegram API ID", default=str(current.get("api_id") or ""))
    api_hash = typer.prompt("Telegram API Hash", default=str(current.get("api_hash") or ""))
    target_chat = typer.prompt("Target Channel / Chat ID (e.g. @my_channel or -100...)", default=str(current.get("target_chat") or ""))
    topic_id = typer.prompt("Forum Topic ID (optional, press Enter to skip)", default=str(current.get("topic_id") or ""), show_default=False)
    bot_token = typer.prompt("Bot Token (optional, press Enter to login as user)", default=str(current.get("bot_token") or ""), show_default=False)

    new_cfg = {
        "api_id": api_id_str.strip(),
        "api_hash": api_hash.strip(),
        "target_chat": target_chat.strip(),
        "topic_id": topic_id.strip() if topic_id else None,
        "bot_token": bot_token.strip() if bot_token else None,
    }
    save_telegram_config(new_cfg)
    console.print("\n[bold green]✓ Configuration saved to ~/.lemida_telegram.json[/bold green]")

    # Test login
    console.print("[cyan]Connecting and verifying Telegram session...[/cyan]")
    try:
        uploader = TelegramUploader(new_cfg)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(uploader.connect(interactive=True))
        loop.run_until_complete(uploader.disconnect())
        loop.close()

        if success:
            console.print("[bold green]✓ Telegram authentication succeeded and session is active![/bold green]")
        else:
            console.print("[yellow]Could not verify authorization.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Connection error:[/bold red] {e}")


@telegram_app.command("status")
def telegram_status():
    """
    Check current Telegram configuration and upload history.
    """
    from .telegram_client import load_telegram_config, load_uploads_cache, is_telegram_configured

    if not is_telegram_configured():
        console.print("[yellow]Telegram is not configured yet.[/yellow]")
        console.print("Run [cyan]uv run lemida-cli telegram config[/cyan] to set up.")
        return

    cfg = load_telegram_config()
    cache = load_uploads_cache()

    console.print(f"[bold cyan]Telegram Configuration:[/bold cyan]")
    console.print(f"  API ID: [green]{cfg.get('api_id')}[/green]")
    console.print(f"  Target Chat: [green]{cfg.get('target_chat')}[/green]")
    if cfg.get("topic_id"):
        console.print(f"  Forum Topic ID: [green]{cfg.get('topic_id')}[/green]")
    if cfg.get("bot_token"):
        console.print(f"  Auth: [magenta]Bot Token[/magenta]")
    else:
        console.print(f"  Auth: [magenta]User Account (MTProto)[/magenta]")

    console.print(f"\n[dim]Uploaded Videos Cache:[/dim] [bold green]{len(cache)}[/bold green] videos recorded in ~/.lemida_telegram_uploads.json")


@telegram_app.command("create-topic")
def telegram_create_topic(
    title: str = typer.Argument(..., help="Title for the new forum topic (e.g. '[89210] Algorithms 1')"),
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Override destination Telegram supergroup/channel"),
):
    """
    Create a new forum topic in your Telegram supergroup/channel.
    """
    import asyncio
    from .telegram_client import TelegramUploader, load_telegram_config, is_telegram_configured

    if not is_telegram_configured():
        console.print("[bold red]Telegram is not configured.[/bold red]")
        console.print("Run [cyan]uv run lemida-cli telegram config[/cyan] first.")
        sys.exit(1)

    cfg = load_telegram_config()
    if channel:
        if "_" in channel:
            cfg["target_chat"] = channel.split("_", 1)[0]
        else:
            cfg["target_chat"] = channel

    uploader = TelegramUploader(cfg)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        console.print(f"[cyan]Connecting to Telegram to create topic '{title}'...[/cyan]")
        connected = loop.run_until_complete(uploader.connect(interactive=True))
        if not connected:
            console.print("[bold red]Failed to authenticate with Telegram.[/bold red]")
            sys.exit(1)

        topic_id, msg = loop.run_until_complete(uploader.create_forum_topic(title))
        if topic_id:
            console.print(f"[bold green]✓ {msg}[/bold green]")
            console.print(f"\n[dim]To upload videos into this topic, run:[/dim]")
            console.print(f"[cyan]uv run lemida-cli telegram upload <course_id> --topic {topic_id}[/cyan]")
        else:
            console.print(f"[bold red]✗ {msg}[/bold red]")
            sys.exit(1)
    finally:
        loop.run_until_complete(uploader.disconnect())
        loop.close()


@telegram_app.command("upload")
def telegram_upload(
    course_input: Optional[str] = typer.Argument(None, help="Course ID or URL to crawl and upload"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Upload from an exported JSON file"),
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Override destination Telegram channel/chat"),
    topic: Optional[int] = typer.Option(None, "--topic", "-t", help="Override forum topic ID"),
    create_topic: bool = typer.Option(
        False, "--create-topic", "--new-topic", help="Automatically create a new forum topic using the course title"
    ),
):
    """
    Upload course videos directly to Telegram (from a Course ID or from an exported JSON file).
    """
    import asyncio
    from .telegram_client import (
        TelegramUploader,
        parse_videos_from_json,
        is_already_uploaded,
        is_telegram_configured,
        load_telegram_config,
    )
    from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn

    if not is_telegram_configured():
        console.print("[bold red]Telegram is not configured.[/bold red]")
        console.print("Run [cyan]uv run lemida-cli telegram config[/cyan] first.")
        sys.exit(1)

    # 1. Resolve source of videos (JSON file vs Course crawl)
    if file:
        console.print(f"[cyan]Loading videos from JSON file:[/cyan] [bold]{file}[/bold]")
        try:
            course, videos = parse_videos_from_json(file)
        except Exception as e:
            console.print(f"[bold red]Failed to load JSON file:[/bold red] {e}")
            sys.exit(1)
    elif course_input:
        from .crawler import crawl_course_videos
        console.print(f"[cyan]Crawling Lemida for Course {course_input}...[/cyan]")
        course, videos = crawl_course_videos(course_input, headless=True)
    else:
        console.print("[bold red]Please specify either a Course ID or an exported JSON file with --file <path>.[/bold red]")
        sys.exit(1)

    if not videos:
        console.print("[yellow]No video links found to upload.[/yellow]")
        return

    console.print(f"\n[bold green]Ready to upload {len(videos)} videos from '{course.title}'[/bold green]")

    cfg = load_telegram_config()
    if channel:
        if "_" in channel:
            parts = channel.split("_", 1)
            cfg["target_chat"] = parts[0]
            if topic is None and parts[1].isdigit():
                cfg["topic_id"] = int(parts[1])
        else:
            cfg["target_chat"] = channel
    if topic is not None:
        cfg["topic_id"] = topic

    uploader = TelegramUploader(cfg)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        console.print("[dim]Connecting to Telegram MTProto...[/dim]")
        connected = loop.run_until_complete(uploader.connect(interactive=True))
        if not connected:
            console.print("[bold red]Failed to authenticate with Telegram.[/bold red]")
            sys.exit(1)

        if create_topic:
            topic_title = f"[{course.course_id}] {course.title}" if course.course_id and course.course_id != "unknown" else course.title
            console.print(f"[cyan]Creating new Telegram topic: [bold]{topic_title}[/bold]...[/cyan]")
            new_topic_id, t_msg = loop.run_until_complete(uploader.create_forum_topic(topic_title))
            if new_topic_id:
                console.print(f"[bold green]✓ {t_msg}[/bold green]")
                uploader.topic_id = new_topic_id
                cfg["topic_id"] = new_topic_id
            else:
                console.print(f"[bold yellow]Warning: {t_msg}. Proceeding with default destination.[/bold yellow]")

        for idx, vid in enumerate(videos, 1):
            if is_already_uploaded(vid.url):
                console.print(f"[dim][{idx}/{len(videos)}] ⏭ Skipped (already uploaded): {vid.title}[/dim]")
                continue

            console.print(f"\n[bold cyan][{idx}/{len(videos)}] Processing: {vid.title}[/bold cyan]")

            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                transient=True,
            ) as progress:
                upload_task = progress.add_task("Uploading to Telegram...", total=100)

                def progress_cb(current, total):
                    if total > 0:
                        pct = (current / total) * 100
                        progress.update(upload_task, completed=pct)

                success, msg = loop.run_until_complete(
                    uploader.upload_video(vid, course=course, progress_cb=progress_cb)
                )

            if success:
                console.print(f"[bold green]✓ {msg}[/bold green]")
            else:
                console.print(f"[bold red]✗ {msg}[/bold red]")

        console.print("\n[bold green]✓ All uploads completed![/bold green]")

    finally:
        loop.run_until_complete(uploader.disconnect())
        loop.close()


def main():
    app()


if __name__ == "__main__":
    main()

