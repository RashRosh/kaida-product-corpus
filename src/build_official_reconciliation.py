"""Build the deterministic KAIDA Product ↔ official entity reference layer."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from kb.io import read_csv, write_csv, write_json  # noqa: E402
from kb.official import (  # noqa: E402
    RELATIONS,
    build_unresolved_queue,
    extract_kpved_entities,
    extract_legacy_bns_evidence,
    load_registry,
    materialize_crosswalk,
    validate_decisions,
)


DEFAULT_REGISTRY = ROOT / "kb" / "official" / "sources.json"
DEFAULT_DECISIONS = ROOT / "kb" / "official" / "crosswalk_decisions.csv"
DEFAULT_PRODUCTS = ROOT / "kb" / "seed" / "products.csv"
DEFAULT_OUT = ROOT / "data" / "kb" / "official"

ENTITY_FIELDS = [
    "official_source_id",
    "official_entity_code",
    "official_entity_name_ru",
    "official_entity_name_kk",
    "code_level",
    "source_version",
    "source_url",
    "dataset_sha256",
]
CROSSWALK_FIELDS = [
    "mapping_id",
    "product_id",
    "product_name",
    "official_source_id",
    "official_source_name",
    "official_entity_code",
    "official_entity_name_ru",
    "official_entity_name_kk",
    "relation",
    "verification_status",
    "provenance_type",
    "provenance_reference",
    "source_version",
    "source_url",
    "notes",
]
LEGACY_FIELDS = [
    "legacy_candidate_code",
    "legacy_product_name",
    "current_product_id",
    "legacy_source_code",
    "official_source_id",
    "legacy_source_url",
    "official_entity_code",
    "evidence_status",
    "reason",
]
UNRESOLVED_FIELDS = [
    "product_id",
    "product_name",
    "product_status",
    "official_source_id",
    "legacy_bns_reference",
    "candidate_official_codes",
    "candidate_official_names",
    "status",
    "reason",
]


def build(
    root: Path = ROOT,
    registry_path: Path = DEFAULT_REGISTRY,
    decisions_path: Path = DEFAULT_DECISIONS,
    products_path: Path = DEFAULT_PRODUCTS,
    out_dir: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    registry = load_registry(registry_path, root)
    sources = {
        row["official_source_id"]: row for row in registry["official_sources"]
    }
    _, product_rows = read_csv(products_path)
    products = {row["product_id"]: row for row in product_rows}

    entities = []
    for source in registry["official_sources"]:
        if source.get("dataset_parser") == "KPVED_XLS":
            entities.extend(extract_kpved_entities(source, root))
    entity_index = {
        (row["official_source_id"], row["official_entity_code"]): row
        for row in entities
    }

    legacy_config = registry["legacy_evidence"]
    legacy_evidence = extract_legacy_bns_evidence(
        root / legacy_config["workbook_path"],
        products,
        legacy_config["official_source_id"],
        legacy_config["legacy_source_url"],
    )
    _, raw_decisions = read_csv(decisions_path)
    decisions, duplicate_count = validate_decisions(
        raw_decisions, products, sources, entity_index
    )
    crosswalk = materialize_crosswalk(decisions, products, sources, entity_index)
    primary_source_id = registry["primary_crosswalk_source_id"]
    primary_entities = [
        row for row in entities if row["official_source_id"] == primary_source_id
    ]
    legacy_product_ids = {
        row["current_product_id"]
        for row in legacy_evidence
        if row["current_product_id"]
    }
    unresolved, conflicts = build_unresolved_queue(
        products,
        primary_source_id,
        primary_entities,
        crosswalk,
        legacy_product_ids,
    )

    relation_counts = Counter(row["relation"] for row in crosswalk)
    verification_counts = Counter(row["verification_status"] for row in crosswalk)
    report = {
        "official_sources": [
            {
                key: source.get(key, "")
                for key in (
                    "official_source_id",
                    "agency",
                    "name",
                    "abbreviation",
                    "version",
                    "introduced_on",
                    "updated_on",
                    "legacy_url",
                    "current_url",
                    "dataset_url",
                    "dataset_sha256",
                )
            }
            for source in registry["official_sources"]
        ],
        "legacy_bns": {
            "meaning": "Bureau of National Statistics source identifier",
            "legacy_workbook_sha256": legacy_config["workbook_sha256"],
            "product_reference_count": len(legacy_evidence),
            "current_product_link_count": sum(
                bool(row["current_product_id"]) for row in legacy_evidence
            ),
            "unique_entity_code_count": len(
                {
                    row["official_entity_code"]
                    for row in legacy_evidence
                    if row["official_entity_code"]
                }
            ),
            "entity_mapping_count": 0,
            "limitation": (
                "The legacy workbook stores BNS as a source tag and a shared "
                "classifiers landing-page URL, not entity-level classifier codes."
            ),
        },
        "official_entity_count": len(entities),
        "current_product_count": len(products),
        "source_selection_note": (
            "KPVED is used as the first current authoritative crosswalk source. "
            "It is not inferred to be the unspecified classifier behind the legacy BNS tag."
        ),
        "crosswalk_counts": {
            relation: relation_counts.get(relation, 0) for relation in sorted(RELATIONS)
        },
        "currently_verified_decision_count": verification_counts.get(
            "CURRENT_VERIFIED", 0
        ),
        "currently_verified_entity_mapping_count": sum(
            row["verification_status"] == "CURRENT_VERIFIED"
            and row["relation"] in {"EXACT", "BROADER", "NARROWER"}
            for row in crosswalk
        ),
        "legacy_entity_mapping_count": 0,
        "unresolved_product_count": len(unresolved),
        "unresolved_reason_counts": dict(
            sorted(Counter(row["reason"] for row in unresolved).items())
        ),
        "conflict_count": len(conflicts),
        "conflict_type_counts": dict(
            sorted(Counter(row["conflict_type"] for row in conflicts).items())
        ),
        "duplicate_decision_count": duplicate_count,
        "invariants": {
            "all_crosswalk_products_exist": all(
                row["product_id"] in products for row in crosswalk
            ),
            "all_crosswalk_sources_exist": all(
                row["official_source_id"] in sources for row in crosswalk
            ),
            "entity_relations_point_to_existing_entities": all(
                row["relation"] not in {"EXACT", "BROADER", "NARROWER"}
                or (row["official_source_id"], row["official_entity_code"])
                in entity_index
                for row in crosswalk
            ),
            "legacy_bns_has_no_invented_entity_codes": all(
                not row["official_entity_code"] for row in legacy_evidence
            ),
            "resolved_plus_unresolved_equals_products": (
                len({row["product_id"] for row in crosswalk}) + len(unresolved)
                == len(products)
            ),
        },
    }
    if not all(report["invariants"].values()):
        failed = [
            name for name, passed in report["invariants"].items() if not passed
        ]
        raise RuntimeError(f"Official reconciliation invariants failed: {failed}")

    write_csv(out_dir / "official_entities.csv", ENTITY_FIELDS, entities)
    write_csv(out_dir / "legacy_bns_evidence.csv", LEGACY_FIELDS, legacy_evidence)
    write_csv(out_dir / "crosswalk.csv", CROSSWALK_FIELDS, crosswalk)
    write_csv(out_dir / "unresolved.csv", UNRESOLVED_FIELDS, unresolved)
    write_json(out_dir / "conflicts.json", conflicts)
    write_json(out_dir / "official_reconciliation_report.json", report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--products", type=Path, default=DEFAULT_PRODUCTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build(args.root, args.registry, args.decisions, args.products, args.out)
    print("Official reconciliation build complete")
    print(f"Official entities: {report['official_entity_count']}")
    print(f"Legacy BNS references: {report['legacy_bns']['product_reference_count']}")
    print(f"Crosswalk: {report['crosswalk_counts']}")
    print(f"Unresolved Products: {report['unresolved_product_count']}")
    print(f"Conflicts: {report['conflict_count']}")
    print(f"Outputs: {args.out}")


if __name__ == "__main__":
    main()
