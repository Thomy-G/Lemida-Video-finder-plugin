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


def _get_candidate_vlc_paths() -> List[Path]:
    """Dynamically locates VLC paths across Windows, macOS, and Linux."""
    paths: List[Path] = []
    if sys.platform == "win32":
        for env_var in ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"]:
            val = os.environ.get(env_var)
            if val:
                paths.append(Path(val) / "VideoLAN" / "VLC" / "vlc.exe")
                paths.append(Path(val) / "Programs" / "VideoLAN" / "VLC" / "vlc.exe")
    elif sys.platform == "darwin":
        paths.extend([
            Path("/Applications/VLC.app/Contents/MacOS/VLC"),
            Path.home() / "Applications/VLC.app/Contents/MacOS/VLC",
        ])
    return paths


def _get_candidate_mpv_paths() -> List[Path]:
    """Dynamically locates MPV paths across Windows, macOS, and Linux."""
    paths: List[Path] = []
    if sys.platform == "win32":
        for env_var in ["LOCALAPPDATA", "ProgramFiles", "ProgramData"]:
            val = os.environ.get(env_var)
            if val:
                paths.append(Path(val) / "Programs" / "mpv" / "mpv.exe")
                paths.append(Path(val) / "mpv" / "mpv.exe")
                paths.append(Path(val) / "chocolatey" / "bin" / "mpv.exe")
        paths.append(Path.home() / "scoop" / "apps" / "mpv" / "current" / "mpv.exe")
    elif sys.platform == "darwin":
        paths.extend([
            Path("/opt/homebrew/bin/mpv"),
            Path("/usr/local/bin/mpv"),
        ])
    return paths


def detect_available_players() -> Dict[str, Optional[str]]:
    """Returns a dictionary of supported player names mapped to their executable path (if found)."""
    players: Dict[str, Optional[str]] = {}

    # 1. MPV
    mpv_path = shutil.which("mpv")
    if not mpv_path:
        for p in _get_candidate_mpv_paths():
            if p.is_file():
                mpv_path = str(p)
                break
    players["mpv"] = mpv_path

    # 2. VLC
    vlc_path = shutil.which("vlc")
    if not vlc_path:
        for p in _get_candidate_vlc_paths():
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
