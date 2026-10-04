"""Observation history validation and latest-state selection."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime


OBSERVATION_COLUMNS = [
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
]


def validate_observation_schema(fieldnames: Iterable[str] | None) -> None:
    actual = list(fieldnames or [])
    missing = [name for name in OBSERVATION_COLUMNS if name not in actual]
    if missing:
        raise ValueError(f"Observation input is missing columns: {', '.join(missing)}")


def timestamp_key(value: str, row_number: int) -> tuple[datetime, int]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid observed_at at data row {row_number}: {value!r}") from exc
    return parsed, row_number


def latest_observations(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    latest: dict[tuple[str, str], tuple[tuple[datetime, int], dict[str, str]]] = {}
    for row_number, source_row in enumerate(rows, start=2):
        row = dict(source_row)
        key = (row.get("branch_id", ""), row.get("product_id", ""))
        if not all(key):
            raise ValueError(f"Blank branch_id/product_id at data row {row_number}")
        order = timestamp_key(row.get("observed_at", ""), row_number)
        if key not in latest or order > latest[key][0]:
            latest[key] = (order, row)
    return [
        latest[key][1]
        for key in sorted(latest, key=lambda item: (item[0], item[1]))
    ]
