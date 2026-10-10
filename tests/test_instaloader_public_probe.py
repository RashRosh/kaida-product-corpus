import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from instaloader_public_probe import normalize_username


class TestUsername(unittest.TestCase):
    def test_username(self):
        self.assertEqual(normalize_username("@Bakery.Almaty"), "bakery.almaty")

    def test_url(self):
        self.assertEqual(normalize_username("https://www.instagram.com/cakes.kz/"), "cakes.kz")

    def test_reject_post(self):
        with self.assertRaises(ValueError):
            normalize_username("https://www.instagram.com/p/xyz/")


if __name__ == "__main__":
    unittest.main()
