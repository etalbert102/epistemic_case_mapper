from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_global_plan import section_plan_for_title


def compile_model_section_packet(title: str, contract: dict[str, Any]) -> dict[str, Any]:
    """Build the compact synthesis input shown to the model for one memo section.

    The full section synthesis packet remains useful as a debug artifact, but it
    repeats the same evidence through several views. This compiler turns it into
    one section-local instruction packet with clear ownership boundaries.
    """
    scaffold = (
        contract.get("_section_synthesis_scaffold", {})
        if isinstance(contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    title_key = title.lower()
    packet = contract.get("section_synthesis_packet", {}) if isinstance(contract.get("section_synthesis_packet"), dict) else {}
    section_plan = _compact_section_plan(section_plan_for_title(scaffold, title), contract)
    owned_evidence = _owned_evidence(contract)
    fallback_thesis = _section_thesis(title_key, contract, packet)
    section_thesis = str(section_plan.get("thesis") or fallback_thesis).strip()
    if _uses_evidence_owned_elsewhere(section_thesis, contract):
        section_plan.pop("thesis", None)
        section_thesis = fallback_thesis if not _uses_evidence_owned_elsewhere(fallback_thesis, contract) else ""
    model_packet = {
        "schema_id": "model_section_packet_v1",
        "global_section_plan": section_plan,
        "section_thesis": section_thesis,
        "target_shape": _target_shape(title_key),
        "owned_evidence": owned_evidence,
        "reference_only_evidence": _reference_only_evidence(contract),
        "must_include_quantities": _must_include_quantities(contract),
        "local_tensions": _local_tensions(packet) if _section_should_receive_tensions(title_key) else [],
        "canonical_cruxes": _canonical_cruxes(contract, packet),
        "style_instruction": packet.get("style_instruction") or _default_style_instruction(title_key),
    }
    return _drop_empty(model_packet)


def _compact_section_plan(plan: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or not plan:
        return {}
    owned_ids = set(_section_obligation_ids(contract))
    compact = _drop_empty(
        {
            "thesis": plan.get("thesis"),
            "target_words": plan.get("target_words"),
            "owned_obligation_ids": [
                item for item in _string_list(plan.get("owned_obligation_ids"))
                if item in owned_ids
            ],
            "owned_evidence_roles": _string_list(plan.get("owned_evidence_roles")),
            "cross_reference_only": _string_list(plan.get("cross_reference_only"))[:6],
            "omit_or_appendix": _string_list(plan.get("omit_or_appendix"))[:6],
            "transition_goal": plan.get("transition_goal"),
        }
    )
    for key in ("thesis", "transition_goal"):
        if key in compact and _uses_evidence_owned_elsewhere(str(compact.get(key, "")), contract):
            compact.pop(key, None)
    return compact


def select_section_cruxes(full_contract: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    scaffold = (
        full_contract.get("_section_synthesis_scaffold", {})
        if isinstance(full_contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    candidates: list[dict[str, Any]] = []
    artifacts = scaffold.get("decision_argument_artifacts", {}) if isinstance(scaffold.get("decision_argument_artifacts"), dict) else {}
    structured = artifacts.get("structured_decision_cruxes", {}) if isinstance(artifacts.get("structured_decision_cruxes"), dict) else {}
    candidates.extend(row for row in structured.get("cruxes", []) if isinstance(row, dict))
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    candidates.extend(row for row in synthesis.get("cruxes", []) if isinstance(row, dict))
    argument = scaffold.get("argument_model", {}) if isinstance(scaffold.get("argument_model"), dict) else {}
    candidates.extend(_argument_crux_to_decision_crux(row) for row in argument.get("cruxes", []) if isinstance(row, dict))
    required = full_contract.get("required_cruxes", []) if isinstance(full_contract.get("required_cruxes"), list) else []
    candidates.extend(row for row in required if isinstance(row, dict))
    return _best_cruxes(candidates, limit=limit)


def compact_main_memo_obligations(rows: Any, *, limit: int = 5) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        item = {
            "obligation_id": row.get("obligation_id"),
            "category": row.get("category"),
            "statement": _short_text(str(row.get("statement", "")), 220),
            "search_terms": _string_list(row.get("search_terms"))[:4],
            "satisfied_by": "faithful paraphrase or one listed search term",
        }
        compact.append(_drop_empty(item))
    return compact[:limit]


def _section_thesis(title_key: str, contract: dict[str, Any], packet: dict[str, Any]) -> str:
    job = str(contract.get("section_job", "")).strip()
    goal = str(packet.get("section_goal", "")).strip()
    if job and "smooth this section" not in job.lower() and not _looks_like_instruction(job):
        return job
    if goal and not _looks_like_instruction(goal):
        return goal
    return ""


def _looks_like_instruction(text: str) -> bool:
    lowered = str(text).strip().lower()
    return lowered.startswith(
        (
            "name ",
            "explain ",
            "translate ",
            "separate ",
            "state ",
            "convert ",
            "group ",
            "write ",
            "improve ",
        )
    )


def _target_shape(title_key: str) -> str:
    if "decision brief" in title_key:
        return "One short answer paragraph, then a confidence line."
    if "practical read" in title_key:
        return "Two short paragraphs or up to four practical bullets."
    if "why this read" in title_key:
        return "Two paragraphs: reasoning path first, key tension second."
    if "evidence carrying" in title_key:
        return "Two to three evidence-cluster paragraphs; avoid claim-by-claim lists."
    if "scope" in title_key or "exception" in title_key:
        return "A short default-scope paragraph followed by compact boundary bullets."
    if "crux" in title_key:
        return "A three-row crux table with concrete decision-changing conditions."
    if "limit" in title_key:
        return "A short paragraph plus bullets for named gaps or failure modes."
    return "One compact section with no repeated source-level detail."


def _owned_evidence(contract: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in contract.get("required_evidence", []) if isinstance(row, dict)]
    compact: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        claim = _short_text(str(row.get("claim", "")), 260)
        key = _normalize_key(claim)
        if not claim or key in seen:
            continue
        seen.add(key)
        compact.append(
            _drop_empty(
                {
                    "slot": row.get("slot"),
                    "claim": claim,
                    "source": row.get("source"),
                    "anchor_terms": _string_list(row.get("anchor_terms"))[:6],
                    "intended_role": _intended_role(row),
                    "reason_for_inclusion": _reason_for_inclusion(row),
                    "use": "This section may explain this evidence fully.",
                }
            )
        )
    return compact[:5]


def _intended_role(row: dict[str, Any]) -> str:
    slot = str(row.get("slot") or row.get("section") or row.get("evidence_role") or "").lower()
    if any(term in slot for term in ("counter", "conflict", "tension", "challenge")):
        return "counterweight"
    if any(term in slot for term in ("scope", "limit", "exception", "boundary")):
        return "scope boundary"
    if any(term in slot for term in ("quant", "effect", "estimate", "anchor")):
        return "quantitative anchor"
    if any(term in slot for term in ("practical", "recommend", "action")):
        return "practical implication"
    if any(term in slot for term in ("confidence", "uncertain", "method")):
        return "uncertainty/confidence driver"
    return "support"


def _reason_for_inclusion(row: dict[str, Any]) -> str:
    slot = str(row.get("slot") or "owned evidence").strip()
    source = str(row.get("source") or "").strip()
    reason = f"This card is assigned to this section as {slot}."
    if source:
        reason += f" It is anchored to {source}."
    return reason


def _reference_only_evidence(contract: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in contract.get("evidence_references", []) if isinstance(contract.get("evidence_references"), list) else []:
        if not isinstance(row, dict) or row.get("allowed") is False:
            continue
        refs.append(
            _drop_empty(
                {
                    "slot": row.get("slot"),
                    "owner_section": row.get("owner_section"),
                    "reference_style": row.get("reference_style"),
                    "instruction": row.get("reference_instruction"),
                    "role_summary": row.get("role_summary"),
                }
            )
        )
    return refs[:4]


def _must_include_quantities(contract: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for obligation in contract.get("required_main_memo_obligations", []) if isinstance(contract.get("required_main_memo_obligations"), list) else []:
        if not isinstance(obligation, dict) or obligation.get("category") != "quantitative_anchor":
            continue
        terms = _string_list(obligation.get("search_terms"))
        rows.append(
            _drop_empty(
                {
                    "obligation_id": obligation.get("obligation_id"),
                    "statement": _short_text(str(obligation.get("statement", "")), 220),
                    "key_terms": terms[:4],
                    "reason": _short_text(str(obligation.get("reason", "")), 160),
                }
            )
        )
    return _dedupe_dicts(rows)[:4]


def _section_obligation_ids(contract: dict[str, Any]) -> list[str]:
    return [
        str(row.get("obligation_id", "")).strip()
        for row in contract.get("required_main_memo_obligations", [])
        if isinstance(row, dict) and str(row.get("obligation_id", "")).strip()
    ]


def _section_should_receive_tensions(title_key: str) -> bool:
    return "evidence carrying" in title_key or "crux" in title_key


def _local_tensions(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidates: list[Any] = []
    candidates.extend(packet.get("central_tensions", []) if isinstance(packet.get("central_tensions"), list) else [])
    synthesis = packet.get("decision_synthesis", {}) if isinstance(packet.get("decision_synthesis"), dict) else {}
    candidates.extend(synthesis.get("central_tensions", []) if isinstance(synthesis.get("central_tensions"), list) else [])
    for item in candidates:
        if not isinstance(item, dict):
            continue
        rows.append(
            _drop_empty(
                {
                    "tension": _short_text(str(item.get("tension") or _pair_tension(item)), 180),
                    "why_it_matters": _short_text(str(item.get("why_it_matters") or item.get("why_reasonable_people_disagree") or ""), 220),
                    "current_resolution": _short_text(str(item.get("current_resolution") or item.get("rationale") or ""), 240),
                    "would_change_if": _short_text(str(item.get("would_change_if") or item.get("failure_condition") or ""), 220),
                }
            )
        )
    return _dedupe_dicts(rows)[:2]


def _canonical_cruxes(contract: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    candidates.extend(row for row in contract.get("required_cruxes", []) if isinstance(row, dict))
    synthesis = packet.get("decision_synthesis", {}) if isinstance(packet.get("decision_synthesis"), dict) else {}
    candidates.extend(row for row in synthesis.get("cruxes", []) if isinstance(row, dict))
    argument = packet.get("argument_model", {}) if isinstance(packet.get("argument_model"), dict) else {}
    candidates.extend(_argument_crux_to_decision_crux(row) for row in argument.get("cruxes", []) if isinstance(row, dict))
    return _best_cruxes(candidates, limit=3)


def _argument_crux_to_decision_crux(row: dict[str, Any]) -> dict[str, Any]:
    statement = str(row.get("statement") or row.get("crux") or "").strip()
    return _drop_empty(
        {
            "crux": statement,
            "why_it_matters": row.get("why_it_matters"),
            "current_read": row.get("current_read") or statement,
            "would_change_if": row.get("would_change_if"),
            "claim_ids": row.get("claim_ids"),
            "relation_ids": row.get("relation_ids"),
            "source_ids": row.get("source_ids"),
        }
    )


def _best_cruxes(candidates: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, row in enumerate(candidates):
        crux = _clean_sentence(str(row.get("crux") or row.get("statement") or ""))
        current = _clean_sentence(str(row.get("current_read") or ""))
        would_change = _clean_sentence(str(row.get("would_change_if") or ""))
        if not crux:
            continue
        if not current or not would_change:
            continue
        normalized = _drop_empty(
            {
                "crux": crux,
                "why_it_matters": _clean_sentence(str(row.get("why_it_matters") or row.get("decision_effect") or "")),
                "current_read": current,
                "would_change_if": would_change,
                "crux_type": row.get("crux_type"),
                "claim_ids": _string_list(row.get("claim_ids") or row.get("supporting_claim_ids"))[:4],
                "relation_ids": _string_list(row.get("relation_ids"))[:3],
                "source_ids": _string_list(row.get("source_ids"))[:4],
                "finding_ids": _string_list(row.get("supporting_finding_ids"))
                + _string_list(row.get("challenging_finding_ids")),
            }
        )
        scored.append((_crux_specificity_score(normalized), -index, normalized))
    ordered = sorted(scored, key=lambda item: (-item[0], item[1]))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, _index, row in ordered:
        if score <= 0:
            continue
        key = _normalize_key(str(row.get("crux", "")))
        semantic_key = _normalize_key(f"{row.get('crux_type', '')} {row.get('would_change_if', '')}")
        if not key or key in seen or (semantic_key and semantic_key in seen):
            continue
        seen.add(key)
        if semantic_key:
            seen.add(semantic_key)
        deduped.append(_model_facing_crux(row))
        if len(deduped) >= limit:
            break
    return deduped


def _model_facing_crux(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "crux": row.get("crux"),
            "why_it_matters": row.get("why_it_matters"),
            "current_read": row.get("current_read"),
            "would_change_if": row.get("would_change_if"),
            "crux_type": row.get("crux_type"),
        }
    )


def _crux_specificity_score(row: dict[str, Any]) -> int:
    text = " ".join(str(row.get(key, "")) for key in ("crux", "current_read", "would_change_if", "why_it_matters")).lower()
    score = 0
    if row.get("claim_ids"):
        score += 3
    if row.get("relation_ids"):
        score += 3
    if row.get("source_ids"):
        score += 1
    if row.get("finding_ids"):
        score += 2
    if row.get("would_change_if"):
        score += 2
    score += min(4, len(set(_content_terms(text))) // 6)
    if any(marker in text for marker in ("confound", "adjust", "proxy", "biomarker", "mechanism", "dose", "population", "subgroup", "comparator", "endpoint", "implementation", "capacity", "constraint")):
        score += 3
    if _generic_crux_text(text):
        score -= 12
    return score


def _generic_crux_text(text: str) -> bool:
    generic_phrases = (
        "whether method or validity is a separate exception",
        "whether the evidence favors the unfavorable",
        "whether the evidence favors the neutral",
        "leading alternative",
        "diagnostic evidence consistently supported this read",
        "current packet treats this condition",
    )
    return any(phrase in text for phrase in generic_phrases)


def _pair_tension(item: dict[str, Any]) -> str:
    left = item.get("left", {}) if isinstance(item.get("left"), dict) else {}
    right = item.get("right", {}) if isinstance(item.get("right"), dict) else {}
    left_claim = str(left.get("claim", "")).strip()
    right_claim = str(right.get("claim", "")).strip()
    if left_claim and right_claim:
        return f"{_short_text(left_claim, 100)} versus {_short_text(right_claim, 100)}"
    return ""


def _default_style_instruction(title_key: str) -> str:
    if "crux" in title_key:
        return "Use concrete crux names and decision-changing conditions."
    if "evidence" in title_key:
        return "Synthesize by evidence role rather than listing isolated claims."
    return "Use polished human prose and avoid internal map terminology."


def _dedupe_dicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = _normalize_key(str(row))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ({}, [], "", None)}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _clean_sentence(text: str) -> str:
    cleaned = _short_text(text, 320).strip(" .")
    return cleaned + "." if cleaned else ""


def _normalize_key(text: str) -> str:
    return " ".join(_content_terms(text))


def _uses_evidence_owned_elsewhere(text: str, contract: dict[str, Any]) -> bool:
    cleaned = str(text).strip()
    if not cleaned:
        return False
    rows = contract.get("owned_elsewhere_evidence", [])
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        policy = row.get("reference_policy", {}) if isinstance(row.get("reference_policy"), dict) else {}
        if str(policy.get("reference_style", "")).strip() == "full":
            continue
        if _evidence_text_overlap(cleaned, str(row.get("claim", ""))):
            return True
    return False


def _evidence_text_overlap(text: str, claim: str) -> bool:
    text_terms = set(_content_terms(text))
    claim_terms = set(_content_terms(claim))
    if not text_terms or not claim_terms:
        return False
    overlap = text_terms & claim_terms
    distinctive = {term for term in overlap if term not in _GENERIC_EVIDENCE_TERMS}
    if len(distinctive) >= 2:
        return True
    if len(overlap) >= 3 and len(overlap) >= min(5, max(3, len(claim_terms) // 3)):
        return True
    text_lower = text.lower()
    claim_lower = claim.lower()
    for phrase in _distinctive_phrases(claim_lower):
        if phrase in text_lower:
            return True
    return False


def _distinctive_phrases(text: str) -> list[str]:
    phrases = []
    for match in re.findall(r"\b[a-z]+(?:-[a-z]+|/[a-z]+)+\b", text):
        if len(match) >= 6:
            phrases.append(match)
    for match in re.findall(r"\b(?:[a-z0-9]{4,}\s+){1,3}[a-z0-9]{4,}\b", text):
        terms = set(_content_terms(match))
        if len(terms - _GENERIC_EVIDENCE_TERMS) >= 2:
            phrases.append(match.strip())
    return phrases[:8]


def _content_terms(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "into",
        "than",
        "when",
        "where",
        "which",
        "should",
        "would",
        "could",
        "current",
        "read",
        "recommendation",
        "evidence",
        "claim",
        "source",
    }
    return [term for term in re.findall(r"[a-z0-9]{4,}", text.lower()) if term not in stop]


_GENERIC_EVIDENCE_TERMS = {
    "associated",
    "association",
    "consumption",
    "evidence",
    "impact",
    "intervention",
    "interventions",
    "profiles",
    "risk",
    "study",
    "studies",
}
