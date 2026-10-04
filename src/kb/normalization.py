"""Normalization shared by collection probes and the KB resolver."""

from __future__ import annotations

import re


NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")
MEASUREMENT_TOKEN_RE = re.compile(
    r"(?<!\w)\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?\s*"
    r"(?:кг|kg|гр|г|g|мл|ml|л|l|шт)\b",
    re.IGNORECASE,
)
PERCENT_TOKEN_RE = re.compile(r"(?<!\d)\d+(?:[.,]\d+)?\s*%")
CALIBRE_TOKEN_RE = re.compile(r"(?<!\d)\d{1,3}\s*/\s*\d{1,3}(?!\d)")
PACK_COUNT_RE = re.compile(r"(?<!\d)\d+\s*[xх×]\s*\d+(?:[.,]\d+)?")


def normalize(text: str | None) -> str:
    """Match the legacy lowercase/ё/punctuation/whitespace semantics exactly."""
    value = (text or "").lower().replace("ё", "е")
    value = NON_WORD_RE.sub(" ", value)
    return WHITESPACE_RE.sub(" ", value).strip()


def identity_key(text: str | None) -> str:
    """Remove only non-identity quantity tokens, then apply legacy normalization."""
    value = text or ""
    value = MEASUREMENT_TOKEN_RE.sub(" ", value)
    value = PERCENT_TOKEN_RE.sub(" ", value)
    value = CALIBRE_TOKEN_RE.sub(" ", value)
    value = PACK_COUNT_RE.sub(" ", value)
    return normalize(value)
