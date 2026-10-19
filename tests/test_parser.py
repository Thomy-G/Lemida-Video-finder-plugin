"""
Unit tests for Lemida Video Finder parser, XPath extraction, and exporter.
"""

import unittest
from cli.parser import parse_videos_from_html, extract_course_info, PRIMARY_XPATH
from cli.exporter import export_plain_links, export_to_json, export_to_m3u, export_to_ytdlp


MOCK_LEMIDA_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Calculus 1 - Course 108883</title>
</head>
<body>
    <div class="page-header-headings">
        <h1>Calculus 1 - Advanced Mathematics</h1>
    </div>
    <div>Wrapper 1</div>
    <div>Wrapper 2</div>
    <div id="wrapper-3">
        <div>Inner 1</div>
        <div>Inner 2</div>
        <div>Inner 3</div>
        <div>Inner 4</div>
        <div id="inner-5">
            <div>Deep 1</div>
            <div id="main-content">
                <div>Section container 1</div>
                <div class="content-body">
                    <div>
                        <!-- Section matching user's exact xpath: /html/body/div[3]/div[5]/div/div/div[2]/div[2]/div/section/div[2]/div[1]/div[1]/div/video/source -->
                        <section id="section-1" class="section">
                            <h3 class="sectionname">Week 1: Limits & Continuity</h3>
                            <div>Unused div 1</div>
                            <div class="activity-section">
                                <div class="activity-item">
                                    <div class="activity-content">
                                        <div class="video-wrapper">
                                            <span class="instancename">Lecture 1 - Introduction to Limits</span>
                                            <video controls title="Lecture 1 Video">
                                                <source src="https://lemida.biu.ac.il/pluginfile.php/12345/mod_resource/content/1/lecture1.mp4" type="video/mp4" />
                                            </video>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </section>

                        <!-- Section 2 matching generalized section xpath -->
                        <section id="section-2" class="section">
                            <h3 class="sectionname">Week 2: Derivatives</h3>
                            <div>Unused div 1</div>
                            <div class="activity-section">
                                <div class="activity-item">
                                    <div class="activity-content">
                                        <div class="video-wrapper">
                                            <span class="instancename">Lecture 2 - Derivative Rules</span>
                                            <video controls>
                                                <source src="/files/lecture2.mp4" type="video/mp4" />
                                            </video>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </section>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""


class TestLemidaParser(unittest.TestCase):
    def test_extract_course_info(self):
        info = extract_course_info(MOCK_LEMIDA_HTML, "https://lemida.biu.ac.il/course/view.php?id=108883")
        self.assertEqual(info.title, "Calculus 1 - Advanced Mathematics")
        self.assertEqual(info.course_id, "108883")

    def test_parse_videos_exact_xpath(self):
        videos = parse_videos_from_html(
            MOCK_LEMIDA_HTML,
            "https://lemida.biu.ac.il/course/view.php?id=108883",
            custom_xpath=PRIMARY_XPATH
        )
        self.assertGreaterEqual(len(videos), 1)

        # Check first video
        vid1 = videos[0]
        self.assertIn("lecture1.mp4", vid1.url)
        self.assertTrue(vid1.url.startswith("https://lemida.biu.ac.il"))
        self.assertEqual(vid1.video_type, "video/mp4")
        self.assertIn("Lecture 1", vid1.title)
        self.assertIn("Week 1", vid1.section)

    def test_relative_url_resolution(self):
        videos = parse_videos_from_html(
            MOCK_LEMIDA_HTML,
            "https://lemida.biu.ac.il/course/view.php?id=108883"
        )
        self.assertEqual(len(videos), 2)
        vid2 = videos[1]
        self.assertEqual(vid2.url, "https://lemida.biu.ac.il/files/lecture2.mp4")
        self.assertIn("Lecture 2", vid2.title)
        self.assertIn("Week 2", vid2.section)

    def test_exporters(self):
        info = extract_course_info(MOCK_LEMIDA_HTML, "https://lemida.biu.ac.il/course/view.php?id=108883")
        videos = parse_videos_from_html(MOCK_LEMIDA_HTML, "https://lemida.biu.ac.il/course/view.php?id=108883")

        # Plain links
        plain = export_plain_links(videos)
        self.assertIn("lecture1.mp4", plain)
        self.assertIn("lecture2.mp4", plain)

        # JSON
        json_str = export_to_json(info, videos)
        self.assertIn("108883", json_str)
        self.assertIn("lecture1.mp4", json_str)

        # M3U
        m3u = export_to_m3u(info, videos)
        self.assertTrue(m3u.startswith("#EXTM3U"))
        self.assertIn("#EXTINF:-1", m3u)

        # yt-dlp
        ytdlp = export_to_ytdlp(videos)
        self.assertIn("yt-dlp", ytdlp)


if __name__ == "__main__":
    unittest.main()
