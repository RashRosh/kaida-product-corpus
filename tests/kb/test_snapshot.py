import pytest

from kb.snapshot import latest_observations, validate_observation_schema


def observation(observed_at: str, price: str) -> dict[str, str]:
    return {
        "source": "2gis",
        "branch_id": "1",
        "product_id": "2",
        "observed_at": observed_at,
        "raw_title": "Молоко",
        "raw_description": "",
        "categories": "Молочная продукция",
        "price": price,
        "currency": "KZT",
        "source_code": "manual",
        "product_type": "raw_product",
        "catalog_updated_at": "",
    }


def test_latest_snapshot_uses_timestamp_not_input_position():
    rows = [
        observation("2026-10-03T00:00:00+00:00", "200"),
        observation("2026-10-02T00:00:00+00:00", "100"),
    ]
    assert latest_observations(rows)[0]["price"] == "200"


def test_latest_snapshot_uses_last_row_for_timestamp_tie():
    rows = [
        observation("2026-10-03T00:00:00+00:00", "200"),
        observation("2026-10-03T00:00:00+00:00", "250"),
    ]
    assert latest_observations(rows)[0]["price"] == "250"


def test_schema_validation_rejects_missing_columns():
    with pytest.raises(ValueError, match="missing columns"):
        validate_observation_schema(["branch_id", "product_id"])
