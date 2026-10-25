"""
tests/test_telegram.py - Unit tests for Telegram JSON parsing and player detection
"""

import json
import tempfile
import unittest
from pathlib import Path
from cli.telegram_client import parse_videos_from_json, is_already_uploaded
from cli.player import detect_available_players, get_default_player


class TestTelegramAndPlayer(unittest.TestCase):

    def test_parse_videos_from_json_standard(self):
        sample = {
            "course": {
                "title": "שיטות סטטיסטיות במדעי המחשב",
                "id": "108883",
                "url": "https://lemida.biu.ac.il/course/view.php?id=108883"
            },
            "total": 2,
            "videos": [
                {
                    "title": "הרצאה 1",
                    "section": "שבוע 1",
                    "url": "https://axt1t2yu790u.compat.objectstorage.il-jerusalem-1.oraclecloud.com/video_bucket/1.mp4"
                },
                {
                    "title": "הרצאה 2",
                    "section": "שבוע 2",
                    "url": "https://axt1t2yu790u.compat.objectstorage.il-jerusalem-1.oraclecloud.com/video_bucket/2.mp4"
                },
                # Moodle page link should be ignored automatically
                {
                    "title": "Invalid Page",
                    "section": "General",
                    "url": "https://lemida.biu.ac.il/mod/videostream/view.php?id=123"
                }
            ]
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(sample, f)
            temp_path = f.name

        try:
            course, videos = parse_videos_from_json(temp_path)
            self.assertEqual(course.title, "שיטות סטטיסטיות במדעי המחשב")
            self.assertEqual(course.course_id, "108883")
            self.assertEqual(len(videos), 2)
            self.assertEqual(videos[0].title, "הרצאה 1")
            self.assertTrue(videos[0].url.endswith("1.mp4"))
            self.assertTrue(videos[1].url.endswith("2.mp4"))
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_parse_videos_from_raw_array(self):
        sample = [
            {"title": "Lesson 1", "url": "https://host.com/vid1.mp4"},
            {"title": "Lesson 2", "url": "https://host.com/vid2.mp4"},
            "https://host.com/raw_link.mp4",
            "https://lemida.biu.ac.il/mod/videostream/view.php?id=999"
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(sample, f)
            temp_path = f.name

        try:
            _, videos = parse_videos_from_json(temp_path)
            self.assertEqual(len(videos), 3)
            self.assertEqual(videos[0].title, "Lesson 1")
            self.assertEqual(videos[2].url, "https://host.com/raw_link.mp4")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_detect_players(self):
        players = detect_available_players()
        self.assertIn("vlc", players)
        self.assertIn("mpv", players)
        self.assertIn("system", players)
        default = get_default_player()
        self.assertIn(default, ["vlc", "mpv", "ffplay", "system"])


if __name__ == "__main__":
    unittest.main()
