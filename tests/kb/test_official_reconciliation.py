from __future__ import annotations

import copy
from pathlib import Path

import pytest

from build_official_reconciliation import build
from kb.io import read_csv
from kb.official import (
    build_unresolved_queue,
    extract_kpved_entities,
    load_registry,
    validate_decisions,
)


OUTPUTS = {
    "conflicts.json",
    "crosswalk.csv",
    "legacy_bns_evidence.csv",
    "official_entities.csv",
    "official_reconciliation_report.json",
    "unresolved.csv",
}


def build_args(root: Path, out: Path) -> tuple[Path, Path, Path, Path, Path]:
    return (
        root,
        root / "kb" / "official" / "sources.json",
        root / "kb" / "official" / "crosswalk_decisions.csv",
        root / "kb" / "seed" / "products.csv",
        out,
    )


@pytest.fixture(scope="module")
def official_build(root: Path, tmp_path_factory):
    out = tmp_path_factory.mktemp("official-reconciliation")
    report = build(*build_args(root, out))
    return out, report


@pytest.fixture()
def official_inputs(root: Path):
    registry = load_registry(root / "kb" / "official" / "sources.json", root)
    sources = {
        row["official_source_id"]: row for row in registry["official_sources"]
    }
    entities = []
    for source in sources.values():
        if source.get("dataset_parser") == "KPVED_XLS":
            entities.extend(extract_kpved_entities(source, root))
    entity_index = {
        (row["official_source_id"], row["official_entity_code"]): row
        for row in entities
    }
    _, product_rows = read_csv(root / "kb" / "seed" / "products.csv")
    products = {row["product_id"]: row for row in product_rows}
    _, decisions = read_csv(root / "kb" / "official" / "crosswalk_decisions.csv")
    return registry, sources, entities, entity_index, products, decisions


def test_legacy_bns_extraction_preserves_source_evidence_without_codes(official_build):
    out, report = official_build
    _, rows = read_csv(out / "legacy_bns_evidence.csv")
    assert len(rows) == report["legacy_bns"]["product_reference_count"] == 748
    assert report["legacy_bns"]["unique_entity_code_count"] == 0
    assert report["legacy_bns"]["entity_mapping_count"] == 0
    assert report["legacy_bns"]["current_product_link_count"] == 748
    assert all(row["legacy_source_code"] == "BNS" for row in rows)
    assert all(
        row["official_source_id"] == "BNS_LEGACY_REFERENCE_PAGE" for row in rows
    )
    assert all(row["official_entity_code"] == "" for row in rows)
    assert all(row["evidence_status"] == "LEGACY_SOURCE_REFERENCE_ONLY" for row in rows)


def test_reconciliation_totals_and_invariants(official_build):
    _, report = official_build
    assert report["currently_verified_decision_count"] == 19
    assert report["currently_verified_entity_mapping_count"] == 17
    assert report["unresolved_product_count"] == 849
    assert report["conflict_count"] == 1
    assert all(report["invariants"].values())


def test_official_source_identity_and_snapshot_are_valid(official_inputs):
    registry, sources, entities, _, _, _ = official_inputs
    assert registry["primary_crosswalk_source_id"] == "BNS_KPVED_2008_2024"
    assert sources["BNS_KPVED_2008_2024"]["dataset_sha256"] == (
        "ccb341dd1034254e07f5554ba528bfd06fed9dc60adaa9376dbd07131abb2617"
    )
    assert len(entities) == 5429


@pytest.mark.parametrize(
    ("relation", "product_id", "official_code"),
    [
        ("EXACT", "KAIDA-P0342", "011351"),
        ("BROADER", "KAIDA-P0003", "101111"),
        ("NARROWER", "KAIDA-P0265", "014120"),
        ("NO_MATCH", "KAIDA-P0836", ""),
        ("NOT_APPLICABLE", "KAIDA-P0834", ""),
    ],
)
def test_closed_relation_semantics_are_materialized(
    official_build, relation: str, product_id: str, official_code: str
):
    out, _ = official_build
    _, rows = read_csv(out / "crosswalk.csv")
    assert any(
        row["relation"] == relation
        and row["product_id"] == product_id
        and row["official_entity_code"] == official_code
        for row in rows
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("product_id", "KAIDA-NOT-A-PRODUCT", "unknown KAIDA Product ID"),
        ("official_source_id", "UNKNOWN_SOURCE", "unknown official source ID"),
        ("official_entity_code", "", "EXACT requires official entity code"),
        ("official_entity_code", "NOT-A-CODE", "official entity does not exist"),
        ("provenance_reference", "", "provenance_reference is required"),
    ],
)
def test_invalid_crosswalk_reference_fails(
    official_inputs, field: str, value: str, message: str
):
    _, sources, _, entity_index, products, decisions = official_inputs
    invalid = copy.deepcopy(decisions[:1])
    invalid[0][field] = value
    with pytest.raises(ValueError, match=message):
        validate_decisions(invalid, products, sources, entity_index)


def test_contradictory_relation_fails(official_inputs):
    _, sources, _, entity_index, products, decisions = official_inputs
    contradictory = copy.deepcopy(decisions[:1])
    second = copy.deepcopy(contradictory[0])
    second["mapping_id"] = "OFFICIAL-CW-CONTRADICTION"
    second["relation"] = "BROADER"
    contradictory.append(second)
    with pytest.raises(ValueError, match="contradictory relations"):
        validate_decisions(contradictory, products, sources, entity_index)


def test_legacy_reference_never_becomes_current_verified_mapping(official_build):
    out, report = official_build
    _, legacy = read_csv(out / "legacy_bns_evidence.csv")
    _, crosswalk = read_csv(out / "crosswalk.csv")
    assert report["legacy_entity_mapping_count"] == 0
    assert all(row["evidence_status"] != "CURRENT_VERIFIED" for row in legacy)
    assert all(row["provenance_type"] != "LEGACY_WORKBOOK" for row in crosswalk)


def test_official_build_is_byte_deterministic(root: Path, tmp_path: Path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    build(*build_args(root, one))
    build(*build_args(root, two))
    assert {path.name for path in one.iterdir()} == OUTPUTS
    assert {path.name for path in two.iterdir()} == OUTPUTS
    for filename in OUTPUTS:
        assert (one / filename).read_bytes() == (two / filename).read_bytes()


def test_identical_duplicate_decision_is_deduplicated(official_inputs):
    _, sources, _, entity_index, products, decisions = official_inputs
    duplicate = copy.deepcopy(decisions[0])
    duplicate["mapping_id"] = "OFFICIAL-CW-DUPLICATE"
    deduped, duplicate_count = validate_decisions(
        [decisions[0], duplicate], products, sources, entity_index
    )
    assert len(deduped) == 1
    assert duplicate_count == 1


def test_one_official_code_can_have_explicit_non_exact_relations(official_inputs):
    _, sources, _, entity_index, products, decisions = official_inputs
    shared = [
        row
        for row in decisions
        if row["official_entity_code"] == "101111"
    ]
    validated, _ = validate_decisions(shared, products, sources, entity_index)
    assert {(row["product_id"], row["relation"]) for row in validated} == {
        ("KAIDA-P0003", "BROADER"),
        ("KAIDA-P0004", "BROADER"),
    }


def test_fuzzy_name_similarity_does_not_create_candidate(official_inputs):
    _, _, entities, _, products, _ = official_inputs
    potato = copy.deepcopy(products["KAIDA-P0342"])
    potato["canonical_name_ru"] = "Картофел"
    unresolved, conflicts = build_unresolved_queue(
        {potato["product_id"]: potato},
        "BNS_KPVED_2008_2024",
        entities,
        [],
        set(),
    )
    assert conflicts == []
    assert unresolved[0]["candidate_official_codes"] == []
    assert unresolved[0]["reason"] == "NOT_RESEARCHED_NO_SAFE_AUTOMATIC_CANDIDATE"
