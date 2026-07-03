from __future__ import annotations

import re


def reader_facing_practical_items(items: list[str]) -> list[str]:
    """Convert internal practical instructions into memo-facing bullets."""
    cleaned = _drop_weaker_duplicate_boundaries([_reader_facing_practical_item(item) for item in items])
    seen: set[str] = set()
    result: list[str] = []
    for item in cleaned:
        key = re.sub(r"\W+", " ", item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _reader_facing_practical_item(item: str) -> str:
    text = re.sub(r"\s+", " ", item).strip().rstrip(".")
    lowered = text.lower()
    state_match = re.match(r"state the default as (.+?)(?:;\s*do not frame the default as (.+))?$", text, flags=re.IGNORECASE)
    if state_match:
        default = state_match.group(1).strip()
        forbidden = state_match.group(2)
        condition = "" if "under the stated conditions" in default.lower() else " under the stated conditions"
        sentence = f"The default practical read is {default}{condition}"
        if forbidden:
            sentence += f"; it should not be treated as {forbidden.strip()}"
        return sentence + "."
    boundary_match = re.match(r"preserve this dose/intensity boundary in practical guidance:\s*(.+)$", text, flags=re.IGNORECASE)
    if boundary_match:
        return f"The practical boundary to keep visible is {boundary_match.group(1).strip()}."
    subgroup_match = re.match(r"name this subgroup separately from the default case:\s*(.+)$", text, flags=re.IGNORECASE)
    if subgroup_match:
        return f"Treat {subgroup_match.group(1).strip()} as a separate subgroup rather than folding that group into the default case."
    if lowered.startswith("do not "):
        return text[:1].upper() + text[1:] + "."
    return text[:1].upper() + text[1:] + "." if text else ""


def _drop_weaker_duplicate_boundaries(items: list[str]) -> list[str]:
    boundary_items = [item for item in items if "practical boundary to keep visible is" in item.lower()]
    if len(boundary_items) < 2:
        return items
    preferred = _preferred_boundary(boundary_items)
    return [item for item in items if item not in boundary_items or item == preferred]


def _preferred_boundary(items: list[str]) -> str:
    def score(item: str) -> tuple[int, int]:
        lowered = item.lower()
        limiting = any(marker in lowered for marker in ("up to", "no more than", "less than", "≤", "<="))
        expansive = any(marker in lowered for marker in ("at least", "more than", "greater than", ">", "≥"))
        return (2 if limiting else 0) - (1 if expansive else 0), -len(item)

    return max(items, key=score)
