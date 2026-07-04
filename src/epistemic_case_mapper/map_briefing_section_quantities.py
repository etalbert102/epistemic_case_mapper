from __future__ import annotations

from typing import Any


def section_quantitative_anchors(title_key: str, scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    cards = [card for card in scaffold.get("quantitative_evidence_cards", []) if isinstance(card, dict)]
    if cards:
        return _section_quantity_cards(title_key, cards)
    anchors = [row for row in scaffold.get("quantitative_anchors", []) if isinstance(row, dict)]
    if "limit" in title_key:
        return []
    limit = 6 if "evidence carrying" in title_key else 4 if "crux" in title_key or "why this read" in title_key else 3
    return [
        {
            "quantity_text": row.get("quantity_text"),
            "quantity_type": row.get("quantity_type"),
            "source": row.get("source"),
            "context_window": _short_text(str(row.get("context_window", "")), 240),
        }
        for row in anchors[:limit]
    ]


def _section_quantity_cards(title_key: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if "limit" in title_key:
        return []
    limit = 6 if "evidence carrying" in title_key else 4 if "crux" in title_key or "why this read" in title_key else 3
    return [
        {
            "evidence_use": card.get("evidence_use"),
            "key_quantities": card.get("key_quantities", [])[:6],
            "source": card.get("source"),
            "interpretation_hint": card.get("interpretation_hint"),
            "context": _short_text(str(card.get("context", "")), 260),
        }
        for card in cards[:limit]
    ]


def _short_text(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."
