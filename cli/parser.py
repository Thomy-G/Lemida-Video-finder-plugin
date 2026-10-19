"""
cli/parser.py - Video & Course Parser using XPath & DOM Traversal
Extracts videos matching the user's specific XPath as well as robust selectors.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup
import lxml.html

# The exact user-provided XPath:
PRIMARY_XPATH = "/html/body/div[3]/div[5]/div/div/div[2]/div[2]/div/section/div[2]/div[1]/div[1]/div/video/source"

# Fallback & section-wide XPath patterns
FALLBACK_XPATHS = [
    # Across all sections matching the same relative structure:
    "//section/div[2]/div[1]/div[1]/div/video/source",
    "//section//div//video/source",
    "//section//video/source",
    "//section//video",
    "//video/source",
    "//video",
    "//iframe[contains(@src, 'kaltura') or contains(@src, 'panopto') or contains(@src, 'embed') or contains(@src, 'video') or contains(@src, 'mediaspace')]",
]


@dataclass
class VideoItem:
    id: str
    title: str
    section: str
    url: str
    video_type: str
    xpath_matched: str
    source_type: str
    origin_url: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class CourseInfo:
    title: str
    course_id: str
    url: str


def extract_course_info(html: str, page_url: str) -> CourseInfo:
    """Extracts course title and ID from the page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    title_el = (
        soup.select_one(".page-header-headings h1")
        or soup.select_one("#page-header h1")
        or soup.select_one(".page-header-headings")
        or soup.select_one("h1")
    )
    title = title_el.get_text(strip=True) if title_el else "Lemida Course"

    parsed_url = urlparse(page_url)
    qs = parse_qs(parsed_url.query)
    course_id = qs.get("id", ["unknown"])[0]

    return CourseInfo(title=title, course_id=course_id, url=page_url)


def _clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    # Collapse extra whitespace
    return " ".join(text.split()).strip()


def _extract_title_from_lxml_node(node) -> str:
    """Heuristic to extract a clean title from a video/source element or its parent."""
    # 1. Direct title or aria-label
    title_attr = node.get("title") or node.get("aria-label")
    if title_attr:
        clean = _clean_text(title_attr)
        if clean:
            return clean

    parent = node.getparent()
    if parent is not None:
        p_title = parent.get("title") or parent.get("aria-label")
        if p_title:
            clean = _clean_text(p_title)
            if clean:
                return clean

    # 2. Look for enclosing activity container
    curr = node
    while curr is not None:
        classes = (curr.get("class") or "").split()
        if any(c in classes for c in ["activity-item", "activityinstance", "activity", "mod-indent-outer"]):
            # Check for title elements inside activity
            title_nodes = curr.xpath(".//span[contains(@class, 'instancename')] | .//*[contains(@class, 'activityname')] | .//h3 | .//h4")
            for t_node in title_nodes:
                text = _clean_text(t_node.text_content())
                if text:
                    return text
        curr = curr.getparent()

    # 3. Check preceding headings
    if parent is not None:
        prev = parent.getprevious()
        while prev is not None:
            if prev.tag.upper() in ["H1", "H2", "H3", "H4", "H5"]:
                text = _clean_text(prev.text_content())
                if text:
                    return text
            prev = prev.getprevious()

    # 4. Fallback to filename
    src = node.get("src") or ""
    if src:
        parsed = urlparse(src)
        filename = parsed.path.split("/")[-1]
        if filename and len(filename) > 3:
            return filename

    return "Lemida Video"


def _extract_section_from_lxml_node(node) -> str:
    """Finds enclosing section/topic heading."""
    curr = node
    while curr is not None:
        tag = curr.tag.lower()
        classes = (curr.get("class") or "").split()
        if tag == "section" or "section" in classes:
            # Look for section header
            headers = curr.xpath(".//*[contains(@class, 'sectionname')] | .//*[contains(@class, 'section-title')] | .//h3 | .//h4")
            for h in headers:
                text = _clean_text(h.text_content())
                if text:
                    return text
            sec_id = curr.get("id") or curr.get("data-sectionid") or ""
            if sec_id:
                return f"Section {sec_id}"
        curr = curr.getparent()
    return "General"


def parse_videos_from_html(
    html: str,
    base_url: str,
    custom_xpath: Optional[str] = None,
) -> List[VideoItem]:
    """
    Parses video sources from HTML string using XPath and DOM traversal.
    """
    if not html:
        return []

    try:
        tree = lxml.html.fromstring(html)
    except Exception as e:
        return []

    videos: List[VideoItem] = []
    seen_urls: set[str] = set()

    xpaths_to_evaluate: List[str] = []
    if custom_xpath:
        xpaths_to_evaluate.append(custom_xpath)
    xpaths_to_evaluate.append(PRIMARY_XPATH)
    xpaths_to_evaluate.extend(FALLBACK_XPATHS)

    for xpath in xpaths_to_evaluate:
        try:
            matches = tree.xpath(xpath)
        except Exception:
            continue

        for element in matches:
            if not isinstance(element, lxml.html.HtmlElement):
                continue

            src = element.get("src") or element.get("data-src")
            if not src:
                continue

            abs_url = urljoin(base_url, src)
            if abs_url in seen_urls:
                continue

            tag_name = element.tag.lower()
            source_type = "iframe" if tag_name == "iframe" else "html5_video"

            # Filter out non-video iframes
            if source_type == "iframe":
                if not any(
                    kw in abs_url.lower()
                    for kw in ["kaltura", "panopto", "embed", "video", "mediaspace", "player"]
                ):
                    continue

            seen_urls.add(abs_url)

            title = _extract_title_from_lxml_node(element)
            section = _extract_section_from_lxml_node(element)
            v_type = element.get("type") or ("video/mp4" if abs_url.endswith(".mp4") else "video")

            videos.append(
                VideoItem(
                    id=f"video_{len(videos) + 1}",
                    title=title,
                    section=section,
                    url=abs_url,
                    video_type=v_type,
                    xpath_matched=xpath,
                    source_type=source_type,
                    origin_url=base_url,
                )
            )

    return videos


def find_activity_links(html: str, base_url: str) -> List[dict]:
    """
    Finds links to Moodle activities that may contain videos on subpages.
    """
    soup = BeautifulSoup(html, "html.parser")
    activity_links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        abs_href = urljoin(base_url, href)

        if abs_href in seen:
            continue

        # Filter for Moodle video/resource modules
        is_video_module = any(
            mod in abs_href
            for mod in [
                "/mod/videostream/view.php",
                "/mod/videostream/",
                "/mod/kalvidres/view.php",
                "/mod/panopto/view.php",
                "/mod/resource/view.php",
                "/mod/page/view.php",
                "/mod/url/view.php",
            ]
        )

        text = (a.get_text() + " " + (a.parent.get_text() if a.parent else "")).lower()
        has_video_clues = any(
            word in text
            for word in [
                "video",
                "recording",
                "lecture",
                "הקלטה",
                "הרצאה",
                "שיעור",
                "וידאו",
            ]
        )

        if is_video_module or has_video_clues:
            seen.add(abs_href)
            title_node = a.select_one(".instancename") or a
            title = _clean_text(title_node.get_text()) or "Activity Link"
            activity_links.append({"url": abs_href, "title": title})

    return activity_links
