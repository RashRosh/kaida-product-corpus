"""Offline audit of Data Slayer discoveries against local seller and activity data.

No network calls. No modification of canonical candidates or activity history.
Raw JSON and reports remain in gitignored data/.
"""
import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTED = ROOT / "data" / "extracted"
LEDGER = EXTRACTED / "instagram_dataslayer_ledger.json"
CANDIDATES = EXTRACTED / "instagram_seller_candidates.csv"
ACTIVITY = EXTRACTED / "instagram_activity_review.csv"
OUTPUT = EXTRACTED / "instagram_dataslayer_review.csv"
USERNAME = re.compile(r"^[a-z0-9._]{1,30}$")
FIELDS = ("query", "username", "instagram_url", "corpus_status",
          "activity_status", "last_post_at", "seller_status", "city_status",
          "next_action", "source_file")


def load_csv(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {(row.get("username") or "").strip().lower().lstrip("@"): row
                for row in csv.DictReader(stream) if row.get("username")}


def normalize(value):
    user = str(value or "").strip().lower().lstrip("@")
    return user if USERNAME.fullmatch(user) else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not args.ledger.exists():
        parser.error("Missing Data Slayer experiment ledger")
    entries = json.loads(args.ledger.read_text(encoding="utf-8-sig"))
    if not isinstance(entries, list):
        parser.error("Ledger must be a list")
    candidate = load_csv(CANDIDATES)
    activity = load_csv(ACTIVITY)
    output = {}
    skipped = 0
    for entry in entries:
        filename = Path(str(entry.get("file") or "")).name
        if not filename.startswith("apify_dataslayer_") or not filename.endswith(".json"):
            skipped += 1
            continue
        source = ROOT / "data/raw" / filename
        if not source.is_file():
            print("MISSING LOCAL RAW FILE:", filename)
            skipped += 1
            continue
        items = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(items, list):
            print("INVALID RAW FILE:", filename)
            skipped += 1
            continue
        for obj in items:
            if not isinstance(obj, dict):
                continue
            username = normalize(obj.get("username"))
            if not username:
                continue
            existing = candidate.get(username)
            checked = activity.get(username, {})
            status = checked.get("activity_status") or "NOT_CHECKED"
            if existing:
                next_action = "REVIEW_EXISTING"
                seller_status = "UNVERIFIED"
                # Historical heuristics are not independent evidence of fitness.
                corpus_status = "EXISTING"
            else:
                next_action = "VERIFY_SELLER_AND_CITY"
                seller_status = "UNVERIFIED"
                corpus_status = "NEW"
            # Do not label an account active based on its username or search appearance.
            key = (entry.get("query") or "", username)
            output[key] = {
                "query": entry.get("query") or "",
                "username": username,
                "instagram_url": "https://www.instagram.com/" + username + "/",
                "corpus_status": corpus_status,
                "activity_status": status,
                "last_post_at": checked.get("last_post_at") or "",
                "seller_status": seller_status,
                "city_status": (existing or {}).get("city_status") or "UNVERIFIED",
                "next_action": next_action,
                "source_file": filename,
            }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output[key] for key in sorted(output))
    unique_new = {r["username"] for r in output.values() if r["corpus_status"] == "NEW"}
    unique_existing = {r["username"] for r in output.values() if r["corpus_status"] == "EXISTING"}
    print("Audit rows:", len(output), "new unique:", len(unique_new),
          "overlap:", len(unique_existing), "skipped sources:", skipped)
    print("New usernames need seller, geography, and post-date verification.")
    print("Saved local review:", args.output)
    print("No Apify calls. Canonical candidate and activity CSVs unchanged.")


if __name__ == "__main__":
    main()
