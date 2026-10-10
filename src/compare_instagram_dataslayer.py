"""Compare Data Slayer Instagram keyword search against local candidates.

Offline by default. No Instagram credentials. Never commit raw responses.
A paid call requires --run, --max-usd, and APIFY_TOKEN.
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

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "data/extracted/instagram_seller_candidates.csv"
RAW = ROOT / "data/raw"
LEDGER = ROOT / "data/extracted/instagram_dataslayer_ledger.json"
ACTOR = "data-slayer~instagram-search-users"
USERNAME = re.compile(r"^[a-z0-9._]{1,30}$")


def users_from_csv():
    if not CANDIDATES.exists():
        raise FileNotFoundError("Local candidate CSV missing: " + str(CANDIDATES))
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as handle:
        return {(r.get("username") or "").strip().lower().lstrip("@")
                for r in csv.DictReader(handle) if r.get("username")}


def usernames(items):
    return {str(x.get("username") or "").strip().lower().lstrip("@")
            for x in items if isinstance(x, dict)
            and USERNAME.fullmatch(str(x.get("username") or "").strip().lower().lstrip("@"))}


def read_ledger():
    if not LEDGER.exists():
        return []
    result = json.loads(LEDGER.read_text(encoding="utf-8"))
    if not isinstance(result, list):
        raise ValueError("Expected JSON list for experiment ledger")
    return result


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def report(items, existing, query):
    all_users = usernames(items)
    fresh = sorted(all_users - existing)
    print("Query:", query)
    print("Returned rows:", len(items), "valid unique usernames:", len(all_users))
    print("Overlap with local corpus:", len(all_users & existing))
    print("New unique usernames:", len(fresh))
    print("New accounts (not yet verified as sellers):", ", ".join(fresh))
    return all_users, fresh


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--query", default="пельмени Алматы")
    p.add_argument("--max-items", type=int, default=20)
    p.add_argument("--input-json", type=Path, help="Offline analysis of an existing actor export; free")
    p.add_argument("--run", action="store_true", help="Authorize a paid Apify call")
    p.add_argument("--max-usd", type=float, help="Hard per-run cap; mandatory for --run")
    p.add_argument("--allow-repeat", action="store_true")
    args = p.parse_args()
    if not 1 <= args.max_items <= 50:
        p.error("--max-items must be 1..50")
    if args.run and args.input_json:
        p.error("--run and --input-json are mutually exclusive")
    existing = users_from_csv()
    ledger = read_ledger()
    query_key = " ".join(args.query.casefold().split())
    payload = {"query": args.query, "mode": "basic", "maxItems": args.max_items}
    print("Actor:", ACTOR, "input:", json.dumps(payload, ensure_ascii=False))
    print("Existing corpus:", len(existing))
    if args.input_json:
        items = json.loads(args.input_json.read_text(encoding="utf-8-sig"))
        if not isinstance(items, list):
            p.error("Input must be a JSON array")
        report(items, existing, args.query)
        return
    if not args.run:
        print("DRY RUN. No paid request.")
        print("Search fee varies: check the Actor live pricing before --run.")
        return
    if args.max_usd is None or not 0.01 <= args.max_usd <= 0.05:
        p.error("--run requires --max-usd between 0.01 and 0.05")
    if abs(round(args.max_usd * 100) / 100 - args.max_usd) > 1e-6:
        p.error("--max-usd must use whole cents")
    if not args.allow_repeat and any(
        x.get("query_key") == query_key and x.get("mode") == "basic" for x in ledger
    ):
        p.error("Repeat paid query blocked; use --allow-repeat only intentionally.")
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        p.error("APIFY_TOKEN not set")
    endpoint = ("https://api.apify.com/v2/acts/" + ACTOR
                + "/run-sync-get-dataset-items?"
                + urlencode({"maxTotalChargeUsd": f"{args.max_usd:.2f}",
                             "timeout": 120, "restartOnError": "false"}))
    req = Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                  headers={"Authorization": "Bearer " + token,
                           "Content-Type": "application/json",
                           "Accept": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=200) as response:
            items = json.load(response)
    except HTTPError as e:
        sys.exit(f"Apify HTTP {e.code}; inspect Console before retrying")
    except Exception as e:
        sys.exit(f"Unknown run outcome ({type(e).__name__}); do not retry blindly")
    if not isinstance(items, list):
        sys.exit("Unexpected response; do not retry blindly")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    raw_path = RAW / ("apify_dataslayer_" + stamp + ".json")
    save(raw_path, items)
    unique, fresh = report(items, existing, args.query)
    ledger.append({"query": args.query, "query_key": query_key, "mode": "basic",
                   "requested_max_items": args.max_items, "returned": len(items),
                   "unique": len(unique), "overlap": len(unique & existing),
                   "new_unique": len(fresh), "file": raw_path.name,
                   "max_usd": args.max_usd, "actual_usd": None,
                   "recorded_at": datetime.now(timezone.utc).isoformat()})
    save(LEDGER, ledger)
    print("Saved raw locally. No automatic import or activity-check charges.")
    print("Actual charges need confirmation in Apify Console.")


if __name__ == "__main__":
    main()
