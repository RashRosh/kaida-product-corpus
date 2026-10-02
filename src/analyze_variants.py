import csv
import re
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "data" / "extracted" / "observations.csv"


def normalize(text):
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


with FILE.open("r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))


titles = sorted({
    row["raw_title"].strip()
    for row in rows
    if row["raw_title"].strip()
})


pairs = []

for i, left in enumerate(titles):
    left_norm = normalize(left)

    for right in titles[i + 1:]:
        right_norm = normalize(right)

        if left_norm == right_norm:
            score = 1.0
        else:
            score = SequenceMatcher(
                None,
                left_norm,
                right_norm,
            ).ratio()

        if score >= 0.72:
            pairs.append((score, left, right))


pairs.sort(reverse=True)
OUTPUT = ROOT / "data" / "extracted" / "similar_pairs.csv"

with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "similarity",
            "left_title",
            "right_title",
            "decision",
        ],
    )

    writer.writeheader()

    for score, left, right in pairs:
        writer.writerow(
            {
                "similarity": f"{score:.4f}",
                "left_title": left,
                "right_title": right,
                "decision": "",
            }
        )

print(f"SAVED: {OUTPUT}")


print(f"UNIQUE TITLES: {len(titles)}")
print(f"SIMILAR PAIRS >= 0.72: {len(pairs)}")
print()

for score, left, right in pairs[:60]:
    print(f"{score:.2f}  {left}")
    print(f"      {right}")
    print()