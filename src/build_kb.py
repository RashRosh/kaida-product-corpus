"""Build deterministic Product KB outputs from immutable observation history."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from kb.io import file_sha256, read_csv, write_csv, write_json  # noqa: E402
from kb.normalization import identity_key, normalize  # noqa: E402
from kb.report import counter_dict, run_regressions  # noqa: E402
from kb.resolver import Resolver  # noqa: E402
from kb.rules import load_rules  # noqa: E402
from kb.snapshot import (  # noqa: E402
    OBSERVATION_COLUMNS,
    latest_observations,
    validate_observation_schema,
)


DEFAULT_INPUT = ROOT / "data" / "extracted" / "observations.csv"
DEFAULT_OUT = ROOT / "data" / "kb"
DEFAULT_KB = ROOT / "kb"
DEFAULT_FIXTURES = ROOT / "tests" / "kb" / "fixtures"

MAPPING_FIELDS = [
    "raw_title",
    "normalized_title",
    "family_key",
    "entity_class",
    "canonical_product_id",
    "canonical_name",
    "mapping_status",
    "mapping_method",
    "confidence",
    "provenance",
    "matched_rule_id",
    "attributes_json",
    "categories",
    "branch_count",
    "current_branch_count",
    "observation_count",
    "history_count",
    "current_count",
    "legacy_candidate_name",
]


def numeric_price(value: str) -> float | None:
    if not value.strip():
        return None
    try:
        return float(value.replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def group_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["raw_title"].strip(), row.get("categories", "").strip())].append(row)
    return grouped


def impact_score(row: dict[str, Any], family_size: int) -> float:
    score = 3.0 * int(row["current_branch_count"])
    score += 2.0 * math.log2(int(row["observation_count"]) + 1)
    score += 1.5 if row.get("has_current_price") else 0.0
    score += min(family_size, 10) * 0.5
    score += 1.0 if row.get("legacy_candidate_name") else 0.0
    if row.get("entity_class") in {"READY_DISH", "MALFORMED"}:
        score += 2.0
    return round(score, 4)


def build(
    input_path: Path,
    out_dir: Path,
    kb_dir: Path,
    fixtures_dir: Path,
    top_unresolved: int,
) -> dict[str, Any]:
    input_hash_before = file_sha256(input_path)
    fieldnames, history = read_csv(input_path)
    validate_observation_schema(fieldnames)
    latest = latest_observations(history)
    rules = load_rules(kb_dir / "rules.yaml")
    resolver = Resolver(kb_dir, rules)
    regression = run_regressions(resolver, fixtures_dir)
    if not regression["passed"]:
        write_json(out_dir / "regression_report.json", regression)
        failed = [item["case_id"] for item in regression["results"] if not item["passed"]]
        raise RuntimeError(f"Mandatory KB regressions failed: {', '.join(failed)}")

    history_groups = group_rows(history)
    current_groups = group_rows(latest)
    mapping_rows: list[dict[str, Any]] = []
    family_counts = Counter(identity_key(title) for title, _ in current_groups)

    for title, categories in sorted(current_groups, key=lambda key: (normalize(key[0]), key[1], key[0])):
        current_rows = current_groups[(title, categories)]
        historical_rows = history_groups.get((title, categories), [])
        resolution = resolver.resolve(title, categories)
        row = resolution.to_dict()
        row.update(
            {
                "family_key": identity_key(title),
                "categories": categories,
                "branch_count": len({item["branch_id"] for item in historical_rows}),
                "current_branch_count": len({item["branch_id"] for item in current_rows}),
                "observation_count": len(historical_rows),
                "history_count": len(historical_rows),
                "current_count": len(current_rows),
                "has_current_price": any(numeric_price(item.get("price", "")) is not None for item in current_rows),
            }
        )
        mapping_rows.append(row)

    unresolved_statuses = {"UNRESOLVED", "PROVISIONAL_MAPPING", "PRODUCT_CANDIDATE"}
    unresolved_rows = []
    for row in mapping_rows:
        if row["mapping_status"] not in unresolved_statuses:
            continue
        unresolved = dict(row)
        unresolved["impact_score"] = impact_score(
            row, family_counts.get(row["family_key"], 1)
        )
        unresolved["recommended_action"] = (
            "REVIEW_PROVISIONAL_PRODUCT"
            if row["mapping_status"] == "PROVISIONAL_MAPPING"
            else "CHECK_LEGACY_CANDIDATE"
            if row.get("legacy_candidate_name")
            else "REVIEW_SEMANTIC_FAMILY"
        )
        unresolved_rows.append(unresolved)
    unresolved_rows.sort(
        key=lambda row: (-row["impact_score"], row["family_key"], row["raw_title"], row["categories"])
    )
    for rank, row in enumerate(unresolved_rows, start=1):
        row["rank"] = rank

    prices = []
    for row in mapping_rows:
        key = (row["raw_title"], row["categories"])
        current_values = [
            value
            for value in (numeric_price(item.get("price", "")) for item in current_groups[key])
            if value is not None
        ]
        history_values = [
            value
            for value in (numeric_price(item.get("price", "")) for item in history_groups.get(key, []))
            if value is not None
        ]
        if not current_values and not history_values:
            continue
        currencies = sorted(
            {item.get("currency", "") for item in current_groups[key] if item.get("currency", "")}
        )
        prices.append(
            {
                "raw_title": row["raw_title"],
                "normalized_title": row["normalized_title"],
                "canonical_product_id": row["canonical_product_id"],
                "canonical_name": row["canonical_name"],
                "mapping_status": row["mapping_status"],
                "categories": row["categories"],
                "current_price_count": len(current_values),
                "current_price_min": min(current_values) if current_values else "",
                "current_price_median": statistics.median(current_values) if current_values else "",
                "current_price_max": max(current_values) if current_values else "",
                "historical_price_count": len(history_values),
                "currency": " | ".join(currencies),
                "price_basis": "UNKNOWN",
            }
        )

    observed_names = [
        {
            "raw_title": row["raw_title"],
            "normalized_title": row["normalized_title"],
            "family_key": row["family_key"],
            "entity_class": row["entity_class"],
            "categories": row["categories"],
            "current_count": row["current_count"],
            "current_branch_count": row["current_branch_count"],
            "history_count": row["history_count"],
            "mapping_status": row["mapping_status"],
            "canonical_product_id": row["canonical_product_id"],
            "canonical_name": row["canonical_name"],
        }
        for row in mapping_rows
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "latest_observations.csv", OBSERVATION_COLUMNS, latest)
    write_csv(
        out_dir / "observed_names.csv",
        list(observed_names[0]) if observed_names else [],
        observed_names,
    )
    write_csv(out_dir / "mappings.csv", MAPPING_FIELDS, mapping_rows)
    unresolved_fields = [
        "rank",
        "impact_score",
        *MAPPING_FIELDS,
        "recommended_action",
    ]
    write_csv(
        out_dir / "unresolved.csv",
        unresolved_fields,
        unresolved_rows[:top_unresolved] if top_unresolved > 0 else unresolved_rows,
    )
    price_fields = [
        "raw_title",
        "normalized_title",
        "canonical_product_id",
        "canonical_name",
        "mapping_status",
        "categories",
        "current_price_count",
        "current_price_min",
        "current_price_median",
        "current_price_max",
        "historical_price_count",
        "currency",
        "price_basis",
    ]
    write_csv(out_dir / "prices.csv", price_fields, prices)
    shutil.copyfile(kb_dir / "seed" / "products.csv", out_dir / "products.csv")
    shutil.copyfile(kb_dir / "seed" / "aliases.csv", out_dir / "aliases.csv")
    write_json(out_dir / "regression_report.json", regression)

    unique_titles = sorted({row["raw_title"] for row in latest})
    statuses_by_title: dict[str, set[str]] = defaultdict(set)
    for row in mapping_rows:
        statuses_by_title[row["raw_title"]].add(row["mapping_status"])
    mapped_unique = sum(statuses == {"MAPPED"} for statuses in statuses_by_title.values())
    unresolved_unique = sum(bool(statuses & unresolved_statuses) for statuses in statuses_by_title.values())
    mapped_current_rows = sum(
        int(row["current_count"]) for row in mapping_rows if row["mapping_status"] == "MAPPED"
    )
    unresolved_current_rows = sum(
        int(row["current_count"])
        for row in mapping_rows
        if row["mapping_status"] in unresolved_statuses
    )
    out_of_scope_rows = sum(
        int(row["current_count"])
        for row in mapping_rows
        if row["mapping_status"] in {"OUT_OF_SCOPE", "MALFORMED"}
    )
    current_price_rows = sum(numeric_price(row.get("price", "")) is not None for row in latest)
    report: dict[str, Any] = {
        "input": {
            "path": str(input_path.relative_to(ROOT)) if input_path.is_relative_to(ROOT) else str(input_path),
            "sha256": input_hash_before,
        },
        "raw_history_rows": len(history),
        "current_latest_rows": len(latest),
        "unique_current_raw_names": len(unique_titles),
        "resolution_groups": len(mapping_rows),
        "mapped_unique_names": mapped_unique,
        "mapped_current_rows": mapped_current_rows,
        "unresolved_unique_names": unresolved_unique,
        "unresolved_current_rows": unresolved_current_rows,
        "out_of_scope_current_rows": out_of_scope_rows,
        "mapping_coverage_unique": round(mapped_unique / len(unique_titles), 6) if unique_titles else 0.0,
        "mapping_coverage_current": round(mapped_current_rows / len(latest), 6) if latest else 0.0,
        "current_price_rows": current_price_rows,
        "current_price_coverage": round(current_price_rows / len(latest), 6) if latest else 0.0,
        "historical_price_rows": sum(numeric_price(row.get("price", "")) is not None for row in history),
        "counts_by_mapping_method": counter_dict([row["mapping_method"] for row in mapping_rows]),
        "counts_by_confidence": counter_dict([row["confidence"] for row in mapping_rows]),
        "counts_by_entity_class": counter_dict([row["entity_class"] for row in mapping_rows]),
        "new_product_candidates": sum(row["mapping_status"] == "PRODUCT_CANDIDATE" for row in mapping_rows),
        "rules_applied": dict(
            sorted(Counter(row["matched_rule_id"] for row in mapping_rows if row["matched_rule_id"]).items())
        ),
        "regression": {
            "passed": regression["passed"],
            "case_count": regression["case_count"],
            "passed_count": regression["passed_count"],
            "failed_count": regression["failed_count"],
        },
    }
    previous_path = out_dir / "previous_build_report.json"
    if previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        metric_names = [
            "mapped_unique_names",
            "mapped_current_rows",
            "unresolved_unique_names",
            "unresolved_current_rows",
            "mapping_coverage_unique",
            "mapping_coverage_current",
        ]
        report["comparison_with_previous_report"] = {
            name: round(report[name] - previous.get(name, 0), 6) for name in metric_names
        }
    write_json(out_dir / "build_report.json", report)

    if file_sha256(input_path) != input_hash_before:
        raise RuntimeError("Input observations.csv changed during build")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--kb-dir", type=Path, default=DEFAULT_KB)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--top-unresolved", type=int, default=0, help="0 writes the full queue")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build(args.input, args.out, args.kb_dir, args.fixtures, args.top_unresolved)
    print("KB build complete")
    print(f"History rows: {report['raw_history_rows']}")
    print(f"Latest rows: {report['current_latest_rows']}")
    print(
        f"Mapped: {report['mapped_unique_names']} unique / "
        f"{report['mapped_current_rows']} current rows"
    )
    print(
        f"Unresolved: {report['unresolved_unique_names']} unique / "
        f"{report['unresolved_current_rows']} current rows"
    )
    print(f"Regression: {report['regression']['passed_count']}/{report['regression']['case_count']} passed")
    print(f"Outputs: {args.out}")


if __name__ == "__main__":
    main()
