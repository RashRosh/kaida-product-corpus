import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

INPUT = ROOT / "data" / "extracted" / "observations.csv"
OUTPUT = ROOT / "data" / "extracted" / "measurement_probe.csv"


UNIT_MAP = {
    "г": "g",
    "гр": "g",
    "g": "g",
    "кг": "kg",
    "kg": "kg",
    "мл": "ml",
    "ml": "ml",
    "л": "l",
    "l": "l",
    "шт": "pcs",
}


MEASURE_RE = re.compile(
    r"""
    (?P<first>\d+(?:[.,]\d+)?)
    \s*
    (?:
        [-–—]
        \s*
        (?P<second>\d+(?:[.,]\d+)?)
        \s*
    )?
    (?P<unit>
        кг|kg|
        гр|г|g|
        мл|ml|
        л|l|
        шт
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


PERCENT_RE = re.compile(
    r"(?<!\d)(\d+(?:[.,]\d+)?)\s*%"
)


CALIBRE_RE = re.compile(
    r"""
    (?<!\d)
    (?P<first>\d{1,3})
    \s*/\s*
    (?P<second>\d{1,3})
    (?!\d)
    (?!\s*(?:г|гр|кг|g|kg|мл|ml|л|l)\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def number(value):
    return float(value.replace(",", "."))


def extract(title):
    measurements = []

    for match in MEASURE_RE.finditer(title):
        first = number(match.group("first"))
        second_raw = match.group("second")

        unit_raw = match.group("unit").lower()
        unit = UNIT_MAP[unit_raw]

        if second_raw:
            measurements.append(
                {
                    "kind": "range",
                    "min": first,
                    "max": number(second_raw),
                    "unit": unit,
                    "raw": match.group(0),
                }
            )
        else:
            measurements.append(
                {
                    "kind": "value",
                    "value": first,
                    "unit": unit,
                    "raw": match.group(0),
                }
            )

    percentages = [
        number(match.group(1))
        for match in PERCENT_RE.finditer(title)
    ]

    calibres = [
        f"{match.group('first')}/{match.group('second')}"
        for match in CALIBRE_RE.finditer(title)
    ]

    return measurements, percentages, calibres


with INPUT.open("r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))


output_rows = []

with_measurements = 0
with_percentages = 0
with_calibres = 0


for row in rows:
    title = row["raw_title"]

    measurements, percentages, calibres = extract(title)

    if measurements:
        with_measurements += 1

    if percentages:
        with_percentages += 1

    if calibres:
        with_calibres += 1

    output_rows.append(
        {
            "branch_id": row["branch_id"],
            "product_id": row["product_id"],
            "raw_title": title,
            "measurements": json.dumps(
                measurements,
                ensure_ascii=False,
            ),
            "percentages": json.dumps(
                percentages,
                ensure_ascii=False,
            ),
            "calibres": json.dumps(
                calibres,
                ensure_ascii=False,
            ),
        }
    )


with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "branch_id",
            "product_id",
            "raw_title",
            "measurements",
            "percentages",
            "calibres",
        ],
    )

    writer.writeheader()
    writer.writerows(output_rows)


print(f"PRODUCT ROWS: {len(rows)}")
print(f"WITH EXPLICIT MEASUREMENTS: {with_measurements}")
print(f"WITH PERCENTAGES: {with_percentages}")
print(f"WITH CALIBRES: {with_calibres}")
print(f"SAVED: {OUTPUT}")