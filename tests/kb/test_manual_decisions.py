from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from kb.resolver import Resolver


APPROVED_PRODUCT_ID = "KAIDA-P0265"
PROVISIONAL_PRODUCT_ID = "KAIDA-P0817"


def decision(
    decision_id: str,
    scope: str,
    action: str,
    *,
    product_id: str = "",
    authority: str = "USER",
    attributes: dict | None = None,
    **extra,
) -> dict:
    record = {
        "decision_id": decision_id,
        "scope": scope,
        "category_condition": "",
        "context_condition": "",
        "action": action,
        "product_id": product_id,
        "product_name": "",
        "reference_product_name": "",
        "attributes": attributes or {},
        "confidence": "HIGH" if authority == "USER" else "PROVISIONAL",
        "provenance": "test",
        "rationale": "test",
        "authority": authority,
    }
    record.update(extra)
    return record


def resolver_with_decisions(
    root: Path, tmp_path: Path, decisions: list[dict]
) -> Resolver:
    kb_dir = tmp_path / "kb"
    shutil.copytree(root / "kb" / "seed", kb_dir / "seed")
    payload = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
        for item in decisions
    )
    (kb_dir / "manual_decisions.jsonl").write_text(payload, encoding="utf-8")
    return Resolver(kb_dir, [])


@pytest.mark.parametrize(
    ("action", "product_id", "expected_status", "expected_product_id"),
    [
        ("MAP_EXISTING", APPROVED_PRODUCT_ID, "MAPPED", APPROVED_PRODUCT_ID),
        ("OUT_OF_SCOPE", "", "OUT_OF_SCOPE", ""),
        ("MALFORMED", "", "MALFORMED", ""),
        ("DEFER", "", "UNRESOLVED", ""),
        ("ATTRIBUTES_ONLY", APPROVED_PRODUCT_ID, "MAPPED", APPROVED_PRODUCT_ID),
        ("CREATE_PRODUCT_CANDIDATE", "", "PRODUCT_CANDIDATE", ""),
        ("ALIAS", APPROVED_PRODUCT_ID, "MAPPED", APPROVED_PRODUCT_ID),
    ],
)
def test_each_manual_decision_action_is_executable(
    root: Path,
    tmp_path: Path,
    action: str,
    product_id: str,
    expected_status: str,
    expected_product_id: str,
):
    title = f"Тестовое решение {action}"
    record = decision(
        f"D-{action}",
        title,
        action,
        product_id=product_id,
        attributes={"test_attribute": action},
        reference_product_name="Legacy candidate",
    )
    resolver = resolver_with_decisions(root, tmp_path, [record])

    result = resolver.resolve(title, "Тестовая категория")

    assert result.mapping_status == expected_status
    assert result.canonical_product_id == expected_product_id
    assert result.attributes["test_attribute"] == action
    assert result.matched_rule_id == f"D-{action}"
    if action == "CREATE_PRODUCT_CANDIDATE":
        assert result.legacy_candidate_name == "Legacy candidate"


def test_targetless_attributes_only_is_unresolved(root: Path, tmp_path: Path):
    action = "ATTRIBUTES_ONLY"
    title = "Решение без base Product"
    resolver = resolver_with_decisions(
        root, tmp_path, [decision(f"D-{action}", title, action)]
    )
    result = resolver.resolve(title, "Тестовая категория")
    assert result.mapping_status == "UNRESOLVED"
    assert result.canonical_product_id == ""


@pytest.mark.parametrize("action", ["MAP_EXISTING", "ALIAS", "ATTRIBUTES_ONLY"])
def test_manual_target_never_promotes_provisional_product(
    root: Path, tmp_path: Path, action: str
):
    title = f"Предварительный продукт {action}"
    resolver = resolver_with_decisions(
        root,
        tmp_path,
        [decision(f"D-PROVISIONAL-{action}", title, action, product_id=PROVISIONAL_PRODUCT_ID)],
    )
    result = resolver.resolve(title, "Десерты")
    assert result.mapping_status == "PROVISIONAL_MAPPING"
    assert result.canonical_product_id == PROVISIONAL_PRODUCT_ID


def test_defer_prevents_reference_or_exact_fallback(root: Path, tmp_path: Path):
    resolver = resolver_with_decisions(
        root, tmp_path, [decision("D-DEFER", "Молоко коровье", "DEFER")]
    )
    result = resolver.resolve("Молоко коровье", "Молочные продукты")
    assert result.mapping_status == "UNRESOLVED"
    assert result.canonical_product_id == ""
    assert result.mapping_method == "MANUAL_DEFER"


def test_defer_prevents_classifier_fallback(root: Path, tmp_path: Path):
    title = "Чай, Кофе, Какао"
    resolver = resolver_with_decisions(
        root, tmp_path, [decision("D-DEFER-CLASSIFIER", title, "DEFER")]
    )
    result = resolver.resolve(title, "Чай, Кофе")
    assert result.mapping_status == "UNRESOLVED"
    assert result.canonical_product_id == ""
    assert result.mapping_method == "MANUAL_DEFER"


def test_same_authority_conflict_fails_safe_to_defer(root: Path, tmp_path: Path):
    title = "Конфликтующее решение"
    resolver = resolver_with_decisions(
        root,
        tmp_path,
        [
            decision("D-1", title, "MAP_EXISTING", product_id=APPROVED_PRODUCT_ID),
            decision("D-2", title, "DEFER"),
        ],
    )
    result = resolver.resolve(title, "Тестовая категория")
    assert result.mapping_status == "UNRESOLVED"
    assert result.canonical_product_id == ""
    assert result.mapping_method == "MANUAL_DEFER"


def test_user_decision_precedes_ai_provisional(root: Path, tmp_path: Path):
    title = "Решение с приоритетом"
    resolver = resolver_with_decisions(
        root,
        tmp_path,
        [
            decision("D-AI", title, "DEFER", authority="AI_PROVISIONAL"),
            decision(
                "D-USER", title, "MAP_EXISTING", product_id=APPROVED_PRODUCT_ID
            ),
        ],
    )
    result = resolver.resolve(title, "Тестовая категория")
    assert result.mapping_status == "MAPPED"
    assert result.canonical_product_id == APPROVED_PRODUCT_ID


@pytest.mark.parametrize("field", ["category_condition", "context_condition"])
def test_unimplemented_decision_condition_is_rejected(
    root: Path, tmp_path: Path, field: str
):
    record = decision("D-CONDITION", "Условное решение", "DEFER")
    record[field] = "not empty"
    with pytest.raises(ValueError, match=f"{field} is not implemented"):
        resolver_with_decisions(root, tmp_path, [record])


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (decision("D-UNKNOWN", "Неизвестное действие", "SURPRISE"), "unsupported action"),
        (decision("D-MAP", "Нет цели", "MAP_EXISTING"), "requires product_id"),
        (decision("D-ALIAS", "Alias без цели", "ALIAS"), "ALIAS requires product_id"),
        (
            decision("D-DEFER", "Лишняя цель", "DEFER", product_id=APPROVED_PRODUCT_ID),
            "must not define canonical product_id",
        ),
        (
            decision("D-MISSING", "Несуществующая цель", "MAP_EXISTING", product_id="NOPE"),
            "target Product does not exist",
        ),
        (
            decision("D-ALIAS-MISSING", "Alias с неверной целью", "ALIAS", product_id="NOPE"),
            "target Product does not exist",
        ),
    ],
)
def test_invalid_manual_decision_is_fatal(
    root: Path, tmp_path: Path, record: dict, message: str
):
    with pytest.raises(ValueError, match=message):
        resolver_with_decisions(root, tmp_path, [record])
