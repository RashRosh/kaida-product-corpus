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
    # A previous version incorrectly marked all requested usernames as checked,
    # even when Apify returned only 10. Trust persisted *results*, not requests.
    checked = set()
    if OUTPUT.exists():
        with OUTPUT.open(encoding="utf-8-sig", newline="") as fh:
            checked = {r["username"] for r in csv.DictReader(fh) if r.get("username")}
    selected = [r for r in candidates if args.allow_repeat or r["username"] not in checked][:args.limit]
    if not selected:
        print("All candidates already have saved results. Nothing to do.")
        return
    batches = [selected[i:i+10] for i in range(0, len(selected), 10)]
    # max-usd is a TOTAL ceiling for this CLI invocation. Every Apify run
    # has its own independently enforced maxTotalChargeUsd budget.
    total_cents = int(round(args.max_usd * 100))
    if abs(total_cents / 100 - args.max_usd) > 0.000001:
        p.error("--max-usd must be specified in whole cents")
    if total_cents < len(batches):
        p.error(f"Budget too small for {len(batches)} batches; need at least ${len(batches)/100:.2f}")
    cents = [total_cents // len(batches)] * len(batches)
    for i in range(total_cents % len(batches)):
        cents[i] += 1
    print("Actor:", ACTOR)
    print("Already saved:", len(checked))
    print("Pending:", len(selected), "in", len(batches), "batches of at most 10")
    print("TOTAL maximum charge USD:", f"{args.max_usd:.2f}")
    print("Per-batch caps USD:", [f"{x/100:.2f}" for x in cents])
    if not args.run:
        print("DRY RUN. No paid request. Use --run to execute.")
        return
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        p.error("Missing APIFY_TOKEN environment variable")
    ledger = load_ledger()
    for ix, (batch, budget_cents) in enumerate(zip(batches, cents), start=1):
        usernames = [r["username"] for r in batch]
        data = {"usernames": usernames, "includeRecentPosts": True,
                "includeBio": False, "summaryFallback": True}
        url = ("https://api.apify.com/v2/acts/" + ACTOR + "/run-sync-get-dataset-items?" +
               urlencode({"maxTotalChargeUsd": f"{budget_cents/100:.2f}",
                          "timeout": 120, "restartOnError": "false"}))
        req = Request(url, data=json.dumps(data).encode("utf-8"),
                      headers={"Authorization": "Bearer " + token,
                               "Content-Type": "application/json",
                               "Accept": "application/json"}, method="POST")
        print(f"Batch {ix}/{len(batches)}: requested {len(usernames)}, cap ${budget_cents/100:.2f}")
        try:
            with urlopen(req, timeout=200) as response:
                result = json.load(response)
        except HTTPError as exc:
            print(f"Apify HTTP {exc.code}. STOP: inspect Console before retrying.", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"Request outcome unknown ({type(exc).__name__}). STOP: inspect Console.", file=sys.stderr)
            sys.exit(1)
        if not isinstance(result, list):
            print("Unexpected response: not a JSON list. STOP.", file=sys.stderr)
            sys.exit(1)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        filename = "apify_instagram_activity_" + stamp + ".json"
        save_json(RAW / filename, result)
        # Save only confirmed returned usernames as checked, never entire request.
        returned = {str(x.get("requestedUsername") or x.get("username") or "").strip().lower().lstrip("@")
                    for x in result if isinstance(x, dict)}
        valid = returned.intersection(usernames)
        ledger.append({"usernames": sorted(valid), "requested_usernames": usernames,
                       "file": filename, "recorded_at": stamp,
                       "max_usd": budget_cents / 100, "actual_usd": None})
        save_json(LEDGER, ledger)
        append_review(result, batch, filename)
        print(f"Returned {len(valid)}/{len(usernames)}; saved {filename}")
        missing = set(usernames) - valid
        if missing:
            print("Missing:", ", ".join(sorted(missing)))
            print("STOP: partial batch. No automatic retries; inspect actor and cost.")
            break
    print("Actual charges: check Apify Console. UNKNOWN is not inactive.")

if __name__ == "__main__":
    main()
