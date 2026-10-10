"""Check recent post/Reel activity for existing Instagram seller candidates via Apify.

Dry run by default. Does not use Instagram credentials, and never modifies the source CSV.
"""
import argparse
import csv
import json
import os
import re
import sys
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "extracted" / "instagram_seller_candidates.csv"
RAW = ROOT / "data" / "raw"
OUTPUT = ROOT / "data" / "extracted" / "instagram_activity_review.csv"
LEDGER = ROOT / "data" / "extracted" / "instagram_activity_ledger.json"
ACTOR = "one_dollar_store~instagram-profile-data-scraper"
FIELDS = ("username", "instagram_url", "city_status", "last_post_at", "age_days",
          "activity_status", "date_evidence", "recent_post_count", "source_file")
USERNAME = re.compile(r"^[a-z0-9._]{1,30}$")


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except ValueError:
        return None


def activity(item, now=None, days=180):
    now = now or datetime.now(timezone.utc)
    timestamps = []
    direct = parse_date(item.get("lastPostAt"))
    if direct:
        timestamps.append((direct, "lastPostAt"))
    posts = item.get("recentPosts") or []
    if not isinstance(posts, list):
        posts = []
    for p in posts:
        if isinstance(p, dict):
            t = parse_date(p.get("postedAt"))
            if t:
                timestamps.append((t, "recentPosts.postedAt"))
    if not timestamps:
        return ("UNKNOWN", "", "", "NO_POST_DATE", len(posts))
    last, evidence = max(timestamps, key=lambda pair: pair[0])
    age = (now - last).days
    if last > now + timedelta(days=1):
        return ("UNKNOWN", last.isoformat(), "", "FUTURE_DATE", len(posts))
    status = "ACTIVE_180D" if last >= now - timedelta(days=days) else "INACTIVE_180D"
    return (status, last.isoformat(), max(age, 0), evidence, len(posts))


def load_candidates(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    seen = set()
    candidates = []
    for row in rows:
        username = (row.get("username") or "").strip().lower().lstrip("@")
        if USERNAME.fullmatch(username) and username not in seen:
            seen.add(username)
            candidates.append({**row, "username": username})
    # Favor candidate accounts explicitly claiming Almaty, without pretending it verifies location.
    candidates.sort(key=lambda r: (r.get("city_status") != "ALMATY_CLAIMED", r["username"]))
    return candidates


def load_ledger():
    if not LEDGER.exists():
        return []
    result = json.loads(LEDGER.read_text(encoding="utf-8"))
    if not isinstance(result, list):
        raise ValueError("Activity ledger must be a JSON list")
    return result


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def append_review(rows, source_rows, source_file):
    old = {}
    if OUTPUT.exists():
        with OUTPUT.open(encoding="utf-8-sig", newline="") as fh:
            old = {r["username"]: r for r in csv.DictReader(fh) if r.get("username")}
    by_user = {r["username"]: r for r in source_rows}
    stamp = datetime.now(timezone.utc)
    for item in rows:
        if not isinstance(item, dict):
            continue
        username = str(item.get("requestedUsername") or item.get("username") or "").strip().lower().lstrip("@")
        if username not in by_user:
            continue
        status, last, age, evidence, n = activity(item, stamp)
        source = by_user[username]
        old[username] = dict(username=username,
            instagram_url=source.get("instagram_url") or f"https://www.instagram.com/{username}/",
            city_status=source.get("city_status", ""),
            last_post_at=last, age_days=age, activity_status=status,
            date_evidence=evidence, recent_post_count=n, source_file=source_file)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(old[k] for k in sorted(old))
    counts = {}
    for row in old.values():
        counts[row["activity_status"]] = counts.get(row["activity_status"], 0) + 1
    print("Activity statuses:", counts)
    print("Saved:", OUTPUT)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true", help="Execute a paid Apify call; dry-run otherwise")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--max-usd", type=float, default=0.05)
    p.add_argument("--allow-repeat", action="store_true")
    args = p.parse_args()
    if not 1 <= args.limit <= 100:
        p.error("--limit must be 1-100")
    if not 0 < args.max_usd <= 0.50:
        p.error("--max-usd must be >0 and <=0.50")
    if not SOURCE.exists():
        p.error(f"Missing source CSV: {SOURCE}")
    candidates = load_candidates(SOURCE)
    ledger = load_ledger()
    checked = {name for entry in ledger for name in entry.get("usernames", [])}
    selected = ([r for r in candidates if args.allow_repeat or r["username"] not in checked])[:args.limit]
    if not selected:
        print("No unchecked accounts left. Nothing to do.")
        return
    usernames = [r["username"] for r in selected]
    data = {"usernames": usernames, "includeRecentPosts": True, "includeBio": False, "summaryFallback": True}
    print("Actor:", ACTOR)
    print("Accounts:", usernames)
    print("Maximum charge USD:", args.max_usd)
    if not args.run:
        print("DRY RUN. No paid request. Use --run to execute.")
        return
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        p.error("Missing APIFY_TOKEN environment variable")
    url = ("https://api.apify.com/v2/acts/" + ACTOR + "/run-sync-get-dataset-items?" +
           urlencode({"maxTotalChargeUsd": f"{args.max_usd:.2f}",
                      "timeout": 120, "restartOnError": "false"}))
    req = Request(url, data=json.dumps(data).encode("utf-8"),
                  headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                           "Accept": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=200) as response:
            result = json.load(response)
    except HTTPError as exc:
        print(f"Apify HTTP {exc.code}; check Apify Console for charges BEFORE retrying.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Run result unknown ({type(exc).__name__}); check Apify Console BEFORE retrying.", file=sys.stderr)
        sys.exit(1)
    if not isinstance(result, list):
        p.error("Unexpected Apify output (not a JSON list)")
    RAW.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = "apify_instagram_activity_" + timestamp + ".json"
    save_json(RAW / filename, result)
    print(f"Saved {len(result)} results: {RAW / filename}")
    ledger.append({"usernames": usernames, "file": filename, "recorded_at": timestamp,
                   "max_usd": args.max_usd, "actual_usd": None})
    save_json(LEDGER, ledger)
    append_review(result, selected, filename)
    missing = set(usernames) - {str(r.get("requestedUsername") or r.get("username") or "").lower().lstrip("@")
                                for r in result if isinstance(r, dict)}
    if missing:
        print("No result returned for:", ", ".join(sorted(missing)), "(not classified)")
    print("Actual charge: check Apify Console. Never treat UNKNOWN as inactive.")


if __name__ == "__main__":
    main()
