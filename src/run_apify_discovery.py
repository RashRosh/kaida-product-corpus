"""Run a small Apify Instagram Profile Finder batch with a hard USD cap.

Requires APIFY_TOKEN in local environment. No Instagram credentials.
Default is dry-run; execution requires --run.
"""
import argparse
import csv
import json
import os
import sys
import subprocess
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

ACTOR = "instagram-scraper~instagram-profile-finder"
ROOT = Path(__file__).resolve().parents[1]
QUERIES = ROOT / "input" / "instagram_queries.txt"
RAW = ROOT / "data" / "raw"
LEDGER = ROOT / "data" / "extracted" / "instagram_search_ledger.json"


def payload(queries, mode="profiles", time_range=None):
    return {
        "queries": queries,
        "emailDiscoveryMode": False,
        "searchMode": mode,
        "queryMaxPages": 1,
        "searchCountry": "kz",
        "searchLanguage": "ru",
        "scrapeFacebookProfile": False,
        "skipPostCount": True,
        "skipLatestPosts": True,
        "skipRelatedProfiles": True,
    } if not time_range else {
        "queries": queries, "emailDiscoveryMode": False,
        "searchMode": mode, "searchTimeRange": time_range,
        "queryMaxPages": 1, "searchCountry": "kz", "searchLanguage": "ru",
        "scrapeFacebookProfile": False, "skipPostCount": True,
        "skipLatestPosts": True, "skipRelatedProfiles": True,
    }


def fingerprint(queries, mode="profiles", time_range=None):
    canonical = json.dumps(payload(queries, mode, time_range), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_ledger():
    if not LEDGER.exists():
        return []
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Search ledger must be a JSON array")
    return data


def write_ledger(entries):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    temp = LEDGER.with_suffix(".tmp")
    temp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(LEDGER)


def candidate_usernames():
    """Read only usernames; local seller data never enters the Git repository."""
    path = ROOT / "data" / "extracted" / "instagram_seller_candidates.csv"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {(row.get("username") or "").strip().lower()
                for row in csv.DictReader(fh) if row.get("username")}


def query_key(query):
    return " ".join(query.casefold().split())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",action="store_true",help="Spend money and call Apify")
    p.add_argument("--max-usd",type=float,default=0.10)
    p.add_argument("--limit",type=int,default=2)
    p.add_argument("--queries-file",type=Path,default=QUERIES,help="Search terms file, relative to repository root")
    p.add_argument("--allow-repeat", action="store_true", help="Explicitly allow previously recorded query batch")
    p.add_argument("--mode", choices=("profiles", "posts_and_reels"), default="profiles")
    p.add_argument("--time-range", choices=("day","week","month","year"), default=None)
    args=p.parse_args()
    if not 0 < args.max_usd <= 0.50: p.error("Cap must be >0 and <= $0.50")
    if not 1 <= args.limit <= 10: p.error("Limit must be 1-10")
    queries_path = args.queries_file if args.queries_file.is_absolute() else ROOT / args.queries_file
    if not queries_path.exists(): p.error(f"Missing query list: {queries_path}")
    qs=list(dict.fromkeys(q.strip() for q in queries_path.read_text(encoding="utf-8-sig").splitlines() if q.strip() and not q.strip().startswith("#")))[:args.limit]
    if not qs:p.error("No queries")
    data=payload(qs, args.mode, args.time_range)
    stamp_id=fingerprint(qs, args.mode, args.time_range)
    ledger=read_ledger()
    already=any(e.get("fingerprint")==stamp_id for e in ledger)
    # Prior runs may have contained several queries. Conservatively block every
    # previously paid query even if it appears in a different batch or order.
    used = {query_key(q) for entry in ledger for q in entry.get("queries", [])
            if isinstance(q, str)}
    repeats = [q for q in qs if query_key(q) in used]
    if repeats:
        print("WARNING: Previously executed search phrases:", repeats)
    if already:
        print("WARNING: This exact query batch and settings were already recorded.")
    print("Query file:",queries_path)
    print("Actor:", ACTOR, "Queries:",qs,"Mode:",args.mode,"Time range:",args.time_range or "any","Cost ceiling:",args.max_usd)
    if not args.run:
        print(json.dumps(data,ensure_ascii=False,indent=2))
        print("DRY RUN. No paid request. Use --run to execute.")
        return
    if (already or repeats) and not args.allow_repeat:
        p.error("Paid search blocked: one or more phrases were already used. "
                "Change queries or explicitly use --allow-repeat.")
    before_users = candidate_usernames()
    token=os.environ.get("APIFY_TOKEN","").strip()
    if not token:p.error("Missing APIFY_TOKEN environment variable")
    # Sync endpoint returns items, or 408 after 300s. Never automatically retry.
    url=("https://api.apify.com/v2/acts/"+ACTOR+"/run-sync-get-dataset-items?"
         +urlencode({"maxTotalChargeUsd":f"{args.max_usd:.2f}","timeout":120,"memory":256,"restartOnError":"false"}))
    request=Request(url,data=json.dumps(data,ensure_ascii=False).encode("utf-8"),
        headers={"Authorization":"Bearer "+token,"Content-Type":"application/json","Accept":"application/json"},
        method="POST")
    try:
        with urlopen(request,timeout=200) as response:
            items=json.load(response)
    except HTTPError as exc:
        print(f"Apify HTTP {exc.code}. Inspect Apify Console for run status and charges; DO NOT retry automatically.",file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Request outcome unknown: {type(exc).__name__}. Inspect Apify Console before any retry.",file=sys.stderr)
        sys.exit(1)
    if not isinstance(items,list):p.error("Unexpected output: not an array")
    RAW.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest=RAW/f"apify_instagram_{stamp}.json"
    dest.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Saved {len(items)} items to {dest}.")
    ledger.append({"fingerprint": stamp_id, "queries":qs,
                   "mode":args.mode,"search_time_range":args.time_range,
                   "file":dest.name,"items":len(items),
                   "recorded_at":datetime.now(timezone.utc).isoformat(),
                   "max_usd":args.max_usd,
                   "actual_usd":None,
                   "unique_before":len(before_users),
                   "new_unique":None,
                   "unique_after":None})
    write_ledger(ledger)
    print("Search recorded. Actual USD charge is unknown until verified in Apify Console.")
    if args.mode=="posts_and_reels":
        print("NOTICE: searchTimeRange limits search results, NOT confirmed Instagram publication dates.")
        print("For date validation, export searchPostResults from the Apify run; default dataset alone is insufficient.")
    # Rebuild from ALL historical exports, not just the latest run.
    # Only do so after successfully persisting the raw dataset.
    exports = sorted(set(RAW.glob("dataset_instagram*.json")) | set(RAW.glob("apify_instagram_*.json")))
    if not exports:
        print("No import inputs found; original raw file is preserved.", file=sys.stderr)
        sys.exit(1)
    importer = ROOT / "src" / "import_apify_instagram.py"
    print(f"Rebuilding candidates from {len(exports)} saved exports...")
    try:
        subprocess.run([sys.executable, str(importer), *map(str, exports)], check=True, cwd=ROOT)
    except subprocess.CalledProcessError:
        print("Import failed. Raw JSON was saved; existing CSV may need rechecking.", file=sys.stderr)
        sys.exit(1)
    after_users = candidate_usernames()
    new_users = after_users - before_users
    ledger[-1]["unique_after"] = len(after_users)
    ledger[-1]["new_unique"] = len(new_users)
    write_ledger(ledger)
    print(f"New unique profiles: {len(new_users)}; total unique: {len(after_users)}")
    if len(qs) > 1:
        print("NOTE: New-profile yield belongs to this batch, not to any individual query.")
        print("Use --limit 1 for interpretable per-query experiments.")
    print("Check actual charge in Apify Console.")
if __name__=="__main__":main()
