import csv
from pathlib import Path

from bootstrap_kb_reference import EXPECTED_SHA256, bootstrap, file_sha256


def test_reference_workbook_hash_and_bootstrap(root: Path, tmp_path: Path):
    workbook = root / "reference" / "KAIDA_Master_KB_Iteration_3.xlsx"
    assert file_sha256(workbook) == EXPECTED_SHA256
    counts = bootstrap(workbook, tmp_path / "kb")
    assert counts["PRODUCTS"] == 868
    assert counts["ALIASES"] == 231
    with (tmp_path / "kb" / "seed" / "products.csv").open(encoding="utf-8", newline="") as handle:
        statuses = {row["status"] for row in csv.DictReader(handle)}
    assert "PROVISIONAL_AI" in statuses
    assert "LEGACY_APPROVED" in statuses
