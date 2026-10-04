"""Conservative, context-aware Product resolver."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .classifier import classify, context_compatible
from .io import read_csv, read_jsonl
from .measurements import extract_measurements
from .normalization import normalize
from .rules import RuleMatch, match_rule


APPROVED_PRODUCT_STATUSES = {"LEGACY_APPROVED"}
SUPPORTED_DECISION_ACTIONS = {
    "MAP_EXISTING",
    "OUT_OF_SCOPE",
    "MALFORMED",
    "DEFER",
    "ATTRIBUTES_ONLY",
    "CREATE_PRODUCT_CANDIDATE",
    "ALIAS",
}
TARGET_OPTIONAL_ACTIONS = {"ALIAS", "ATTRIBUTES_ONLY"}
TARGET_FORBIDDEN_ACTIONS = {
    "OUT_OF_SCOPE",
    "MALFORMED",
    "DEFER",
    "CREATE_PRODUCT_CANDIDATE",
}


@dataclass
class Resolution:
    raw_title: str
    normalized_title: str
    entity_class: str
    canonical_product_id: str = ""
    canonical_name: str = ""
    mapping_status: str = "UNRESOLVED"
    mapping_method: str = "NONE"
    confidence: float = 0.0
    provenance: str = ""
    matched_rule_id: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    legacy_candidate_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["attributes_json"] = json.dumps(
            value.pop("attributes"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        value["confidence"] = f"{self.confidence:.2f}"
        return value


def _words(value: str) -> set[str]:
    return {word for word in normalize(value).split() if len(word) >= 4}


def _reference_context_compatible(observed: str, reference: str) -> bool:
    observed_words = _words(observed)
    reference_words = _words(reference)
    return bool(observed_words and reference_words and observed_words & reference_words)


class Resolver:
    def __init__(self, kb_dir: Path, rules: list[dict[str, Any]]):
        self.kb_dir = kb_dir
        self.rules = rules
        _, products = read_csv(kb_dir / "seed" / "products.csv")
        _, aliases = read_csv(kb_dir / "seed" / "aliases.csv")
        _, reference_mappings = read_csv(kb_dir / "seed" / "reference_mappings.csv")
        self.decisions = read_jsonl(kb_dir / "manual_decisions.jsonl")
        self.products = {row["product_id"]: row for row in products}
        self._validate_decisions()
        self.canonical_index: dict[str, list[dict[str, str]]] = {}
        for product in products:
            self.canonical_index.setdefault(
                normalize(product.get("canonical_name_ru", "")), []
            ).append(product)
            kk_name = normalize(product.get("canonical_name_kk", ""))
            if kk_name:
                self.canonical_index.setdefault(kk_name, []).append(product)

        self.alias_index: dict[str, list[dict[str, str]]] = {}
        for alias in aliases:
            if alias.get("status") not in {"ACTIVE", "ACTIVE_GUARDED"}:
                continue
            self.alias_index.setdefault(normalize(alias.get("alias", "")), []).append(alias)

        self.reference_mapping_index: dict[str, list[dict[str, str]]] = {}
        for mapping in reference_mappings:
            self.reference_mapping_index.setdefault(
                normalize(mapping.get("raw_title", "")), []
            ).append(mapping)

        self.decision_index: dict[str, list[dict[str, Any]]] = {}
        for decision in self.decisions:
            for raw_scope in str(decision.get("scope", "")).splitlines():
                scope = normalize(raw_scope)
                if scope:
                    self.decision_index.setdefault(scope, []).append(decision)

    def _validate_decisions(self) -> None:
        seen_ids: set[str] = set()
        errors = []
        for line_number, decision in enumerate(self.decisions, start=1):
            decision_id = str(decision.get("decision_id", "")).strip()
            action = str(decision.get("action", "")).strip()
            product_id = str(decision.get("product_id", "")).strip()
            if not decision_id:
                errors.append(f"line {line_number}: decision_id is required")
            elif decision_id in seen_ids:
                errors.append(f"{decision_id}: duplicate decision_id")
            seen_ids.add(decision_id)
            if action not in SUPPORTED_DECISION_ACTIONS:
                errors.append(
                    f"{decision_id or f'line {line_number}'}: unsupported action {action!r}; "
                    f"supported actions: {', '.join(sorted(SUPPORTED_DECISION_ACTIONS))}"
                )
                continue
            if not str(decision.get("scope", "")).strip():
                errors.append(f"{decision_id}: scope is required")
            for condition_field in ("category_condition", "context_condition"):
                if str(decision.get(condition_field, "")).strip():
                    errors.append(
                        f"{decision_id}: {condition_field} is not implemented; "
                        "leave it empty or promote the condition to kb/rules.yaml"
                    )
            if action == "MAP_EXISTING" and not product_id:
                errors.append(f"{decision_id}: MAP_EXISTING requires product_id")
            if action in TARGET_FORBIDDEN_ACTIONS and product_id:
                errors.append(
                    f"{decision_id}: {action} must not define canonical product_id"
                )
            if product_id and product_id not in self.products:
                errors.append(
                    f"{decision_id}: target Product does not exist: {product_id}"
                )
            attributes = decision.get("attributes", {})
            if not isinstance(attributes, dict):
                errors.append(f"{decision_id}: attributes must be an object")
        if errors:
            raise ValueError("Invalid manual_decisions.jsonl:\n- " + "\n- ".join(errors))

    def _selected_decision(self, normalized_title: str) -> dict[str, Any] | None:
        decisions = self.decision_index.get(normalized_title, [])
        if not decisions:
            return None
        authority_rank = {"USER": 2, "AI_PROVISIONAL": 1}
        best_rank = max(authority_rank.get(item.get("authority", ""), 0) for item in decisions)
        highest = [
            item
            for item in decisions
            if authority_rank.get(item.get("authority", ""), 0) == best_rank
        ]
        signatures = {
            (
                item["action"],
                item.get("product_id", ""),
                json.dumps(item.get("attributes", {}), sort_keys=True),
            )
            for item in highest
        }
        if len(signatures) > 1:
            decision_ids = sorted(item["decision_id"] for item in highest)
            return {
                "decision_id": "CONFLICT:" + ",".join(decision_ids),
                "action": "DEFER",
                "product_id": "",
                "product_name": "",
                "reference_product_name": "",
                "attributes": {},
                "confidence": "PROVISIONAL",
                "provenance": "Conflicting manual decisions",
                "authority": "CONFLICT",
            }
        return sorted(highest, key=lambda item: item["decision_id"])[0]

    def _from_decision(
        self,
        decision: dict[str, Any],
        raw_title: str,
        entity_class: str,
    ) -> Resolution:
        action = decision["action"]
        decision_id = decision["decision_id"]
        provenance = decision.get("provenance", "manual_decisions.jsonl")
        confidence = 1.0 if decision.get("confidence") == "HIGH" else 0.5
        attributes = extract_measurements(raw_title)
        attributes.update(decision.get("attributes", {}))

        if action == "MAP_EXISTING" or (
            action in TARGET_OPTIONAL_ACTIONS and decision.get("product_id")
        ):
            return self._product_mapping(
                raw_title,
                entity_class,
                decision["product_id"],
                f"MANUAL_{action}",
                confidence,
                provenance,
                decision_id,
                attributes,
            )

        status_by_action = {
            "OUT_OF_SCOPE": ("OUT_OF_SCOPE", "OUT_OF_SCOPE"),
            "MALFORMED": ("MALFORMED", "MALFORMED"),
            "DEFER": ("UNRESOLVED", entity_class),
            "ATTRIBUTES_ONLY": ("UNRESOLVED", entity_class),
            "CREATE_PRODUCT_CANDIDATE": ("PRODUCT_CANDIDATE", entity_class),
            "ALIAS": ("UNRESOLVED", entity_class),
        }
        mapping_status, resolved_class = status_by_action[action]
        return Resolution(
            raw_title=raw_title,
            normalized_title=normalize(raw_title),
            entity_class=resolved_class,
            mapping_status=mapping_status,
            mapping_method=f"MANUAL_{action}",
            confidence=confidence,
            provenance=provenance,
            matched_rule_id=decision_id,
            attributes=attributes,
            legacy_candidate_name=decision.get("reference_product_name", ""),
        )

    def _product_mapping(
        self,
        raw_title: str,
        entity_class: str,
        product_id: str,
        method: str,
        confidence: float,
        provenance: str,
        rule_id: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> Resolution:
        product = self.products.get(product_id)
        if not product:
            return Resolution(
                raw_title=raw_title,
                normalized_title=normalize(raw_title),
                entity_class=entity_class,
                mapping_status="UNRESOLVED",
                mapping_method="INVALID_PRODUCT_REFERENCE",
                confidence=0.0,
                provenance=provenance,
                matched_rule_id=rule_id,
                attributes=attributes or extract_measurements(raw_title),
            )
        status = product.get("status", "")
        mapping_status = (
            "MAPPED" if status in APPROVED_PRODUCT_STATUSES else "PROVISIONAL_MAPPING"
        )
        return Resolution(
            raw_title=raw_title,
            normalized_title=normalize(raw_title),
            entity_class=entity_class or product.get("entity_class", "PRODUCT"),
            canonical_product_id=product_id,
            canonical_name=product.get("canonical_name_ru", ""),
            mapping_status=mapping_status,
            mapping_method=method,
            confidence=confidence,
            provenance=provenance,
            matched_rule_id=rule_id,
            attributes=attributes or extract_measurements(raw_title),
        )

    def _from_rule(
        self, rule: RuleMatch, raw_title: str, categories: str, default_class: str
    ) -> Resolution:
        entity_class = rule.entity_class or default_class
        attributes = extract_measurements(raw_title)
        attributes.update(rule.attributes)
        if rule.action == "MAP_EXISTING":
            return self._product_mapping(
                raw_title,
                entity_class,
                rule.product_id,
                "RULE",
                rule.confidence,
                rule.provenance,
                rule.rule_id,
                attributes,
            )
        status_by_action = {
            "OUT_OF_SCOPE": "OUT_OF_SCOPE",
            "MALFORMED": "MALFORMED",
            "CREATE_PRODUCT_CANDIDATE": "PRODUCT_CANDIDATE",
            "DEFER": "UNRESOLVED",
            "ATTRIBUTES_ONLY": "UNRESOLVED",
        }
        return Resolution(
            raw_title=raw_title,
            normalized_title=normalize(raw_title),
            entity_class=entity_class,
            canonical_name=rule.product_name,
            mapping_status=status_by_action.get(rule.action, "UNRESOLVED"),
            mapping_method=f"RULE_{rule.action}",
            confidence=rule.confidence,
            provenance=rule.provenance,
            matched_rule_id=rule.rule_id,
            attributes=attributes,
        )

    def resolve(self, raw_title: str, categories: str) -> Resolution:
        normalized = normalize(raw_title)
        entity_class, class_confidence, class_reason = classify(raw_title, categories)
        attributes = extract_measurements(raw_title)

        rule = match_rule(self.rules, raw_title, categories)
        if rule:
            return self._from_rule(rule, raw_title, categories, entity_class)

        decision = self._selected_decision(normalized)
        if decision:
            return self._from_decision(decision, raw_title, entity_class)

        if entity_class in {"MALFORMED", "CATEGORY_HEADER", "OUT_OF_SCOPE"}:
            status = "OUT_OF_SCOPE" if entity_class == "CATEGORY_HEADER" else entity_class
            return Resolution(
                raw_title=raw_title,
                normalized_title=normalized,
                entity_class=entity_class,
                mapping_status=status,
                mapping_method="CLASSIFIER",
                confidence=class_confidence,
                provenance=class_reason,
                attributes=attributes,
            )

        candidates = []
        for mapping in self.reference_mapping_index.get(normalized, []):
            if mapping.get("entity_class") != entity_class:
                continue
            if not _reference_context_compatible(categories, mapping.get("categories", "")):
                continue
            product_id = mapping.get("mapped_product_id", "")
            if product_id in self.products:
                candidates.append(mapping)
        product_ids = {item.get("mapped_product_id", "") for item in candidates}
        if len(product_ids) == 1:
            candidate = sorted(candidates, key=lambda item: item.get("mapping_id", ""))[0]
            confidence = min(float(candidate.get("confidence") or 0.0), 0.99)
            return self._product_mapping(
                raw_title,
                entity_class,
                candidate["mapped_product_id"],
                "REFERENCE_MAPPING",
                confidence,
                "KAIDA_Master_KB_Iteration_3.xlsx:MAPPINGS",
                candidate.get("rule_id", ""),
                attributes,
            )

        exact_products = self.canonical_index.get(normalized, [])
        compatible_products = [
            product
            for product in exact_products
            if product.get("entity_class") == entity_class
            and context_compatible(
                categories,
                raw_title,
                product.get("category_code", ""),
                product.get("category_ru", ""),
            )
        ]
        if len(compatible_products) == 1:
            return self._product_mapping(
                raw_title,
                entity_class,
                compatible_products[0]["product_id"],
                "EXACT_CANONICAL_CONTEXT",
                0.99,
                "kb/seed/products.csv",
                attributes=attributes,
            )

        alias_products = []
        for alias in self.alias_index.get(normalized, []):
            if alias.get("safe_for_auto_match") != "YES":
                continue
            product = self.products.get(alias.get("product_id", ""))
            if not product or product.get("entity_class") != entity_class:
                continue
            if context_compatible(
                categories,
                raw_title,
                product.get("category_code", ""),
                product.get("category_ru", ""),
            ):
                alias_products.append(product)
        unique_alias_products = {product["product_id"]: product for product in alias_products}
        if len(unique_alias_products) == 1:
            product = next(iter(unique_alias_products.values()))
            return self._product_mapping(
                raw_title,
                entity_class,
                product["product_id"],
                "EXACT_ALIAS_CONTEXT",
                0.97,
                "kb/seed/aliases.csv",
                attributes=attributes,
            )

        legacy_candidate = ""
        lexical_candidates = exact_products or [
            self.products[item["product_id"]]
            for item in self.alias_index.get(normalized, [])
            if item.get("product_id") in self.products
        ]
        if len(lexical_candidates) == 1:
            legacy_candidate = lexical_candidates[0].get("canonical_name_ru", "")
        return Resolution(
            raw_title=raw_title,
            normalized_title=normalized,
            entity_class=entity_class,
            mapping_status="UNRESOLVED",
            mapping_method="CONTEXT_REQUIRED" if lexical_candidates else "NONE",
            confidence=0.0,
            provenance="No safe exact/rule/context match",
            attributes=attributes,
            legacy_candidate_name=legacy_candidate,
        )
