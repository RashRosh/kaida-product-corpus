from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from kb.export_package import ExportValidationError, build_package, validate_package
from kb.io import read_csv, write_csv, write_json


EXPECTED_FILES = {
    "CONTRACT.md",
    "aliases.csv",
    "categories.csv",
    "manifest.json",
    "products.csv",
}


def package_rows(path: Path, name: str) -> list[dict[str, str]]:
    _, rows = read_csv(path / name)
    return rows


@pytest.fixture()
def package(root: Path, tmp_path: Path) -> Path:
    out = tmp_path / "kaida-kb-v1"
    build_package(root, out)
    return out


def test_export_package_counts_manifest_and_file_list(package: Path):
    manifest = validate_package(package)
    assert {path.name for path in package.iterdir() if path.is_file()} == EXPECTED_FILES
    assert manifest["package_schema_version"] == 1
    assert manifest["source_checkpoint_tag"] == "v0.1.0-kb-foundation"
    assert manifest["source_commit_sha"] == "25a27637d3c131c6ab22f855e7d0d872745ea6e9"
    assert manifest["observations_sha256"] == (
        "7071860efc890ad0bb46a6bc02072b33fbb784004ea64c5a75c6876ba206a870"
    )
    assert manifest["raw_tree_sha256"] == (
        "2029db154b59b3a155c3caf602ad75c2cc9f90362631d9e042e283debf074666"
    )
    assert manifest["included_datasets"] == [
        "products.csv",
        "aliases.csv",
        "categories.csv",
        "CONTRACT.md",
    ]
    assert "official_mapping_eligibility" not in manifest
    assert "official_sources" not in manifest
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
    assert "official_mappings" not in manifest["counts"]


def test_products_do_not_export_parent_hierarchy(package: Path):
    products = package_rows(package, "products.csv")
    assert "parent_product_id" not in products[0]


def test_existing_approved_children_still_export_without_provisional_parents(package: Path):
    exported_ids = {row["product_id"] for row in package_rows(package, "products.csv")}
    assert {
        "KAIDA-P0163",
        "KAIDA-P0164",
        "KAIDA-P0165",
        "KAIDA-P0170",
        "KAIDA-P0173",
        "KAIDA-P0174",
    }.issubset(exported_ids)
    assert {"KAIDA-P0801", "KAIDA-P0802", "KAIDA-P0803"}.isdisjoint(exported_ids)


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


def test_unknown_product_status_fails(root: Path, tmp_path: Path):
    source = tmp_path / "source"
    shutil.copytree(root / "kb", source / "kb")
    (source / "data" / "extracted").mkdir(parents=True)
    (source / "data" / "raw").mkdir(parents=True)
    shutil.copy2(
        root / "data" / "extracted" / "observations.csv",
        source / "data" / "extracted" / "observations.csv",
    )
    for item in (root / "data" / "raw").rglob("*"):
        if item.is_file():
            target = source / "data" / "raw" / item.relative_to(root / "data" / "raw")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    fields, products = read_csv(source / "kb" / "seed" / "products.csv")
    products[0]["status"] = "NEW_APPROVED_MAYBE"
    write_csv(source / "kb" / "seed" / "products.csv", fields, products)
    with pytest.raises(ExportValidationError, match="Unknown Product statuses"):
        build_package(source, tmp_path / "out")


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


def test_raw_observations_unresolved_and_official_mappings_are_not_in_package(package: Path):
    names = {path.name for path in package.iterdir()}
    assert "observations.csv" not in names
    assert "unresolved.csv" not in names
    assert "official_mappings.csv" not in names
    assert not (package / "raw").exists()


def test_clean_state_export_does_not_require_generated_official_outputs(root: Path, tmp_path: Path):
    official_out = root / "data" / "kb" / "official"
    backup = tmp_path / "official-backup"
    if official_out.exists():
        shutil.move(str(official_out), str(backup))
    try:
        one = tmp_path / "one"
        two = tmp_path / "two"
        build_package(root, one)
        build_package(root, two)
        assert {path.name for path in one.iterdir() if path.is_file()} == EXPECTED_FILES
        manifest = validate_package(one)
        assert manifest["counts"]["exported_products"] == 682
        assert manifest["counts"]["exported_aliases"] == 210
        assert manifest["counts"]["categories"] == 35
        assert _file_bytes(one) == _file_bytes(two)
    finally:
        if backup.exists():
            if official_out.exists():
                shutil.rmtree(official_out)
            shutil.move(str(backup), str(official_out))


def test_stale_generated_official_state_does_not_affect_export(root: Path, tmp_path: Path):
    official_out = root / "data" / "kb" / "official"
    backup = tmp_path / "official-backup"
    if official_out.exists():
        shutil.move(str(official_out), str(backup))
    try:
        clean = tmp_path / "clean"
        stale = tmp_path / "stale"
        build_package(root, clean)
        official_out.mkdir(parents=True, exist_ok=True)
        (official_out / "crosswalk.csv").write_text(
            "mapping_id,product_id,official_source_id,official_entity_code,relation,verification_status\n"
            "STALE,KAIDA-P9999,STALE,000000,EXACT,CURRENT_VERIFIED\n",
            encoding="utf-8",
            newline="\n",
        )
        build_package(root, stale)
        assert _file_bytes(clean) == _file_bytes(stale)
    finally:
        if official_out.exists():
            shutil.rmtree(official_out)
        if backup.exists():
            shutil.move(str(backup), str(official_out))


def test_repeated_export_builds_are_byte_identical(root: Path, tmp_path: Path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    build_package(root, one)
    build_package(root, two)
    assert _file_bytes(one) == _file_bytes(two)


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


def test_duplicate_alias_id_fails(package: Path):
    aliases = package_rows(package, "aliases.csv")
    aliases.append(dict(aliases[0]))
    write_csv(package / "aliases.csv", list(aliases[0]), aliases)
    _refresh_hash(package, "aliases.csv")
    with pytest.raises(ExportValidationError, match="Duplicate alias IDs"):
        validate_package(package)


def test_category_label_conflict_fails(package: Path):
    categories = package_rows(package, "categories.csv")
    categories.append(dict(categories[0], category_ru="conflict"))
    write_csv(package / "categories.csv", list(categories[0]), categories)
    _refresh_hash(package, "categories.csv")
    with pytest.raises(ExportValidationError, match="Conflicting category labels"):
        validate_package(package)


def test_unknown_product_category_fails(package: Path):
    products = package_rows(package, "products.csv")
    products[0]["category_code"] = "UNKNOWN_CATEGORY"
    write_csv(package / "products.csv", list(products[0]), products)
    _refresh_hash(package, "products.csv")
    with pytest.raises(ExportValidationError, match="unknown categories"):
        validate_package(package)


def test_corrupt_manifest_hash_is_detected(package: Path):
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    manifest["file_hashes"]["products.csv"] = "0" * 64
    write_json(package / "manifest.json", manifest)
    with pytest.raises(ExportValidationError, match="Manifest hash mismatch"):
        validate_package(package)


def test_product_ids_use_stable_kaida_format(package: Path):
    assert all(
        row["product_id"].startswith("KAIDA-P") and len(row["product_id"]) == 11
        for row in package_rows(package, "products.csv")
    )


def test_source_tree_is_not_mutated(root: Path, package: Path):
    assert package.exists()
    assert (root / "kb" / "seed" / "products.csv").exists()
    assert not (root / "kb" / "seed" / "products.csv").read_text(encoding="utf-8").startswith("product_id,\n")


def _refresh_hash(package: Path, filename: str) -> None:
    from kb.io import file_sha256

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    manifest["file_hashes"][filename] = file_sha256(package / filename)
    write_json(package / "manifest.json", manifest)


def _file_bytes(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }
