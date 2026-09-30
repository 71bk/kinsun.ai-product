"""Bounded statute spelling normalization; no semantic expansion or scope changes."""

from __future__ import annotations

import re
import unicodedata

VERSION = "legal-spelling-v1"
_NUMBER = r"[0-9〇零一二兩三四五六七八九十百]+"
_ARTICLE = re.compile(rf"第\s*({_NUMBER})(?:\s*[-之]\s*({_NUMBER}))?\s*條(?:\s*之\s*({_NUMBER}))?")
_DIGITS = {char: value for value, char in enumerate("零一二三四五六七八九")}
_DIGITS.update({"〇": 0, "兩": 2})


def _number(value: str) -> str | None:
    if value.isascii() and value.isdigit():
        return str(int(value)) if len(value) <= 3 and 0 < int(value) < 1000 else None
    # Reject ambiguous/malformed mixtures rather than guessing an article number.
    if any(char.isascii() for char in value):
        return None
    if all(char in _DIGITS for char in value):
        number = int("".join(str(_DIGITS[char]) for char in value))
        return str(number) if 0 < number < 1000 else None
    digit_pattern = r"[一二兩三四五六七八九]"
    tens = rf"{digit_pattern}?十{digit_pattern}?"
    hundreds = rf"{digit_pattern}百(?:零{digit_pattern}|{digit_pattern}十{digit_pattern}?)?"
    if not re.fullmatch(rf"(?:{tens}|{hundreds})", value):
        return None
    total, digit = 0, 0
    for char in value:
        if char in _DIGITS:
            digit = _DIGITS[char]
        else:
            total += (digit or 1) * {"十": 10, "百": 100}[char]
            digit = 0
    number = total + digit
    return str(number) if 0 < number < 1000 else None


def normalize_legal_query(query: str) -> str:
    """Match corpus locators such as 第 8-1 條, preserving unsupported spelling.

    Only retrieval queries use this; the original user message remains unchanged.
    Reject expansion beyond the wire query bound by returning the original input.
    """
    if len(query) > 2000:
        return query
    normalized = unicodedata.normalize("NFKC", query)
    normalized = normalized.replace("長照服務法", "長期照顧服務法").replace(
        "長照法", "長期照顧服務法"
    )

    def replace(match: re.Match) -> str:
        number, before, after = match.groups()
        if before and after:
            return match.group()
        primary = _number(number)
        secondary = _number(before or after) if before or after else None
        if primary is None or ((before or after) and secondary is None):
            return match.group()
        return f"第 {primary}{'-' + secondary if secondary else ''} 條"

    normalized = _ARTICLE.sub(replace, normalized)
    return normalized if len(normalized) <= 2000 else query
