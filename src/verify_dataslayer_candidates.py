"""Verify only NEW Data Slayer accounts. Local files never enter GitHub.

Dry-run by default. Paid check requires --run --max-usd with hard API cap.
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
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from check_instagram_activity import activity, save_json

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data/extracted/instagram_dataslayer_review.csv"
OUTPUT = ROOT / "data/extracted/instagram_dataslayer_verified.csv"
LEDGER = ROOT / "data/extracted/instagram_dataslayer_verification_ledger.json"
RAW = ROOT / "data/raw"
ACTOR = "one_dollar_store~instagram-profile-data-scraper"
USER = re.compile(r"^[a-z0-9._]{1,30}$")
FIELDS = ("username", "instagram_url", "biography", "business_name", "category",
          "city_status", "seller_status", "public_contacts", "last_post_at",
          "age_days", "activity_status", "date_evidence", "source_file")
CITY = re.compile(r"алмат|almaty|almati", re.I)
FOOD = re.compile(r"пельмен|манты|сыр|мяс|рыб|выпеч|торт|десерт|колбас|полуфабрикат|хлеб|еда|кухн|продукт", re.I)


def rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(data)
    tmp.replace(path)


def extract(item, filename, now):
    user = str(item.get("requestedUsername") or item.get("username") or "").strip().lower().lstrip("@")
    if not USER.fullmatch(user):
        return None
    status, last, age, evidence, _ = activity(item, now=now)
    bio = str(item.get("biography") or item.get("bio") or "")
    name = str(item.get("fullName") or item.get("full_name") or "")
    category = str(item.get("category") or "")
    text = " ".join((user, bio, name, category))
    contact = []
    for key in ("externalUrl", "external_url", "businessPhoneNumber", "businessEmail"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            contact.append(value.strip())
    return dict(username=user, instagram_url="https://www.instagram.com/" + user + "/",
                biography=bio, business_name=name, category=category,
                city_status="ALMATY_CLAIMED" if CITY.search(text) else "UNVERIFIED",
                seller_status="FOOD_LIKELY_REVIEW" if FOOD.search(text) else "UNVERIFIED",
                public_contacts="; ".join(sorted(set(contact))), last_post_at=last,
                age_days=age, activity_status=status, date_evidence=evidence,
                source_file=filename)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true")
    p.add_argument("--max-usd", type=float)
    p.add_argument("--limit", type=int, default=6)
    p.add_argument("--input-json", type=Path, help="Offline test existing profile Actor export")
    a = p.parse_args()
    if not 1 <= a.limit <= 10:
        p.error("--limit must be 1..10")
    if a.run and a.input_json:
        p.error("--run and --input-json are mutually exclusive")
    if not REVIEW.exists():
        p.error("Missing review CSV; first run review_dataslayer_discovery.py")
    candidates = sorted({(r.get("username") or "").strip().lower() for r in rows(REVIEW)
                         if r.get("corpus_status") == "NEW" and
                         USER.fullmatch((r.get("username") or "").strip().lower())})
    saved = {r.get("username") for r in rows(OUTPUT)}
    pending = [u for u in candidates if u not in saved][:a.limit]
    print("New discoveries:", len(candidates), "Already verified:", len(saved),
          "Pending:", len(pending))
    print("Selected:", ", ".join(pending) or "(none)")
    if a.input_json:
        items = json.loads(a.input_json.read_text(encoding="utf-8-sig"))
        if not isinstance(items, list):
            p.error("JSON input must be an array")
        filename = a.input_json.name
    else:
        if not pending:
            print("Nothing to verify.")
            return
        if not a.run:
            print("DRY RUN. No paid request. With --run use --max-usd 0.02.")
            return
        if a.max_usd is None or not 0.01 <= a.max_usd <= 0.05:
            p.error("--run requires --max-usd between $0.01 and $0.05")
        if abs(round(a.max_usd * 100) / 100 - a.max_usd) > 0.000001:
            p.error("Use whole cents")
        token = os.getenv("APIFY_TOKEN", "").strip()
        if not token:
            p.error("Missing APIFY_TOKEN")
        payload = {"usernames": pending, "includeRecentPosts": True,
                   "includeBio": True, "summaryFallback": True}
        url = ("https://api.apify.com/v2/acts/" + ACTOR + "/run-sync-get-dataset-items?"
               + urlencode({"maxTotalChargeUsd": f"{a.max_usd:.2f}",
                            "timeout": 120, "restartOnError": "false"}))
        request = Request(url, data=json.dumps(payload).encode("utf-8"),
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/json"}, method="POST")
        print("Paid request for", len(pending), "accounts; server cap:", f"${a.max_usd:.2f}")
        try:
            with urlopen(request, timeout=200) as response:
                items = json.load(response)
        except HTTPError as exc:
            sys.exit(f"HTTP {exc.code}. STOP; inspect Apify billing before retry.")
        except Exception as exc:
            sys.exit(f"Unknown outcome ({type(exc).__name__}). STOP; do not retry.")
        if not isinstance(items, list):
            sys.exit("Non-array actor response. STOP; do not retry.")
        filename = "apify_dataslayer_verification_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
        save_json(RAW / filename, items)
    now = datetime.now(timezone.utc)
    allowed = set(candidates if a.input_json else pending)
    verified = {r["username"]: r for r in rows(OUTPUT) if r.get("username")}
    returned = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        parsed = extract(item, filename, now)
        if parsed and parsed["username"] in allowed:
            returned.add(parsed["username"])
            verified[parsed["username"]] = parsed
    write_rows(OUTPUT, [verified[u] for u in sorted(verified)])
    if not a.input_json:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else []
        ledger.append(dict(requested=pending, returned=sorted(returned), file=filename,
                           max_usd=a.max_usd, actual_usd=None, checked_at=now.isoformat()))
        save_json(LEDGER, ledger)
    statuses = {}
    for u in returned:
        state = verified[u]["activity_status"]
        statuses[state] = statuses.get(state, 0) + 1
    print("Returned:", len(returned), "/", len(pending) if not a.input_json else len(allowed),
          "Activity:", statuses)
    print("Saved local verification:", OUTPUT)
    print("Food relevance and Almaty are heuristic, NOT independently confirmed.")
    print("Missing accounts are not treated as inactive; never automatically retry.")
    print("Actual costs require billing verification.")


if __name__ == "__main__":
    main()
