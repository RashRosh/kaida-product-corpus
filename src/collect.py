import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from scrapling.fetchers import Fetcher


ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = ROOT / "input" / "firms.csv"
RAW_DIR = ROOT / "data" / "raw"
EXTRACTED_DIR = ROOT / "data" / "extracted"

PRODUCTS_FILE = EXTRACTED_DIR / "products.csv"
OBSERVATIONS_FILE = EXTRACTED_DIR / "observations.csv"

ENDPOINT = "https://market-backend.api.2gis.ru/5.0/product/items_by_branch"
PAGE_SIZE = 50

RAW_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_branch_id(url: str) -> str:
    if "/firm/" not in url:
        raise ValueError(f"Cannot find firm id in URL: {url}")

    return url.split("/firm/")[1].split("/")[0]


def load_csv(path):
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fetch_catalog(branch_id: str, current_run_id: str):
    page_number = 1
    all_items = []
    updated_at = None
    total = None

    while True:
        print(f"Fetching branch {branch_id}, page {page_number}...")

        response = Fetcher.get(
            ENDPOINT,
            params={
                "branch_id": branch_id,
                "locale": "ru_KZ",
                "page": page_number,
                "page_size": PAGE_SIZE,
            },
            timeout=30,
        )

        if response.status != 200:
            raise RuntimeError(
                f"HTTP {response.status} for branch {branch_id}, page {page_number}"
            )

        data = response.json()

        raw_file = (
            RAW_DIR
            / f"{branch_id}_{current_run_id}_page_{page_number}.json"
        )

        raw_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = data.get("result", {})
        items = result.get("items", [])

        if total is None:
            total = result.get("total", 0)
            updated_at = result.get("updated_at")

        print(f"  received: {len(items)} / total: {total}")

        all_items.extend(items)

        if not items or len(all_items) >= total:
            break

        page_number += 1
        time.sleep(1)

    return all_items, updated_at


products = load_csv(PRODUCTS_FILE)
observations = load_csv(OBSERVATIONS_FILE)

product_index = {
    (row["branch_id"], row["product_id"]): row
    for row in products
}

latest_state = {}

for row in observations:
    key = (row["branch_id"], row["product_id"])

    latest_state[key] = (
        row["raw_title"],
        row["raw_description"],
        row["categories"],
        row["price"],
        row["currency"],
        row["source_code"],
        row["product_type"],
    )


with INPUT_FILE.open("r", encoding="utf-8-sig", newline="") as f:
    firms = list(csv.DictReader(f))


observed_at = now_utc()
current_run_id = run_id()

new_observations = 0
new_products = 0


for firm in firms:
    city = firm["city"].strip()
    seller_name = firm["seller_name"].strip()
    source_url = firm["url"].strip()

    branch_id = get_branch_id(source_url)

    try:
        items, catalog_updated_at = fetch_catalog(
            branch_id,
            current_run_id,
        )

        for item in items:
            product = item.get("product", {})
            offer = item.get("offer", {})

            product_id = str(product.get("id") or "")

            if not product_id:
                continue

            categories = product.get("categories", [])

            category_labels = [
                str(category.get("label"))
                for category in categories
                if category.get("label")
            ]

            categories_text = " | ".join(category_labels)

            raw_title = str(product.get("name") or "")
            raw_description = str(product.get("description") or "")
            price = str(offer.get("price") or "")
            currency = str(offer.get("currency") or "")
            source_code = str(
                (product.get("source") or {}).get("code") or ""
            )
            product_type = str(product.get("type") or "")

            key = (branch_id, product_id)

            if key not in product_index:
                product_row = {
                    "source": "2gis",
                    "branch_id": branch_id,
                    "city": city,
                    "seller_name": seller_name,
                    "source_url": source_url,
                    "product_id": product_id,
                    "first_seen_at": observed_at,
                    "last_seen_at": observed_at,
                }

                products.append(product_row)
                product_index[key] = product_row
                new_products += 1

            else:
                product_index[key]["last_seen_at"] = observed_at

            current_state = (
                raw_title,
                raw_description,
                categories_text,
                price,
                currency,
                source_code,
                product_type,
            )

            if latest_state.get(key) == current_state:
                continue

            observation = {
                "source": "2gis",
                "branch_id": branch_id,
                "product_id": product_id,
                "observed_at": observed_at,
                "raw_title": raw_title,
                "raw_description": raw_description,
                "categories": categories_text,
                "price": price,
                "currency": currency,
                "source_code": source_code,
                "product_type": product_type,
                "catalog_updated_at": catalog_updated_at or "",
            }

            observations.append(observation)
            latest_state[key] = current_state
            new_observations += 1

        print(f"Collected {len(items)} current products from {branch_id}")

    except Exception as exc:
        print(f"FAILED {branch_id}: {exc}")


write_csv(
    PRODUCTS_FILE,
    [
        "source",
        "branch_id",
        "city",
        "seller_name",
        "source_url",
        "product_id",
        "first_seen_at",
        "last_seen_at",
    ],
    products,
)

write_csv(
    OBSERVATIONS_FILE,
    [
        "source",
        "branch_id",
        "product_id",
        "observed_at",
        "raw_title",
        "raw_description",
        "categories",
        "price",
        "currency",
        "source_code",
        "product_type",
        "catalog_updated_at",
    ],
    observations,
)


print()
print("Finished.")
print(f"Current products: {len(products)}")
print(f"New products: {new_products}")
print(f"New observations: {new_observations}")
print(f"All observations: {len(observations)}")