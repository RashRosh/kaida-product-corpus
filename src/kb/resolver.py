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
            scope = normalize(str(decision.get("scope", "")))
            if scope:
                self.decision_index.setdefault(scope, []).append(decision)

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

        for decision in self.decision_index.get(normalized, []):
            if decision.get("authority") != "USER" or decision.get("confidence") != "HIGH":
                continue
            if decision.get("action") == "MAP_EXISTING" and decision.get("product_id"):
                return self._product_mapping(
                    raw_title,
                    entity_class,
                    decision["product_id"],
                    "MANUAL_DECISION",
                    1.0,
                    decision.get("provenance", "manual_decisions.jsonl"),
                    decision.get("decision_id", ""),
                    attributes,
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
