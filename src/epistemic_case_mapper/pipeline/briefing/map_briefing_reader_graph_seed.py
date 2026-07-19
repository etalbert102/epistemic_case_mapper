from __future__ import annotations

import re
from typing import Any


def reader_graph_seed_decision_brief(scaffold: dict[str, Any]) -> str:
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    claims = [row for row in graph_packet.get("load_bearing_claims", []) if isinstance(row, dict)]
    if not claims:
        clusters = [row for row in graph_packet.get("issue_clusters", []) if isinstance(row, dict)]
        for cluster in clusters[:2]:
            claims.extend(row for row in cluster.get("representative_claims", []) if isinstance(row, dict))
    if not claims:
        return ""
    first = _claim_sentence_for_reader(claims[0])
    second = _claim_sentence_for_reader(claims[1]) if len(claims) > 1 else ""
    return _join_sentences(
        [
            "The current map supports a scoped decision read.",
            first,
            second,
        ],
        max_sentences=3,
    )


def _claim_sentence_for_reader(row: dict[str, Any]) -> str:
    claim = _first_complete_sentence(_clean_text(str(row.get("claim", "")), max_chars=280))
    source = str(row.get("source", "")).strip()
    if not claim:
        return ""
    return claim.rstrip(".") + (f" ({source})." if source and source not in claim else ".")


def _first_complete_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return parts[0].strip() if parts and parts[0].strip() else text.strip()


def _clean_text(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _join_sentences(items: list[str], *, max_sentences: int) -> str:
    cleaned = []
    for item in items:
        text = _clean_text(item, max_chars=320).strip()
        if not text:
            continue
        cleaned.append(text.rstrip(".") + ".")
        if len(cleaned) >= max_sentences:
            break
    return " ".join(cleaned)
