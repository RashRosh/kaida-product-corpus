"""Bounded Instagrapi seller-search experiment, never imports into KAIDA.

Requires explicit --run and Instagram credentials supplied via environment.
Unofficial API: may trigger security checkpoints or account restrictions.
"""
import argparse
import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "extracted" / "instagrapi_candidates.csv"
QUERIES = ("торты алматы", "домашняя выпечка алматы", "пельмени алматы")
FIELDS = ("username", "profile_url", "full_name", "biography", "query", "city_status", "seller_status")


def user_record(user, query):
    name = str(getattr(user, "username", "") or "").strip().lower()
    if not name:
        return None
    return {
        "username": name,
        "profile_url": f"https://www.instagram.com/{name}/",
        "full_name": str(getattr(user, "full_name", "") or ""),
        "biography": str(getattr(user, "biography", "") or ""),
        "query": query,
        "city_status": "UNVERIFIED",
        "seller_status": "UNVERIFIED",
    }


def run_search(client, queries, amount):
    records = {}
    for query in queries:
        print(f"Search: {query}")
        try:
            users = client.search_users(query, amount=amount)
        except Exception as exc:
            print(f"Search failed ({type(exc).__name__}): {exc}")
            print("Stopping. Do not retry repeatedly after a challenge or block.")
            break
        for user in users:
            record = user_record(user, query)
            if record:
                records.setdefault(record["username"], record)
        print(f"  returned {len(users)} results; unique candidates {len(records)}")
    return list(records.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Opt in to logging in and querying Instagram")
    parser.add_argument("--amount", type=int, default=5, help="Max results per query, 1..10")
    args = parser.parse_args()
    if not 1 <= args.amount <= 10:
        parser.error("--amount must be 1..10")
    print("Queries:", ", ".join(QUERIES))
    if not args.run:
        print("DRY RUN: No login and no Instagram requests.")
        return
    username = os.environ.get("IG_USERNAME", "").strip()
    password = os.environ.get("IG_PASSWORD", "")
    if not username or not password:
        parser.error("Set IG_USERNAME and IG_PASSWORD locally; never commit credentials.")
    try:
        from instagrapi import Client
    except ImportError:
        parser.error("Install optional dependency: python -m pip install instagrapi")
    client = Client()
    try:
        client.login(username, password)
    except Exception as exc:
        print(f"Login failed ({type(exc).__name__}): {exc}")
        print("Stop here if Instagram requires verification; do not attempt to bypass it.")
        return
    rows = run_search(client, QUERIES, args.amount)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} unverified candidates to {OUTPUT}")


if __name__ == "__main__":
    main()
