"""
cli/tui.py - Textual TUI for Watching Videos and Uploading to Telegram
Allows interactive browsing, one-key streaming to media players (VLC, MPV),
and batch uploading of videos directly or from exported JSON files to Telegram.
"""

from __future__ import annotations
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from .crawler import crawl_course_videos
from .parser import CourseInfo, VideoItem
from .player import detect_available_players, get_default_player, play_video
from .telegram_client import (
    TelegramUploader,
    is_already_uploaded,
    is_telegram_configured,
    load_telegram_config,
    parse_videos_from_json,
    save_telegram_config,
)


def copy_to_clipboard(text: str) -> bool:
    """Copies text to clipboard cross-platform."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard", "-Value", text],
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return True
    except Exception:
        pass
    return False


class LemidaTUIApp(App):
    """Lemida Video Finder & Telegram Backup Terminal App."""

    CSS = """
    Screen {
        background: #0f172a;
        color: #f8fafc;
    }

    Header {
        background: #1e293b;
        color: #38bdf8;
    }

    Footer {
        background: #1e293b;
    }

    .panel-card {
        background: #1e293b;
        border: solid #334155;
        padding: 1 2;
        margin: 1;
        border-title-color: #38bdf8;
    }

    .action-bar {
        height: auto;
        margin-bottom: 1;
    }

    .action-btn {
        margin-right: 1;
    }

    DataTable {
        height: 1fr;
        border: solid #334155;
        background: #0f172a;
    }

    DataTable > .datatable--header {
        background: #1e293b;
        color: #38bdf8;
        text-style: bold;
    }

    #details-panel {
        height: auto;
        min-height: 8;
        max-height: 12;
        background: #1e293b;
        border-top: solid #334155;
        padding: 1 2;
    }

    .status-badge-uploaded {
        color: #4ade80;
        text-style: bold;
    }

    .status-badge-pending {
        color: #94a3b8;
    }

    #status-bar {
        background: #090d16;
        color: #38bdf8;
        padding: 0 1;
        height: 1;
        dock: bottom;
    }

    Input {
        border: solid #475569;
        background: #0f172a;
    }

    Input:focus {
        border: solid #38bdf8;
    }

    ProgressBar {
        padding: 1 0;
    }

    RichLog {
        background: #090d16;
        border: solid #334155;
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("space", "play_selected", "Watch Video", show=True),
        Binding("u", "upload_selected", "Upload to TG", show=True),
        Binding("a", "upload_all", "Upload All", show=True),
        Binding("c", "copy_url", "Copy URL", show=True),
        Binding("r", "refresh_list", "Reload", show=False),
    ]

    def __init__(self, initial_json_path: Optional[str] = None):
        super().__init__()
        self.initial_json_path = initial_json_path
        self.course: Optional[CourseInfo] = None
        self.videos: List[VideoItem] = []
        self.selected_video: Optional[VideoItem] = None
        self.current_player: str = get_default_player()
        self.tg_config = load_telegram_config()
        self.is_uploading: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent(initial="explorer-tab"):
            # TAB 1: Video Explorer
            with TabPane("📺 Video Explorer", id="explorer-tab"):
                with Horizontal(classes="action-bar"):
                    yield Input(placeholder="Course ID (e.g. 108883)", id="course-id-input", value="108883")
                    yield Button("Fetch Course", id="fetch-btn", variant="primary", classes="action-btn")
                    yield Input(placeholder="or path to exported JSON file...", id="json-path-input")
                    yield Button("Load JSON", id="load-json-btn", variant="default", classes="action-btn")

                with Horizontal(classes="action-bar"):
                    yield Input(placeholder="🔍 Search lectures by title or section...", id="filter-input")
                    yield Button("▶ Watch Video", id="play-btn", variant="success", classes="action-btn")
                    yield Button("✈ Upload to TG", id="upload-btn", variant="warning", classes="action-btn")
                    yield Button("📋 Copy URL", id="copy-btn", variant="default", classes="action-btn")

                yield DataTable(id="videos-table", cursor_type="row")

                with Vertical(id="details-panel"):
                    yield Label("Select a video from the table above to view details.", id="detail-title")
                    yield Label("", id="detail-meta")
                    yield Label("", id="detail-url")

            # TAB 2: Telegram Uploader & Queue
            with TabPane("✈ Telegram Uploader", id="telegram-tab"):
                with Vertical(classes="panel-card"):
                    yield Label("[bold cyan]Upload Videos to Telegram Channel / Topic[/bold cyan]")
                    yield Label("[dim]Supports direct upload from current course or any exported JSON file.[/dim]")

                    with Horizontal(classes="action-bar", style="margin-top: 1;"):
                        yield Input(
                            placeholder="Path to JSON file (e.g. lemida_course_108883_videos.json)",
                            id="tg-json-file-input",
                        )
                        yield Button("Load & Upload from JSON", id="start-json-upload-btn", variant="warning")

                    with Horizontal(classes="action-bar"):
                        yield Input(
                            placeholder="Create new topic (e.g. [89210] Algorithms 1)",
                            id="new-topic-title-input",
                        )
                        yield Button("➕ Create Topic", id="create-topic-btn", variant="primary")

                    yield Label("Idle", id="upload-status-label")
                    yield ProgressBar(id="upload-progress-bar", total=100, show_eta=True)
                    yield RichLog(id="upload-log", highlight=True, markup=True)

            # TAB 3: Settings
            with TabPane("⚙ Settings", id="settings-tab"):
                with VerticalScroll(classes="panel-card"):
                    yield Label("[bold cyan]Media Player Settings[/bold cyan]")
                    players = detect_available_players()
                    player_options = []
                    for name in ["vlc", "mpv", "ffplay", "system"]:
                        status = "Available" if players.get(name) else "Not detected"
                        player_options.append((f"{name.upper()} ({status})", name))

                    yield Select(player_options, value=self.current_player, id="player-select", prompt="Select Video Player")

                    yield Label("[bold cyan]Telegram MTProto Credentials[/bold cyan]", style="margin-top: 1;")
                    yield Label("[dim]Obtain api_id and api_hash from https://my.telegram.org[/dim]")

                    yield Label("API ID:")
                    yield Input(value=str(self.tg_config.get("api_id") or ""), placeholder="e.g. 12345678", id="cfg-api-id")

                    yield Label("API Hash:")
                    yield Input(value=str(self.tg_config.get("api_hash") or ""), placeholder="e.g. 0123456789abcdef0123456789abcdef", id="cfg-api-hash")

                    yield Label("Target Channel / Chat ID (e.g. @my_channel or -1001234567890):")
                    yield Input(value=str(self.tg_config.get("target_chat") or ""), placeholder="Channel username or numeric ID", id="cfg-target-chat")

                    yield Label("Forum Topic ID (optional):")
                    yield Input(value=str(self.tg_config.get("topic_id") or ""), placeholder="e.g. 2", id="cfg-topic-id")

                    yield Label("Bot Token (optional, if uploading as bot instead of user):")
                    yield Input(value=str(self.tg_config.get("bot_token") or ""), placeholder="Optional bot token", id="cfg-bot-token")

                    yield Button("💾 Save Settings", id="save-settings-btn", variant="success", style="margin-top: 1;")
                    yield Label("", id="settings-feedback")

        yield Static("Ready", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize table columns and load initial data."""
        table = self.query_one("#videos-table", DataTable)
        table.add_columns("#", "Section", "Lecture Title", "Backend Video Stream", "Telegram")

        if self.initial_json_path:
            self.query_one("#json-path-input", Input).value = self.initial_json_path
            self.load_from_json(self.initial_json_path)
        else:
            # Check if there are any course JSON files in current directory to suggest
            for f in Path(".").glob("*.json"):
                if "lemida" in f.name.lower() or "video" in f.name.lower():
                    self.query_one("#json-path-input", Input).value = str(f)
                    break

    def set_status(self, message: str) -> None:
        """Updates the bottom status bar."""
        self.query_one("#status-bar", Static).update(f" {message}")

    # ---------------- Data Loading ----------------

    def load_from_json(self, path_str: str) -> None:
        """Loads videos from a local JSON file."""
        try:
            course, videos = parse_videos_from_json(path_str)
            self.course = course
            self.videos = videos
            self.populate_table(self.videos)
            self.set_status(f"Loaded {len(videos)} videos from JSON: {course.title}")
            self.notify(f"Loaded {len(videos)} videos from JSON file!", title="JSON Loaded", severity="information")
        except Exception as e:
            self.set_status(f"Error loading JSON: {str(e)}")
            self.notify(f"Failed to read JSON: {str(e)}", title="Load Error", severity="error")

    @work(thread=True)
    def fetch_course_background(self, course_id: str) -> None:
        """Crawls course videos in a background worker."""
        self.app.call_from_thread(self.set_status, f"Crawling Lemida for Course {course_id}...")
        self.app.call_from_thread(self.notify, f"Extracting backend streams for course {course_id}...", title="Crawling")

        try:
            from .crawler import crawl_course_videos
            course, videos = crawl_course_videos(course_id, headless=True)
            self.course = course
            self.videos = videos
            self.app.call_from_thread(self.populate_table, self.videos)
            self.app.call_from_thread(self.set_status, f"Found {len(videos)} backend video streams for: {course.title}")
            self.app.call_from_thread(
                self.notify, f"Successfully loaded {len(videos)} videos!", title="Course Ready", severity="information"
            )
        except Exception as e:
            self.app.call_from_thread(self.set_status, f"Crawl failed: {str(e)}")
            self.app.call_from_thread(self.notify, f"Error: {str(e)}", title="Crawl Failed", severity="error")

    def populate_table(self, videos: List[VideoItem]) -> None:
        """Fills the DataTable with videos."""
        table = self.query_one("#videos-table", DataTable)
        table.clear()

        for idx, vid in enumerate(videos, 1):
            is_up = is_already_uploaded(vid.url)
            status_text = "[bold green]✓ Uploaded[/bold green]" if is_up else "[dim]Pending[/dim]"
            
            # Shorten host display
            host_display = "Oracle Cloud" if "oraclecloud" in vid.url else vid.url[:35] + "..."

            table.add_row(
                str(idx),
                vid.section,
                vid.title,
                host_display,
                status_text,
                key=vid.url,
            )

        if videos:
            self.selected_video = videos[0]
            self.update_details(videos[0])

    def update_details(self, vid: VideoItem) -> None:
        """Updates the video details card."""
        self.query_one("#detail-title", Label).update(f"[bold cyan]{vid.title}[/bold cyan]")
        self.query_one("#detail-meta", Label).update(
            f"[dim]Section:[/dim] {vid.section}   |   [dim]Type:[/dim] {vid.video_type}   |   [dim]Player:[/dim] {self.current_player.upper()}"
        )
        self.query_one("#detail-url", Label).update(f"[dim]Stream URL:[/dim] [underline]{vid.url}[/underline]")

    # ---------------- Table Selection & Filtering ----------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handles user clicking or moving rows in the table."""
        url = event.row_key.value
        matched = next((v for v in self.videos if v.url == url), None)
        if matched:
            self.selected_video = matched
            self.update_details(matched)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Real-time table search filtering."""
        if event.input.id == "filter-input":
            q = event.value.strip().lower()
            if not q:
                self.populate_table(self.videos)
                return

            filtered = [
                v for v in self.videos
                if q in v.title.lower() or q in v.section.lower() or q in v.url.lower()
            ]
            self.populate_table(filtered)

    # ---------------- Playback Actions ----------------

    def action_play_selected(self) -> None:
        """Plays the selected video in the media player."""
        if not self.selected_video:
            self.notify("No video selected.", severity="warning")
            return

        vid = self.selected_video
        success, msg = play_video(vid.url, title=vid.title, player_choice=self.current_player)
        if success:
            self.set_status(msg)
            self.notify(msg, title="Playing Video", severity="information")
        else:
            self.set_status(f"Playback error: {msg}")
            self.notify(msg, title="Player Error", severity="error")

    def action_copy_url(self) -> None:
        """Copies the direct stream URL to the clipboard."""
        if not self.selected_video:
            return
        url = self.selected_video.url
        if copy_to_clipboard(url):
            self.notify("Direct stream URL copied to clipboard!", title="Copied")
            self.set_status(f"Copied: {url}")
        else:
            self.set_status(f"Direct URL: {url}")

    # ---------------- Telegram Upload ----------------

    def action_upload_selected(self) -> None:
        """Uploads the currently selected video to Telegram."""
        if not self.selected_video:
            self.notify("No video selected.", severity="warning")
            return

        if self.is_uploading:
            self.notify("An upload is already in progress.", severity="warning")
            return

        self.start_telegram_upload([self.selected_video])

    def action_upload_all(self) -> None:
        """Batch uploads all loaded videos to Telegram."""
        if not self.videos:
            self.notify("No videos loaded.", severity="warning")
            return

        if self.is_uploading:
            self.notify("An upload is already in progress.", severity="warning")
            return

        self.start_telegram_upload(self.videos)

    def start_telegram_upload(self, video_list: List[VideoItem]) -> None:
        """Switches to the Telegram tab and starts background upload worker."""
        if not is_telegram_configured():
            self.notify("Please configure your Telegram credentials in the Settings tab first!", severity="error")
            self.query_one(TabbedContent).active = "settings-tab"
            return

        self.query_one(TabbedContent).active = "telegram-tab"
        self.run_telegram_upload_worker(video_list)

    @work(thread=True)
    def run_telegram_upload_worker(self, video_list: List[VideoItem]) -> None:
        """Executes the Telegram upload loop with live progress updates."""
        self.is_uploading = True
        log = self.query_one("#upload-log", RichLog)
        status_label = self.query_one("#upload-status-label", Label)
        prog_bar = self.query_one("#upload-progress-bar", ProgressBar)

        uploader = TelegramUploader()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            self.app.call_from_thread(log.write, "[bold cyan]Connecting to Telegram MTProto...[/bold cyan]")
            connected = loop.run_until_complete(uploader.connect(interactive=False))
            if not connected:
                self.app.call_from_thread(
                    log.write, "[bold red]Telegram authentication required! Run 'lemida-cli telegram config' in terminal once.[/bold red]"
                )
                return

            self.app.call_from_thread(log.write, f"[bold green]✓ Connected to Telegram! Starting upload of {len(video_list)} videos.[/bold green]")

            for idx, vid in enumerate(video_list, 1):
                if is_already_uploaded(vid.url):
                    self.app.call_from_thread(
                        log.write, f"[dim][{idx}/{len(video_list)}] Skipped (already uploaded): {vid.title}[/dim]"
                    )
                    continue

                self.app.call_from_thread(
                    status_label.update, f"[{idx}/{len(video_list)}] Uploading: [bold]{vid.title}[/bold]"
                )
                self.app.call_from_thread(
                    log.write, f"\n[yellow]→ [{idx}/{len(video_list)}] Downloading & Uploading:[/yellow] [bold]{vid.title}[/bold]"
                )

                def progress_cb(current, total):
                    if total > 0:
                        pct = (current / total) * 100
                        self.app.call_from_thread(prog_bar.update, progress=pct)

                success, msg = loop.run_until_complete(
                    uploader.upload_video(vid, course=self.course, progress_cb=progress_cb)
                )

                if success:
                    self.app.call_from_thread(log.write, f"[bold green]✓ {msg}[/bold green]")
                else:
                    self.app.call_from_thread(log.write, f"[bold red]✗ {msg}[/bold red]")

            self.app.call_from_thread(status_label.update, "All uploads completed!")
            self.app.call_from_thread(log.write, "\n[bold green]✓ Batch upload finished![/bold green]")
            self.app.call_from_thread(self.populate_table, self.videos)

        except Exception as e:
            self.app.call_from_thread(log.write, f"[bold red]Upload worker error: {str(e)}[/bold red]")
        finally:
            loop.run_until_complete(uploader.disconnect())
            loop.close()
            self.is_uploading = False

    @work(thread=True)
    def create_topic_background(self, title: str) -> None:
        """Worker that connects to Telegram and creates a new topic."""
        log = self.query_one("#upload-log", RichLog)
        if not is_telegram_configured():
            self.app.call_from_thread(self.notify, "Configure Telegram in Settings first!", severity="error")
            return

        uploader = TelegramUploader()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            self.app.call_from_thread(log.write, f"[cyan]Creating topic '{title}'...[/cyan]")
            connected = loop.run_until_complete(uploader.connect(interactive=False))
            if not connected:
                self.app.call_from_thread(log.write, "[bold red]Telegram not authenticated! Run 'lemida-cli telegram config' in terminal once.[/bold red]")
                return

            topic_id, msg = loop.run_until_complete(uploader.create_forum_topic(title))
            if topic_id:
                self.app.call_from_thread(log.write, f"[bold green]✓ {msg}[/bold green]")
                self.app.call_from_thread(self.notify, f"Topic created! ID: {topic_id}", title="Topic Created")
                # Auto set topic id in settings / config
                self.tg_config["topic_id"] = topic_id
                save_telegram_config(self.tg_config)
            else:
                self.app.call_from_thread(log.write, f"[bold red]✗ {msg}[/bold red]")
                self.app.call_from_thread(self.notify, f"Error: {msg}", severity="error")
        except Exception as e:
            self.app.call_from_thread(log.write, f"[bold red]Error: {str(e)}[/bold red]")
        finally:
            loop.run_until_complete(uploader.disconnect())
            loop.close()

    # ---------------- Button Handlers ----------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "fetch-btn":
            cid = self.query_one("#course-id-input", Input).value.strip()
            if cid:
                self.fetch_course_background(cid)
            else:
                self.notify("Please enter a valid Course ID", severity="warning")

        elif button_id == "load-json-btn":
            path = self.query_one("#json-path-input", Input).value.strip()
            if path:
                self.load_from_json(path)
            else:
                self.notify("Please enter a JSON file path", severity="warning")

        elif button_id == "play-btn":
            self.action_play_selected()

        elif button_id == "upload-btn":
            self.action_upload_selected()

        elif button_id == "copy-btn":
            self.action_copy_url()

        elif button_id == "start-json-upload-btn":
            json_file = self.query_one("#tg-json-file-input", Input).value.strip()
            if not json_file:
                self.notify("Please provide a JSON file path to upload from.", severity="warning")
                return
            try:
                course, vids = parse_videos_from_json(json_file)
                self.course = course
                self.videos = vids
                self.populate_table(vids)
                self.start_telegram_upload(vids)
            except Exception as e:
                self.notify(f"Could not load JSON: {str(e)}", severity="error")

        elif button_id == "create-topic-btn":
            t_title = self.query_one("#new-topic-title-input", Input).value.strip()
            if not t_title:
                self.notify("Please enter a topic title.", severity="warning")
                return
            self.create_topic_background(t_title)

        elif button_id == "save-settings-btn":
            cfg = {
                "api_id": self.query_one("#cfg-api-id", Input).value.strip(),
                "api_hash": self.query_one("#cfg-api-hash", Input).value.strip(),
                "target_chat": self.query_one("#cfg-target-chat", Input).value.strip(),
                "topic_id": self.query_one("#cfg-topic-id", Input).value.strip() or None,
                "bot_token": self.query_one("#cfg-bot-token", Input).value.strip() or None,
            }
            save_telegram_config(cfg)
            self.tg_config = cfg
            self.query_one("#settings-feedback", Label).update("[bold green]✓ Settings saved successfully![/bold green]")
            self.notify("Telegram settings saved to ~/.lemida_telegram.json", title="Settings Saved")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "player-select" and event.value is not None:
            self.current_player = str(event.value)
            self.set_status(f"Default player set to: {self.current_player.upper()}")
            if self.selected_video:
                self.update_details(self.selected_video)


def launch_tui(initial_json_path: Optional[str] = None):
    """Entry point to start the Textual TUI."""
    app = LemidaTUIApp(initial_json_path=initial_json_path)
    app.run()
