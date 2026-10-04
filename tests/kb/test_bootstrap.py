from pathlib import Path

import pytest

from bootstrap_kb_reference import (
    EXPECTED_SHA256,
    bootstrap,
    decision_records,
    file_sha256,
)


def test_reference_workbook_hash_and_bootstrap_fails_on_targetless_alias(
    root: Path, tmp_path: Path
):
    workbook = root / "reference" / "KAIDA_Master_KB_Iteration_3.xlsx"
    assert file_sha256(workbook) == EXPECTED_SHA256
    with pytest.raises(ValueError, match="RB02-X01.*ALIAS requires"):
        bootstrap(workbook, tmp_path / "kb")


def test_bootstrap_rejects_alias_without_resolvable_product_target():
    rows = [
        {
            "decision_id": "D-ALIAS-MISSING",
            "subject": "Alias title",
            "decision": "ALIAS",
            "canonical_or_old": "Missing Product",
        }
    ]
    with pytest.raises(ValueError, match="ALIAS requires an explicit resolvable"):
        decision_records(rows, [])
