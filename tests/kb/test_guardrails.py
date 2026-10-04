import json
from pathlib import Path

import pytest


@pytest.mark.parametrize("filename", ["positive_cases.json", "negative_cases.json"])
def test_regression_fixtures(resolver, root: Path, filename: str):
    cases = json.loads((root / "tests" / "kb" / "fixtures" / filename).read_text(encoding="utf-8"))
    for case in cases:
        result = resolver.resolve(case["raw_title"], case.get("categories", ""))
        expected = case["expected"]
        for field in (
            "canonical_product_id",
            "canonical_name",
            "mapping_status",
            "entity_class",
            "matched_rule_id",
        ):
            if field in expected:
                assert getattr(result, field) == expected[field], case["case_id"]
        assert result.canonical_product_id != expected.get("not_product_id"), case["case_id"]
        assert result.canonical_name != expected.get("not_canonical_name"), case["case_id"]
