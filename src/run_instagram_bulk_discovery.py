"""Batch Instagram hashtag discovery. No 2GIS; local data only."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCOVER = ROOT / "src/discover_instagram_hashtag.py"
IMPORT = ROOT / "src/import_instagram_hashtag_authors.py"
LEDGER = ROOT / "data/extracted/instagram_hashtag_ledger.json"
ACTOR = "apify~instagram-hashtag-scraper"
GROUPS = [
    "алматытағам,алматыжеткізу,үйтағамдары,үйтамақтары,алматыет,қазыалматы,шұжықалматы,бауырсақалматы",
    "корейскиесалатыалматы,салатыалматы,соленьяалматы,домашниесоленья,медалматы,орехиалматы,сухофруктыалматы,специиалматы",
    "готоваяедаалматы,доставкапродуктовалматы,продуктыподомашнему,халяльалматы,халалпродуктыалматы,фермерскаялавкаалматы,кулинарияалматы,кондитерскиеназаказалматы",
]
CAP = 0.50

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true")
    p.add_argument("--posts-per-tag", type=int, default=100)
    a = p.parse_args()
    if not 1 <= a.posts_per_tag <= 100:
        p.error("--posts-per-tag must be 1..100")
    print("Batches:", len(GROUPS), "Maximum total charge USD:", round(len(GROUPS)*CAP, 2), flush=True)
    if not a.run:
        print("DRY RUN. No paid requests.", flush=True)
    entries = json.loads(LEDGER.read_text(encoding="utf-8-sig")) if LEDGER.exists() else []
    used = {tag for entry in entries if entry.get("actor") == ACTOR
            for tag in entry.get("hashtags", [])}
    for i, group in enumerate(GROUPS, 1):
        requested = group.split(",")
        fresh = [tag for tag in requested if tag not in used]
        if not fresh:
            print("Batch", i, "skipped: all hashtags already in local ledger", flush=True)
            continue
        tags = ",".join(fresh)
        print("Batch", i, "of", len(GROUPS), "new hashtags:", tags,
              "skipped previously used:", len(requested)-len(fresh), "cap USD:", CAP, flush=True)
        cmd = [sys.executable, str(DISCOVER), "--hashtag", tags,
               "--limit", str(a.posts_per_tag), "--max-usd", str(CAP)]
        if a.run:
            cmd.append("--run")
        res = subprocess.run(cmd, cwd=ROOT)
        if res.returncode:
            sys.exit("STOP: discovery failure, no further paid requests")
        if a.run:
            used.update(fresh)
            res = subprocess.run([sys.executable, str(IMPORT)], cwd=ROOT)
            if res.returncode:
                sys.exit("STOP: import failure, local raw file preserved")
    print("Finished. All new accounts are unverified candidates.", flush=True)

if __name__ == "__main__":
    main()
