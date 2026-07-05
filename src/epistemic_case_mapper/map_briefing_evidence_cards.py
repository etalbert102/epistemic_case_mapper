from __future__ import annotations

import re
from collections import Counter
from typing import Any


def build_atomic_evidence_cards(
    candidate_map: dict[str, Any],
    evidence_ledger: dict[str, Any],
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    rows = [row for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)]
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in _claims(candidate_map)}
    cards = [
        _card_for_row(index, row, claim_lookup.get(str(row.get("claim_id", "")), {}), source_lookup)
        for index, row in enumerate(rows, start=1)
    ]
    return {
        "schema_id": "atomic_evidence_cards_v1",
        "method": "deterministic_claim_atomicity_noise_and_decision_proposition_normalization",
        "card_count": len(cards),
        "noise_counts": dict(Counter(flag for card in cards for flag in card.get("noise_flags", []))),
        "appendix_only_count": sum(1 for card in cards if card.get("appendix_only")),
        "cards": cards,
    }


def apply_evidence_cards_to_ledger(evidence_ledger: dict[str, Any], evidence_cards: dict[str, Any]) -> dict[str, Any]:
    cards = {
        str(card.get("claim_id", "")): card
        for card in evidence_cards.get("cards", [])
        if isinstance(card, dict) and str(card.get("claim_id", "")).strip()
    }
    updated = dict(evidence_ledger)
    rows = [_row_with_card(row, cards.get(str(row.get("claim_id", "")))) for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)]
    rows.sort(key=_row_rank)
    updated["all_evidence"] = rows
    updated["atomic_evidence_cards"] = {
        "schema_id": evidence_cards.get("schema_id"),
        "card_count": evidence_cards.get("card_count"),
        "appendix_only_count": evidence_cards.get("appendix_only_count"),
        "noise_counts": evidence_cards.get("noise_counts", {}),
    }
    by_section: dict[str, list[dict[str, Any]]] = {"main_support": [], "conflicting_evidence": [], "scope_limits": [], "method_limits": []}
    for row in rows:
        if row.get("appendix_only"):
            continue
        by_section.setdefault(str(row.get("section", "")), []).append(row)
    updated["top_evidence_by_section"] = {section: items[:6] for section, items in by_section.items()}
    updated["weight_counts"] = _counts(str(row.get("weight", "")) for row in rows)
    updated["eligibility_counts"] = _counts(_eligibility_bucket(row) for row in rows)
    updated["noise_counts"] = _counts(flag for row in rows for flag in _noise_flags(row))
    return updated


def apply_evidence_cards_to_quantity_ledger(quantity_ledger: dict[str, Any], evidence_cards: dict[str, Any]) -> dict[str, Any]:
    cards = {
        str(card.get("claim_id", "")): card
        for card in evidence_cards.get("cards", [])
        if isinstance(card, dict) and str(card.get("claim_id", "")).strip()
    }
    updated = dict(quantity_ledger)
    updated["quantities"] = [
        _quantity_row_with_proposition(row, cards.get(str(row.get("claim_id", ""))))
        for row in quantity_ledger.get("quantities", [])
        if isinstance(row, dict)
    ]
    updated["evidence_cards"] = [
        _quantity_card_with_proposition(card, cards.get(str(card.get("claim_id", ""))))
        for card in quantity_ledger.get("evidence_cards", [])
        if isinstance(card, dict)
    ]
    updated["top_quantitative_anchors"] = _top_quantity_anchors(updated["quantities"])
    return updated


def apply_evidence_cards_to_map(candidate_map: dict[str, Any], evidence_cards: dict[str, Any]) -> dict[str, Any]:
    cards = {
        str(card.get("claim_id", "")): card
        for card in evidence_cards.get("cards", [])
        if isinstance(card, dict) and str(card.get("claim_id", "")).strip()
    }
    updated = dict(candidate_map)
    updated["claims"] = [
        _claim_with_card(claim, cards.get(str(claim.get("claim_id", ""))))
        for claim in _claims(candidate_map)
    ]
    updated["relations"] = [
        _relation_with_cards(relation, cards)
        for relation in _relations(candidate_map)
    ]
    return updated


def _card_for_row(index: int, row: dict[str, Any], claim: dict[str, Any], source_lookup: dict[str, str]) -> dict[str, Any]:
    raw = str(row.get("claim") or claim.get("claim") or claim.get("text") or "").strip()
    source_id = str(claim.get("source_id", "") or row.get("source_id", ""))
    flags = _noise_flags_for_text(raw)
    proposition = _decision_proposition(raw, row, flags)
    decision_relevance = int(row.get("decision_relevance_score", 0) or 0)
    appendix_only = _appendix_only(flags, row, decision_relevance)
    if appendix_only:
        proposition = _appendix_proposition(flags)
    return {
        "card_id": f"ec{index:04d}",
        "claim_id": str(row.get("claim_id", "") or claim.get("claim_id", "")),
        "source_id": source_id,
        "source": source_lookup.get(source_id, str(row.get("source", ""))),
        "proposition": proposition,
        "raw_claim": raw,
        "evidence_role": str(row.get("section", "")),
        "evidence_family": str(row.get("evidence_family", "general_evidence")),
        "endpoint_type": _endpoint_type(row, raw),
        "population_scope": _population_scope(raw),
        "effect_or_finding": _effect_or_finding(raw),
        "limitations": _limitations(flags, row),
        "decision_relevance": decision_relevance,
        "noise_flags": flags,
        "appendix_only": appendix_only,
        "top_line_eligible": bool(row.get("top_line_eligible")) and not appendix_only and "overlong_claim" not in flags,
    }


def _row_with_card(row: dict[str, Any], card: dict[str, Any] | None) -> dict[str, Any]:
    if not card:
        return dict(row)
    updated = dict(row)
    flags = list(card.get("noise_flags", []))
    eligibility = dict(updated.get("eligibility", {}) if isinstance(updated.get("eligibility"), dict) else {})
    updated["raw_claim"] = updated.get("claim", "")
    updated["claim"] = card.get("proposition") or updated.get("claim", "")
    updated["atomic_evidence_card_id"] = card.get("card_id")
    updated["atomic_evidence_card"] = card
    updated["noise"] = _merge_noise(updated.get("noise"), flags)
    updated["top_line_eligible"] = bool(updated.get("top_line_eligible")) and bool(card.get("top_line_eligible"))
    if card.get("appendix_only"):
        updated["appendix_only"] = True
        eligibility["appendix_only"] = True
        updated["score"] = min(int(updated.get("score", 0) or 0), 2)
        updated["weight"] = "low"
        updated.setdefault("modifiers", []).append("atomic_card:appendix_only")
    elif flags:
        updated["score"] = min(int(updated.get("score", 0) or 0), 5)
        updated["weight"] = _weight_label(int(updated["score"]))
        updated.setdefault("modifiers", []).append("atomic_card:noise_penalty")
    updated["eligibility"] = eligibility
    return updated


def _quantity_card_with_proposition(card: dict[str, Any], evidence_card: dict[str, Any] | None) -> dict[str, Any]:
    if not evidence_card:
        return dict(card)
    updated = dict(card)
    updated["raw_claim"] = updated.get("claim", "")
    updated["claim"] = evidence_card.get("proposition") or updated.get("claim", "")
    updated["atomic_evidence_card_id"] = evidence_card.get("card_id")
    if evidence_card.get("appendix_only") and updated.get("evidence_use") == "study scale or follow-up context":
        updated["appendix_only"] = True
        updated["evidence_use"] = "appendix quantitative context"
        updated["card_score"] = min(int(updated.get("card_score", 0) or 0), 3)
    return updated


def _quantity_row_with_proposition(row: dict[str, Any], evidence_card: dict[str, Any] | None) -> dict[str, Any]:
    if not evidence_card:
        return dict(row)
    updated = dict(row)
    updated["raw_claim"] = updated.get("claim", "")
    updated["claim"] = evidence_card.get("proposition") or updated.get("claim", "")
    updated["atomic_evidence_card_id"] = evidence_card.get("card_id")
    if evidence_card.get("appendix_only"):
        updated["appendix_only"] = True
        updated["relevance_score"] = min(int(updated.get("relevance_score", 0) or 0), 2)
    return updated


def _claim_with_card(claim: dict[str, Any], card: dict[str, Any] | None) -> dict[str, Any]:
    if not card:
        return dict(claim)
    updated = dict(claim)
    updated["raw_claim"] = updated.get("claim", "")
    updated["claim"] = card.get("proposition") or updated.get("claim", "")
    updated["atomic_evidence_card_id"] = card.get("card_id")
    updated["atomic_noise_flags"] = card.get("noise_flags", [])
    if card.get("appendix_only"):
        updated["appendix_only"] = True
    return updated


def _relation_with_cards(relation: dict[str, Any], cards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    left = cards.get(str(relation.get("source_claim", "")))
    right = cards.get(str(relation.get("target_claim", "")))
    if not left and not right:
        return dict(relation)
    updated = dict(relation)
    raw_rationale = str(updated.get("rationale", "")).strip()
    if raw_rationale and _relation_rationale_needs_rewrite(raw_rationale):
        updated["raw_rationale"] = raw_rationale
        updated["rationale"] = _relation_proposition(
            left,
            right,
            str(updated.get("relation_type", "")),
            raw_rationale,
        )
    if left:
        updated["source_anchor_a"] = _shorten(str(left.get("proposition", "")), 160)
    if right:
        updated["source_anchor_b"] = _shorten(str(right.get("proposition", "")), 160)
    return updated


def _decision_proposition(text: str, row: dict[str, Any], flags: list[str]) -> str:
    sentences = _sentences(text)
    if not sentences:
        return text
    if "overlong_claim" not in flags and "multi_finding_claim" not in flags:
        return _clean_sentence(sentences[0])
    ranked = sorted(sentences, key=lambda sentence: _sentence_rank(sentence, row), reverse=True)
    selected = [sentence for sentence in ranked if not _method_only(sentence)][:2] or ranked[:1]
    proposition = " ".join(_clean_sentence(sentence) for sentence in selected)
    return _shorten(proposition, 360)


def _appendix_proposition(flags: list[str]) -> str:
    severe = {flag.replace("_", " ") for flag in flags if flag in {"fragment_or_truncation", "malformed_prose"}}
    if severe:
        return "Appendix-only extraction with malformed or fragmentary prose; consult the source before using it as evidence."
    return "Appendix-only extraction with low atomicity or low decision relevance; use only as source context."


def _relation_proposition(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
    relation_type: str,
    raw_rationale: str,
) -> str:
    relation = relation_type.replace("_", " ").strip() or "relates to"
    left_text = _relation_endpoint_text(left)
    right_text = _relation_endpoint_text(right)
    if left_text and right_text:
        return _shorten(f"{left_text} {relation} {right_text}", 360)
    if left_text:
        return _shorten(f"{left_text} {relation} the paired claim.", 260)
    if right_text:
        return _shorten(f"The paired claim {relation} {right_text}", 260)
    return _shorten(raw_rationale, 260)


def _relation_endpoint_text(card: dict[str, Any] | None) -> str:
    if not card or card.get("appendix_only"):
        return ""
    return str(card.get("proposition", "")).strip()


def _relation_rationale_needs_rewrite(text: str) -> bool:
    return bool(
        re.search(r"\bClaim [AB]\b|\b[cCrR]\d{3,}\b", text)
        or _noise_flags_for_text(text)
    )


def _sentence_rank(sentence: str, row: dict[str, Any]) -> int:
    lower = sentence.lower()
    score = 0
    score += 5 if any(term in lower for term in ("associated", "reduced", "increased", "lower", "higher", "risk", "outcome", "mortality", "events")) else 0
    score += 3 if any(term in lower for term in ("not significant", "confidence interval", "95%", "hr", "rr", "or ")) else 0
    score += 2 if any(term in lower for term in ("subgroup", "diabetes", "population", "compared", "replacement", "substitut")) else 0
    score -= 5 if _method_only(sentence) else 0
    score -= 2 if "recruited" in lower and "associated" not in lower else 0
    score += int(row.get("decision_relevance_score", 0) or 0)
    return score


def _noise_flags_for_text(text: str) -> list[str]:
    words = re.findall(r"\w+", text)
    sentences = _sentences(text)
    flags: list[str] = []
    if len(words) > 55 or len(text) > 420:
        flags.append("overlong_claim")
    if len(sentences) >= 3:
        flags.append("multi_finding_claim")
    if _method_only(text):
        flags.append("method_or_population_description")
    if text.startswith(("...", ",", ";", ":", ")")) or "..." in text or re.search(r"\brespectively\.\s+in\b", text, flags=re.I):
        flags.append("fragment_or_truncation")
    if _malformed_prose(text):
        flags.append("malformed_prose")
    return flags


def _appendix_only(flags: list[str], row: dict[str, Any], decision_relevance: int) -> bool:
    if "fragment_or_truncation" in flags or "malformed_prose" in flags:
        return True
    if "method_or_population_description" in flags and decision_relevance < 8:
        return True
    if "overlong_claim" in flags and not row.get("top_line_eligible"):
        return True
    return False


def _method_only(text: str) -> bool:
    lower = text.lower()
    method_markers = ("recruited", "assessed by", "models", "adjusted for", "analysis plan", "entry criteria", "data were analyzed", "questionnaire")
    finding_markers = ("associated", "reduced", "increased", "lower", "higher", "risk", "mortality", "events", "not significant")
    return sum(marker in lower for marker in method_markers) >= 2 and not any(marker in lower for marker in finding_markers)


def _malformed_prose(text: str) -> bool:
    lower = text.lower()
    return bool(re.search(r"\bpopulation\b.{0,40}\bhave increased\b", lower) or re.search(r"\bWHO\b", text))


def _endpoint_type(row: dict[str, Any], text: str) -> str:
    concepts = set(str(item) for item in row.get("decision_concepts", []) if isinstance(item, str))
    lower = text.lower()
    if "hard_outcome_endpoint" in concepts or any(term in lower for term in ("mortality", "cvd events", "hospitalization", "stroke")):
        return "hard_or_decision_relevant_outcome"
    if "surrogate_or_biomarker_endpoint" in concepts or any(term in lower for term in ("biomarker", "marker", "concentration")):
        return "biomarker_or_surrogate"
    if "dose_or_threshold" in concepts:
        return "dose_or_exposure"
    return "unspecified"


def _population_scope(text: str) -> str:
    match = re.search(r"\b(?:people|patients|participants|adults|children|households|schools)\s+with\s+[^.;,]{3,90}", text, flags=re.I)
    return _clean_sentence(match.group(0)) if match else ""


def _effect_or_finding(text: str) -> str:
    for sentence in _sentences(text):
        if _sentence_rank(sentence, {}) >= 5:
            return _shorten(_clean_sentence(sentence), 260)
    return _shorten(_clean_sentence(_sentences(text)[0]) if _sentences(text) else text, 260)


def _limitations(flags: list[str], row: dict[str, Any]) -> list[str]:
    limitations = [flag.replace("_", " ") for flag in flags]
    if row.get("appendix_only"):
        limitations.append("appendix only in original evidence ledger")
    if not row.get("top_line_eligible"):
        limitations.append("not top line eligible")
    return limitations[:5]


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip()) if item.strip()]


def _clean_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = cleaned.replace("WHO", "who")
    return cleaned.rstrip(" ,;")


def _shorten(text: str, max_chars: int) -> str:
    cleaned = _clean_sentence(text)
    return cleaned if len(cleaned) <= max_chars else cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _merge_noise(existing: Any, flags: list[str]) -> dict[str, Any]:
    base = dict(existing) if isinstance(existing, dict) else {}
    existing_flags = [str(item) for item in base.get("flags", []) if str(item).strip()] if isinstance(base.get("flags"), list) else []
    merged = sorted(set(existing_flags + flags))
    base["flags"] = merged
    base["kind"] = "none" if not merged else "high" if any(flag in merged for flag in ("fragment_or_truncation", "malformed_prose")) else "medium"
    return base


def _row_rank(row: dict[str, Any]) -> tuple[int, int, int, int, str, str]:
    return (
        1 if row.get("appendix_only") else 0,
        0 if row.get("top_line_eligible") else 1,
        -int(row.get("score", 0)),
        -int(row.get("decision_relevance_score", 0) or 0),
        str(row.get("section", "")),
        str(row.get("claim_id", "")),
    )


def _eligibility_bucket(row: dict[str, Any]) -> str:
    if row.get("appendix_only"):
        return "appendix_only"
    if row.get("top_line_eligible"):
        return "top_line_eligible"
    if row.get("crux_eligible"):
        return "crux_eligible"
    return "body_only"


def _noise_flags(row: dict[str, Any]) -> list[str]:
    noise = row.get("noise", {}) if isinstance(row.get("noise"), dict) else {}
    return [str(flag) for flag in noise.get("flags", []) if str(flag).strip()] if isinstance(noise.get("flags"), list) else []


def _weight_label(score: int) -> str:
    if score >= 8:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _top_quantity_anchors(rows: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    usable = [
        row for row in rows
        if isinstance(row, dict) and not row.get("appendix_only") and row.get("quantity_type") != "year_or_date"
    ]
    ranked = sorted(usable, key=lambda row: (-int(row.get("relevance_score", 0)), str(row.get("source", "")), str(row.get("claim_id", ""))))
    anchors: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in ranked:
        key = (str(row.get("quantity_text", "")).lower(), str(row.get("claim_id", "")), str(row.get("source", "")))
        if key in seen:
            continue
        seen.add(key)
        anchors.append(
            {
                "quantity_text": row.get("quantity_text"),
                "quantity_type": row.get("quantity_type"),
                "source": row.get("source"),
                "claim_id": row.get("claim_id"),
                "claim": row.get("claim"),
                "relevance_score": row.get("relevance_score"),
            }
        )
        if len(anchors) >= limit:
            break
    return anchors


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    claims = candidate_map.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    relations = candidate_map.get("relations", [])
    return [relation for relation in relations if isinstance(relation, dict)] if isinstance(relations, list) else []
