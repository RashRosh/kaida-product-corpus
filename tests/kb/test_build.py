from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from build_kb import build
from kb.io import file_sha256, read_csv
from kb.reconciliation import terminal_current_row_counts, terminal_title_records


OUTPUTS = {
    "latest_observations.csv",
    "observed_names.csv",
    "mappings.csv",
    "unresolved.csv",
    "prices.csv",
    "products.csv",
    "aliases.csv",
    "build_report.json",
    "reconciliation_report.json",
    "regression_report.json",
}


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_file():
            digest.update(item.relative_to(path).as_posix().encode())
            digest.update(item.read_bytes())
    return digest.hexdigest()


@pytest.fixture(scope="module")
def builds(root: Path, tmp_path_factory):
    temp = tmp_path_factory.mktemp("determinism")
    input_path = root / "data" / "extracted" / "observations.csv"
    raw_path = root / "data" / "raw"
    input_before = file_sha256(input_path)
    raw_before = tree_hash(raw_path)
    reports = []
    for name in ("one", "two"):
        out = temp / name
        reports.append(
            build(
                input_path,
                out,
                root / "kb",
                root / "tests" / "kb" / "fixtures",
                0,
            )
        )
    assert file_sha256(input_path) == input_before
    assert tree_hash(raw_path) == raw_before
    return temp, reports


def test_build_is_byte_deterministic(builds):
    temp, _ = builds
    one = temp / "one"
    two = temp / "two"
    assert {path.name for path in one.iterdir()} == OUTPUTS
    assert {path.name for path in two.iterdir()} == OUTPUTS
    for name in OUTPUTS:
        assert (one / name).read_bytes() == (two / name).read_bytes(), name


def test_consecutive_builds_in_same_directory_are_byte_identical(
    root: Path, tmp_path: Path
):
    out = tmp_path / "repeated"
    args = (
        root / "data" / "extracted" / "observations.csv",
        out,
        root / "kb",
        root / "tests" / "kb" / "fixtures",
        0,
    )
    build(*args)
    first = {name: (out / name).read_bytes() for name in OUTPUTS}
    build(*args)
    second = {name: (out / name).read_bytes() for name in OUTPUTS}
    assert first == second


def test_output_schema_and_regression_gate(builds):
    temp, reports = builds
    _, mappings = read_csv(temp / "one" / "mappings.csv")
    required = {
        "raw_title",
        "normalized_title",
        "entity_class",
        "canonical_product_id",
        "mapping_status",
        "attributes_json",
        "current_branch_count",
        "history_count",
    }
    assert required.issubset(mappings[0])
    regression = json.loads((temp / "one" / "regression_report.json").read_text(encoding="utf-8"))
    assert regression["passed"] is True
    assert reports[0]["raw_history_rows"] == 18686
    assert reports[0]["current_latest_rows"] == 18686
    assert reports[0]["price_present_rows"] == 16977
    assert reports[0]["price_present_rate"] == pytest.approx(16977 / 18686, abs=1e-6)
    assert "current_price_coverage" not in reports[0]
    _, prices = read_csv(temp / "one" / "prices.csv")
    assert prices
    assert {row["price_basis"] for row in prices} == {"UNKNOWN"}


def test_reconciliation_invariants(builds):
    temp, _ = builds
    report = json.loads(
        (temp / "one" / "reconciliation_report.json").read_text(encoding="utf-8")
    )
    assert report["unique_observed_titles"] == 12877
    assert report["terminal_status_total"] == 12877
    assert sum(report["terminal_status_counts"].values()) == 12877
    assert set(report["terminal_status_counts"]) == {
        "APPROVED_MAPPED",
        "PROVISIONAL_MAPPED",
        "OUT_OF_SCOPE",
        "UNRESOLVED",
    }
    assert len(report["titles"]) == 12877
    assert len({row["normalized_title"] for row in report["titles"]}) == 12877
    assert all(report["invariants"].values())
    assert sum(row["count"] for row in report["reference_to_pipeline"]) == 12877


def test_approved_out_of_scope_and_provisional_separation(builds):
    temp, _ = builds
    report = json.loads(
        (temp / "one" / "reconciliation_report.json").read_text(encoding="utf-8")
    )
    _, products = read_csv(temp / "one" / "products.csv")
    products_by_id = {row["product_id"]: row for row in products}
    for row in report["titles"]:
        if row["pipeline_status"] == "APPROVED_MAPPED":
            product = products_by_id[row["canonical_product_id"]]
            assert product["status"] == "LEGACY_APPROVED"
            assert product["decision_source"]
        if row["pipeline_status"] == "OUT_OF_SCOPE":
            assert row["canonical_product_id"] == ""
    provisional = report["provisional_product_audit"]
    assert provisional["product_count"] == 81
    assert provisional["approved_violation_count"] == 0
    assert provisional["passed"] is True
    assert all(item["approved_terminal_title_count"] == 0 for item in provisional["products"])


def test_mixed_context_title_keeps_row_metrics_separate(resolver):
    approved = resolver.resolve("Молоко коровье", "Молочные продукты").to_dict()
    excluded = resolver.resolve("Молоко коровье", "Коробки, упаковка").to_dict()
    approved.update({"categories": "Молочные продукты", "current_count": 2})
    excluded.update({"categories": "Коробки, упаковка", "current_count": 3})
    rows = [approved, excluded]

    title_records = terminal_title_records(rows, resolver.products)
    row_counts = terminal_current_row_counts(rows)

    assert len(title_records) == 1
    assert title_records[0]["pipeline_status"] == "APPROVED_MAPPED"
    assert row_counts == {
        "APPROVED_MAPPED": 2,
        "PROVISIONAL_MAPPED": 0,
        "OUT_OF_SCOPE": 3,
        "UNRESOLVED": 0,
    }
    assert sum(row_counts.values()) == 5


def test_build_report_row_metrics_cover_every_current_row(builds):
    _, reports = builds
    report = reports[0]
    counts = report["terminal_status_current_rows"]
    assert sum(counts.values()) == report["current_latest_rows"]
    assert report["approved_mapping_rate_by_current_rows"] == pytest.approx(
        counts["APPROVED_MAPPED"] / report["current_latest_rows"], abs=1e-6
    )
