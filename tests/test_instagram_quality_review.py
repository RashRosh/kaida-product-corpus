"""Offline quality-classification tests."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from review_instagram_candidates import classify, analyze

class ReviewTests(unittest.TestCase):
    def test_producer_in_almaty_with_whatsapp(self):
        row={"username":"home_bakery","business_name":"Пироги Алматы","biography":"Пеку домашние пироги","city_status":"ALMATY_CLAIMED","whatsapp_urls":"https://wa.me/77771112233"}
        result=classify(row)
        self.assertEqual(result["priority"],"HIGH")
        self.assertEqual(result["review_status"],"PENDING")
        self.assertIn("recent_activity",result["manual_check"])

    def test_other_city_not_prioritized(self):
        row={"username":"cheese_semey","business_name":"Домашний сыр","city_status":"OTHER_CITY_REVIEW","phones":"+77771112233"}
        self.assertEqual(classify(row)["priority"],"CHECK_GEO")

    def test_offline_csv_and_no_false_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            inp=Path(temp)/"input.csv";out=Path(temp)/"review.csv"
            with inp.open("w",encoding="utf-8",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=["username","business_name","biography","city_status","whatsapp_urls"])
                writer.writeheader()
                writer.writerow({"username":"bakery","business_name":"Домашний хлеб Алматы","biography":"Пеку хлеб","city_status":"ALMATY_CLAIMED","whatsapp_urls":""})
            analyze(inp,out)
            with out.open("r",encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["priority"],"MEDIUM")
            self.assertEqual(rows[0]["review_status"],"PENDING")

if __name__=="__main__":
    unittest.main()
