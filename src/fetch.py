import csv
from pathlib import Path

from scrapling.fetchers import Fetcher


ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT / "input" / "firms.csv"
RAW_DIR = ROOT / "data" / "raw"

RAW_DIR.mkdir(parents=True, exist_ok=True)


with INPUT_FILE.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    row = next(reader)

url = row["url"].strip()

if "/firm/" in url:
    firm_id = url.split("/firm/")[1].split("/")[0]
else:
    firm_id = "unknown"

print(f"Fetching firm {firm_id}...")

page = Fetcher.get(
    url,
    timeout=30,
)

print(f"HTTP status: {page.status}")
print(f"Received bytes: {len(page.body)}")

output_file = RAW_DIR / f"{firm_id}.html"
output_file.write_bytes(page.body)

print(f"Saved to: {output_file}")