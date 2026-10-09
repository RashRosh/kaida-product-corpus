import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from instagrapi_probe import user_record, run_search


class InstagrapiProbeTests(unittest.TestCase):
    def test_user_record(self):
        row = user_record(SimpleNamespace(username="Cake.Almaty", full_name="Cakes", biography=""), "торты алматы")
        self.assertEqual(row["username"], "cake.almaty")
        self.assertEqual(row["city_status"], "UNVERIFIED")

    def test_deduplicates(self):
        class Fake:
            def search_users(self, query, amount):
                return [SimpleNamespace(username="cakes", full_name="Cake", biography="")]
        self.assertEqual(len(run_search(Fake(), ["a", "b"], 2)), 1)

    def test_stops_on_error(self):
        class Fake:
            calls = 0
            def search_users(self, query, amount):
                self.calls += 1
                raise RuntimeError("checkpoint")
        client = Fake()
        self.assertEqual(run_search(client, ["a", "b"], 2), [])
        self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
