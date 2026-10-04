"""Regression fixtures and deterministic build-report helpers."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .resolver import Resolver


def run_regressions(resolver: Resolver, fixtures_dir: Path) -> dict[str, Any]:
    cases = []
    for filename, kind in (("positive_cases.json", "positive"), ("negative_cases.json", "negative")):
        path = fixtures_dir / filename
        loaded = json.loads(path.read_text(encoding="utf-8"))
        cases.extend((kind, item) for item in loaded)

    results = []
    for kind, case in cases:
        result = resolver.resolve(case["raw_title"], case.get("categories", ""))
        failures = []
        expected = case.get("expected", {})
        for key in (
            "canonical_product_id",
            "canonical_name",
            "mapping_status",
            "entity_class",
            "matched_rule_id",
        ):
            if key in expected and getattr(result, key) != expected[key]:
                failures.append(
                    f"{key}: expected {expected[key]!r}, got {getattr(result, key)!r}"
                )
        if expected.get("not_product_id") and result.canonical_product_id == expected["not_product_id"]:
            failures.append(f"must not map to {expected['not_product_id']}")
        if expected.get("not_canonical_name") and result.canonical_name == expected["not_canonical_name"]:
            failures.append(f"must not map to {expected['not_canonical_name']}")
        results.append(
            {
                "case_id": case["case_id"],
                "kind": kind,
                "passed": not failures,
                "failures": failures,
                "actual": {
                    "canonical_product_id": result.canonical_product_id,
                    "canonical_name": result.canonical_name,
                    "mapping_status": result.mapping_status,
                    "entity_class": result.entity_class,
                    "matched_rule_id": result.matched_rule_id,
                },
            }
        )
    passed = sum(item["passed"] for item in results)
    return {
        "passed": passed == len(results),
        "case_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "results": results,
    }


def counter_dict(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))
