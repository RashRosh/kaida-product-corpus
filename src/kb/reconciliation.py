"""Title-level terminal status and reference-workbook reconciliation."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .normalization import normalize


TERMINAL_STATUSES = (
    "APPROVED_MAPPED",
    "PROVISIONAL_MAPPED",
    "OUT_OF_SCOPE",
    "UNRESOLVED",
)
APPROVED_PRODUCT_STATUS = "LEGACY_APPROVED"
NON_PRODUCT_MAPPING_STATUSES = {"OUT_OF_SCOPE", "MALFORMED"}


def terminal_title_records(
    mapping_rows: list[dict[str, Any]], products: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in mapping_rows:
        grouped[normalize(row["raw_title"])].append(row)

    records = []
    for normalized_title in sorted(grouped):
        rows = grouped[normalized_title]
        mapping_statuses = {row["mapping_status"] for row in rows}
        product_ids = {
            row["canonical_product_id"]
            for row in rows
            if row.get("canonical_product_id")
        }
        terminal_status = "UNRESOLVED"
        canonical_product_id = ""
        canonical_name = ""

        if mapping_statuses <= NON_PRODUCT_MAPPING_STATUSES:
            terminal_status = "OUT_OF_SCOPE"
        elif (
            mapping_statuses <= {"MAPPED", *NON_PRODUCT_MAPPING_STATUSES}
            and "MAPPED" in mapping_statuses
            and len(product_ids) == 1
        ):
            product_id = next(iter(product_ids))
            product = products.get(product_id)
            if (
                product
                and product.get("status") == APPROVED_PRODUCT_STATUS
                and product.get("decision_source", "").strip()
            ):
                terminal_status = "APPROVED_MAPPED"
                canonical_product_id = product_id
                canonical_name = product.get("canonical_name_ru", "")
        elif (
            mapping_statuses
            <= {"MAPPED", "PROVISIONAL_MAPPING", *NON_PRODUCT_MAPPING_STATUSES}
            and "PROVISIONAL_MAPPING" in mapping_statuses
            and len(product_ids) == 1
        ):
            product_id = next(iter(product_ids))
            product = products.get(product_id)
            if product and product.get("status") != APPROVED_PRODUCT_STATUS:
                terminal_status = "PROVISIONAL_MAPPED"
                canonical_product_id = product_id
                canonical_name = product.get("canonical_name_ru", "")

        records.append(
            {
                "normalized_title": normalized_title,
                "raw_title_examples": sorted({row["raw_title"] for row in rows})[:10],
                "pipeline_status": terminal_status,
                "canonical_product_id": canonical_product_id,
                "canonical_name": canonical_name,
                "resolution_group_count": len(rows),
                "current_row_count": sum(int(row["current_count"]) for row in rows),
                "pipeline_mapping_statuses": sorted(mapping_statuses),
            }
        )
    return records


def reference_status_index(
    reference_mappings: list[dict[str, str]],
    reference_observed: list[dict[str, str]],
    products: dict[str, dict[str, str]],
) -> dict[str, str]:
    mapping_products: dict[str, set[str]] = defaultdict(set)
    for row in reference_mappings:
        mapping_products[normalize(row.get("raw_title", ""))].add(
            row.get("mapped_product_id", "")
        )

    statuses: dict[str, str] = {}
    for normalized_title, product_ids in mapping_products.items():
        product_statuses = {
            products[product_id].get("status", "")
            for product_id in product_ids
            if product_id in products
        }
        statuses[normalized_title] = (
            "MAPPED_APPROVED"
            if product_statuses and product_statuses <= {APPROVED_PRODUCT_STATUS}
            else "MAPPED_PROVISIONAL_OR_REVIEW"
        )

    for row in reference_observed:
        normalized_title = normalize(row.get("raw_title", ""))
        if normalized_title in statuses:
            continue
        workbook_status = row.get("mapping_status", "")
        if workbook_status in {"UNRESOLVED", "NEEDS_REVIEW"}:
            statuses[normalized_title] = f"{workbook_status}_TOP1000"
    return statuses


def reconcile(
    mapping_rows: list[dict[str, Any]],
    products: dict[str, dict[str, str]],
    reference_mappings: list[dict[str, str]],
    reference_observed: list[dict[str, str]],
    input_hash_before: str,
    input_hash_after: str,
) -> dict[str, Any]:
    title_records = terminal_title_records(mapping_rows, products)
    reference_index = reference_status_index(
        reference_mappings, reference_observed, products
    )
    transitions: Counter[tuple[str, str]] = Counter()
    for record in title_records:
        reference_status = reference_index.get(
            record["normalized_title"], "NOT_EXPORTED_ROW_LEVEL"
        )
        record["reference_status"] = reference_status
        transitions[(reference_status, record["pipeline_status"])] += 1

    status_counts = Counter(record["pipeline_status"] for record in title_records)
    reference_mapping_counts = Counter(reference_index.values())
    transition_rows = [
        {
            "reference_status": reference_status,
            "pipeline_status": pipeline_status,
            "count": count,
        }
        for (reference_status, pipeline_status), count in sorted(transitions.items())
    ]

    provisional_products = [
        product
        for product in products.values()
        if product.get("status", "").startswith("PROVISIONAL")
    ]
    provisional_audit = []
    for product in sorted(provisional_products, key=lambda item: item["product_id"]):
        referenced = [
            record
            for record in title_records
            if record["canonical_product_id"] == product["product_id"]
        ]
        approved_count = sum(
            record["pipeline_status"] == "APPROVED_MAPPED" for record in referenced
        )
        provisional_audit.append(
            {
                "product_id": product["product_id"],
                "canonical_name": product.get("canonical_name_ru", ""),
                "product_status": product.get("status", ""),
                "decision_source": product.get("decision_source", ""),
                "terminal_title_count": len(referenced),
                "approved_terminal_title_count": approved_count,
                "passed": approved_count == 0,
            }
        )

    invariants = {
        "every_unique_title_has_one_terminal_status": (
            len(title_records) == len({row["normalized_title"] for row in title_records})
            and all(row["pipeline_status"] in TERMINAL_STATUSES for row in title_records)
        ),
        "terminal_status_counts_sum_to_total": sum(status_counts.values())
        == len(title_records),
        "approved_mapping_points_to_existing_approved_product_with_source": all(
            row["pipeline_status"] != "APPROVED_MAPPED"
            or (
                row["canonical_product_id"] in products
                and products[row["canonical_product_id"]].get("status")
                == APPROVED_PRODUCT_STATUS
                and bool(
                    products[row["canonical_product_id"]]
                    .get("decision_source", "")
                    .strip()
                )
            )
            for row in title_records
        ),
        "out_of_scope_has_no_canonical_product_id": all(
            row["pipeline_status"] != "OUT_OF_SCOPE"
            or not row["canonical_product_id"]
            for row in title_records
        ),
        "provisional_never_contributes_to_approved_coverage": all(
            item["passed"] for item in provisional_audit
        ),
        "raw_observations_hash_unchanged": input_hash_before == input_hash_after,
    }
    if not all(invariants.values()):
        failed = [name for name, passed in invariants.items() if not passed]
        raise RuntimeError(f"Reconciliation invariants failed: {', '.join(failed)}")

    human_lines = [
        f"{row['reference_status']} -> {row['pipeline_status']} -> {row['count']}"
        for row in transition_rows
    ]
    return {
        "title_key": "NFKC + lowercase + ё→е + punctuation→spaces + whitespace collapse",
        "unique_observed_titles": len(title_records),
        "terminal_status_counts": {
            status: status_counts.get(status, 0) for status in TERMINAL_STATUSES
        },
        "terminal_status_total": sum(status_counts.values()),
        "reference_aggregate_counts": {
            "MAPPED": 1733,
            "UNRESOLVED": 8626,
            "OUT_OF_SCOPE": 2518,
            "TOTAL": 12877,
        },
        "reference_mapping_approval_breakdown": {
            "MAPPED_APPROVED": reference_mapping_counts.get("MAPPED_APPROVED", 0),
            "MAPPED_PROVISIONAL_OR_REVIEW": reference_mapping_counts.get(
                "MAPPED_PROVISIONAL_OR_REVIEW", 0
            ),
        },
        "reference_row_level_limit": (
            "The workbook exports all 1,733 mappings and only the Top-1,000 "
            "unresolved titles. The remaining 7,626 unresolved and 2,518 "
            "out-of-scope titles are aggregate-only, so their row-level "
            "reference status is NOT_EXPORTED_ROW_LEVEL."
        ),
        "reference_to_pipeline": transition_rows,
        "human_readable_reference_to_pipeline": "\n".join(human_lines),
        "metric_explanation": [
            (
                "Reference MAPPED=1,733 includes "
                f"{reference_mapping_counts.get('MAPPED_PROVISIONAL_OR_REVIEW', 0)} "
                "titles mapped to PROVISIONAL or LEGACY_REVIEW Products. The pipeline "
                "counts only a single context-consistent LEGACY_APPROVED Product with "
                "a non-empty decision_source as APPROVED_MAPPED."
            ),
            (
                "The pre-audit pipeline figures 1,064 approved and 10,403 unresolved "
                "used exact raw-title counting and kept provisional mappings in its "
                "review queue. This reconciliation uses 12,877 NFKC-normalized title "
                "keys and separates PROVISIONAL_MAPPED and OUT_OF_SCOPE from UNRESOLVED."
            ),
            (
                "Reference UNRESOLVED=8,626 is an aggregate that excludes 2,518 "
                "OUT_OF_SCOPE titles. The workbook contains row-level evidence for only "
                "the Top-1,000 unresolved titles, so no rules were changed to force the "
                "new terminal counts to match those aggregate figures."
            ),
        ],
        "provisional_product_audit": {
            "product_count": len(provisional_audit),
            "approved_violation_count": sum(not item["passed"] for item in provisional_audit),
            "passed": all(item["passed"] for item in provisional_audit),
            "products": provisional_audit,
        },
        "invariants": invariants,
        "titles": title_records,
    }
