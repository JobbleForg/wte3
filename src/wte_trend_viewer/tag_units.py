from __future__ import annotations

import re


_SUPERSCRIPT_CHARACTERS = str.maketrans(
    {
        "0": "\u2070",
        "1": "\u00b9",
        "2": "\u00b2",
        "3": "\u00b3",
        "4": "\u2074",
        "5": "\u2075",
        "6": "\u2076",
        "7": "\u2077",
        "8": "\u2078",
        "9": "\u2079",
        "+": "\u207a",
        "-": "\u207b",
    }
)


def normalize_unit_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    if not text:
        return None
    return _apply_superscript_formatting(text)


def display_unit_text(value: object) -> str | None:
    unit = normalize_unit_text(value)
    if unit is None:
        return None
    return f"[{unit}]"


def normalize_unit_list(values: list[object] | tuple[object, ...]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        unit = normalize_unit_text(raw_value)
        if unit is None:
            continue
        key = unit.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(unit)
    return normalized


def _apply_superscript_formatting(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        exponent = match.group(1)
        return exponent.translate(_SUPERSCRIPT_CHARACTERS)

    return re.sub(r"\^([0-9+-]+)", replace, text)
