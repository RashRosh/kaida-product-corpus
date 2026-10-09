"""Offline regression tests for the Apify discovery workflow; no network calls."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from import_apify_instagram import import_files, phone
from run_apify_discovery import payload


class InstagramPipelineTests(unittest.TestCase):
    def test_phone_normalization(self):
        self.assertEqual(phone("8 707 170 2972"), "+77071702972")
        self.assertEqual(phone("+7 (777) 283-18-14"), "+77772831814")
        self.assertEqual(phone("12345"), "")

    def test_payload_is_minimal_and_no_login(self):
        d = payload(["домашний хлеб Алматы"])
        self.assertEqual(d["searchCountry"], "kz")
        self.assertTrue(d["skipLatestPosts"])
        self.assertFalse(d["emailDiscoveryMode"])
        self.assertNotIn("password", d)

    def test_dedup_and_contact_union_and_geo_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = root / "first.json"
            b = root / "second.json"
            a.write_text(json.dumps([
                {"username":"BAKERY_ALMATY","full_name":"Пекарня Алматы",
                 "biography":"Звоните 8 707 170 2972",
                 "bio_links":[{"url":"https://wa.me/77071702972"}]},
                {"username":"cheese_semey","full_name":"Сыры Семей",
                 "biography":"Сыры на заказ"}
            ],ensure_ascii=False),encoding="utf-8")
            b.write_text(json.dumps([
                {"username":"bakery_almaty","full_name":"Пекарня Алматы",
                 "biography":"Печём хлеб",
                 "bio_links":[{"url":"https://wa.me/77771234567"}]},
                {"username":"bakery_almaty","full_name":"Пекарня Алматы",
                 "biography":"Печём хлеб"}
            ],ensure_ascii=False),encoding="utf-8")
            rows=import_files([a,b])
            self.assertEqual(len(rows),2)
            row=rows["bakery_almaty"]
            self.assertEqual(row["city_status"],"ALMATY_CLAIMED")
            self.assertIn("+77071702972",row["phones"])
            self.assertIn("https://wa.me/77071702972",row["whatsapp_urls"])
            self.assertIn("https://wa.me/77771234567",row["whatsapp_urls"])
            self.assertEqual(row["contact_status"],"PUBLIC_CONTACT")
            self.assertEqual(row["review_status"],"PENDING")
            self.assertEqual(rows["cheese_semey"]["city_status"],"OTHER_CITY_REVIEW")
            self.assertEqual(len(import_files([a,b,a])),2)

    def test_both_actor_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"mixed.json"
            p.write_text(json.dumps([
                {"username":"single_test","fullName":"Test","followersCount":42,
                 "profileUrl":"https://www.instagram.com/single_test/"},
                {"username":"another_test","full_name":"Test 2","followers":5,"bio_links":[]}
            ]),encoding="utf-8")
            result=import_files([p])
            self.assertEqual(result["single_test"]["followers"],42)
            self.assertEqual(result["single_test"]["business_name"],"Test")
            self.assertEqual(result["another_test"]["followers"],5)


if __name__ == "__main__":
    unittest.main()
