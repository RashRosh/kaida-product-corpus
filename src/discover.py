import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

from scrapling.fetchers import Fetcher


ROOT = Path(__file__).resolve().parents[1]
SEARCHES_FILE = ROOT / "input" / "searches.csv"
FIRMS_FILE = ROOT / "input" / "firms.csv"
COLLECT_SCRIPT = ROOT / "src" / "collect.py"

FIRM_RE = re.compile(r"/firm/(\d+)")
MAX_PAGES_PER_QUERY = 200
REQUEST_DELAY_SECONDS = 0.2


def load_csv(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_firms(rows):
    with FIRMS_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["city", "seller_name", "url"])
        writer.writeheader()
        writer.writerows(rows)


def branch_id_from_url(url: str):
    match = FIRM_RE.search(url or "")
    return match.group(1) if match else None


def search_url(city: str, query: str, page_number: int):
    encoded_query = quote(query, safe="")
    base = f"https://2gis.kz/{city}/search/{encoded_query}"
    if page_number == 1:
        return base
    return f"{base}/page/{page_number}"


def extract_branch_ids(page):
    hrefs = [str(x) for x in page.css("a::attr(href)").getall()]
    ids = []
    seen = set()

    for href in hrefs:
        match = FIRM_RE.search(href)
        if not match:
            continue
        branch_id = match.group(1)
        if branch_id in seen:
            continue
        seen.add(branch_id)
        ids.append(branch_id)

    return ids, hrefs


def discover_query(city: str, query: str):
    found = []
    seen = set()
    previous_page_ids = None

    print(f"\nDISCOVER: {city} / {query}")

    for page_number in range(1, MAX_PAGES_PER_QUERY + 1):
        url = search_url(city, query, page_number)
        page = Fetcher.get(url, timeout=30)

        if page.status != 200:
            print(f"  page {page_number}: HTTP {page.status}, stop")
            break

        page_ids, hrefs = extract_branch_ids(page)
        print(f"  page {page_number}: {len(page_ids)} branch ids")

        if not page_ids:
            break

        page_signature = tuple(page_ids)
        if page_signature == previous_page_ids:
            print("  repeated page detected, stop")
            break
        previous_page_ids = page_signature

        for branch_id in page_ids:
            if branch_id not in seen:
                seen.add(branch_id)
                found.append(branch_id)

        next_fragment = f"/page/{page_number + 1}"
        has_next = any(next_fragment in href for href in hrefs)
        if not has_next:
            break

        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"  total unique for query: {len(found)}")
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Update firms.csv but do not run collect.py afterwards.",
    )
    args = parser.parse_args()

    searches = load_csv(SEARCHES_FILE)
    firms = load_csv(FIRMS_FILE)

    if not searches:
        raise SystemExit(f"No searches found in {SEARCHES_FILE}")

    existing_ids = {
        branch_id
        for branch_id in (branch_id_from_url(row.get("url", "")) for row in firms)
        if branch_id
    }

    newly_added = 0

    for row in searches:
        city = (row.get("city") or "").strip()
        query = (row.get("query") or "").strip()

        if not city or not query:
            continue

        for branch_id in discover_query(city, query):
            if branch_id in existing_ids:
                continue

            firms.append(
                {
                    "city": city,
                    "seller_name": "UNKNOWN",
                    "url": f"https://2gis.kz/{city}/firm/{branch_id}",
                }
            )
            existing_ids.add(branch_id)
            newly_added += 1

    write_firms(firms)

    print("\nDISCOVERY FINISHED")
    print(f"New firms: {newly_added}")
    print(f"Total firms: {len(existing_ids)}")
    print(f"Saved: {FIRMS_FILE}")

    if args.discover_only:
        return

    print("\nSTARTING PRODUCT COLLECTION\n")
    completed = subprocess.run([sys.executable, str(COLLECT_SCRIPT)])
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
