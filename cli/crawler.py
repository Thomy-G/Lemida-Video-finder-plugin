"""
cli/crawler.py - Headless Browser Crawler for Lemida Courses & VideoStream Lectures
Bypasses Radware Bot Protection and extracts all direct video streams.
"""

from __future__ import annotations
import sys
from typing import List, Optional, Dict
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from playwright.sync_api import sync_playwright

from .parser import VideoItem, CourseInfo, PRIMARY_XPATH
from .auth import load_session, save_cookie_string

console = Console()

# Ensure utf-8 terminal output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def get_clean_playwright_cookies(cookies_dict: Dict[str, str]) -> List[dict]:
    """Filters out bloated Microsoft SSO telemetry cookies that trigger 400 Bad Request."""
    ms_prefixes = [
        "ests",
        "esctx",
        "buid",
        "signinstate",
        "fpc",
        "x-ms",
        "sts",
        "aadsso",
        "ssocookie",
        "wlid",
        "mspre",
        "brcap",
        "uaid",
    ]
    pw_cookies = []
    for k, v in cookies_dict.items():
        if any(k.lower().startswith(p) for p in ms_prefixes):
            continue
        domain = ".biu.ac.il" if any(s in k for s in ["uzm", "ssuz", "cbf", "cf_bm"]) else "lemida.biu.ac.il"
        pw_cookies.append({"name": k, "value": v, "domain": domain, "path": "/"})
    return pw_cookies


def crawl_course_videos(
    course_url: str,
    cookie_override: Optional[str] = None,
    custom_xpath: Optional[str] = None,
) -> tuple[CourseInfo, List[VideoItem]]:
    """
    Crawls a Lemida course and its VideoStream lecture pages using Playwright.
    Returns (course_info, video_items).
    """
    if cookie_override:
        cookies_dict = save_cookie_string(cookie_override)
    else:
        cookies_dict = load_session()

    if not cookies_dict:
        raise ValueError("No active session found. Run 'uv run lemida-cli login' first or pass --cookie.")

    playwright_cookies = get_clean_playwright_cookies(cookies_dict)

    with sync_playwright() as pw:
        launch_kwargs = {
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        }
        try:
            browser = pw.chromium.launch(channel="chrome", **launch_kwargs)
        except Exception:
            browser = pw.chromium.launch(**launch_kwargs)

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        context.add_cookies(playwright_cookies)

        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        with console.status(f"[cyan]Connecting to course: {course_url} ...[/cyan]"):
            page.goto(course_url, timeout=40000)

        # Check if redirected to login
        if "login" in page.url and "course" not in page.url:
            browser.close()
            raise PermissionError("Access Denied: Session expired or not enrolled. Please run 'uv run lemida-cli login'.")

        # Extract course title & ID
        page_title = page.title()
        heading_el = page.query_selector(".page-header-headings h1, #page-header h1, h1, .page-header-title")
        course_title = heading_el.inner_text().strip() if heading_el else page_title

        # Determine course ID
        import urllib.parse
        parsed = urllib.parse.urlparse(course_url)
        qs = urllib.parse.parse_qs(parsed.query)
        course_id = qs.get("id", ["unknown"])[0]

        course_info = CourseInfo(title=course_title, course_id=course_id, url=course_url)

        # 1. Check for direct videos on the course overview page
        target_xpath = custom_xpath or PRIMARY_XPATH
        videos: List[VideoItem] = []
        seen_urls = set()

        direct_sources = page.query_selector_all("video source, video")
        for s in direct_sources:
            src = s.get_attribute("src")
            if src and src not in seen_urls and not any(x in src for x in ["/mod/", "/course/", "view.php"]):
                seen_urls.add(src)
                videos.append(
                    VideoItem(
                        id=f"vid_{len(videos) + 1}",
                        title=course_title,
                        section="Course Page",
                        url=src,
                        video_type=s.get_attribute("type") or "video/mp4",
                        xpath_matched=target_xpath,
                        source_type="direct_video",
                        origin_url=course_url,
                    )
                )

        # 2. Find all VideoStream lecture links on the course page
        lecture_elements = page.query_selector_all('a[href*="/mod/videostream/view.php"], a[href*="/mod/videostream/"]')
        lecture_links = []
        for el in lecture_elements:
            href = el.get_attribute("href")
            if not href or any(href == x["url"] for x in lecture_links):
                continue

            raw_title = el.inner_text().strip()
            # Clean title
            clean_title = raw_title.replace("שילוב סרטון", "").replace("VideoStream", "").strip() or f"Lecture {len(lecture_links) + 1}"

            # Find parent section name if available
            section_name = "General"
            try:
                sec_el = el.evaluate("""(node) => {
                    const sec = node.closest('section, .section, li.section');
                    if (sec) {
                        const h = sec.querySelector('.sectionname, .section-title, h3, h4');
                        if (h) return h.innerText.trim();
                    }
                    return null;
                }""")
                if sec_el:
                    section_name = sec_el
            except Exception:
                pass

            lecture_links.append({"url": href, "title": clean_title, "section": section_name})

        # 3. If lecture links found, visit each one and extract the direct video URL
        if lecture_links:
            console.print(f"[cyan]Found {len(lecture_links)} VideoStream lectures. Extracting direct streams...[/cyan]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                transient=True,
            ) as progress:
                task = progress.add_task("Extracting videos...", total=len(lecture_links))

                for idx, act in enumerate(lecture_links, 1):
                    progress.update(task, advance=1, description=f"[{idx}/{len(lecture_links)}] {act['title'][:32]}")
                    try:
                        # Navigate to lecture subpage
                        page.goto(act["url"], timeout=25000)

                        # Extract video source using XPath & CSS
                        sources = page.query_selector_all("video source, video")
                        direct_url = None
                        video_type = "video/mp4"

                        for s in sources:
                            src = s.get_attribute("src")
                            if src and src.startswith("http"):
                                direct_url = src
                                video_type = s.get_attribute("type") or "video/mp4"
                                break

                        # Fallback: check page HTML with regex for direct .mp4 / .m3u8
                        if not direct_url:
                            import re
                            html = page.content()
                            match = re.search(r'["\'](https?://[^"\'\s<>]+\.(?:mp4|m3u8)[^"\'\s<>]*)["\']', html)
                            if match:
                                direct_url = match.group(1)

                        if direct_url and direct_url not in seen_urls:
                            if not any(x in direct_url for x in ["/mod/", "/course/", "view.php"]):
                                seen_urls.add(direct_url)
                                videos.append(
                                    VideoItem(
                                        id=f"vid_{len(videos) + 1}",
                                        title=act["title"],
                                        section=act["section"],
                                        url=direct_url,
                                        video_type=video_type,
                                        xpath_matched=target_xpath,
                                        source_type="videostream_direct",
                                        origin_url=act["url"],
                                    )
                                )
                    except Exception:
                        pass

        browser.close()

    return course_info, videos
