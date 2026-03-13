from __future__ import annotations


def normalize_unit_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
