from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from build_kb import build
from kb.io import file_sha256, read_csv


OUTPUTS = {
    "latest_observations.csv",
    "observed_names.csv",
    "mappings.csv",
    "unresolved.csv",
    "prices.csv",
    "products.csv",
    "aliases.csv",
    "build_report.json",
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
    _, prices = read_csv(temp / "one" / "prices.csv")
    assert prices
    assert {row["price_basis"] for row in prices} == {"UNKNOWN"}
