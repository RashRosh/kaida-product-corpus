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
PROCESS_TERMS = {
    "варено-копченый": re.compile(r"\bвар[её]но[- ]копч[её]н\w*", re.IGNORECASE),
    "замороженный": re.compile(r"\b(?:свежеморожен|заморож)\w*", re.IGNORECASE),
    "копченый": re.compile(r"\bкопч[её]н\w*", re.IGNORECASE),
    "слабосоленый": re.compile(r"\bслабо[- ]?сол[её]н\w*", re.IGNORECASE),
    "соленый": re.compile(r"\bсол[её]н\w*", re.IGNORECASE),
    "охлажденный": re.compile(r"\bохлажд[её]н\w*", re.IGNORECASE),
}


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

    processes = [
        name for name, pattern in PROCESS_TERMS.items() if pattern.search(text)
    ]
    if "варено-копченый" in processes and "копченый" in processes:
        processes.remove("копченый")
    if "слабосоленый" in processes and "соленый" in processes:
        processes.remove("соленый")
    return {
        "measurements": measurements,
        "percentages": [number(match.group(1)) for match in PERCENT_RE.finditer(text)],
        "calibres": [
            f"{match.group('first')}/{match.group('second')}"
            for match in CALIBRE_RE.finditer(text)
        ],
        "process": processes,
    }
