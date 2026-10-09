import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from instagram_discover import extract_usernames, search_url


class InstagramDiscoveryTests(unittest.TestCase):
    def test_extract_variants_and_dedupe(self):
        body = (
            'https://www.instagram.com/Almaty.Cakes/ '
            'https%3A%2F%2Finstagram.com%2Falmaty.cakes%2F '
            'https:\\/\\/instagram.com\\/home_pelmeni'
        )
        self.assertEqual(extract_usernames(body), ["almaty.cakes", "home_pelmeni"])

    def test_reject_non_profile_paths(self):
        body = "https://instagram.com/p/abc https://instagram.com/reel/xyz https://instagram.com/real_shop/"
        self.assertEqual(extract_usernames(body), ["real_shop"])

    def test_query_is_bounded_to_profiles(self):
        self.assertIn("site%3Ainstagram.com", search_url("торты Алматы"))


if __name__ == "__main__":
    unittest.main()
