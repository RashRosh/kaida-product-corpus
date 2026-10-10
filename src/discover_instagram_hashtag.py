"""Discover unique Instagram authors from public hashtag posts.

Dry-run by default. Never uses personal Instagram credentials.
Requires local APIFY_TOKEN and explicit --run --max-usd for paid calls.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ACTOR = "prodiger~instagram-scraper"
RAW = ROOT / "data/raw"
LEDGER = ROOT / "data/extracted/instagram_hashtag_ledger.json"
BASE = ROOT / "data/extracted/instagram_seller_candidates.csv"
USERNAME = re.compile(r"^[a-z0-9._]{1,30}$")


def load_json(path, fallback):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else fallback


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def baseline():
    if not BASE.exists():
        raise FileNotFoundError("Missing local seller corpus: " + str(BASE))
    with BASE.open(encoding="utf-8-sig", newline="") as f:
        return {(r.get("username") or "").strip().lower().lstrip("@")
                for r in csv.DictReader(f) if r.get("username")}


def author(item):
    for candidate in (item.get("ownerUsername"), item.get("owner_username"),
                      item.get("username"), item.get("owner")):
        if isinstance(candidate, dict):
            candidate = candidate.get("username")
        value = str(candidate or "").strip().lower().lstrip("@")
        if USERNAME.fullmatch(value):
            return value
    return ""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hashtag", default="доставкаалматы")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--max-usd", type=float)
    p.add_argument("--run", action="store_true")
    p.add_argument("--input-json", type=Path, help="Free offline inspection of existing Actor export")
    a = p.parse_args()
    tag = a.hashtag.strip().lstrip("#").lower()
    if not re.fullmatch(r"[\w]{2,80}", tag):
        p.error("Hashtag must contain 2-80 letters, numbers, or underscores")
    if not 1 <= a.limit <= 50:
        p.error("--limit must be 1..50")
    if a.run and a.input_json:
        p.error("Choose --run or --input-json, not both")
    known = baseline()
    ledger = load_json(LEDGER, [])
    if not isinstance(ledger, list):
        p.error("Ledger must be a list")
    # Documented schema: directUrls, resultsType, resultsLimit, onlyPostsNewerThan.
    payload = {"directUrls": ["https://www.instagram.com/explore/tags/" + quote(tag) + "/"],
               "resultsType": "posts", "resultsLimit": a.limit,
               "onlyPostsNewerThan": "180 days"}
    print("Actor:", ACTOR)
    print("Input:", json.dumps(payload, ensure_ascii=False))
    print("Known usernames:", len(known))
    if a.input_json:
        items = json.loads(a.input_json.read_text(encoding="utf-8-sig"))
    else:
        if any(x.get("hashtag") == tag for x in ledger):
            p.error("Hashtag already tested. Refusing repeat paid call; inspect ledger.")
        if not a.run:
            print("DRY RUN. No paid request.")
            return
        if a.max_usd is None or not 0.01 <= a.max_usd <= 0.10:
            p.error("--run requires --max-usd between $0.01 and $0.10")
        if abs(round(a.max_usd * 100) / 100 - a.max_usd) > 1e-6:
            p.error("--max-usd must be expressed in whole cents")
        token = os.environ.get("APIFY_TOKEN", "").strip()
        if not token:
            p.error("Missing APIFY_TOKEN")
        url = ("https://api.apify.com/v2/acts/" + ACTOR + "/run-sync-get-dataset-items?"
               + urlencode({"maxTotalChargeUsd": f"{a.max_usd:.2f}",
                            "timeout": 120, "restartOnError": "false"}))
        req = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                      method="POST")
        print("PAID CALL, SERVER CAP USD:", f"{a.max_usd:.2f}")
        try:
            with urlopen(req, timeout=200) as response:
                items = json.load(response)
        except HTTPError as e:
            sys.exit(f"HTTP {e.code}; outcome may be charged; do not retry without checking Console")
        except Exception as e:
            sys.exit(f"Unknown outcome ({type(e).__name__}); STOP, do not retry")
    if not isinstance(items, list):
        sys.exit("Non-array response; STOP")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    filename = "apify_hashtag_" + stamp + ".json"
    # Keep complete responses local, ignored by git.
    if not a.input_json:
        save(RAW / filename, items)
    unique = {name for item in items if isinstance(item, dict) for name in [author(item)] if name}
    fresh = sorted(unique - known)
    print("Posts:", len(items), "Unique authors:", len(unique),
          "Already in corpus:", len(unique & known), "New authors:", len(fresh))
    print("New authors (NOT verified food producers):", ", ".join(fresh) or "(none)")
    if not a.input_json:
        ledger.append({"hashtag": tag, "limit": a.limit, "posts": len(items),
                       "unique_authors": len(unique), "new_authors": len(fresh),
                       "source_file": filename, "max_usd": a.max_usd,
                       "actual_usd": None, "checked_at": datetime.now(timezone.utc).isoformat()})
        save(LEDGER, ledger)
    print("No changes to canonical seller data. Author identity and food relevance need validation.")


if __name__ == "__main__":
    main()
