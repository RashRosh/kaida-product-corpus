"""Conservative entity/context classification before Product resolution."""

from __future__ import annotations

import re

from .normalization import normalize


OUT_OF_SCOPE_TERMS = {
    "коробки",
    "упаковка",
    "молды",
    "формы силиконовые",
    "пластик формы",
    "инвентарь",
    "посуда",
}
READY_CONTEXT_TERMS = {
    "блюда",
    "готов",
    "гарнир",
    "салат",
    "суп",
    "десерт",
    "пирож",
    "торт",
    "напит",
    "кофе",
    "чай",
    "лимонад",
    "фреш",
    "меню",
    "выпеч",
}
CATEGORY_HEADER_TITLES = {
    "гастрономия",
    "кондитерские изделия",
    "молочные продукты",
    "мясо",
    "овощи фрукты",
    "рыба",
    "напитки",
    "салаты",
    "десерты",
    "горячие напитки",
    "готовая еда",
    "чай кофе какао",
}
LIST_ITEM_RE = re.compile(r"(?:^|[,;|/])\s*[а-яәіңғүұқөһa-z][^,;|/]{2,}", re.I)


def contains_term(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def looks_malformed_list(title: str) -> bool:
    normalized = normalize(title)
    separators = sum(title.count(char) for char in (",", ";", "|"))
    listed_items = len(LIST_ITEM_RE.findall(title))
    salad_mentions = normalized.count("салат")
    return (
        (len(title) >= 140 and separators >= 4)
        or listed_items >= 7
        or (salad_mentions >= 4 and separators >= 3)
    )


def classify(raw_title: str, categories: str) -> tuple[str, float, str]:
    title = normalize(raw_title)
    context = normalize(categories)
    if looks_malformed_list(raw_title):
        return "MALFORMED", 0.99, "MULTI_PRODUCT_LIST"
    if title in CATEGORY_HEADER_TITLES and (
        not context or title in context or title.rstrip("ыи") in context
    ):
        return "CATEGORY_HEADER", 0.99, "CATEGORY_HEADER"
    if contains_term(context, OUT_OF_SCOPE_TERMS):
        return "OUT_OF_SCOPE", 0.99, "NON_FOOD_CONTEXT"
    if contains_term(context, READY_CONTEXT_TERMS):
        return "READY_DISH", 0.9, "PREPARED_CONTEXT"
    return "PRODUCT", 0.75, "DEFAULT_PRODUCT_CANDIDATE"


DOMAIN_TERMS = {
    "MEAT": {"мяс", "говяд", "свинин", "баран", "птиц", "куриц", "колбас"},
    "FISH": {"рыб", "лосос", "кревет", "икр", "морепродукт"},
    "DAIRY": {"молоч", "молоко", "сыр", "творог", "сметан", "сливк", "йогурт"},
    "PRODUCE": {"овощ", "фрукт", "яблок", "картоф", "зелень"},
    "BAKERY": {"хлеб", "выпеч", "пирог", "торт", "десерт", "круассан"},
    "DRINK": {"напит", "кофе", "чай", "лимонад", "сок", "фреш", "какао"},
    "GROCERY": {"бакале", "круп", "рис", "макарон", "мука"},
}


def domains(*values: str) -> set[str]:
    text = normalize(" ".join(values))
    return {
        domain
        for domain, terms in DOMAIN_TERMS.items()
        if any(term in text for term in terms)
    }


def context_compatible(
    categories: str,
    raw_title: str,
    product_category_code: str,
    product_category_ru: str,
) -> bool:
    observed = domains(categories, raw_title)
    product = domains(product_category_code, product_category_ru)
    if not observed or not product:
        return False
    return bool(observed.intersection(product))
