"""Small opt-in pilot: discover public Instagram profile links in search results.

No Instagram requests, logins, bypasses, private account access or outreach.
Candidates are NOT confirmed sellers and are never imported into KAIDA.
"""
import argparse
import csv
import html
import re
import time
from pathlib import Path
from urllib.parse import quote_plus, unquote

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "extracted" / "instagram_candidates.csv"
TERMS = (
    "домашняя выпечка Алматы",
    "торты на заказ Алматы",
    "домашние полуфабрикаты Алматы",
    "домашние пельмени Алматы",
    "домашние соленья Алматы",
    "домашний сыр Алматы",
    "копчености домашние Алматы",
    "домашние десерты Алматы",
)
INSTAGRAM_RE = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9._]{1,30})",
    flags=re.IGNORECASE,
)
RESERVED = {
    "p", "reel", "reels", "stories", "explore", "accounts", "direct",
    "about", "developer", "privacy", "legal", "challenge", "graphql",
    "api", "tags", "locations", "tv",
}
FIELDNAMES = (
    "username", "profile_url", "discovery_query", "source_url",
    "city_status", "seller_status", "review_status",
)


def extract_usernames(document: str) -> list[str]:
    # SERPs commonly contain escaped links, HTML entities and encoded URLs.
    normalized = html.unescape(document).replace("\\/", "/")
    normalized = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda match: chr(int(match.group(1), 16)),
        normalized,
    )
    for _ in range(2):
        normalized = unquote(normalized)
    found = set()
    for match in INSTAGRAM_RE.finditer(normalized):
        name = match.group(1).rstrip(".").lower()
        if name not in RESERVED and not name.startswith("."):
            found.add(name)
    return sorted(found)


def search_url(term: str) -> str:
    return "https://www.bing.com/search?q=" + quote_plus(
        'site:instagram.com/ "' + term + '"'
    )


def read_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["username"].lower(): row
            for row in csv.DictReader(handle)
            if row.get("username")
        }


def collect(terms: list[str], output: Path, delay: float) -> tuple[int, int]:
    from scrapling.fetchers import Fetcher

    rows = read_existing(output)
    before = len(rows)
    for index, term in enumerate(terms):
        url = search_url(term)
        print(f"[{index + 1}/{len(terms)}] {term}")
        try:
            response = Fetcher.get(url, timeout=30)
        except Exception as exc:
            print(f"  fetch error: {type(exc).__name__}: {exc}")
            break
        if response.status in (401, 403, 429):
            print(f"  HTTP {response.status}: access limited; stopping")
            break
        if response.status != 200:
            print(f"  HTTP {response.status}: skipped")
            continue
        body = response.body.decode("utf-8", errors="replace")
        if any(token in body.lower() for token in ("unusual traffic", "captcha", "verify you are human")):
            print("  challenge detected: stopping")
            break
        matches = extract_usernames(body)
        print(f"  profile candidates: {len(matches)}")
        for username in matches:
            if username not in rows:
                rows[username] = {
                    "username": username,
                    "profile_url": f"https://www.instagram.com/{username}/",
                    "discovery_query": term,
                    "source_url": url,
                    "city_status": "UNVERIFIED",
                    "seller_status": "UNVERIFIED",
                    "review_status": "PENDING",
                }
        if index + 1 < len(terms):
            time.sleep(delay)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows[key] for key in sorted(rows))
    return len(rows) - before, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Actually request public search-result pages")
    parser.add_argument("--limit", type=int, default=3, help="Number of search queries (1-8)")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between requests (min 3)")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not 1 <= args.limit <= len(TERMS):
        parser.error(f"--limit must be 1..{len(TERMS)}")
    if args.delay < 3:
        parser.error("--delay must be at least 3 seconds")
    terms = list(TERMS[: args.limit])
    for term in terms:
        print(search_url(term))
    if not args.run:
        print("DRY RUN: no network calls. Add --run for a bounded pilot.")
        return
    added, total = collect(terms, args.output, args.delay)
    print(f"Added: {added}; total candidates: {total}; file: {args.output}")
    print("All accounts remain UNVERIFIED; no Instagram pages were requested.")


if __name__ == "__main__":
    main()
