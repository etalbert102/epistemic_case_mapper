from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.submission_manifest import WorkedRegion
from epistemic_case_mapper.synthesis_uplift_types import PacketSlot, RewriteRequirement


def _deterministic_requirement_coverage(synthesis: str, requirements: tuple[RewriteRequirement, ...]) -> dict[str, Any]:
    text = _normalize_for_coverage(synthesis)
    rows = []
    for req in requirements:
        term_hits = [term for term in req.required_terms if term in text]
        phrase_hits = [phrase for phrase in req.required_phrases if _phrase_present_in_synthesis(phrase, synthesis)]
        id_hits = [item for item in (*req.claim_ids, *req.relation_ids) if item.lower() in text]
        source_hits = [
            source_ref
            for source_ref in req.source_refs
            if source_ref.split()[0].lower() in text
        ]
        needed = min(4, max(2, len(req.required_terms) // 3))
        phrase_required = bool(req.required_phrases)
        phrase_ok = not phrase_required or bool(phrase_hits)
        if phrase_ok and (len(term_hits) >= needed or len(id_hits) >= 2):
            status = "clear"
        elif term_hits or id_hits or source_hits or phrase_hits:
            status = "partial"
        else:
            status = "missing"
        rows.append(
            {
                "requirement_id": req.requirement_id,
                "loss_id": req.loss_id,
                "status": status,
                "term_hits": term_hits,
                "phrase_hits": phrase_hits,
                "id_hits": id_hits,
                "source_hits": source_hits,
                "required_phrases": list(req.required_phrases),
                "required_terms": list(req.required_terms),
            }
        )
    return {
        "clear_count": sum(1 for row in rows if row["status"] == "clear"),
        "partial_count": sum(1 for row in rows if row["status"] == "partial"),
        "missing_count": sum(1 for row in rows if row["status"] == "missing"),
        "requirements": rows,
    }
def _needs_repair(coverage: dict[str, Any]) -> bool:
    return any(
        isinstance(row, dict) and row.get("status") != "clear"
        for row in coverage.get("requirements", [])
    )
def _phrase_present_in_synthesis(phrase: str, synthesis: str) -> bool:
    normalized_phrase = _normalize_for_coverage(phrase)
    normalized_synthesis = _normalize_for_coverage(synthesis)
    if normalized_phrase in normalized_synthesis:
        return True
    if _requires_exact_phrase_order(phrase):
        return False
    phrase_tokens = _content_token_set(phrase)
    if len(phrase_tokens) < 5:
        return False
    for segment in _reader_text_segments(synthesis):
        segment_tokens = _content_token_set(segment)
        if len(segment_tokens) < 4:
            continue
        overlap = len(phrase_tokens & segment_tokens) / len(phrase_tokens)
        if overlap >= 0.58:
            return True
    return False
def _requires_exact_phrase_order(phrase: str) -> bool:
    normalized = f" {_normalize_for_coverage(phrase)} "
    ordered_markers = (
        r"\bmay be\b.+\bthan\b",
        r"\brather than\b",
        r"\bslower\b.+\bthan\b",
        r"\bfaster\b.+\bthan\b",
        r"\bmore\b.+\bthan\b",
        r"\bless\b.+\bthan\b",
    )
    return any(re.search(marker, normalized) for marker in ordered_markers)
def _reader_text_segments(text: str) -> list[str]:
    segments = []
    for line in text.splitlines():
        stripped = line.strip(" -|\t")
        if not stripped or stripped.startswith("#") or stripped.startswith("|---"):
            continue
        segments.extend(
            segment.strip()
            for segment in re.split(r"(?<=[.!?])\s+|;\s+", stripped)
            if len(segment.split()) >= 4
        )
    return segments
def _accepted_synthesis(coverage: dict[str, Any]) -> str:
    map_only = coverage["map_only"]
    stress = coverage["stress_assisted"]
    if stress["clear_count"] > map_only["clear_count"]:
        return "stress_assisted"
    if stress["clear_count"] == map_only["clear_count"] and stress["partial_count"] > map_only["partial_count"]:
        return "stress_assisted"
    if stress["clear_count"] == map_only["clear_count"] and stress["partial_count"] == map_only["partial_count"]:
        return "tie"
    return "map_only"
def _requirements_prompt_block(requirements: tuple[RewriteRequirement, ...]) -> str:
    lines = []
    for req in requirements:
        refs = ", ".join(req.source_refs) or "no source refs recovered"
        ids = ", ".join((*req.claim_ids, *req.relation_ids)) or "no map IDs recovered"
        terms = ", ".join(req.required_terms[:8])
        phrases = " | ".join(req.required_phrases) or "none"
        anchors = " ".join(
            (
                "Claim anchors:",
                " | ".join(req.claim_anchors) or "none",
                "Relation anchors:",
                " | ".join(req.relation_anchors) or "none",
                "Reader anchors:",
                " | ".join(req.reader_anchors) or "none",
                "Relation types:",
                ", ".join(req.relation_types) or "none",
                "Claim roles:",
                ", ".join(req.claim_roles) or "none",
            )
        )
        lines.append(
            f"- {req.requirement_id} / {req.loss_id}: {req.instruction} "
            f"Anchors: {ids}. Source refs: {refs}. {anchors}. Coverage terms: {terms}."
            f" Directional phrases to preserve: {phrases}."
        )
    return "\n".join(lines)
def _packet_scaffold_prompt_block(requirements: tuple[RewriteRequirement, ...]) -> str:
    scaffold = _packet_scaffold(requirements)
    return json.dumps(scaffold, indent=2, ensure_ascii=True)
def _packet_scaffold(requirements: tuple[RewriteRequirement, ...]) -> dict[str, Any]:
    evidence_roles = {
        "main_support": [],
        "conflicting_evidence": [],
        "scope_limits": [],
        "method_limits": [],
    }
    for slot in _packet_slots_for_requirements(requirements):
        evidence_roles[slot.section].append(slot.text)
    for key, items in evidence_roles.items():
        evidence_roles[key] = _dedupe_text_items(items)
    audit_trail = [
        f"{req.loss_id}: {slot.text}"
        for req in requirements
        for slot in (_audit_slot_for_requirement(req),)
        if slot.text
    ]
    return {
        "purpose": "minimum map-backed packet content for the model to organize and phrase coherently",
        "evidence_roles": evidence_roles,
        "crux_candidates": _crux_candidates(requirements),
        "audit_trail": _dedupe_text_items(audit_trail),
        "forbidden_reader_language": [
            "flat baseline",
            "baseline failure",
            "explicitly avoid",
            "bare claim IDs",
            "bare relation IDs",
        ],
    }
def _crux_candidates(requirements: tuple[RewriteRequirement, ...]) -> list[dict[str, str]]:
    candidates = []
    requirement_lookup = {req.requirement_id: req for req in requirements}
    for slot in _packet_slots_for_requirements(requirements):
        if slot.section == "main_support":
            continue
        req = requirement_lookup.get(slot.requirement_id)
        candidates.append(
            {
                "candidate_crux": _short_text(slot.text, 140),
                "why_it_matters": _crux_why_it_matters(slot.section),
                "current_read": slot.text,
                "would_change_if": _crux_change_condition(slot.section, req),
            }
        )
        if len(candidates) >= 5:
            break
    return candidates
def _crux_why_it_matters(section: str) -> str:
    if section == "conflicting_evidence":
        return "It marks evidence that should not be collapsed into one bottom-line answer without resolving the disagreement."
    if section == "scope_limits":
        return "It bounds where the conclusion applies and prevents over-generalizing the packet."
    if section == "method_limits":
        return "It affects how strongly the evidence can support the decision."
    return "It is a load-bearing mapped distinction for the decision packet."
def _crux_change_condition(section: str, req: RewriteRequirement | None) -> str:
    anchor = ""
    if req is not None:
        anchor = _first_reader_anchor(req)
    if section == "conflicting_evidence":
        return "A stronger source or method comparison resolved this tension."
    if section == "scope_limits":
        return "The same claim was shown to apply outside the mapped scope boundary."
    if section == "method_limits":
        return "The mapped methodological limitation no longer applied to the evidence."
    if anchor:
        return "This mapped distinction no longer applied."
    return "A stronger source changed the mapped distinction."
def _requirement_dict(req: RewriteRequirement) -> dict[str, Any]:
    return {
        "requirement_id": req.requirement_id,
        "loss_id": req.loss_id,
        "loss_type": req.loss_type,
        "instruction": req.instruction,
        "claim_ids": list(req.claim_ids),
        "relation_ids": list(req.relation_ids),
        "source_refs": list(req.source_refs),
        "claim_anchors": list(req.claim_anchors),
        "relation_anchors": list(req.relation_anchors),
        "required_phrases": list(req.required_phrases),
        "required_terms": list(req.required_terms),
        "claim_roles": list(req.claim_roles),
        "relation_types": list(req.relation_types),
        "relation_rationales": list(req.relation_rationales),
        "reader_anchors": list(req.reader_anchors),
    }

def _claim_lookup(map_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = _worked_map_payload(map_payload)
    claims = payload.get("claims", []) if isinstance(payload, dict) else []
    return {
        claim["claim_id"]: claim
        for claim in claims
        if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)
    }
def _relation_lookup(map_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = _worked_map_payload(map_payload)
    relations = payload.get("relations", []) if isinstance(payload, dict) else []
    return {
        relation["relation_id"]: relation
        for relation in relations
        if isinstance(relation, dict) and isinstance(relation.get("relation_id"), str)
    }


def _worked_map_payload(map_payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(map_payload.get("worked_map"), dict):
        return map_payload["worked_map"]
    return map_payload
def _clean_required_phrase(text: str) -> str:
    text = re.sub(r"^[A-Za-z0-9_\-]+:\s*", "", text)
    text = re.sub(r"\brole=[^;]+", "", text)
    text = re.sub(r"\bsource=[^;]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .;")
    if len(text.split()) < 5:
        return ""
    if len(text) <= 220:
        return text
    return text[:220].rsplit(" ", 1)[0]

def _run_text_backend(prompt: str, backend: str, timeout_seconds: int, max_retries: int) -> str:
    result = run_model_backend(prompt, backend, timeout_seconds=timeout_seconds, max_retries=max_retries)
    return result.text.strip()
def _run_synthesis_backend(
    prompt: str,
    backend: str,
    timeout_seconds: int,
    max_retries: int,
    map_payload: dict[str, Any] | None = None,
    requirements: tuple[RewriteRequirement, ...] = (),
) -> str:
    raw = _run_text_backend(prompt, backend, timeout_seconds, max_retries)
    payload = _parse_json(raw)
    if isinstance(payload, dict) and (
        isinstance(payload.get("decision_brief"), str) or isinstance(payload.get("synthesis"), str)
    ):
        return _render_synthesis_packet(payload, map_payload=map_payload, requirements=requirements)
    if _looks_like_structured_packet_attempt(raw):
        return _render_unparsed_structured_packet(raw)
    return raw
def _render_synthesis_packet(
    payload: dict[str, Any],
    map_payload: dict[str, Any] | None = None,
    requirements: tuple[RewriteRequirement, ...] = (),
) -> str:
    anchor_lookup = _anchor_text_lookup(map_payload or {})
    decision_brief = _as_text(payload.get("decision_brief") or payload.get("synthesis"))
    confidence = _confidence_label(payload.get("confidence"))
    implications = _expand_map_ids(_string_list(payload.get("decision_implications")), anchor_lookup)
    cruxes = _crux_list(payload.get("top_cruxes"), anchor_lookup)
    evidence_roles = _evidence_roles(payload.get("evidence_roles"), anchor_lookup)
    _backfill_evidence_roles(evidence_roles, requirements)
    _dedupe_evidence_roles(evidence_roles)
    audit = _expand_map_ids(
        _string_list(payload.get("audit_trail")) or _string_list(payload.get("mapped_distinctions")),
        anchor_lookup,
    )
    audit = _audit_items(audit, requirements)
    caveats = _expand_map_ids(_string_list(payload.get("stress_caveats")), anchor_lookup)
    if not any((implications, cruxes, any(evidence_roles.values()), audit, caveats)):
        return decision_brief
    lines = [
        "## Decision Brief",
        "",
        decision_brief or "No decision brief returned.",
        "",
        f"**Confidence:** {confidence}",
        "",
        "## Decision Implications",
        "",
    ]
    if implications:
        lines.extend(f"- {item}" for item in implications)
    else:
        lines.append("- No decision implications returned.")
    lines.extend(
        [
            "",
            "## What Could Change the Decision",
            "",
            "| Crux | Why it matters | Current read | Would change if |",
            "|---|---|---|---|",
        ]
    )
    if cruxes:
        lines.extend(
            "| "
            + " | ".join(
                _table_cell(crux[key])
                for key in ("crux", "why_it_matters", "current_read", "would_change_if")
            )
            + " |"
            for crux in cruxes
        )
    else:
        lines.append(
            "| No crux returned | No crux explanation returned. | No current read returned. | No change condition returned. |"
        )
    lines.extend(["", "## Evidence Roles", ""])
    role_labels = (
        ("main_support", "Main Support"),
        ("conflicting_evidence", "Conflicting Evidence"),
        ("scope_limits", "Scope Limits"),
        ("method_limits", "Method Limits"),
    )
    for role_key, role_label in role_labels:
        lines.extend([f"### {role_label}", ""])
        role_items = evidence_roles[role_key]
        if role_items:
            lines.extend(f"- {item}" for item in role_items)
        else:
            lines.append(f"- No {role_label.lower()} returned.")
        lines.append("")
    lines.extend(["## Decision-Relevant Caveats", ""])
    if caveats:
        lines.extend(f"- {item}" for item in caveats)
    else:
        lines.append("- No stress caveats returned.")
    lines.extend(["", "## Audit Trail", ""])
    if audit:
        lines.extend(f"- {item}" for item in audit)
    else:
        lines.append("- No audit trail returned.")
    lines.append("")
    return "\n".join(lines)
def _looks_like_structured_packet_attempt(text: str) -> bool:
    stripped = text.strip()
    return (
        stripped.startswith("```json")
        or stripped.startswith("{")
        or '"decision_brief"' in stripped[:500]
        or '"evidence_roles"' in stripped[:1500]
    )
def _render_unparsed_structured_packet(text: str) -> str:
    brief = _extract_json_string_field(text, "decision_brief")
    confidence = _extract_json_string_field(text, "confidence") or "Not specified"
    return "\n".join(
        [
            "## Decision Brief",
            "",
            brief or "The model returned an incomplete structured packet, so this section needs regeneration.",
            "",
            f"**Confidence:** {_confidence_label(confidence)}",
            "",
            "## Decision Implications",
            "",
            "- Structured output was incomplete before decision implications could be parsed.",
            "",
            "## What Could Change the Decision",
            "",
            "| Crux | Why it matters | Current read | Would change if |",
            "|---|---|---|---|",
            "| Structured output incomplete | The model response could not be parsed as a complete packet. | Deterministic coverage repair will preserve required map distinctions below. | Regenerate with a larger output budget or a stricter shorter schema. |",
            "",
            "## Evidence Roles",
            "",
            "### Main Support",
            "",
            "- Structured output was incomplete before evidence roles could be parsed.",
            "",
            "### Conflicting Evidence",
            "",
            "- Structured output was incomplete before conflicting evidence could be parsed.",
            "",
            "### Scope Limits",
            "",
            "- Structured output was incomplete before scope limits could be parsed.",
            "",
            "### Method Limits",
            "",
            "- Structured output was incomplete before method limits could be parsed.",
            "",
            "## Decision-Relevant Caveats",
            "",
            "- Structured output was incomplete before caveats could be parsed.",
            "",
            "## Audit Trail",
            "",
            "- The model returned a truncated or invalid structured packet; deterministic repair should add required map-backed distinctions.",
            "",
        ]
    )
def _confidence_label(value: Any) -> str:
    if not isinstance(value, str):
        return "Not specified"
    normalized = value.strip().lower()
    return normalized if normalized in {"low", "medium", "high"} else value.strip() or "Not specified"
def _crux_list(value: Any, anchor_lookup: dict[str, str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        row = {
            "crux": _clean_reader_text(_expand_map_id_text(_as_text(item.get("crux")), anchor_lookup)),
            "why_it_matters": _clean_reader_text(_expand_map_id_text(_as_text(item.get("why_it_matters")), anchor_lookup)),
            "current_read": _clean_reader_text(_expand_map_id_text(_as_text(item.get("current_read")), anchor_lookup)),
            "would_change_if": _clean_reader_text(_expand_map_id_text(_as_text(item.get("would_change_if")), anchor_lookup)),
        }
        if any(row.values()):
            rows.append(row)
    return rows
def _evidence_roles(value: Any, anchor_lookup: dict[str, str]) -> dict[str, list[str]]:
    roles = {
        "main_support": [],
        "conflicting_evidence": [],
        "scope_limits": [],
        "method_limits": [],
    }
    if not isinstance(value, dict):
        return roles
    for key in roles:
        roles[key] = _expand_map_ids(_string_list(value.get(key)), anchor_lookup)
    return roles
def _backfill_evidence_roles(
    roles: dict[str, list[str]],
    requirements: tuple[RewriteRequirement, ...],
) -> None:
    for slot in _packet_slots_for_requirements(requirements):
        if _similar_item_exists(roles[slot.section], slot.text):
            continue
        if slot.text not in roles[slot.section]:
            roles[slot.section].append(slot.text)
def _dedupe_evidence_roles(roles: dict[str, list[str]]) -> None:
    seen: set[str] = set()
    for key in ("main_support", "conflicting_evidence", "scope_limits", "method_limits"):
        unique = []
        for item in roles[key]:
            normalized = _dedupe_key(item)
            if not normalized or normalized in seen or _similar_item_exists(unique, item):
                continue
            seen.add(normalized)
            unique.append(item)
        roles[key] = unique
def _dedupe_key(text: str) -> str:
    normalized = _normalize_for_coverage(text)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return normalized.strip()
def _packet_slots_for_requirements(requirements: tuple[RewriteRequirement, ...]) -> tuple[PacketSlot, ...]:
    slots = [_slot_for_requirement(req) for req in requirements]
    return _dedupe_slots(slot for slot in slots if slot.text)
def _slot_for_requirement(req: RewriteRequirement) -> PacketSlot:
    return PacketSlot(
        section=_slot_section_for_requirement(req),
        text=_slot_text_for_requirement(req),
        requirement_id=req.requirement_id,
        loss_id=req.loss_id,
    )
def _audit_slot_for_requirement(req: RewriteRequirement) -> PacketSlot:
    anchor = _first_reader_anchor(req) or _fallback_slot_text(req)
    if not anchor:
        return PacketSlot("audit_trail", "", req.requirement_id, req.loss_id)
    return PacketSlot(
        section="audit_trail",
        text=anchor,
        requirement_id=req.requirement_id,
        loss_id=req.loss_id,
    )
def _slot_text_for_requirement(req: RewriteRequirement) -> str:
    candidates = [
        *req.relation_rationales,
        *req.reader_anchors,
        *[_reader_relation_anchor_text(anchor) for anchor in req.relation_anchors],
        *[_reader_anchor_text(anchor) for anchor in req.claim_anchors],
        *req.required_phrases,
    ]
    for candidate in candidates:
        cleaned = _clean_reader_text(candidate)
        if cleaned and not _is_meta_loss_text(cleaned):
            return cleaned
    return _fallback_slot_text(req)
def _first_reader_anchor(req: RewriteRequirement) -> str:
    for candidate in (*req.relation_rationales, *req.reader_anchors):
        cleaned = _clean_reader_text(candidate)
        if cleaned and not _is_meta_loss_text(cleaned):
            return cleaned
    return ""
def _fallback_slot_text(req: RewriteRequirement) -> str:
    evidence_terms = [term for term in req.required_terms if term not in {"baseline", "flat", "loss", "preserve"}]
    if evidence_terms:
        return "Evidence distinction to preserve: " + ", ".join(evidence_terms[:6]) + "."
    return ""
def _slot_section_for_requirement(req: RewriteRequirement) -> str:
    return (
        _role_section_from_relation_types(req.relation_types)
        or _role_section_from_claim_roles(req.claim_roles)
        or _role_section_from_loss_type(req.loss_type)
        or "main_support"
    )
def _role_section_from_relation_types(relation_types: tuple[str, ...]) -> str:
    text = _normalize_for_coverage(" ".join(relation_types))
    if any(marker in text for marker in ("tension", "conflict", "contradict", "challenge", "rebuts", "opposes")):
        return "conflicting_evidence"
    if any(marker in text for marker in ("limits", "bounds", "conditional", "scope", "exception", "qualifies")):
        return "scope_limits"
    if any(marker in text for marker in ("method", "measures", "proxy", "endpoint", "operationalizes")):
        return "method_limits"
    if any(marker in text for marker in ("supports", "entails", "grounds", "backs")):
        return "main_support"
    return ""
def _role_section_from_claim_roles(claim_roles: tuple[str, ...]) -> str:
    text = _normalize_for_coverage(" ".join(claim_roles))
    if any(marker in text for marker in ("conflict", "counter", "tension", "challenge", "opposing")):
        return "conflicting_evidence"
    if any(marker in text for marker in ("method", "measurement", "endpoint", "quality", "design", "validity", "proxy")):
        return "method_limits"
    if any(marker in text for marker in ("scope", "boundary", "subgroup", "population", "caveat", "limit")):
        return "scope_limits"
    if any(marker in text for marker in ("support", "premise", "finding", "evidence")):
        return "main_support"
    return ""
def _role_section_from_loss_type(loss_type: str) -> str:
    text = _normalize_for_coverage(loss_type)
    if any(marker in text for marker in ("conflict", "tension", "challenge", "critique", "response", "inconsistent")):
        return "conflicting_evidence"
    if any(marker in text for marker in ("scope", "population", "replacement", "regional", "caveat")):
        return "scope_limits"
    if any(marker in text for marker in ("method", "endpoint", "guideline", "authority", "scoping", "systematic", "study design")):
        return "method_limits"
    return ""
def _dedupe_slots(slots: Any) -> tuple[PacketSlot, ...]:
    unique = []
    seen: set[tuple[str, str]] = set()
    for slot in slots:
        key = (slot.section, _dedupe_key(slot.text))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        unique.append(slot)
    return tuple(unique)
def _audit_items(model_items: list[str], requirements: tuple[RewriteRequirement, ...]) -> list[str]:
    items = [_clean_reader_text(item) for item in model_items]
    items = [item for item in items if item and not _is_meta_loss_text(item)]
    for req in requirements:
        slot = _audit_slot_for_requirement(req)
        if slot.text:
            items.append(f"{req.loss_id}: {slot.text}")
    return _dedupe_text_items(items)
def _dedupe_text_items(items: list[str]) -> list[str]:
    unique = []
    seen: set[str] = set()
    for item in items:
        key = _dedupe_key(item)
        if not key or key in seen or _similar_item_exists(unique, item):
            continue
        seen.add(key)
        unique.append(item)
    return unique
def _similar_item_exists(existing_items: list[str], candidate: str) -> bool:
    return any(_text_overlap_ratio(existing, candidate) >= 0.58 for existing in existing_items)
def _text_overlap_ratio(left: str, right: str) -> float:
    left_tokens = _content_token_set(left)
    right_tokens = _content_token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    smaller = min(len(left_tokens), len(right_tokens))
    if smaller < 4:
        return 0.0
    return len(left_tokens & right_tokens) / smaller
def _content_token_set(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "alone",
        "also",
        "because",
        "being",
        "between",
        "could",
        "from",
        "have",
        "into",
        "more",
        "one",
        "rather",
        "should",
        "than",
        "that",
        "the",
        "their",
        "these",
        "this",
        "using",
        "when",
        "where",
        "which",
        "while",
        "with",
        "without",
    }
    return {
        _content_token(token)
        for token in re.findall(r"[a-z][a-z0-9\-]{2,}", _normalize_for_coverage(text))
        if token not in stopwords
    }
def _content_token(token: str) -> str:
    if token.endswith("ss"):
        return token
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("sses"):
        return token[:-2]
    if len(token) > 5 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token
def _strip_anchor_id(text: str) -> str:
    return re.sub(r"^[A-Za-z0-9_\-]+:\s*", "", text).strip()
def _reader_anchor_text(text: str) -> str:
    return _clean_required_phrase(_strip_anchor_id(text)) or _strip_anchor_id(text)
def _reader_relation_anchor_text(text: str) -> str:
    without_id = _strip_anchor_id(text)
    parts = [part.strip() for part in without_id.split(";") if part.strip()]
    if len(parts) >= 3:
        return parts[-1]
    return _reader_anchor_text(text)
def _is_meta_loss_text(text: str) -> bool:
    normalized = _normalize_for_coverage(text)
    meta_markers = (
        "the flat baseline",
        "flat baseline",
        "the baseline",
        "baseline failure",
        "explicitly avoid",
        "preserve the",
        "distinction from",
        "lost item",
    )
    return any(marker in normalized for marker in meta_markers)
def _evidence_role_for_requirement(req: RewriteRequirement) -> str:
    return _slot_section_for_requirement(req)
def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
def _table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "\\|").strip() or "Not specified"
def _anchor_text_lookup(map_payload: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    claims = _claim_lookup(map_payload)
    for claim_id, claim in claims.items():
        statement = _reader_claim_statement(claim)
        if statement:
            lookup[claim_id] = statement
    for relation_id, relation in _relation_lookup(map_payload).items():
        statement = _reader_relation_statement(relation, lookup)
        if statement:
            lookup[relation_id] = statement
    return lookup
def _reader_claim_statement(claim: dict[str, Any]) -> str:
    return _as_text(claim.get("claim") or claim.get("text"))
def _reader_relation_statement(relation: dict[str, Any], claim_lookup: dict[str, str]) -> str:
    source_claim = _as_text(relation.get("source_claim") or relation.get("source_claim_id"))
    target_claim = _as_text(relation.get("target_claim") or relation.get("target_claim_id"))
    source_text = claim_lookup.get(source_claim, "unresolved source claim" if source_claim else "")
    target_text = claim_lookup.get(target_claim, "unresolved target claim" if target_claim else "")
    relation_type = _as_text(relation.get("relation_type"))
    rationale = _as_text(relation.get("rationale"))
    if rationale:
        return rationale
    edge = ""
    if source_text and target_text:
        edge = f"{_short_text(source_text, 120)} -> {_short_text(target_text, 120)}"
    elif source_text:
        edge = _short_text(source_text, 120)
    elif target_text:
        edge = _short_text(target_text, 120)
    if rationale and edge:
        relation_label = f"{relation_type} relation" if relation_type else "relation"
        return _short_text(f"{rationale} ({relation_label}: {edge})", 360)
    return _short_text("; ".join(part for part in (edge, relation_type, rationale) if part), 360)
def _short_text(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "..."
def _expand_map_ids(items: list[str], anchor_lookup: dict[str, str]) -> list[str]:
    return [_clean_reader_text(_expand_map_id_text(item, anchor_lookup)) for item in items]
def _expand_map_id_text(text: str, anchor_lookup: dict[str, str]) -> str:
    stripped = text.strip("` ")
    if stripped in anchor_lookup:
        return anchor_lookup[stripped]
    return re.sub(
        r"`?([A-Za-z0-9_\-]+_[cr]\d+)`?",
        lambda match: anchor_lookup.get(match.group(1), match.group(0)),
        text,
    )
def _clean_reader_text(text: str) -> str:
    cleaned = re.sub(r";?\s*role=[^;.\n]+", "", text)
    cleaned = re.sub(r";?\s*source=[^;.\n]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" ;")
def _clean_reader_packet_metadata(text: str) -> str:
    cleaned = re.sub(r";?\s*role=[^;.\n]+", "", text)
    cleaned = re.sub(r";?\s*source=[^;.\n]+", "", cleaned)
    return _dedupe_packet_bullets(cleaned)
def _dedupe_packet_bullets(text: str) -> str:
    seen: set[str] = set()
    lines = []
    for line in text.splitlines():
        bullet = re.match(r"^(\s*-\s+)(.+?)\s*$", line)
        if bullet:
            key = _dedupe_key(bullet.group(2))
            if key and key in seen:
                continue
            if key:
                seen.add(key)
        lines.append(line)
    return "\n".join(lines).rstrip() + ("\n" if text.endswith("\n") else "")
def _parse_json(text: str) -> dict[str, Any] | None:
    canonical = canonical_json_output(text)
    try:
        payload = json.loads(canonical)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
def _extract_json_string_field(text: str, field: str) -> str:
    pattern = re.compile(rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"', re.DOTALL)
    match = pattern.search(text)
    if not match:
        return ""
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return re.sub(r"\s+", " ", match.group(1)).strip()
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")
def _read_map_payload(repo_root: Path, region: WorkedRegion) -> dict[str, Any]:
    json_path = repo_root / region.output_json_path
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    map_path = repo_root / region.map_path
    if map_path.suffix.lower() == ".json":
        return json.loads(map_path.read_text(encoding="utf-8"))
    raise ValueError(f"region has no JSON map export region={region.region_id} path={region.output_json_path}")
def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
def _normalize_for_coverage(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("‑", "-").replace("–", "-")).strip()
def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"
def _rel(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
