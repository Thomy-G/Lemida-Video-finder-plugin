"""
cli/telegram_client.py - Telegram MTProto Uploader for Lemida Videos
Uses Telethon to upload large video lectures (>50MB, up to 2GB/4GB) directly
to Telegram channels or forum topics with streamable video tags and metadata.
"""

from __future__ import annotations
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any

import requests
from telethon import TelegramClient
from telethon.tl.types import Message

from .parser import VideoItem, CourseInfo

CONFIG_FILE = Path(os.getenv("LEMIDA_TELEGRAM_CONFIG", Path.home() / ".lemida_telegram.json"))
UPLOADS_CACHE_FILE = Path(os.getenv("LEMIDA_UPLOADS_CACHE", Path.home() / ".lemida_telegram_uploads.json"))
SESSION_DIR = Path(os.getenv("LEMIDA_SESSIONS_DIR", Path.home() / ".lemida_sessions"))


def load_telegram_config() -> Dict[str, Any]:
    """Loads stored Telegram configuration."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_telegram_config(config: Dict[str, Any]) -> None:
    """Saves Telegram configuration securely."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def is_telegram_configured() -> bool:
    """Checks whether the minimum required Telegram credentials are set."""
    cfg = load_telegram_config()
    api_id = os.getenv("TELEGRAM_API_ID") or cfg.get("api_id")
    api_hash = os.getenv("TELEGRAM_API_HASH") or cfg.get("api_hash")
    return bool(api_id and api_hash)


def load_uploads_cache() -> Dict[str, Any]:
    """Loads map of already uploaded video URLs."""
    if UPLOADS_CACHE_FILE.exists():
        try:
            return json.loads(UPLOADS_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def record_upload(video_url: str, message_id: int, title: str, chat_id: Any) -> None:
    """Records an uploaded video in the cache to avoid duplicate uploads."""
    cache = load_uploads_cache()
    import datetime
    cache[video_url] = {
        "message_id": message_id,
        "title": title,
        "chat_id": str(chat_id),
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    UPLOADS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPLOADS_CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def is_already_uploaded(video_url: str) -> bool:
    """Checks if a video URL was already uploaded to Telegram."""
    cache = load_uploads_cache()
    return video_url in cache


def parse_videos_from_json(json_input: str | Path) -> Tuple[CourseInfo, List[VideoItem]]:
    """
    Parses videos from a local JSON file path or directly from a JSON/Base64 string.
    """
    path = Path(json_input) if isinstance(json_input, (str, Path)) else None
    if path and path.is_file():
        content = path.read_text(encoding="utf-8")
        course, vids = parse_videos_from_json_string(content)
        if course.course_id == "unknown":
            course.course_id = path.stem.replace("lemida_course_", "").replace("_videos", "")
        return course, vids

    # Otherwise treat as raw string / base64 string
    return parse_videos_from_json_string(str(json_input))


class TelegramUploader:
    """Manages Telethon client lifecycle and file uploads."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_telegram_config()
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        session_path = str(SESSION_DIR / "lemida_telethon")

        self.api_id = os.getenv("TELEGRAM_API_ID") or self.config.get("api_id")
        self.api_hash = os.getenv("TELEGRAM_API_HASH") or self.config.get("api_hash")
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or self.config.get("bot_token")
        self.target_chat = os.getenv("TELEGRAM_CHAT_ID") or self.config.get("target_chat")
        self.topic_id = os.getenv("TELEGRAM_TOPIC_ID") or self.config.get("topic_id")
        self.session_string = os.getenv("TELEGRAM_SESSION_STRING") or self.config.get("session_string")

        if not self.api_id or not self.api_hash:
            raise ValueError("Telegram api_id and api_hash must be configured via environment or ~/.lemida_telegram.json")

        from telethon.sessions import StringSession
        if self.session_string:
            self.client = TelegramClient(StringSession(self.session_string), int(self.api_id), str(self.api_hash))
        else:
            self.client = TelegramClient(session_path, int(self.api_id), str(self.api_hash))

    async def connect(self, interactive: bool = True) -> bool:
        """Connects and authenticates with Telegram."""
        if not self.client.is_connected():
            await self.client.connect()

        if self.bot_token:
            if not await self.client.is_user_authorized():
                await self.client.sign_in(bot_token=self.bot_token)
        else:
            if not await self.client.is_user_authorized():
                if not interactive:
                    return False
                await self.client.start()

        return await self.client.is_user_authorized()

    async def disconnect(self):
        """Disconnects the client."""
        if self.client.is_connected():
            await self.client.disconnect()

    def download_stream_to_temp(
        self,
        url: str,
        filename_hint: str = "lecture.mp4",
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """
        Downloads a direct video stream URL to a temporary local file with progress reporting.
        """
        temp_dir = Path(tempfile.gettempdir()) / "lemida_videos"
        temp_dir.mkdir(parents=True, exist_ok=True)
        # Sanitize filename
        safe_name = "".join(c for c in filename_hint if c.isalnum() or c in (" ", "_", "-", ".")).strip()
        if not safe_name.endswith(".mp4"):
            safe_name += ".mp4"
        out_path = temp_dir / safe_name

        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total_size)

        return out_path

    async def upload_video(
        self,
        video: VideoItem,
        course: Optional[CourseInfo] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        target_chat: Optional[Any] = None,
        topic_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Downloads and uploads a single video to Telegram.
        """
        dest_chat = target_chat or self.target_chat
        dest_topic = topic_id if topic_id is not None else self.topic_id

        # Parse combined chat_id_topic_id from Telegram Web URLs (e.g. -1004471025562_2)
        if isinstance(dest_chat, str) and "_" in dest_chat:
            parts = dest_chat.split("_", 1)
            dest_chat = parts[0]
            if dest_topic is None and parts[1].isdigit():
                dest_topic = int(parts[1])

        # Parse numeric chat IDs if given as string
        if isinstance(dest_chat, str) and (dest_chat.startswith("-100") or dest_chat.isdigit() or (dest_chat.startswith("-") and dest_chat[1:].isdigit())):
            try:
                dest_chat = int(dest_chat)
            except ValueError:
                pass

        if isinstance(dest_topic, str) and dest_topic.isdigit():
            dest_topic = int(dest_topic)

        # Download to temp file
        local_path = None
        try:
            if os.getenv("GITHUB_ACTIONS") == "true":
                print(f"::add-mask::{video.url}", flush=True)
            filename = f"{video.title[:40]}.mp4"
            local_path = self.download_stream_to_temp(video.url, filename_hint=filename)

            # Build markdown caption
            course_title = course.title if course else "Lemida BIU Course"
            caption_lines = [
                f"🎬 **{video.title}**",
                f"📚 **Course:** {course_title}",
            ]
            if video.section and video.section != "General":
                caption_lines.append(f"📁 **Section:** {video.section}")

            caption = "\n".join(caption_lines)

            # Upload using Telethon
            msg = await self.client.send_file(
                dest_chat,
                local_path,
                caption=caption,
                reply_to=dest_topic if dest_topic else None,
                supports_streaming=True,
                progress_callback=progress_cb,
            )

            msg_id = msg.id if hasattr(msg, "id") else 0
            record_upload(video.url, msg_id, video.title, dest_chat)
            return True, f"Successfully uploaded: {video.title}"

        except Exception as e:
            return False, f"Upload error: {str(e)}"

        finally:
            # Clean up temporary download file
            if local_path and local_path.exists():
                try:
                    local_path.unlink()
                except Exception:
                    pass

    async def create_forum_topic(
        self,
        title: str,
        target_chat: Optional[Any] = None,
        icon_color: Optional[int] = None,
    ) -> Tuple[Optional[int], str]:
        """
        Creates a new forum topic in the target supergroup/channel and returns its topic ID.
        """
        from telethon.tl.functions.messages import CreateForumTopicRequest
        import random

        dest_chat = target_chat or self.target_chat
        if not dest_chat:
            return None, "Target chat/group is not specified."

        if isinstance(dest_chat, str) and "_" in dest_chat:
            dest_chat = dest_chat.split("_", 1)[0]

        if isinstance(dest_chat, str) and (
            dest_chat.startswith("-100") or dest_chat.isdigit() or (dest_chat.startswith("-") and dest_chat[1:].isdigit())
        ):
            try:
                dest_chat = int(dest_chat)
            except ValueError:
                pass

        try:
            entity = await self.client.get_input_entity(dest_chat)
            random_id = random.randint(1, 2**63 - 1)
            res = await self.client(
                CreateForumTopicRequest(
                    peer=entity,
                    title=title,
                    random_id=random_id,
                    icon_color=icon_color,
                )
            )

            topic_id = None
            for u in getattr(res, "updates", []):
                msg = getattr(u, "message", None)
                if msg and getattr(msg, "id", None):
                    topic_id = msg.id
                    break

            if not topic_id and hasattr(res, "id"):
                topic_id = res.id

            if topic_id:
                return topic_id, f"Created topic '{title}' with Topic ID: {topic_id}"
            else:
                return None, "Topic created but could not determine topic ID."

        except Exception as e:
            return None, f"Failed to create topic: {str(e)}"


def parse_videos_from_json_string(json_text: str) -> Tuple[CourseInfo, List[VideoItem]]:
    """Parses videos from a raw JSON or Base64 string directly in memory."""
    import base64
    text = json_text.strip()
    if text.startswith("ey") or not text.startswith(("{", "[")):
        try:
            decoded = base64.b64decode(text).decode("utf-8")
            text = decoded
        except Exception:
            pass

    data = json.loads(text)
    course = CourseInfo(title="Imported Course", course_id="unknown", url="")
    videos: List[VideoItem] = []

    if isinstance(data, dict):
        if "course" in data and isinstance(data["course"], dict):
            c_data = data["course"]
            course = CourseInfo(
                title=c_data.get("title", course.title),
                course_id=str(c_data.get("id", course.course_id)),
                url=c_data.get("url", ""),
            )

        raw_videos = data.get("videos", [])
        if isinstance(raw_videos, list):
            for idx, item in enumerate(raw_videos, 1):
                if isinstance(item, dict) and "url" in item:
                    url = item["url"]
                    if any(x in url for x in ["/mod/", "/course/", "view.php"]):
                        continue
                    videos.append(
                        VideoItem(
                            id=item.get("id", f"vid_{idx}"),
                            title=item.get("title", f"Video {idx}"),
                            section=item.get("section", "General"),
                            url=url,
                            video_type=item.get("type") or item.get("video_type") or "video/mp4",
                            xpath_matched=item.get("xpathMatched") or item.get("xpath_matched") or "json_import",
                            source_type=item.get("sourceType") or item.get("source_type") or "imported_json",
                            origin_url=item.get("originUrl") or item.get("origin_url"),
                        )
                    )

    elif isinstance(data, list):
        for idx, item in enumerate(data, 1):
            if isinstance(item, dict) and "url" in item:
                url = item["url"]
                if any(x in url for x in ["/mod/", "/course/", "view.php"]):
                    continue
                videos.append(
                    VideoItem(
                        id=f"vid_{idx}",
                        title=item.get("title", f"Video {idx}"),
                        section=item.get("section", "General"),
                        url=url,
                        video_type=item.get("type", "video/mp4"),
                        xpath_matched="json_import",
                        source_type="imported_json",
                    )
                )
            elif isinstance(item, str) and item.startswith("http"):
                if any(x in item for x in ["/mod/", "/course/", "view.php"]):
                    continue
                videos.append(
                    VideoItem(
                        id=f"vid_{idx}",
                        title=f"Video {idx}",
                        section="General",
                        url=item,
                        video_type="video/mp4",
                        xpath_matched="json_import",
                        source_type="imported_json",
                    )
                )

    return course, videos


async def export_session_string(config: Optional[Dict[str, Any]] = None) -> str:
    """Exports active or new Telethon session as a portable string for GitHub Secrets."""
    from telethon.sessions import StringSession
    cfg = config or load_telegram_config()
    api_id = os.getenv("TELEGRAM_API_ID") or cfg.get("api_id")
    api_hash = os.getenv("TELEGRAM_API_HASH") or cfg.get("api_hash")
    if not api_id or not api_hash:
        raise ValueError("Telegram api_id and api_hash must be configured first.")

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_path = str(SESSION_DIR / "lemida_telethon")

    client = TelegramClient(session_path, int(api_id), str(api_hash))
    await client.start()
    str_session = StringSession.save(client.session)
    await client.disconnect()
    return str_session


