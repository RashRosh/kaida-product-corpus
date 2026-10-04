"""Load and evaluate versioned declarative resolution rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .normalization import normalize


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    action: str
    entity_class: str
    product_id: str
    product_name: str
    confidence: float
    provenance: str
    attributes: dict[str, Any]


def load_rules(path: Path) -> list[dict[str, Any]]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = value.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("kb/rules.yaml must contain a rules list")
    return sorted(rules, key=lambda item: (-int(item.get("priority", 0)), item["id"]))


def _matches(
    rule: dict[str, Any], raw_title: str, categories: str
) -> re.Match[str] | None | bool:
    when = rule.get("when", {})
    title = normalize(raw_title)
    context = normalize(categories)
    title_regex = when.get("title_regex")
    title_match = re.search(title_regex, title, re.IGNORECASE) if title_regex else True
    if not title_match:
        return False
    category_any = [normalize(value) for value in when.get("category_any", [])]
    if category_any and not any(value in context for value in category_any):
        return False
    category_none = [normalize(value) for value in when.get("category_none", [])]
    if category_none and any(value in context for value in category_none):
        return False
    return title_match


def match_rule(
    rules: list[dict[str, Any]], raw_title: str, categories: str
) -> RuleMatch | None:
    for rule in rules:
        title_match = _matches(rule, raw_title, categories)
        if not rule.get("enabled", True) or not title_match:
            continue
        attributes = dict(rule.get("attributes", {}))
        if isinstance(title_match, re.Match):
            for key, group_number in rule.get("capture_attributes", {}).items():
                attributes[key] = title_match.group(int(group_number)).strip()
        return RuleMatch(
            rule_id=rule["id"],
            action=rule["action"],
            entity_class=rule.get("entity_class", ""),
            product_id=rule.get("product_id", ""),
            product_name=rule.get("product_name", ""),
            confidence=float(rule.get("confidence", 0.0)),
            provenance=rule.get("provenance", "kb/rules.yaml"),
            attributes=attributes,
        )
    return None
