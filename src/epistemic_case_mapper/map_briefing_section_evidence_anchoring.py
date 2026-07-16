from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_markdown_quality import repair_markdown_structure
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_ready_section_notes import render_memo_ready_section_markdown_notes


BRACE_TAG_RE = re.compile(r"\{([^{}\n]{1,240})\}")


def build_evidence_expression_contracts(packet: dict[str, Any]) -> list[dict[str, Any]]:
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    obligations_by_item = _obligations_by_item(canonical)
    source_ids_by_label = _source_ids_by_label(packet)
    language_by_item = {
        str(row.get("item_id") or ""): row
        for row in _list(canonical.get("evidence_language_contracts"))
        if isinstance(row, dict) and row.get("item_id")
    }
    contracts = []
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("item_id") or "").strip()
        if not evidence_id:
            continue
        obligation = obligations_by_item.get(evidence_id, {})
        language = language_by_item.get(evidence_id, {})
        quantities = _quantity_contracts(_list(item.get("quantities")) or _list(obligation.get("quantities")))
        role = str(item.get("role") or obligation.get("role") or "")
        sources = _dedupe(
            [
                *_string_list(item.get("source_ids")),
                *_string_list(obligation.get("source_ids")),
                *_string_list(language.get("source_ids")),
                *_source_ids_from_labels(item, source_ids_by_label),
            ]
        )
        contracts.append(
            _drop_empty(
                {
                    "schema_id": "evidence_expression_contract_v1",
                    "evidence_id": evidence_id,
                    "required": _contract_required(item, obligation, role=role, quantities=quantities),
                    "primary_section": _primary_section_for_role(role),
                    "claim": item.get("reader_claim") or item.get("claim") or obligation.get("statement"),
                    "role": role,
                    "source_ids": sources,
                    "source_labels": item.get("source_labels")
                    or ([item.get("source_label")] if item.get("source_label") else None),
                    "required_quantity_atoms": quantities,
                    "population_scope": item.get("caveat") or item.get("applicability_scope"),
                    "required_caveat": item.get("caveat"),
                    "decision_relevance": item.get("decision_relevance"),
                    "allowed_language": _string_list(_dict(item.get("allowed_wording")).get("allowed_language"))
                    or _string_list(language.get("allowed_language")),
                    "must_qualify_with": _string_list(_dict(item.get("allowed_wording")).get("must_qualify_with"))
                    or _string_list(language.get("must_qualify_with")),
                    "must_not_imply": _dedupe(
                        [
                            *_string_list(_dict(item.get("allowed_wording")).get("avoid_language")),
                            *_string_list(language.get("avoid_language")),
                        ]
                    ),
                }
            )
        )
    return contracts


def contracts_for_section(
    section_packet: dict[str, Any],
    heading: str,
    contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    section_id = str(section_packet.get("section_id") or "").strip()
    local_ids = {
        str(row.get("item_id") or row.get("requirement_id") or "")
        for key in ("evidence_context", "section_retention_requirements", "source_bound_evidence_atoms")
        for row in _list(section_packet.get(key))
        if isinstance(row, dict)
    }
    selected = [
        row
        for row in contracts
        if row.get("evidence_id") in local_ids
        or row.get("primary_section") == section_id
        or _heading_matches_section(str(row.get("primary_section") or ""), heading)
    ]
    if selected:
        return selected[:18]
    return [row for row in contracts if row.get("required")][:12]


def build_evidence_tagged_section_prompt(
    section_packet: dict[str, Any],
    *,
    known_source_ids: list[str],
    contracts: list[dict[str, Any]],
) -> str:
    heading = str(section_packet.get("heading") or "").strip()
    compact_contracts = [_compact_contract_for_prompt(row) for row in contracts]
    return (
        "You are writing one section of a source-grounded decision memo from markdown analyst notes.\n"
        "Write polished decision-ready prose. Evidence tags are trace anchors that the renderer converts into reader citations.\n\n"
        "Output rules:\n"
        f"- Output starts exactly with: ## {heading}\n"
        "- After each load-bearing evidence sentence, add one or more evidence tags like {E:evidence_id}.\n"
        "- Evidence tags use only evidence IDs listed in Evidence expression contracts.\n"
        "- Square-bracket source citations are reserved for the deterministic renderer.\n"
        "- Use parentheses for confidence intervals, uncertainty ranges, and numeric ranges.\n"
        "- Preserve the quantities, scope, direction, and caveats from the evidence contracts.\n"
        "- Write natural prose; tags are trace markers attached to sentences.\n\n"
        f"{render_memo_ready_section_markdown_notes(section_packet, known_source_ids=known_source_ids)}\n\n"
        "### Evidence expression contracts\n"
        f"{json.dumps(compact_contracts, indent=2, ensure_ascii=False)}\n\n"
        "Now write the section as natural Markdown prose with evidence tags.\n"
    )


def render_evidence_tagged_memo(tagged_memo: str, contracts: list[dict[str, Any]]) -> dict[str, Any]:
    contracts_by_id = _contracts_by_evidence_alias(contracts)
    known_source_ids = {
        source_id
        for contract in contracts
        for source_id in _string_list(contract.get("source_ids"))
    }
    trace = []

    def replace(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        evidence_ids = _evidence_ids_from_brace_content(content, contracts_by_id)
        if evidence_ids:
            source_ids = []
            for evidence_id in evidence_ids:
                contract = contracts_by_id.get(evidence_id, {})
                row_source_ids = _string_list(contract.get("source_ids"))
                source_ids.extend(row_source_ids)
                trace.append(
                    {
                        "evidence_id": evidence_id,
                        "source_ids": row_source_ids,
                        "claim": contract.get("claim"),
                        "required_quantity_atoms": contract.get("required_quantity_atoms", []),
                        "tag": match.group(0),
                    }
                )
            source_ids = _dedupe(source_ids)
            return f"[{', '.join(source_ids)}]" if source_ids else ""
        source_ids = _source_ids_from_brace_content(content, known_source_ids)
        if source_ids:
            return f"[{', '.join(source_ids)}]"
        return match.group(0)

    memo = BRACE_TAG_RE.sub(replace, tagged_memo)
    memo = re.sub(r"[ \t]+(\n)", r"\1", memo)
    memo = re.sub(r"\s+\.", ".", memo)
    return {"memo": repair_markdown_structure(memo), "trace": trace}


def build_evidence_reconciliation_report(
    tagged_memo: str,
    rendered_memo: str,
    contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    used_ids = set(evidence_ids_in_text(tagged_memo, contracts))
    known_ids = {str(row.get("evidence_id") or "") for row in contracts}
    required = [row for row in contracts if row.get("required")]
    missing_required = [row.get("evidence_id") for row in required if row.get("evidence_id") not in used_ids]
    unknown = sorted(used_ids - known_ids)
    quantity_warnings = _quantity_warnings(tagged_memo, contracts)
    untagged = _untagged_high_risk_sentences(tagged_memo)
    status = "ready"
    if missing_required or unknown:
        status = "warning"
    return {
        "schema_id": "evidence_reconciliation_report_v1",
        "status": status,
        "known_evidence_id_count": len(known_ids),
        "used_evidence_id_count": len(used_ids & known_ids),
        "required_evidence_id_count": len(required),
        "missing_required_evidence_ids": missing_required,
        "unknown_evidence_ids": unknown,
        "quantity_warning_count": len(quantity_warnings),
        "quantity_warnings": quantity_warnings,
        "untagged_high_risk_sentence_count": len(untagged),
        "untagged_high_risk_sentences": untagged[:20],
        "raw_tag_count": len(evidence_ids_in_text(tagged_memo, contracts)),
        "rendered_raw_tag_count": len(evidence_ids_in_text(rendered_memo, contracts)),
    }


def evidence_ids_in_text(text: str, contracts: list[dict[str, Any]]) -> list[str]:
    contracts_by_id = _contracts_by_evidence_alias(contracts)
    if not contracts_by_id:
        candidates = []
        for content in BRACE_TAG_RE.findall(text or ""):
            candidates.extend(_brace_tokens(content))
        return [token.removeprefix("E:") for token in candidates if token.startswith("E:")]
    found = []
    for content in BRACE_TAG_RE.findall(text or ""):
        found.extend(_evidence_ids_from_brace_content(content.strip(), contracts_by_id))
    return _dedupe(found)


def _obligations_by_item(canonical: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_item = {}
    for row in _list(canonical.get("mandatory_retention_checklist")):
        if not isinstance(row, dict):
            continue
        for item_id in _string_list(row.get("evidence_item_ids")):
            by_item.setdefault(item_id, row)
    return by_item


def _source_ids_by_label(packet: dict[str, Any]) -> dict[str, str]:
    mapping = {}
    for row in _list(packet.get("source_trail")):
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or row.get("citation_key") or "").strip()
        if not source_id:
            continue
        values = (
            row.get("source_label"),
            row.get("display_label"),
            row.get("source_slug"),
            row.get("original_source_id"),
            row.get("citation_key"),
        )
        for value in values:
            key = _label_key(value)
            if key:
                mapping[key] = source_id
        for alias in _string_list(row.get("source_aliases")):
            key = _label_key(alias)
            if key:
                mapping[key] = source_id
    return mapping


def _source_ids_from_labels(item: dict[str, Any], source_ids_by_label: dict[str, str]) -> list[str]:
    labels = [*_string_list(item.get("source_labels")), *_string_list(item.get("source_label"))]
    ids = []
    for label in labels:
        source_id = source_ids_by_label.get(_label_key(label))
        if source_id:
            ids.append(source_id)
    return _dedupe(ids)


def _label_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _contract_required(
    item: dict[str, Any],
    obligation: dict[str, Any],
    *,
    role: str,
    quantities: list[dict[str, Any]],
) -> bool:
    role_text = role.lower()
    return (
        bool(item.get("must_use"))
        or str(item.get("obligation_level") or "") == "must_include"
        or bool(obligation)
        or bool(quantities)
        or role_text in {"strongest_counterweight", "scope_boundary", "quantitative_anchor", "decision_crux"}
    )


def _quantity_contracts(rows: list[Any]) -> list[dict[str, Any]]:
    quantities = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = str(row.get("value") or "").strip()
        if not value:
            continue
        quantities.append(
            _drop_empty(
                {
                    "value": value,
                    "interpretation": row.get("interpretation"),
                    "quantity_role": row.get("quantity_role"),
                    "source_ids": row.get("source_ids"),
                }
            )
        )
    return quantities


def _quantity_warnings(tagged_memo: str, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    for contract in contracts:
        if not contract.get("required"):
            continue
        span = _span_for_evidence_id(tagged_memo, str(contract.get("evidence_id") or ""))
        if not span:
            continue
        for quantity in _list(contract.get("required_quantity_atoms")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if value and not _quantity_surface_present(value, span):
                warnings.append(
                    {
                        "evidence_id": contract.get("evidence_id"),
                        "missing_quantity_near_tag": value,
                        "span": _short_text(span, 240),
                    }
                )
    return warnings


def _span_for_evidence_id(text: str, evidence_id: str) -> str:
    if not evidence_id:
        return ""
    pattern = re.compile(
        rf"[^.\n]*(?:\{{E:{re.escape(evidence_id)}\}}|\{{[^}}\n]*\b{re.escape(evidence_id)}\b[^}}\n]*\}})[^.\n]*(?:\.|\n|$)"
    )
    match = pattern.search(text)
    return match.group(0).strip() if match else ""


def _quantity_surface_present(value: str, text: str) -> bool:
    value_text = str(value or "").lower()
    text_norm = str(text or "").lower()
    if value_text in text_norm:
        return True
    numbers = re.findall(r"\d+(?:\.\d+)?", value_text)
    return bool(numbers) and all(number in text_norm for number in numbers)


def _untagged_high_risk_sentences(tagged_memo: str) -> list[str]:
    rows = []
    for sentence in _sentences_without_sources(tagged_memo):
        if evidence_ids_in_text(sentence, []):
            continue
        lowered = sentence.lower()
        if re.search(r"\d", sentence) or any(
            token in lowered
            for token in ("associated", "risk", "increased", "reduced", "should", "must", "recommend", "causes", "proves")
        ):
            rows.append(_short_text(BRACE_TAG_RE.sub("", sentence).strip(), 300))
    return rows


def _sentences_without_sources(memo: str) -> list[str]:
    body = re.split(r"(?m)^## Sources\s*$", memo)[0]
    body = "\n".join(line for line in body.splitlines() if not line.startswith("#") and not line.startswith("**Decision"))
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", body) if len(part.strip()) > 30]


def _evidence_ids_from_brace_content(content: str, contracts_by_id: dict[str, dict[str, Any]]) -> list[str]:
    ids = []
    for token in _brace_tokens(content):
        candidate = token.removeprefix("E:")
        contract = contracts_by_id.get(candidate)
        if contract:
            ids.append(str(contract.get("evidence_id") or candidate))
    return _dedupe(ids)


def _contracts_by_evidence_alias(contracts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in contracts:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        for alias in _evidence_id_aliases(evidence_id):
            by_id.setdefault(alias, row)
    return by_id


def _evidence_id_aliases(evidence_id: str) -> list[str]:
    aliases = [evidence_id]
    match = re.match(r"^(.*?)(\d+)$", evidence_id)
    if match:
        prefix, digits = match.groups()
        unpadded = str(int(digits)) if digits.strip("0") else "0"
        aliases.append(f"{prefix}{unpadded}")
    return _dedupe(aliases)


def _source_ids_from_brace_content(content: str, known_source_ids: set[str]) -> list[str]:
    tokens = _brace_tokens(content)
    if tokens and all(token in known_source_ids for token in tokens):
        return _dedupe(tokens)
    return []


def _brace_tokens(content: str) -> list[str]:
    return [token.strip() for token in re.split(r"[,;]", str(content or "")) if token.strip()]


def _primary_section_for_role(role: str) -> str:
    text = role.lower()
    if any(token in text for token in ("counter", "scope", "boundary", "crux", "limit")):
        return "counterweights"
    if any(token in text for token in ("practical", "context")):
        return "practical_implication"
    return "answer_evidence"


def _heading_matches_section(section_id: str, heading: str) -> bool:
    lowered = heading.lower()
    return (
        (section_id == "answer_evidence" and "best current" in lowered)
        or (section_id == "counterweights" and ("change" in lowered or "bound" in lowered))
        or (section_id == "practical_implication" and "practical" in lowered)
        or (section_id == "source_weighting" and "weight" in lowered)
    )


def _compact_contract_for_prompt(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "evidence_id": row.get("evidence_id"),
            "claim": row.get("claim"),
            "required": row.get("required"),
            "source_ids": row.get("source_ids"),
            "quantities": row.get("required_quantity_atoms"),
            "scope": row.get("population_scope"),
            "caveat": row.get("required_caveat"),
            "must_qualify_with": row.get("must_qualify_with"),
            "must_not_imply": row.get("must_not_imply"),
        }
    )


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
