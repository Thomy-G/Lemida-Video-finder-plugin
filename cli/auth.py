"""
cli/auth.py - Lemida Authentication & Session Management
Handles Microsoft SSO / Bar-Ilan login via Playwright or saved session cookies.
"""

from __future__ import annotations
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional
import requests
from rich.console import Console

console = Console()

DEFAULT_SESSION_PATH = Path.home() / ".lemida_session.json"
LEMIDA_BASE_URL = "https://lemida.biu.ac.il"
LEMIDA_LOGIN_URL = "https://lemida.biu.ac.il/login/index.php"


def get_session_file_path() -> Path:
    """Returns the path to the stored session file."""
    custom_path = os.getenv("LEMIDA_SESSION_PATH")
    if custom_path:
        return Path(custom_path)
    return DEFAULT_SESSION_PATH


def load_session() -> Dict[str, str]:
    """Loads saved cookies from the session file if available."""
    session_file = get_session_file_path()
    if session_file.exists():
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read session file: {e}[/yellow]")
    return {}


def save_session(cookies: Dict[str, str]) -> None:
    """Saves session cookies to file."""
    session_file = get_session_file_path()
    try:
        session_file.parent.mkdir(parents=True, exist_ok=True)
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        console.print(f"[green]✓ Session saved securely to {session_file}[/green]")
    except Exception as e:
        console.print(f"[red]Error saving session: {e}[/red]")


def save_cookie_string(cookie_str: str) -> Dict[str, str]:
    """Parses a raw cookie string (e.g. from Chrome) and saves it."""
    cookies: Dict[str, str] = {}
    cookie_str = cookie_str.strip()
    if "=" in cookie_str:
        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()
    else:
        cookies["MoodleSession"] = cookie_str

    if cookies:
        save_session(cookies)
    return cookies


def clear_session() -> None:
    """Removes the saved session file."""
    session_file = get_session_file_path()
    if session_file.exists():
        session_file.unlink()
        console.print("[green]✓ Session removed.[/green]")
    else:
        console.print("[dim]No active session file found.[/dim]")


def create_requests_session(
    cookie_override: Optional[str] = None,
) -> tuple[requests.Session, bool]:
    """
    Creates a requests.Session with authenticated headers and cookies.
    Returns (session, is_authenticated).
    """
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    )

    if cookie_override:
        cookies = save_cookie_string(cookie_override)
        for k, v in cookies.items():
            s.cookies.set(k, v, domain="lemida.biu.ac.il")
        return s, True

    cookies = load_session()
    if cookies:
        for k, v in cookies.items():
            s.cookies.set(k, v, domain="lemida.biu.ac.il")
        return s, True

    return s, False


def check_session_status(session: requests.Session) -> tuple[bool, str]:
    """
    Checks whether the session is currently authenticated on Lemida.
    Returns (is_logged_in, message).
    """
    try:
        resp = session.get(f"{LEMIDA_BASE_URL}/my/", timeout=15, allow_redirects=True)
        if "login.microsoftonline.com" in resp.url:
            return False, "Not logged in (redirected to Microsoft login)"

        # Check for Moodle login indicators
        html = resp.text
        is_logged_in = any(
            indicator in html
            for indicator in [
                "user/profile.php",
                "logout",
                "sesskey",
                "usermenu",
                "userpicture",
                "שיטות סטטיסטיות",
            ]
        )

        if is_logged_in and "login/index.php" not in resp.url:
            return True, "Active session verified"
        return False, "Session expired or invalid"
    except Exception as e:
        return False, f"Connection error: {e}"


def interactive_browser_login(headless: bool = False) -> Dict[str, str]:
    """
    Opens a browser window for the user to complete Bar-Ilan Microsoft SSO.
    Captures cookies once redirected back to Lemida, or when user presses Enter.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        console.print(
            "[red]Error: Playwright is required for interactive login.[/red]\n"
            "Run: [cyan]uv add playwright && uv run playwright install chromium[/cyan]"
        )
        return {}

    console.print(
        "\n[bold cyan]=== Bar-Ilan Lemida (Microsoft SSO) Login ===[/bold cyan]\n"
        "[dim]1. A browser window will open to Microsoft sign-in.[/dim]\n"
        "[dim]2. Enter your BIU email (@biu.ac.il) and password, and approve 2FA.[/dim]\n"
        "[dim]3. If asked 'Stay signed in?', click [Yes] or [No].[/dim]\n"
        "[bold green]👉 The CLI detects login automatically, OR you can press [Enter] here once logged in![/bold green]\n"
    )

    captured_cookies: Dict[str, str] = {}
    enter_pressed = threading.Event()

    def wait_for_enter():
        try:
            sys.stdin.readline()
            enter_pressed.set()
        except Exception:
            pass

    input_thread = threading.Thread(target=wait_for_enter, daemon=True)
    input_thread.start()

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        }
        try:
            browser = p.chromium.launch(channel="chrome", **launch_kwargs)
        except Exception:
            browser = p.chromium.launch(**launch_kwargs)

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1024, "height": 768},
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page.goto(LEMIDA_LOGIN_URL, timeout=45000)

        console.print("[yellow]Waiting for sign-in... (press Enter here in terminal once logged in)[/yellow]")

        start_time = time.time()
        timeout = 240  # 4 minutes

        try:
            while time.time() - start_time < timeout:
                curr_url = page.url or ""
                all_cookies = context.cookies()

                # Find any session cookies
                has_session_cookie = any(
                    "moodle" in c["name"].lower() or "sess" in c["name"].lower()
                    for c in all_cookies
                )

                # Check if user pressed Enter in terminal
                if enter_pressed.is_set():
                    console.print("[cyan]Manual confirmation received from terminal![/cyan]")
                    for c in all_cookies:
                        captured_cookies[c["name"]] = c["value"]
                    break

                # Auto-detection check 1: Back on Lemida with MoodleSession
                if "lemida.biu.ac.il" in curr_url and "microsoft" not in curr_url and "perfdrive" not in curr_url:
                    if has_session_cookie:
                        # Check if page has reached a course or dashboard
                        if any(p in curr_url for p in ["/my", "/course", "testsession"]):
                            console.print("[green]✓ Authentication detected! (Reached dashboard/course)[/green]")
                            for c in all_cookies:
                                captured_cookies[c["name"]] = c["value"]
                            break

                        # Check DOM for logged-in indicators
                        try:
                            is_auth_dom = page.evaluate("""() => {
                                return !!(
                                    document.querySelector('.usermenu') ||
                                    document.querySelector('a[href*="logout"]') ||
                                    document.querySelector('a[href*="user/profile.php"]') ||
                                    document.querySelector('.userpicture') ||
                                    document.querySelector('.dashboard-card') ||
                                    document.querySelector('.course-info-container')
                                );
                            }""")
                            if is_auth_dom:
                                console.print("[green]✓ Authentication detected via user profile![/green]")
                                for c in all_cookies:
                                    captured_cookies[c["name"]] = c["value"]
                                break
                        except Exception:
                            pass

                time.sleep(1.0)
            else:
                console.print("[red]Login timed out after 4 minutes.[/red]")

        except Exception as e:
            console.print(f"[red]Note during login session: {e}[/red]")
        finally:
            try:
                # Give a brief moment to ensure cookies are flushed
                for c in context.cookies():
                    captured_cookies[c["name"]] = c["value"]
                browser.close()
            except Exception:
                pass

    if captured_cookies:
        # Check if MoodleSession or any moodle cookies were captured
        moodle_cookies = [k for k in captured_cookies if "moodle" in k.lower()]
        console.print(f"[cyan]Captured {len(captured_cookies)} cookies (including: {', '.join(moodle_cookies) if moodle_cookies else 'session tokens'})[/cyan]")
        save_session(captured_cookies)
        return captured_cookies
    else:
        console.print("[red]No cookies captured after login.[/red]")
        return {}
