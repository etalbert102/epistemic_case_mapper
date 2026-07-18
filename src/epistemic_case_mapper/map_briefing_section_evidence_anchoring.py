from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_decision_argument_contract import build_decision_argument_contract, argument_move_ids_for_evidence
from epistemic_case_mapper.map_briefing_markdown_quality import repair_markdown_structure
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_ready_section_notes import render_memo_ready_section_markdown_notes
from epistemic_case_mapper.map_briefing_section_evidence_utils import (
    brace_tokens as _brace_tokens,
    compact_contract_for_prompt as _compact_contract_for_prompt,
    contract_required as _contract_required,
    contracts_by_evidence_alias as _contracts_by_evidence_alias,
    drop_empty as _drop_empty,
    evidence_ids_in_contract_text as _evidence_ids_in_contract_text,
    evidence_ids_from_brace_content as _evidence_ids_from_brace_content,
    heading_matches_section as _heading_matches_section,
    label_key as _label_key,
    primary_section_for_role as _primary_section_for_role,
    quantity_contracts as _quantity_contracts,
    quantity_source_ids as _quantity_source_ids,
    quantity_warnings as _quantity_warnings,
    source_ids_from_brace_content as _source_ids_from_brace_content,
    untagged_high_risk_sentences as _untagged_high_risk_sentences,
)


BRACE_TAG_RE = re.compile(r"\{([^{}\n]{1,240})\}")


def build_evidence_expression_contracts(packet: dict[str, Any]) -> list[dict[str, Any]]:
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    if canonical and not _dict(canonical.get("decision_argument_contract")):
        canonical = {**canonical, "decision_argument_contract": build_decision_argument_contract(canonical)}
    argument_move_ids = argument_move_ids_for_evidence(_dict(canonical.get("decision_argument_contract")))
    obligations_by_item = _obligations_by_item(canonical)
    quantity_obligations_by_item = _quantity_obligations_by_item(packet)
    source_ids_by_label = _source_ids_by_label(packet)
    source_match_keys_by_id = _source_match_keys_by_id(packet)
    source_weights = _source_weight_judgments_by_source(canonical)
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
        base_quantity_rows = [
            *_list(item.get("quantities")),
            *_list(obligation.get("quantities")),
            *_list(quantity_obligations_by_item.get(evidence_id)),
        ]
        quantities = _quantity_contracts(
            [
                *base_quantity_rows,
                *_numeric_must_preserve_terms(item, base_quantity_rows),
            ]
        )
        role = str(item.get("role") or obligation.get("role") or "")
        sources = _dedupe(
            [
                *_string_list(item.get("source_ids")),
                *_string_list(obligation.get("source_ids")),
                *_string_list(language.get("source_ids")),
                *_source_ids_from_labels(item, source_ids_by_label),
            ]
        )
        citation_sources = _citation_source_ids_for_contract(
            sources,
            role=role,
            item=item,
            obligation=obligation,
            quantities=quantities,
            source_weights=source_weights,
        )
        contracts.append(
            _drop_empty(
                {
                    "schema_id": "evidence_expression_contract_v1",
                    "evidence_id": evidence_id,
                    "argument_move_ids": argument_move_ids.get(evidence_id, []),
                    "required": _contract_required(item, obligation, role=role, quantities=quantities),
                    "primary_section": _primary_section_for_role(role),
                    "claim": item.get("reader_claim") or item.get("claim") or obligation.get("statement"),
                    "role": role,
                    "source_ids": sources,
                    "citation_source_ids": citation_sources,
                    "source_match_keys": _source_match_keys_for_sources(sources, source_match_keys_by_id),
                    "source_labels": item.get("source_labels")
                    or ([item.get("source_label")] if item.get("source_label") else None),
                    "required_quantity_atoms": quantities,
                    "must_preserve_terms": _string_list(item.get("must_preserve_terms")),
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
        return _dedupe_section_quantity_obligations(selected[:18])
    if section_id and section_id not in {"answer_evidence", "bottom_line"}:
        return []
    return _dedupe_section_quantity_obligations([row for row in contracts if row.get("required")][:12])


def _dedupe_section_quantity_obligations(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owners: dict[str, str] = {}
    by_id = {str(row.get("evidence_id") or ""): row for row in contracts if isinstance(row, dict)}
    for row in contracts:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_id") or "").strip()
        for quantity in _list(row.get("required_quantity_atoms")):
            if not isinstance(quantity, dict):
                continue
            key = _quantity_dedupe_key(quantity)
            if not key:
                continue
            current = owners.get(key)
            if not current or _quantity_owner_priority(row) < _quantity_owner_priority(by_id.get(current, {})):
                owners[key] = evidence_id
    cleaned = []
    for row in contracts:
        if not isinstance(row, dict):
            cleaned.append(row)
            continue
        evidence_id = str(row.get("evidence_id") or "").strip()
        kept_quantities = []
        for quantity in _list(row.get("required_quantity_atoms")):
            if not isinstance(quantity, dict):
                continue
            key = _quantity_dedupe_key(quantity)
            if key and owners.get(key) == evidence_id:
                kept_quantities.append(quantity)
        if kept_quantities == _list(row.get("required_quantity_atoms")):
            cleaned.append(row)
        else:
            updated = dict(row)
            if kept_quantities:
                updated["required_quantity_atoms"] = kept_quantities
            else:
                updated.pop("required_quantity_atoms", None)
            cleaned.append(updated)
    return cleaned


def _quantity_dedupe_key(quantity: dict[str, Any]) -> str:
    value = str(quantity.get("value") or "").strip().lower()
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    return numbers[0] if numbers else re.sub(r"\s+", " ", value)


def _quantity_owner_priority(contract: dict[str, Any]) -> int:
    text = _contract_job_text(contract)
    if _matches_any(text, ("dose", "dosage", "intake", "biomarker", "endpoint", "ratio", "mean difference", "hazard ratio", "relative risk", "confidence interval")):
        return 0
    if _matches_any(text, ("subgroup", "population", "condition", "diagnosed", "participants with", "patients with")):
        return 2
    return 1


def build_evidence_tagged_section_prompt(
    section_packet: dict[str, Any],
    *,
    known_source_ids: list[str],
    contracts: list[dict[str, Any]],
) -> str:
    heading = str(section_packet.get("heading") or "").strip()
    compact_contracts = [_compact_contract_for_prompt(row) for row in contracts]
    section_jobs = build_section_local_evidence_jobs(section_packet, contracts)
    return (
        "You are writing one section of a source-grounded decision memo from markdown analyst notes.\n"
        "Write polished decision-ready prose. Evidence tags are trace anchors that the renderer converts into reader citations.\n\n"
        "Output rules:\n"
        f"- Output starts exactly with: ## {heading}\n"
        "- After each load-bearing evidence sentence, add one or more evidence tags like {E:evidence_id}.\n"
        "- Evidence tags use only evidence IDs listed in Evidence expression contracts.\n"
        "- Treat contracts marked required as a coverage checklist: every required contract appears at least once with its evidence tag.\n"
        "- For contracts with quantities, include a listed quantity in the same sentence as that contract's evidence tag.\n"
        "- Square-bracket source citations are reserved for the deterministic renderer.\n"
        "- Use parentheses for confidence intervals, uncertainty ranges, and numeric ranges.\n"
        "- Use the Decision argument for this section as the governing structure; use evidence contracts as anchors for those moves.\n"
        "- Preserve the quantities, scope, direction, and caveats from the evidence contracts.\n"
        "- Use Priority quantity contracts to keep decision-relevant quantities with the exact claim, endpoint, subgroup, and comparator they describe.\n"
        "- Reader-facing allowed-use and not-enough-for limits define the claim role while required contracts still keep their own tags and listed quantities.\n"
        "- If a quantity appears in an evidence expression contract, keep that quantity in the same sentence as that exact contract's tag.\n"
        "- When Section-local evidence jobs are present, write around those paragraph jobs and attach tags from each job's allowed evidence IDs for that paragraph.\n"
        "- Write natural prose; tags are trace markers attached to sentences.\n\n"
        f"{render_memo_ready_section_markdown_notes(section_packet, known_source_ids=known_source_ids)}\n\n"
        f"{_render_section_local_evidence_jobs(section_jobs)}"
        "### Evidence expression contracts\n"
        f"{json.dumps(compact_contracts, indent=2, ensure_ascii=False)}\n\n"
        "Now write the section as natural Markdown prose with evidence tags.\n"
    )


def build_section_local_evidence_jobs(section_packet: dict[str, Any], contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    section_id = str(_dict(section_packet).get("section_id") or "").strip()
    if section_id != "counterweights":
        return []
    move_jobs = _section_jobs_from_argument_moves(section_packet, contracts)
    if move_jobs:
        return move_jobs
    grouped: dict[str, list[dict[str, Any]]] = {}
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        job_id = _counterweight_job_id(contract)
        grouped.setdefault(job_id, []).append(contract)
    jobs = []
    for job_id in _counterweight_job_order():
        rows = grouped.get(job_id, [])
        if not rows:
            continue
        jobs.append(_section_local_job(job_id, rows))
    return jobs


def _section_jobs_from_argument_moves(section_packet: dict[str, Any], contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    argument_section = _dict(section_packet.get("decision_argument_section"))
    moves = [row for row in _list(argument_section.get("owned_moves")) if isinstance(row, dict)]
    if not moves:
        return []
    contracts_by_move: dict[str, list[dict[str, Any]]] = {}
    contracts_by_id = {str(row.get("evidence_id") or ""): row for row in contracts if isinstance(row, dict)}
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        for move_id in _string_list(contract.get("argument_move_ids")):
            contracts_by_move.setdefault(move_id, []).append(contract)
    jobs = []
    used_evidence_ids: set[str] = set()
    for move in moves:
        move_id = str(move.get("move_id") or "").strip()
        rows = contracts_by_move.get(move_id, [])
        if not rows:
            rows = [
                contracts_by_id[evidence_id]
                for evidence_id in _string_list(move.get("evidence_item_ids"))
                if evidence_id in contracts_by_id
            ]
        if not rows:
            continue
        used_evidence_ids.update(str(row.get("evidence_id") or "") for row in rows if row.get("evidence_id"))
        jobs.append(
            _drop_empty(
                {
                    "job_id": move_id,
                    "argument_move_type": move.get("move_type"),
                    "paragraph_job": move.get("writing_job") or move.get("point"),
                    "argument_point": move.get("point"),
                    "allowed_evidence_ids": [str(row.get("evidence_id")) for row in rows if row.get("evidence_id")],
                    "required_quantities_by_evidence_id": {
                        str(row.get("evidence_id")): _quantity_values_for_job(row)
                        for row in rows
                        if row.get("evidence_id") and _quantity_values_for_job(row)
                    },
                }
            )
        )
    remaining = [
        row
        for row in contracts
        if isinstance(row, dict)
        and str(row.get("evidence_id") or "") not in used_evidence_ids
        and row.get("required")
    ]
    if remaining:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for contract in remaining:
            job_id = _counterweight_job_id(contract)
            grouped.setdefault(f"required_{job_id}", []).append(contract)
        for job_id in [f"required_{value}" for value in _counterweight_job_order()]:
            rows = grouped.get(job_id, [])
            if rows:
                jobs.append(_section_local_job(job_id, rows))
    return jobs


def _render_section_local_evidence_jobs(jobs: list[dict[str, Any]]) -> str:
    if not jobs:
        return ""
    return "### Section-local evidence jobs\n" + json.dumps(jobs, indent=2, ensure_ascii=False) + "\n\n"


def _counterweight_job_order() -> list[str]:
    return [
        "dose_or_endpoint_boundary",
        "subgroup_or_population_boundary",
        "comparator_or_context_boundary",
        "update_or_crux_trigger",
        "other_boundary_or_counterweight",
    ]


def _counterweight_job_id(contract: dict[str, Any]) -> str:
    text = _contract_job_text(contract)
    if _matches_any(
        text,
        (
            "subgroup",
            "subpopulation",
            "population",
            "high-risk",
            "risk group",
            "baseline risk",
            "comorbidity",
            "condition",
            "diagnosed",
            "patients with",
            "participants with",
            "adults with",
            "treated population",
        ),
    ):
        return "subgroup_or_population_boundary"
    if _matches_any(
        text,
        (
            "comparator",
            "comparison",
            "instead of",
            "replace",
            "substitution",
            "alternative",
            "background",
            "context",
            "pattern",
            "mechanism",
            "pathway",
            "co-intervention",
            "control group",
        ),
    ):
        return "comparator_or_context_boundary"
    if any(term in text for term in ("would change", "would update", "update", "guideline", "monitoring trigger", "threshold", "crux")):
        return "update_or_crux_trigger"
    if _matches_any(
        text,
        (
            "dose",
            "dosage",
            "serving",
            "intake",
            "exposure",
            "frequency",
            "threshold",
            "gradient",
            "biomarker",
            "endpoint",
            "outcome measure",
            "ratio",
            "mean difference",
            "hazard ratio",
            "relative risk",
            "odds ratio",
            "confidence interval",
        ),
    ) or _contract_has_quantities(contract):
        return "dose_or_endpoint_boundary"
    return "other_boundary_or_counterweight"


def _matches_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _section_local_job(job_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return _drop_empty(
        {
            "job_id": job_id,
            "paragraph_job": _counterweight_job_label(job_id),
            "allowed_evidence_ids": [str(row.get("evidence_id")) for row in rows if row.get("evidence_id")],
            "required_quantities_by_evidence_id": {
                str(row.get("evidence_id")): _quantity_values_for_job(row)
                for row in rows
                if row.get("evidence_id") and _quantity_values_for_job(row)
            },
            "writing_guidance": _counterweight_job_guidance(job_id),
        }
    )


def _counterweight_job_label(job_id: str) -> str:
    labels = {
        "dose_or_endpoint_boundary": "Explain the dose, endpoint, or biomarker boundary.",
        "subgroup_or_population_boundary": "Explain the subgroup or population boundary.",
        "comparator_or_context_boundary": "Explain the comparator, context, or mechanism boundary.",
        "update_or_crux_trigger": "Explain what would change or update the answer.",
        "other_boundary_or_counterweight": "Explain any remaining boundary or counterweight.",
    }
    return labels.get(job_id, "Explain the boundary or counterweight.")


def _counterweight_job_guidance(job_id: str) -> str:
    guidance = {
        "dose_or_endpoint_boundary": "Use these tags for measured quantities, dose thresholds, biomarker endpoints, and clinical endpoint limits.",
        "subgroup_or_population_boundary": "Use these tags for subgroup-specific or population-specific limits.",
        "comparator_or_context_boundary": "Use these tags for comparator, background-context, substitution, or mechanism boundaries.",
        "update_or_crux_trigger": "Use these tags for future evidence, thresholds, or guideline changes that would alter the answer.",
        "other_boundary_or_counterweight": "Use these tags for remaining limiting evidence not covered above.",
    }
    return guidance.get(job_id, "Use these tags for their listed boundary role.")


def _quantity_values_for_job(contract: dict[str, Any]) -> list[str]:
    values = []
    for quantity in _list(contract.get("required_quantity_atoms")):
        if isinstance(quantity, dict):
            values.extend(_string_list(quantity.get("value")))
        else:
            values.extend(_string_list(quantity))
    return _dedupe(values)


def _contract_has_quantities(contract: dict[str, Any]) -> bool:
    return bool(_quantity_values_for_job(contract))


def _contract_job_text(contract: dict[str, Any]) -> str:
    parts = [
        contract.get("claim"),
        contract.get("role"),
        contract.get("decision_relevance"),
        contract.get("population_scope"),
        contract.get("required_caveat"),
        " ".join(_quantity_values_for_job(contract)),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def render_evidence_tagged_memo(tagged_memo: str, contracts: list[dict[str, Any]]) -> dict[str, Any]:
    contracts_by_id = _contracts_by_evidence_alias(contracts)
    known_source_ids = {
        source_id
        for contract in contracts
        for source_id in _string_list(contract.get("source_ids")) + _string_list(contract.get("citation_source_ids"))
    }
    trace = []
    tagged_memo = _strip_source_citations_adjacent_to_evidence_tags(tagged_memo, known_source_ids)

    def replace(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        evidence_ids = _evidence_ids_from_brace_content(content, contracts_by_id)
        if evidence_ids:
            source_ids = []
            for evidence_id in evidence_ids:
                contract = contracts_by_id.get(evidence_id, {})
                row_source_ids = _string_list(contract.get("citation_source_ids")) or _string_list(contract.get("source_ids"))
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


def _strip_source_citations_adjacent_to_evidence_tags(text: str, known_source_ids: set[str]) -> str:
    """Make evidence tags authoritative when a model also emits source brackets.

    Evidence-tagged prompts reserve square-bracket citations for the renderer,
    but weaker local models sometimes append broad `[source_a, source_b]`
    bundles after `{E:item}`. Keeping both recreates over-citation, so remove
    only bracket groups that are adjacent to evidence tags and contain known
    source IDs.
    """
    if not known_source_ids:
        return str(text or "")
    result = str(text or "")
    tag = r"\{[^{}\n]*\bE:[^{}\n]*\}"
    bracket = r"\[([^\[\]\n]{1,300})\]"

    def remove_after(match: re.Match[str]) -> str:
        content = match.group(2)
        return match.group(1) if _bracket_contains_known_source_ids(content, known_source_ids) else match.group(0)

    def remove_before(match: re.Match[str]) -> str:
        content = match.group(1)
        return match.group(2) if _bracket_contains_known_source_ids(content, known_source_ids) else match.group(0)

    previous = None
    while previous != result:
        previous = result
        result = re.sub(rf"({tag})\s*{bracket}", remove_after, result)
        result = re.sub(rf"{bracket}\s*({tag})", remove_before, result)
    return result


def _bracket_contains_known_source_ids(content: str, known_source_ids: set[str]) -> bool:
    tokens = {token.strip() for token in re.split(r"\s*(?:,|;)\s*", str(content or "")) if token.strip()}
    return bool(tokens and tokens.intersection(known_source_ids))


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
    if missing_required or unknown or quantity_warnings:
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
    return _evidence_ids_in_contract_text(text, contracts)


def _obligations_by_item(canonical: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_item = {}
    for row in _list(canonical.get("mandatory_retention_checklist")):
        if not isinstance(row, dict):
            continue
        for item_id in _string_list(row.get("evidence_item_ids")):
            by_item.setdefault(item_id, row)
    return by_item


def _quantity_obligations_by_item(packet: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    plan = _dict(packet.get("quantity_obligation_plan"))
    evidence_to_writer_ids = _source_evidence_id_to_writer_ids(packet)
    by_item: dict[str, list[dict[str, Any]]] = {}
    for row in _list(plan.get("rows")):
        if not isinstance(row, dict):
            continue
        if not bool(row.get("must_retain")):
            continue
        targets = _quantity_row_target_item_ids(row, evidence_to_writer_ids)
        quantity = _quantity_from_obligation_row(row)
        if not quantity:
            continue
        for item_id in targets:
            by_item.setdefault(item_id, []).append(quantity)
    return by_item


def _source_evidence_id_to_writer_ids(packet: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or "").strip()
        if not item_id:
            continue
        lineage = _dict(item.get("lineage"))
        for evidence_id in [
            *_string_list(item.get("source_evidence_item_id")),
            *_string_list(lineage.get("covered_evidence_item_ids")),
            *[
                str(row.get("evidence_item_id") or "")
                for row in _list(item.get("analyst_relevance_decisions"))
                if isinstance(row, dict)
            ],
        ]:
            evidence_id = str(evidence_id or "").strip()
            if evidence_id:
                mapping.setdefault(evidence_id, []).append(item_id)
    return {key: _dedupe(values) for key, values in mapping.items()}


def _quantity_row_target_item_ids(row: dict[str, Any], evidence_to_writer_ids: dict[str, list[str]]) -> list[str]:
    direct = _string_list(row.get("evidence_id")) + _string_list(row.get("item_id"))
    source_evidence_id = str(row.get("source_evidence_item_id") or "").strip()
    if source_evidence_id:
        direct.extend(evidence_to_writer_ids.get(source_evidence_id, []))
    analyst = _dict(row.get("analyst_quantity_relevance"))
    analyst_evidence_id = str(analyst.get("evidence_item_id") or "").strip()
    if analyst_evidence_id:
        direct.extend(evidence_to_writer_ids.get(analyst_evidence_id, []))
    return _dedupe(value for value in direct if value)


def _quantity_from_obligation_row(row: dict[str, Any]) -> dict[str, Any]:
    value = str(row.get("value") or _dict(row.get("analyst_quantity_relevance")).get("quantity_value") or "").strip()
    if not value:
        return {}
    return _drop_empty(
        {
            "value": value,
            "interpretation": row.get("retention_phrase") or row.get("why_quantity_matters"),
            "quantity_role": row.get("quantity_role"),
            "source_ids": row.get("source_ids"),
        }
    )


def _numeric_must_preserve_terms(item: dict[str, Any], base_quantity_rows: list[Any]) -> list[dict[str, Any]]:
    mandatory_surfaces = [
        str(row.get("value") or _dict(row.get("analyst_quantity_relevance")).get("quantity_value") or "").strip()
        for row in base_quantity_rows
        if isinstance(row, dict)
    ]
    rows = []
    for term in _string_list(item.get("must_preserve_terms")):
        if re.search(r"\d", term) and _term_elaborates_mandatory_quantity(term, mandatory_surfaces):
            rows.append({"value": term, "interpretation": "must-preserve numeric detail"})
    return rows


def _term_elaborates_mandatory_quantity(term: str, mandatory_surfaces: list[str]) -> bool:
    term_numbers = set(re.findall(r"\d+(?:\.\d+)?", str(term or "")))
    if not term_numbers:
        return False
    for surface in mandatory_surfaces:
        surface_numbers = set(re.findall(r"\d+(?:\.\d+)?", str(surface or "")))
        if surface_numbers and surface_numbers.intersection(term_numbers):
            return True
    return False


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


def _source_match_keys_by_id(packet: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for row in _list(packet.get("source_trail")):
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or row.get("citation_key") or "").strip()
        if not source_id:
            continue
        values = [
            source_id,
            row.get("citation_key"),
            row.get("source_label"),
            row.get("display_label"),
            row.get("source_slug"),
            row.get("original_source_id"),
            *_string_list(row.get("source_aliases")),
        ]
        mapping[source_id] = _dedupe(key for value in values if (key := _label_key(value)))
    return mapping


def _source_match_keys_for_sources(source_ids: list[str], source_match_keys_by_id: dict[str, list[str]]) -> list[str]:
    keys = []
    for source_id in source_ids:
        keys.extend(source_match_keys_by_id.get(source_id, []))
        key = _label_key(source_id)
        if key:
            keys.append(key)
    return _dedupe(keys)


def _source_ids_from_labels(item: dict[str, Any], source_ids_by_label: dict[str, str]) -> list[str]:
    labels = [*_string_list(item.get("source_labels")), *_string_list(item.get("source_label"))]
    ids = []
    for label in labels:
        source_id = source_ids_by_label.get(_label_key(label))
        if source_id:
            ids.append(source_id)
    return _dedupe(ids)


def _source_weight_judgments_by_source(canonical: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_source: dict[str, dict[str, Any]] = {}
    for row in _list(canonical.get("source_weight_judgments")):
        if not isinstance(row, dict):
            continue
        for source_id in _string_list(row.get("source_ids")):
            by_source[source_id] = row
    return by_source


def _citation_source_ids_for_contract(
    source_ids: list[str],
    *,
    role: str,
    item: dict[str, Any],
    obligation: dict[str, Any],
    quantities: list[dict[str, Any]],
    source_weights: dict[str, dict[str, Any]],
) -> list[str]:
    source_ids = _dedupe(source_ids)
    if len(source_ids) <= 1:
        return source_ids
    desired = _desired_source_weight_roles(role, item=item, obligation=obligation, quantities=quantities)
    if not desired:
        return source_ids
    scored: list[tuple[int, str]] = []
    for source_id in source_ids:
        weight = source_weights.get(source_id, {})
        score = _source_role_score(weight, desired)
        if score > 0:
            scored.append((score, source_id))
    selected = [source_id for _, source_id in sorted(scored, key=lambda row: (-row[0], source_ids.index(row[1])))]
    if selected:
        return selected[:2]
    quantity_sources = _quantity_source_ids(quantities)
    if quantity_sources and "calibration" in desired:
        return [source_id for source_id in source_ids if source_id in quantity_sources][:2] or source_ids[:2]
    return source_ids[:2] if len(source_ids) > 3 else source_ids


def _desired_source_weight_roles(
    role: str,
    *,
    item: dict[str, Any],
    obligation: dict[str, Any],
    quantities: list[dict[str, Any]],
) -> set[str]:
    text = " ".join(
        str(value or "")
        for value in (
            role,
            item.get("role"),
            item.get("reader_evidence_role"),
            item.get("decision_relevance"),
            obligation.get("role"),
            obligation.get("prose_instruction"),
        )
    ).lower()
    if quantities or any(token in text for token in ("quant", "magnitude", "calibrat", "estimate", "threshold", "dose")):
        return {"calibration"}
    if any(token in text for token in ("counter", "tension", "against", "weaken")):
        return {"counterweight", "boundary", "calibration"}
    if any(token in text for token in ("scope", "bound", "boundary", "limit", "caveat", "subgroup", "exception")):
        return {"boundary", "counterweight", "calibration"}
    if any(token in text for token in ("context", "practical", "guidance", "implementation")):
        return {"context", "direct_support"}
    return {"direct_support"}


def _source_weight_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in (
            "main_use",
            "source_type",
            "memo_weight_sentence",
            "why_weight_this_way",
            "reader_facing_limit",
            "what_not_to_use_it_for",
        )
    ).lower()


def _source_role_score(row: dict[str, Any], desired: set[str]) -> int:
    main_use = str(row.get("main_use") or "").lower()
    text = _source_weight_text(row)
    score = 0
    if "direct_support" in desired and re.search(r"\b(drives?_answer|primary_answer|direct_support|supports?_answer)\b", main_use):
        score += 6
    if "boundary" in desired and re.search(r"\b(bounds?_answer|boundary|scope|limiter|limits?_answer)\b", main_use):
        score += 6
    if "counterweight" in desired and re.search(r"\b(counter|tension|weaken)\b", main_use):
        score += 6
    if "calibration" in desired and re.search(r"\b(calibrat|magnitude|quant|estimate)\b", main_use):
        score += 6
    if "context" in desired and re.search(r"\b(context|contextual|guidance)\b", main_use):
        score += 6
    if score:
        return score
    if "direct_support" in desired and re.search(r"\b(directly supports|primary driver|drives the answer|load-bearing support)\b", text):
        score += 3
    if "boundary" in desired and re.search(r"\b(bound|bounds|boundary|scope|limit|caveat|subgroup)\b", text):
        score += 3
    if "counterweight" in desired and re.search(r"\b(counter|tension|weaken|risk|harm|mortality)\b", text):
        score += 3
    if "calibration" in desired and re.search(r"\b(calibrat|magnitude|dose|threshold|estimate|ratio|quantity)\b", text):
        score += 3
    if "context" in desired and re.search(r"\b(context|guidance|practical|pattern|implementation|advisory)\b", text):
        score += 3
    return score
