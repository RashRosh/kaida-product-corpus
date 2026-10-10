import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from check_instagram_activity import activity

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)

class ActivityTests(unittest.TestCase):
    def test_recent_post(self):
        item = {"lastPostAt": "2026-10-01T12:00:00Z"}
        self.assertEqual(activity(item, NOW)[0], "ACTIVE_180D")

    def test_old_post(self):
        item = {"lastPostAt": "2025-10-01T12:00:00Z"}
        self.assertEqual(activity(item, NOW)[0], "INACTIVE_180D")

    def test_missing_date_unknown(self):
        self.assertEqual(activity({"recentPosts": []}, NOW)[0], "UNKNOWN")

    def test_reel_post_date(self):
        item = {"recentPosts": [{"type": "video", "postedAt": "2026-10-09T01:00:00Z"}]}
        self.assertEqual(activity(item, NOW)[0], "ACTIVE_180D")

    def test_newest_of_both_fields(self):
        item = {"lastPostAt": "2025-01-01T00:00:00Z",
                "recentPosts": [{"postedAt": "2026-10-09T00:00:00Z"}]}
        self.assertEqual(activity(item, NOW)[0], "ACTIVE_180D")

    def test_future_date_unknown(self):
        item = {"lastPostAt": "2030-01-01T00:00:00Z"}
        self.assertEqual(activity(item, NOW)[0], "UNKNOWN")

if __name__ == "__main__":
    unittest.main()
