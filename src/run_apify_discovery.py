"""Run a small Apify Instagram Profile Finder batch with a hard USD cap.

Requires APIFY_TOKEN in local environment. No Instagram credentials.
Default is dry-run; execution requires --run.
"""
import argparse
import json
import os
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

ACTOR = "instagram-scraper~instagram-profile-finder"
ROOT = Path(__file__).resolve().parents[1]
QUERIES = ROOT / "input" / "instagram_queries.txt"
RAW = ROOT / "data" / "raw"


def payload(queries):
    return {
        "queries": queries,
        "emailDiscoveryMode": False,
        "searchMode": "profiles",
        "queryMaxPages": 1,
        "searchCountry": "kz",
        "searchLanguage": "ru",
        "scrapeFacebookProfile": False,
        "skipPostCount": True,
        "skipLatestPosts": True,
        "skipRelatedProfiles": True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",action="store_true",help="Spend money and call Apify")
    p.add_argument("--max-usd",type=float,default=0.10)
    p.add_argument("--limit",type=int,default=2)
    args=p.parse_args()
    if not 0 < args.max_usd <= 0.50: p.error("Cap must be >0 and <= $0.50")
    if not 1 <= args.limit <= 10: p.error("Limit must be 1-10")
    if not QUERIES.exists(): p.error(f"Missing query list: {QUERIES}")
    qs=list(dict.fromkeys(q.strip() for q in QUERIES.read_text(encoding="utf-8-sig").splitlines() if q.strip() and not q.startswith("#")))[:args.limit]
    if not qs:p.error("No queries")
    data=payload(qs)
    print("Actor:", ACTOR, "Queries:",qs,"Cost ceiling:",args.max_usd)
    if not args.run:
        print(json.dumps(data,ensure_ascii=False,indent=2))
        print("DRY RUN. No paid request. Use --run to execute.")
        return
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
    print("Check actual charge in Apify Console.")
if __name__=="__main__":main()
