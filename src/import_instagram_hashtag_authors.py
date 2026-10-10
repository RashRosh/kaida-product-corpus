"""Import hashtag post authors into the existing local review-only candidate CSV.

No network calls. Does not replace existing candidate rows. Safe to run again.
Uses source files referenced by the local hashtag ledger.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/extracted/instagram_hashtag_ledger.json"
OUTPUT = ROOT / "data/extracted/instagram_seller_candidates.csv"
RAW = ROOT / "data/raw"
USER = re.compile(r"^[a-z0-9._]{1,30}$")
FIELDS = ("username", "instagram_url", "instagram_id", "business_name",
          "biography", "category", "followers", "source_files", "city_status",
          "phones", "whatsapp_urls", "other_urls", "contact_status", "review_status")

def username(post):
    for value in (post.get("ownerUsername"), post.get("owner_username"),
                  post.get("username"), post.get("owner")):
        if isinstance(value, dict):
            value = value.get("username")
        value = str(value or "").strip().lower().lstrip("@")
        if USER.fullmatch(value):
            return value
    return ""

def main():
    if not LEDGER.exists():
        raise SystemExit("Missing local hashtag ledger")
    entries = json.loads(LEDGER.read_text(encoding="utf-8-sig"))
    if not isinstance(entries, list):
        raise SystemExit("Invalid ledger")
    old = {}
    if OUTPUT.exists():
        with OUTPUT.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key = str(row.get("username") or "").strip().lower().lstrip("@")
                if USER.fullmatch(key):
                    old[key] = {k: row.get(k, "") for k in FIELDS}
    initial = len(old)
    posts = 0
    for entry in entries:
        filename = Path(str(entry.get("source_file") or "")).name
        if not filename.startswith("apify_hashtag_") or not filename.endswith(".json"):
            continue
        path = RAW / filename
        if not path.exists():
            print("Missing local source:", filename)
            continue
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, list):
            continue
        posts += len(data)
        for item in data:
            if not isinstance(item, dict):
                continue
            user = username(item)
            if not user:
                continue
            if user not in old:
                old[user] = dict.fromkeys(FIELDS, "")
                old[user].update(username=user,
                                 instagram_url=f"https://www.instagram.com/{user}/",
                                 city_status="UNVERIFIED",
                                 contact_status="INSTAGRAM_ONLY",
                                 review_status="PENDING")
            sources = set(filter(None, old[user]["source_files"].split("; ")))
            sources.add(filename)
            old[user]["source_files"] = "; ".join(sorted(sources))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(old[key] for key in sorted(old))
    tmp.replace(OUTPUT)
    print("Hashtag posts:", posts, "Previous candidates:", initial,
          "New candidates:", len(old) - initial, "Total candidates:", len(old))
    print("Saved:", OUTPUT)
    print("All newly imported authors are UNVERIFIED, not approved producers.")

if __name__ == "__main__":
    main()
