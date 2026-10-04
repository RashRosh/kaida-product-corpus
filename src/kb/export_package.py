"""Deterministic production Product KB export package."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from .io import file_sha256, read_csv, write_csv, write_json


PACKAGE_SCHEMA_VERSION = 1
PACKAGE_NAME = "kaida-kb-v1"
SOURCE_REPOSITORY = "RashRosh/kaida-product-corpus"
SOURCE_CHECKPOINT_TAG = "v0.1.0-kb-foundation"
SOURCE_COMMIT_SHA = "25a27637d3c131c6ab22f855e7d0d872745ea6e9"
OBSERVATIONS_SHA256 = "7071860efc890ad0bb46a6bc02072b33fbb784004ea64c5a75c6876ba206a870"
RAW_TREE_SHA256 = "2029db154b59b3a155c3caf602ad75c2cc9f90362631d9e042e283debf074666"

PRODUCT_EXPORT_STATUS = "LEGACY_APPROVED"
ALIAS_EXPORT_STATUS = "ACTIVE"
ALIAS_SAFE_VALUE = "YES"
OFFICIAL_INCLUDED_RELATIONS = {"EXACT", "BROADER", "NARROWER"}
OFFICIAL_INCLUDED_VERIFICATION = "CURRENT_VERIFIED"

PRODUCT_FIELDS = [
    "product_id",
    "canonical_name_ru",
    "canonical_name_kk",
    "entity_class",
    "category_code",
    "category_ru",
    "category_kk",
    "parent_product_id",
    "approval_status",
]
PRODUCT_REQUIRED_FIELDS = [
    field for field in PRODUCT_FIELDS if field != "parent_product_id"
]
ALIAS_FIELDS = [
    "alias_id",
    "product_id",
    "alias",
    "language",
    "alias_type",
    "scope",
]
CATEGORY_FIELDS = ["category_code", "category_ru", "category_kk"]
OFFICIAL_MAPPING_FIELDS = [
    "mapping_id",
    "product_id",
    "official_source_id",
    "official_source_name",
    "official_entity_code",
    "official_entity_name_ru",
    "official_entity_name_kk",
    "relation",
    "verification_status",
    "source_version",
]


class ExportValidationError(ValueError):
    """Raised when the production export package contract is violated."""


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_file():
            digest.update(item.relative_to(path).as_posix().encode())
            digest.update(item.read_bytes())
    return digest.hexdigest()


def _require_fields(rows: list[dict[str, str]], fields: list[str], name: str) -> None:
    missing = [
        field for field in fields
        if any(field not in row or not str(row[field]).strip() for row in rows)
    ]
    if missing:
        raise ExportValidationError(f"{name}: required fields are empty: {missing}")


def _read_optional_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    _, rows = read_csv(path)
    return rows


def build_package(root: Path, out_dir: Path) -> dict[str, Any]:
    products_path = root / "kb" / "seed" / "products.csv"
    aliases_path = root / "kb" / "seed" / "aliases.csv"
    official_path = root / "data" / "kb" / "official" / "crosswalk.csv"
    sources_path = root / "kb" / "official" / "sources.json"
    observations_path = root / "data" / "extracted" / "observations.csv"
    raw_path = root / "data" / "raw"

    if file_sha256(observations_path) != OBSERVATIONS_SHA256:
        raise ExportValidationError("observations.csv SHA-256 mismatch")
    if tree_hash(raw_path) != RAW_TREE_SHA256:
        raise ExportValidationError("data/raw tree hash mismatch")

    _, product_rows = read_csv(products_path)
    _, alias_rows = read_csv(aliases_path)
    official_rows = _read_optional_csv(official_path)
    source_registry = json.loads(sources_path.read_text(encoding="utf-8"))

    products = _export_products(product_rows)
    product_ids = {row["product_id"] for row in products}
    aliases, alias_exclusions = _export_aliases(alias_rows, product_ids)
    categories = _export_categories(products)
    official_mappings = _export_official_mappings(official_rows, product_ids)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(out_dir / "products.csv", PRODUCT_FIELDS, products)
    write_csv(out_dir / "aliases.csv", ALIAS_FIELDS, aliases)
    write_csv(out_dir / "categories.csv", CATEGORY_FIELDS, categories)
    write_csv(out_dir / "official_mappings.csv", OFFICIAL_MAPPING_FIELDS, official_mappings)
    _write_contract(out_dir / "CONTRACT.md")

    manifest = _manifest(
        root,
        out_dir,
        product_rows,
        products,
        alias_rows,
        aliases,
        alias_exclusions,
        categories,
        official_mappings,
        source_registry,
    )
    write_json(out_dir / "manifest.json", manifest)
    validate_package(out_dir)
    return manifest


def _export_products(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    statuses = {row["status"] for row in rows}
    known = {"LEGACY_APPROVED", "LEGACY_REVIEW", "PROVISIONAL_AI", "PROVISIONAL_USER"}
    unknown = sorted(statuses - known)
    if unknown:
        raise ExportValidationError(f"Unknown Product statuses: {unknown}")
    products = []
    approved_ids = {
        row["product_id"] for row in rows if row["status"] == PRODUCT_EXPORT_STATUS
    }
    for row in rows:
        if row["status"] != PRODUCT_EXPORT_STATUS:
            continue
        parent = row.get("parent_product_id", "").strip()
        products.append(
            {
                "product_id": row["product_id"],
                "canonical_name_ru": row["canonical_name_ru"],
                "canonical_name_kk": row["canonical_name_kk"],
                "entity_class": row["entity_class"],
                "category_code": row["category_code"],
                "category_ru": row["category_ru"],
                "category_kk": row["category_kk"],
                "parent_product_id": parent if parent in approved_ids else "",
                "approval_status": PRODUCT_EXPORT_STATUS,
            }
        )
    return sorted(products, key=lambda row: row["product_id"])


def _export_aliases(
    rows: list[dict[str, str]], product_ids: set[str]
) -> tuple[list[dict[str, str]], dict[str, int]]:
    aliases = []
    exclusions: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for row in rows:
        alias_id = row["alias_id"]
        if alias_id in seen_ids:
            raise ExportValidationError(f"Duplicate source alias_id: {alias_id}")
        seen_ids.add(alias_id)
        if row["product_id"] not in product_ids:
            exclusions["excluded_product"] += 1
            continue
        if row["status"] != ALIAS_EXPORT_STATUS:
            exclusions["non_active_status"] += 1
            continue
        if row["safe_for_auto_match"] != ALIAS_SAFE_VALUE:
            exclusions["unsafe_for_auto_match"] += 1
            continue
        aliases.append(
            {
                "alias_id": alias_id,
                "product_id": row["product_id"],
                "alias": row["alias"],
                "language": row["language"],
                "alias_type": row["alias_type"],
                "scope": row["scope"],
            }
        )
    return sorted(aliases, key=lambda row: row["alias_id"]), dict(sorted(exclusions.items()))


def _export_categories(products: list[dict[str, str]]) -> list[dict[str, str]]:
    labels: dict[str, tuple[str, str]] = {}
    for row in products:
        code = row["category_code"]
        label = (row["category_ru"], row["category_kk"])
        if code in labels and labels[code] != label:
            raise ExportValidationError(
                f"Conflicting category labels for {code}: {labels[code]} vs {label}"
            )
        labels[code] = label
    return [
        {"category_code": code, "category_ru": labels[code][0], "category_kk": labels[code][1]}
        for code in sorted(labels)
    ]


def _export_official_mappings(
    rows: list[dict[str, str]], product_ids: set[str]
) -> list[dict[str, str]]:
    mappings = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if row.get("product_id", "") not in product_ids:
            continue
        if row.get("verification_status", "") != OFFICIAL_INCLUDED_VERIFICATION:
            continue
        if row.get("relation", "") not in OFFICIAL_INCLUDED_RELATIONS:
            continue
        if not row.get("official_entity_code", ""):
            raise ExportValidationError(f"{row.get('mapping_id')}: missing official entity code")
        key = (
            row["product_id"],
            row["official_source_id"],
            row["official_entity_code"],
            row["relation"],
        )
        if key in seen:
            raise ExportValidationError(f"Duplicate official mapping: {key}")
        seen.add(key)
        mappings.append({field: row.get(field, "") for field in OFFICIAL_MAPPING_FIELDS})
    return sorted(mappings, key=lambda row: row["mapping_id"])


def _manifest(
    root: Path,
    out_dir: Path,
    source_products: list[dict[str, str]],
    products: list[dict[str, str]],
    source_aliases: list[dict[str, str]],
    aliases: list[dict[str, str]],
    alias_exclusions: dict[str, int],
    categories: list[dict[str, str]],
    official_mappings: list[dict[str, str]],
    source_registry: dict[str, Any],
) -> dict[str, Any]:
    file_hashes = {
        path.name: file_sha256(path)
        for path in sorted(out_dir.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    status_counts = Counter(row["status"] for row in source_products)
    excluded_products = {
        status: count for status, count in sorted(status_counts.items())
        if status != PRODUCT_EXPORT_STATUS
    }
    official_sources = [
        {
            "official_source_id": source["official_source_id"],
            "version": source.get("version", ""),
            "dataset_sha256": source.get("dataset_sha256", ""),
        }
        for source in source_registry.get("official_sources", [])
        if source.get("dataset_sha256")
    ]
    return {
        "package_name": PACKAGE_NAME,
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "package_version": "v1",
        "source_repository": SOURCE_REPOSITORY,
        "source_checkpoint_tag": SOURCE_CHECKPOINT_TAG,
        "source_commit_sha": SOURCE_COMMIT_SHA,
        "observations_sha256": OBSERVATIONS_SHA256,
        "raw_tree_sha256": RAW_TREE_SHA256,
        "product_eligibility": {"status": PRODUCT_EXPORT_STATUS},
        "alias_eligibility": {
            "status": ALIAS_EXPORT_STATUS,
            "safe_for_auto_match": ALIAS_SAFE_VALUE,
            "product_must_be_exported": True,
        },
        "official_mapping_eligibility": {
            "verification_status": OFFICIAL_INCLUDED_VERIFICATION,
            "relations": sorted(OFFICIAL_INCLUDED_RELATIONS),
            "product_must_be_exported": True,
        },
        "included_datasets": [
            "products.csv",
            "aliases.csv",
            "categories.csv",
            "official_mappings.csv",
            "CONTRACT.md",
        ],
        "excluded_datasets": [
            "data/raw/**",
            "data/extracted/observations.csv",
            "seller/company data",
            "unresolved queues",
            "provisional mappings and Products",
            "manual review queues",
            "raw price observations and price aggregates",
            "legacy workbook",
            "official XLS snapshot",
            "attribute_definitions.csv",
        ],
        "counts": {
            "source_products_total": len(source_products),
            "exported_products": len(products),
            "products_excluded_by_status": excluded_products,
            "source_aliases": len(source_aliases),
            "exported_aliases": len(aliases),
            "aliases_excluded_by_reason": alias_exclusions,
            "categories": len(categories),
            "official_mappings": len(official_mappings),
        },
        "source_files": {
            "products_sha256": file_sha256(root / "kb" / "seed" / "products.csv"),
            "aliases_sha256": file_sha256(root / "kb" / "seed" / "aliases.csv"),
            "official_sources_sha256": file_sha256(root / "kb" / "official" / "sources.json"),
            "official_decisions_sha256": file_sha256(
                root / "kb" / "official" / "crosswalk_decisions.csv"
            ),
        },
        "official_sources": official_sources,
        "file_hashes": file_hashes,
        "ordering": {
            "products.csv": "product_id ascending",
            "aliases.csv": "alias_id ascending",
            "categories.csv": "category_code ascending",
            "official_mappings.csv": "mapping_id ascending",
        },
    }


def _write_contract(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# KAIDA Product KB Production Export v1",
                "",
                "This package is a deterministic projection of the closed Product KB checkpoint.",
                "It is not a research corpus and it does not approve or create Products.",
                "",
                "Source checkpoint: v0.1.0-kb-foundation",
                "Source commit: 25a27637d3c131c6ab22f855e7d0d872745ea6e9",
                "Package schema version: 1",
                "",
                "## Datasets",
                "",
                "- products.csv: only LEGACY_APPROVED Products with stable KAIDA-Pxxxx IDs.",
                "- aliases.csv: ACTIVE aliases with safe_for_auto_match=YES whose Product is exported.",
                "- categories.csv: category labels used by exported Products.",
                "- official_mappings.csv: optional provenance mappings; they do not control Product eligibility.",
                "- manifest.json: provenance, counts, immutable corpus hashes, and package file hashes.",
                "",
                "## Explicitly excluded",
                "",
                "Raw 2GIS evidence, observations history, unresolved queues, provisional Products,",
                "manual review queues, raw prices, full legacy workbooks, official XLS snapshots,",
                "crawler tooling, and WORKING_I3 attribute definitions are not runtime export data.",
                "",
                "Attribute definitions are omitted from v1 because the current WORKING_I3 schema",
                "belongs to the future Offer attribute system, not the first Product identity import.",
                "",
                "## Importer obligations",
                "",
                "An importer must validate manifest hashes, schema version, unique Product and alias",
                "IDs, category consistency, and absence of dangling Product references before import.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )


def validate_package(out_dir: Path) -> dict[str, Any]:
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        raise ExportValidationError("manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("package_schema_version") != PACKAGE_SCHEMA_VERSION:
        raise ExportValidationError("Unsupported package schema version")

    for filename, expected_hash in manifest.get("file_hashes", {}).items():
        path = out_dir / filename
        if not path.exists():
            raise ExportValidationError(f"Manifest references missing file: {filename}")
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash:
            raise ExportValidationError(
                f"Manifest hash mismatch for {filename}: {actual_hash}; expected {expected_hash}"
            )

    _, products = read_csv(out_dir / "products.csv")
    _, aliases = read_csv(out_dir / "aliases.csv")
    _, categories = read_csv(out_dir / "categories.csv")
    _, official_mappings = read_csv(out_dir / "official_mappings.csv")

    _require_fields(products, PRODUCT_REQUIRED_FIELDS, "products.csv")
    _require_fields(aliases, ALIAS_FIELDS, "aliases.csv")
    _require_fields(categories, CATEGORY_FIELDS, "categories.csv")
    _require_fields(official_mappings, OFFICIAL_MAPPING_FIELDS, "official_mappings.csv")

    product_ids = [row["product_id"] for row in products]
    if len(product_ids) != len(set(product_ids)):
        raise ExportValidationError("Duplicate Product IDs in products.csv")
    invalid_product_ids = [pid for pid in product_ids if not re.fullmatch(r"KAIDA-P\d{4}", pid)]
    if invalid_product_ids:
        raise ExportValidationError(f"Invalid Product IDs: {invalid_product_ids}")
    product_id_set = set(product_ids)

    parent_refs = {
        row["parent_product_id"] for row in products if row.get("parent_product_id", "")
    }
    dangling_parents = sorted(parent_refs - product_id_set)
    if dangling_parents:
        raise ExportValidationError(f"Dangling parent Product references: {dangling_parents}")

    alias_ids = [row["alias_id"] for row in aliases]
    if len(alias_ids) != len(set(alias_ids)):
        raise ExportValidationError("Duplicate alias IDs in aliases.csv")
    dangling_aliases = sorted(
        {row["product_id"] for row in aliases if row["product_id"] not in product_id_set}
    )
    if dangling_aliases:
        raise ExportValidationError(f"Dangling alias Product references: {dangling_aliases}")

    category_labels: dict[str, tuple[str, str]] = {}
    for row in categories:
        code = row["category_code"]
        label = (row["category_ru"], row["category_kk"])
        if code in category_labels and category_labels[code] != label:
            raise ExportValidationError(f"Conflicting category labels for {code}")
        category_labels[code] = label
    unknown_categories = sorted(
        {row["category_code"] for row in products if row["category_code"] not in category_labels}
    )
    if unknown_categories:
        raise ExportValidationError(f"Products reference unknown categories: {unknown_categories}")

    official_keys: set[tuple[str, str, str, str]] = set()
    for row in official_mappings:
        if row["product_id"] not in product_id_set:
            raise ExportValidationError(
                f"Official mapping references missing Product: {row['product_id']}"
            )
        key = (
            row["product_id"],
            row["official_source_id"],
            row["official_entity_code"],
            row["relation"],
        )
        if key in official_keys:
            raise ExportValidationError(f"Duplicate official mapping: {key}")
        official_keys.add(key)

    _assert_sorted(products, "product_id", "products.csv")
    _assert_sorted(aliases, "alias_id", "aliases.csv")
    _assert_sorted(categories, "category_code", "categories.csv")
    _assert_sorted(official_mappings, "mapping_id", "official_mappings.csv")

    return manifest


def _assert_sorted(rows: list[dict[str, str]], field: str, name: str) -> None:
    values = [row[field] for row in rows]
    if values != sorted(values):
        raise ExportValidationError(f"{name} is not sorted by {field}")
