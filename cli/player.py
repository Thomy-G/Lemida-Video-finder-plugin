"""
cli/player.py - Video Playback Launcher for CLI & TUI
Detects and launches external media players (VLC, MPV, FFplay, System Default)
to stream backend video URLs directly without blocking the UI.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, List


COMMON_VLC_WINDOWS_PATHS = [
    Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe"),
    Path(r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"),
    Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\VideoLAN\VLC\vlc.exe")),
]

COMMON_MPV_WINDOWS_PATHS = [
    Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\mpv\mpv.exe")),
    Path(r"C:\Program Files\mpv\mpv.exe"),
    Path(r"C:\ProgramData\chocolatey\bin\mpv.exe"),
    Path(os.path.expandvars(r"%USERPROFILE%\scoop\apps\mpv\current\mpv.exe")),
]


def detect_available_players() -> Dict[str, Optional[str]]:
    """Returns a dictionary of supported player names mapped to their executable path (if found)."""
    players: Dict[str, Optional[str]] = {}

    # 1. MPV
    mpv_path = shutil.which("mpv")
    if not mpv_path and sys.platform == "win32":
        for p in COMMON_MPV_WINDOWS_PATHS:
            if p.is_file():
                mpv_path = str(p)
                break
    players["mpv"] = mpv_path

    # 2. VLC
    vlc_path = shutil.which("vlc")
    if not vlc_path and sys.platform == "win32":
        for p in COMMON_VLC_WINDOWS_PATHS:
            if p.is_file():
                vlc_path = str(p)
                break
    players["vlc"] = vlc_path

    # 3. FFplay
    ffplay_path = shutil.which("ffplay")
    players["ffplay"] = ffplay_path

    # 4. System default
    players["system"] = "system"

    return players


def get_default_player() -> str:
    """Returns the best available player name ('vlc', 'mpv', 'ffplay', or 'system')."""
    players = detect_available_players()
    if players.get("mpv"):
        return "mpv"
    if players.get("vlc"):
        return "vlc"
    if players.get("ffplay"):
        return "ffplay"
    return "system"


def play_video(
    url: str,
    title: Optional[str] = None,
    player_choice: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Launches video playback asynchronously in a background subprocess.
    Returns (success: bool, message: str).
    """
    if not url:
        return False, "No URL provided."

    players = detect_available_players()
    chosen = player_choice or get_default_player()

    title_str = title or "Lemida Video Stream"

    try:
        if chosen == "mpv" and players.get("mpv"):
            cmd = [players["mpv"], url, f"--title={title_str}", "--force-window=immediate"]
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return True, f"Streaming in MPV: {title_str}"

        elif chosen == "vlc" and players.get("vlc"):
            cmd = [players["vlc"], url, f"--meta-title={title_str}"]
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return True, f"Streaming in VLC: {title_str}"

        elif chosen == "ffplay" and players.get("ffplay"):
            cmd = [players["ffplay"], "-window_title", title_str, url]
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return True, f"Streaming in FFplay: {title_str}"

        else:
            # Fallback to system default association or browser
            if sys.platform == "win32":
                os.startfile(url)
            else:
                import webbrowser
                webbrowser.open(url)
            return True, f"Opened in system player/browser: {title_str}"

    except Exception as e:
        return False, f"Failed to launch player: {str(e)}"
