"""Measurement extraction refactored from the original corpus probe."""

from __future__ import annotations

import re
from typing import Any


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
    (?P<first>\d+(?:[.,]\d+)?)\s*
    (?:[-–—]\s*(?P<second>\d+(?:[.,]\d+)?)\s*)?
    (?P<unit>кг|kg|гр|г|g|мл|ml|л|l|шт)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
PERCENT_RE = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*%")
CALIBRE_RE = re.compile(
    r"(?<!\d)(?P<first>\d{1,3})\s*/\s*(?P<second>\d{1,3})(?!\d)"
    r"(?!\s*(?:г|гр|кг|g|kg|мл|ml|л|l)\b)",
    re.IGNORECASE,
)


def number(value: str) -> int | float:
    parsed = float(value.replace(",", "."))
    return int(parsed) if parsed.is_integer() else parsed


def extract_measurements(title: str | None) -> dict[str, Any]:
    text = title or ""
    measurements: list[dict[str, Any]] = []
    for match in MEASURE_RE.finditer(text):
        first = number(match.group("first"))
        second = match.group("second")
        item: dict[str, Any] = {
            "kind": "range" if second else "value",
            "unit": UNIT_MAP[match.group("unit").lower()],
            "raw": match.group(0),
        }
        if second:
            item.update({"min": first, "max": number(second)})
        else:
            item["value"] = first
        measurements.append(item)

    return {
        "measurements": measurements,
        "percentages": [number(match.group(1)) for match in PERCENT_RE.finditer(text)],
        "calibres": [
            f"{match.group('first')}/{match.group('second')}"
            for match in CALIBRE_RE.finditer(text)
        ],
    }
