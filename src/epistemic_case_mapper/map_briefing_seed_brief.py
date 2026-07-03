from __future__ import annotations

import re
from typing import Any


def deterministic_graph_claim_sentences(scaffold: dict[str, Any]) -> list[str]:
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    rows = graph_packet.get("load_bearing_claims", []) if isinstance(graph_packet.get("load_bearing_claims"), list) else []
    sentences = _sentences_from_rows(rows)
    if not sentences:
        ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
        evidence_rows = [row for row in ledger.get("all_evidence", []) if isinstance(row, dict)]
        ranked_rows = sorted(evidence_rows, key=lambda item: -int(item.get("score", 0)))
        sentences.extend(_sentences_from_rows(ranked_rows))
    sentences.extend(_seed_claim_sentences(scaffold, existing=sentences))
    return _dedupe(sentences)[:4]


def _sentences_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    sentences: list[str] = []
    for row in rows[:4]:
        claim = _brief_claim_text(str(row.get("claim", "")))
        source = str(row.get("source", "")).strip()
        if claim:
            sentences.append(claim + (f" ({source})." if source and source not in claim else "."))
    return sentences


def _seed_claim_sentences(scaffold: dict[str, Any], *, existing: list[str]) -> list[str]:
    source_lookup = scaffold.get("source_display_names", {}) if isinstance(scaffold.get("source_display_names"), dict) else {}
    sentences: list[str] = []
    for claim_row in scaffold.get("seed_claims", []) if isinstance(scaffold.get("seed_claims"), list) else []:
        if len(existing) + len(sentences) >= 4:
            break
        if not isinstance(claim_row, dict):
            continue
        claim = _brief_claim_text(str(claim_row.get("claim") or claim_row.get("text") or ""))
        if any(claim and claim in sentence for sentence in [*existing, *sentences]):
            continue
        source_id = str(claim_row.get("source_id", ""))
        source = str(source_lookup.get(source_id, "")).strip()
        if claim:
            sentences.append(claim + (f" ({source})." if source and source not in claim else "."))
    return sentences


def _brief_claim_text(text: str, max_chars: int = 260) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = re.sub(r"\s+", " ", item.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
