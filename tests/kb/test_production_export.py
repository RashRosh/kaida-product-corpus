from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from kb.export_package import (
    ExportValidationError,
    build_package,
    validate_package,
)
from kb.io import read_csv, write_csv, write_json


def package_rows(path: Path, name: str) -> list[dict[str, str]]:
    _, rows = read_csv(path / name)
    return rows


@pytest.fixture()
def package(root: Path, tmp_path: Path) -> Path:
    out = tmp_path / "kaida-kb-v1"
    build_package(root, out)
    return out


def test_export_package_counts_and_manifest(package: Path):
    manifest = validate_package(package)
    assert manifest["package_schema_version"] == 1
    assert manifest["source_checkpoint_tag"] == "v0.1.0-kb-foundation"
    assert manifest["source_commit_sha"] == "25a27637d3c131c6ab22f855e7d0d872745ea6e9"
    assert manifest["observations_sha256"] == (
        "7071860efc890ad0bb46a6bc02072b33fbb784004ea64c5a75c6876ba206a870"
    )
    assert manifest["raw_tree_sha256"] == (
        "2029db154b59b3a155c3caf602ad75c2cc9f90362631d9e042e283debf074666"
    )
    assert manifest["counts"]["source_products_total"] == 868
    assert manifest["counts"]["exported_products"] == 682
    assert manifest["counts"]["products_excluded_by_status"] == {
        "LEGACY_REVIEW": 105,
        "PROVISIONAL_AI": 77,
        "PROVISIONAL_USER": 4,
    }
    assert manifest["counts"]["source_aliases"] == 231
    assert manifest["counts"]["exported_aliases"] == 210
    assert manifest["counts"]["categories"] == 35
    assert manifest["counts"]["official_mappings"] == 17


def test_provisional_and_review_products_are_not_exported(root: Path, package: Path):
    _, source_products = read_csv(root / "kb" / "seed" / "products.csv")
    excluded_ids = {
        row["product_id"]
        for row in source_products
        if row["status"] in {"PROVISIONAL_AI", "PROVISIONAL_USER", "LEGACY_REVIEW"}
    }
    exported_ids = {row["product_id"] for row in package_rows(package, "products.csv")}
    assert exported_ids.isdisjoint(excluded_ids)
    assert {row["approval_status"] for row in package_rows(package, "products.csv")} == {
        "LEGACY_APPROVED"
    }


def test_alias_filters_are_production_safe(root: Path, package: Path):
    products = {row["product_id"] for row in package_rows(package, "products.csv")}
    aliases = package_rows(package, "aliases.csv")
    assert aliases
    assert all(row["product_id"] in products for row in aliases)

    _, source_aliases = read_csv(root / "kb" / "seed" / "aliases.csv")
    exported_alias_ids = {row["alias_id"] for row in aliases}
    for row in source_aliases:
        if row["product_id"] not in products:
            assert row["alias_id"] not in exported_alias_ids
        if row["status"] != "ACTIVE":
            assert row["alias_id"] not in exported_alias_ids
        if row["safe_for_auto_match"] != "YES":
            assert row["alias_id"] not in exported_alias_ids


def test_raw_observations_and_unresolved_are_not_in_package(package: Path):
    names = {path.name for path in package.iterdir()}
    assert "observations.csv" not in names
    assert "unresolved.csv" not in names
    assert not (package / "raw").exists()


def test_official_mapping_cannot_create_product(package: Path):
    products = {row["product_id"] for row in package_rows(package, "products.csv")}
    official_product_ids = {
        row["product_id"] for row in package_rows(package, "official_mappings.csv")
    }
    assert official_product_ids
    assert official_product_ids.issubset(products)


def test_absence_of_official_mapping_does_not_exclude_product(package: Path):
    products = {row["product_id"] for row in package_rows(package, "products.csv")}
    mapped = {row["product_id"] for row in package_rows(package, "official_mappings.csv")}
    assert products - mapped


def test_repeated_export_builds_are_byte_identical(root: Path, tmp_path: Path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    build_package(root, one)
    build_package(root, two)
    one_files = sorted(path.relative_to(one).as_posix() for path in one.rglob("*") if path.is_file())
    two_files = sorted(path.relative_to(two).as_posix() for path in two.rglob("*") if path.is_file())
    assert one_files == two_files
    for rel in one_files:
        assert (one / rel).read_bytes() == (two / rel).read_bytes(), rel


def test_duplicate_product_id_fails(package: Path):
    products = package_rows(package, "products.csv")
    products.append(dict(products[0]))
    write_csv(package / "products.csv", list(products[0]), products)
    with pytest.raises(ExportValidationError, match="Manifest hash mismatch|Duplicate Product IDs"):
        validate_package(package)


def test_dangling_alias_fails(package: Path):
    aliases = package_rows(package, "aliases.csv")
    aliases[0]["product_id"] = "KAIDA-P9999"
    write_csv(package / "aliases.csv", list(aliases[0]), aliases)
    _refresh_hash(package, "aliases.csv")
    with pytest.raises(ExportValidationError, match="Dangling alias"):
        validate_package(package)


def test_category_label_conflict_fails(package: Path):
    categories = package_rows(package, "categories.csv")
    categories.append(dict(categories[0], category_ru="conflict"))
    write_csv(package / "categories.csv", list(categories[0]), categories)
    _refresh_hash(package, "categories.csv")
    with pytest.raises(ExportValidationError, match="Conflicting category labels"):
        validate_package(package)


def test_corrupt_manifest_hash_is_detected(package: Path):
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    manifest["file_hashes"]["products.csv"] = "0" * 64
    write_json(package / "manifest.json", manifest)
    with pytest.raises(ExportValidationError, match="Manifest hash mismatch"):
        validate_package(package)


def test_dangling_parent_fails(package: Path):
    products = package_rows(package, "products.csv")
    products[0]["parent_product_id"] = "KAIDA-P9999"
    write_csv(package / "products.csv", list(products[0]), products)
    _refresh_hash(package, "products.csv")
    with pytest.raises(ExportValidationError, match="Dangling parent"):
        validate_package(package)


def test_official_mapping_to_missing_product_fails(package: Path):
    mappings = package_rows(package, "official_mappings.csv")
    mappings[0]["product_id"] = "KAIDA-P9999"
    write_csv(package / "official_mappings.csv", list(mappings[0]), mappings)
    _refresh_hash(package, "official_mappings.csv")
    with pytest.raises(ExportValidationError, match="Official mapping references missing Product"):
        validate_package(package)


def test_source_tree_is_not_mutated(root: Path, package: Path):
    assert package.exists()
    assert (root / "kb" / "seed" / "products.csv").exists()
    assert not (root / "kb" / "seed" / "products.csv").read_text(encoding="utf-8").startswith("product_id,\n")


def _refresh_hash(package: Path, filename: str) -> None:
    from kb.io import file_sha256

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    manifest["file_hashes"][filename] = file_sha256(package / filename)
    write_json(package / "manifest.json", manifest)
