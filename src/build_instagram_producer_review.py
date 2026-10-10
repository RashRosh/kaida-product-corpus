"""Build an offline actionable review list from existing candidate/activity files.

Never calls Apify. All original files stay unchanged.
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/extracted"
CANDIDATES = DATA / "instagram_seller_candidates.csv"
ACTIVITY = DATA / "instagram_activity_review.csv"
OUTPUT = DATA / "instagram_producer_review.csv"
FOOD = re.compile(r"полуфаб|пельмен|манты|вареник|сырник|творог|сыровар|торт|кондитер|пекар|выпеч|десерт|сладост|мяс|колбас|деликатес|ферм|food|bakery|sweet|cake|tort|vkus|kuhnya|domash|lepit|nan|pirog|пирог|еда|питан", re.I)
EXCLUDE = re.compile(r"парфюм|parfum|mebel|мебел|авто|такси|салон|ремонт", re.I)
FIELDS = ["username", "instagram_url", "business_name", "biography", "category",
          "phones", "whatsapp_urls", "other_urls", "city_status", "last_post_at",
          "activity_status", "review_priority", "producer_status", "delivery_almaty",
          "review_status", "source_files"]

def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def main():
    if not CANDIDATES.exists() or not ACTIVITY.exists():
        raise SystemExit("Missing local candidates or activity CSV")
    activity = {r["username"].strip().lower(): r for r in read(ACTIVITY)}
    output = []
    for row in read(CANDIDATES):
        user = row["username"].strip().lower()
        a = activity.get(user, {})
        text = " ".join(str(row.get(k) or "") for k in ("username", "business_name", "biography", "category"))
        excluded = bool(EXCLUDE.search(text))
        related = bool(FOOD.search(text))
        active = a.get("activity_status") == "ACTIVE_180D"
        if excluded:
            priority = "EXCLUDE_LIKELY_REVIEW"
        elif active and related:
            priority = "HIGH_REVIEW"
        elif active:
            priority = "MEDIUM_REVIEW"
        else:
            priority = "LOW_REVIEW"
        output.append({
            "username": user,
            "instagram_url": row.get("instagram_url") or f"https://www.instagram.com/{user}/",
            "business_name": row.get("business_name", ""),
            "biography": row.get("biography", ""),
            "category": row.get("category", ""),
            "phones": row.get("phones", ""),
            "whatsapp_urls": row.get("whatsapp_urls", ""),
            "other_urls": row.get("other_urls", ""),
            "city_status": row.get("city_status", ""),
            "last_post_at": a.get("last_post_at", ""),
            "activity_status": a.get("activity_status") or "NOT_CHECKED",
            "review_priority": priority,
            "producer_status": "UNVERIFIED",
            "delivery_almaty": "UNVERIFIED",
            "review_status": "PENDING",
            "source_files": row.get("source_files", "")
        })
    order = {"HIGH_REVIEW": 0, "MEDIUM_REVIEW": 1, "LOW_REVIEW": 2, "EXCLUDE_LIKELY_REVIEW": 3}
    output.sort(key=lambda r: (order[r["review_priority"]], r["username"]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(output)
    from collections import Counter
    print("Profiles:", len(output))
    print("Activity:", dict(Counter(r["activity_status"] for r in output)))
    print("Review queues:", dict(Counter(r["review_priority"] for r in output)))
    print("Saved:", OUTPUT)
    print("Priority is only a sorting heuristic; nobody was marked as a confirmed producer.")

if __name__ == "__main__":
    main()
