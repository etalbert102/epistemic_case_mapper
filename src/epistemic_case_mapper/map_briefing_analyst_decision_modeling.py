from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any

from pydantic import ValidationError

from epistemic_case_mapper.classical_ml import relation_edge_weight, tfidf_near_duplicate_pairs, weighted_pagerank
from epistemic_case_mapper.map_briefing_analyst_adjudication import deterministic_adjudication_scaffold
from epistemic_case_mapper.map_briefing_analyst_decision_logic import naturalize_decision_logic_payload
from epistemic_case_mapper.map_briefing_analyst_schemas import (
    AnalystDecisionModel,
    analyst_decision_retention_obligations,
    build_analyst_decision_model_parse_report,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import run_model_backend

DEFAULT_DECISION_MODEL_NUM_PREDICT = 12_288


def run_analyst_decision_model(
    *,
    ledger: dict[str, Any],
    adjudication: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    context = build_analyst_decision_context(ledger=ledger, adjudication=adjudication)
    prompt = build_analyst_decision_model_prompt(context)
    scaffold = deterministic_decision_model_scaffold(ledger=ledger, adjudication=adjudication, context=context)
    if backend.strip() == "prompt":
        parse_report = build_analyst_decision_model_parse_report(scaffold, ledger, retention_obligations=context.get("retention_obligations"))
        return {
            "analyst_decision_context": context,
            "analyst_decision_model": scaffold,
            "analyst_decision_model_prompt": prompt,
            "analyst_decision_model_raw": "",
            "analyst_decision_model_parse_report": parse_report,
            "analyst_decision_model_report": _report("prompt_backend_scaffold", parse_report),
        }
    try:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            num_predict=analyst_decision_model_num_predict(context),
        )
    except RuntimeError as exc:
        parse_report = build_analyst_decision_model_parse_report(scaffold, ledger, retention_obligations=context.get("retention_obligations"))
        return {
            "analyst_decision_context": context,
            "analyst_decision_model": scaffold,
            "analyst_decision_model_prompt": prompt,
            "analyst_decision_model_raw": "",
            "analyst_decision_model_parse_report": parse_report,
            "analyst_decision_model_report": _report("backend_error_scaffold", parse_report, issues=[str(exc)]),
        }
    payload = _extract_json(result.text)
    parse_report = build_analyst_decision_model_parse_report(payload, ledger, retention_obligations=context.get("retention_obligations"))
    if not parse_report.get("valid"):
        return {
            "analyst_decision_context": context,
            "analyst_decision_model": scaffold,
            "analyst_decision_model_prompt": prompt,
            "analyst_decision_model_raw": result.text,
            "analyst_decision_model_parse_report": parse_report,
            "analyst_decision_model_report": _report(
                "model_output_invalid_scaffold",
                parse_report,
                issues=["model decision model failed schema or evidence ID checks"],
            ),
        }
    parsed = AnalystDecisionModel.model_validate(payload).model_dump()
    parsed["decision_logic"] = naturalize_decision_logic_payload(_dict(parsed.get("decision_logic")))
    repair = _maybe_repair_decision_model(
        initial_model=parsed,
        initial_parse_report=parse_report,
        context=context,
        ledger=ledger,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    final_model = repair.get("analyst_decision_model", parsed) if repair.get("accepted") else parsed
    final_parse_report = repair.get("analyst_decision_model_parse_report", parse_report) if repair.get("accepted") else parse_report
    status = "accepted" if final_parse_report.get("status") == "ready" else "accepted_with_warnings"
    if repair.get("accepted"):
        status = "accepted_after_repair" if final_parse_report.get("status") == "ready" else "accepted_after_repair_with_warnings"
    return {
        "analyst_decision_context": context,
        "analyst_decision_model": final_model,
        "analyst_decision_model_prompt": prompt,
        "analyst_decision_model_raw": result.text,
        "analyst_decision_model_parse_report": final_parse_report,
        "analyst_decision_model_report": _report(status, final_parse_report, issues=_list(repair.get("issues"))),
        "analyst_decision_model_initial": parsed,
        "analyst_decision_model_initial_parse_report": parse_report,
        "analyst_decision_model_repair_prompt": repair.get("analyst_decision_model_repair_prompt", ""),
        "analyst_decision_model_repair_raw": repair.get("analyst_decision_model_repair_raw", ""),
        "analyst_decision_model_repair_parse_report": repair.get("analyst_decision_model_repair_parse_report", {}),
        "analyst_decision_model_repair_report": _compact_decision_model_repair_report(repair),
    }


def analyst_decision_model_num_predict(context: dict[str, Any] | None = None) -> int:
    del context
    try:
        return max(2048, int(os.environ.get("ECM_ANALYST_DECISION_MODEL_NUM_PREDICT", DEFAULT_DECISION_MODEL_NUM_PREDICT)))
    except ValueError:
        return DEFAULT_DECISION_MODEL_NUM_PREDICT


def _maybe_repair_decision_model(
    *,
    initial_model: dict[str, Any],
    initial_parse_report: dict[str, Any],
    context: dict[str, Any],
    ledger: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    repair_packet = _decision_model_repair_packet(initial_parse_report, context)
    if not repair_packet.get("omitted_obligations"):
        return _repair_report("not_needed", initial_parse_report, accepted=False)
    if backend.strip() == "prompt":
        return _repair_report("skipped_prompt_backend", initial_parse_report, accepted=False, issues=["prompt backend cannot run repair"])
    prompt = build_analyst_decision_model_repair_prompt(
        current_model=initial_model,
        parse_report=initial_parse_report,
        repair_packet=repair_packet,
        decision_question=str(context.get("decision_question") or ""),
    )
    try:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            num_predict=analyst_decision_model_num_predict(context),
        )
    except RuntimeError as exc:
        report = _repair_report("backend_error_kept_initial", initial_parse_report, accepted=False, issues=[str(exc)])
        report["analyst_decision_model_repair_prompt"] = prompt
        return report
    payload = _extract_json(result.text)
    candidate_parse_report = build_analyst_decision_model_parse_report(payload, ledger, retention_obligations=context.get("retention_obligations"))
    report = _repair_report(
        "candidate_invalid_kept_initial" if not candidate_parse_report.get("valid") else "candidate_evaluated",
        candidate_parse_report,
        accepted=False,
    )
    report["analyst_decision_model_repair_prompt"] = prompt
    report["analyst_decision_model_repair_raw"] = result.text
    report["analyst_decision_model_repair_parse_report"] = candidate_parse_report
    if not candidate_parse_report.get("valid"):
        return report
    candidate = AnalystDecisionModel.model_validate(payload).model_dump()
    candidate["decision_logic"] = naturalize_decision_logic_payload(_dict(candidate.get("decision_logic")))
    before_score = _decision_model_warning_score(initial_parse_report)
    after_score = _decision_model_warning_score(candidate_parse_report)
    report["before_warning_score"] = before_score
    report["after_warning_score"] = after_score
    if after_score >= before_score:
        report["status"] = "no_improvement_kept_initial"
        report["issues"] = ["repair did not reduce decision-model warning score"]
        return report
    report["status"] = "accepted"
    report["accepted"] = True
    report["analyst_decision_model"] = candidate
    report["analyst_decision_model_parse_report"] = candidate_parse_report
    report["issues"] = []
    return report


def build_analyst_decision_model_repair_prompt(
    *,
    current_model: dict[str, Any],
    parse_report: dict[str, Any],
    repair_packet: dict[str, Any],
    decision_question: str,
) -> str:
    packet = {
        "decision_question": decision_question,
        "task": [
            "Repair a valid analyst decision model that omitted decision-relevant obligations from evidence_groups.",
            "Return a complete analyst_decision_model_v1 JSON object, not a patch.",
            "Use the current model as the base; preserve its answer unless the omitted obligations require a bounded correction.",
            "For each omitted obligation, either add its evidence_item_id to the most appropriate evidence_group, create a new group, or add an explicit evidence_disposition explaining why it stays background.",
            "Do not remove already useful groups unless merging improves the argument.",
            "Keep support, counterweight, crux, quantity, and scope evidence analytically distinguishable.",
            "Return strict JSON only.",
        ],
        "current_model": current_model,
        "parse_report": {
            "issues": parse_report.get("issues", []),
            "missing_accounting_ids": parse_report.get("missing_accounting_ids", []),
            "obligation_omissions": parse_report.get("obligation_omissions", {}),
        },
        "repair_packet": repair_packet,
        "required_output_schema": {
            "schema_id": "analyst_decision_model_v1",
            "decision_question": decision_question,
            "direct_answer": "one sentence answering the decision question",
            "confidence": "low | medium | high | not_specified",
            "overall_rationale": "why the evidence groups support this answer",
            "evidence_groups": [
                {
                    "group_id": "stable group label",
                    "proposition": "decision-relevant proposition synthesized across covered evidence",
                    "memo_role": "one allowed memo role",
                    "importance_rank": "integer 1-100; 1 is most important globally",
                    "covered_evidence_item_ids": ["evidence IDs from current model or repair packet"],
                    "rationale": "why this group matters to the decision",
                    "evidence_strength": "brief strength assessment",
                    "answer_impact": "how this group supports, weakens, bounds, or changes the answer",
                    "uncertainty_type": "measurement, external validity, confounding, missing evidence, implementation, none, or other",
                    "applicability_limits": ["scope/population/context limits"],
                    "conflict_note": "how this group relates to conflicting evidence, if any",
                }
            ],
            "evidence_dispositions": [
                {
                    "evidence_item_id": "evidence ID from current model or repair packet",
                    "disposition": "foreground | background | not_decision_relevant | covered_by_group | needs_review",
                    "group_id": "group that uses or covers this item, if applicable",
                    "rationale": "why it is backgrounded, excluded, or needs review",
                }
            ],
            "quantitative_anchors": ["quantities that should survive final synthesis"],
            "what_would_change_the_answer": ["cruxes or missing evidence that would change the answer"],
            "decision_logic": "same object shape as current_model.decision_logic",
            "argument_plan": "same list shape as current_model.argument_plan",
        },
    }
    return (
        "You are repairing an intermediate analyst decision model for source-grounded memo synthesis.\n"
        "The model is already schema-valid; your job is only to account for omitted decision-relevant obligations.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def _decision_model_repair_packet(parse_report: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    omitted = {
        obligation_type: _string_list(ids)
        for obligation_type, ids in _dict(parse_report.get("obligation_omissions")).items()
        if _string_list(ids)
    }
    missing_accounting_ids = set(_string_list(parse_report.get("missing_accounting_ids")))
    all_omitted_ids = _dedupe([evidence_id for ids in omitted.values() for evidence_id in ids])
    row_lookup = {str(row.get("evidence_item_id") or ""): row for row in _list(context.get("evidence_rows")) if isinstance(row, dict)}
    return {
        "schema_id": "analyst_decision_model_repair_packet_v1",
        "omitted_obligations": {
            obligation_type: [_repair_context_row(row_lookup.get(evidence_id, {}), obligation_type) for evidence_id in ids]
            for obligation_type, ids in omitted.items()
        },
        "missing_accounting_rows": [
            _repair_context_row(row_lookup.get(evidence_id, {}), "missing_accounting")
            for evidence_id in sorted(missing_accounting_ids - set(all_omitted_ids))
        ][:12],
    }


def _repair_context_row(row: dict[str, Any], obligation_type: str) -> dict[str, Any]:
    return _drop_empty(
        {
            "evidence_item_id": row.get("evidence_item_id"),
            "obligation_type": obligation_type,
            "claim_id": row.get("claim_id"),
            "current_role": row.get("current_role"),
            "adjudicated_memo_use": row.get("adjudicated_memo_use"),
            "quantity_values": row.get("quantity_values", []),
            "source_labels": row.get("source_labels", []),
            "claim": _short_text(str(row.get("claim") or ""), 420),
            "source_excerpt": _short_text(str(row.get("source_excerpt") or ""), 260),
            "why_it_matters": _short_text(str(row.get("why_it_matters") or ""), 220),
            "relation_context": row.get("relation_context", [])[:3] if isinstance(row.get("relation_context"), list) else [],
        }
    )


def _decision_model_warning_score(parse_report: dict[str, Any]) -> int:
    omissions = sum(len(_string_list(ids)) for ids in _dict(parse_report.get("obligation_omissions")).values())
    missing = len(_string_list(parse_report.get("missing_accounting_ids")))
    fatal = 1000 if not parse_report.get("valid") else 0
    issue_penalty = len(_list(parse_report.get("issues")))
    covered = int(parse_report.get("covered_evidence_item_count") or 0)
    return fatal + omissions * 100 + missing * 10 + issue_penalty - covered


def _repair_report(
    status: str,
    parse_report: dict[str, Any],
    *,
    accepted: bool,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_id": "analyst_decision_model_repair_report_v1",
        "status": status,
        "accepted": accepted,
        "parse_status": parse_report.get("status"),
        "valid": parse_report.get("valid", False),
        "covered_evidence_item_count": parse_report.get("covered_evidence_item_count", 0),
        "missing_accounting_count": len(_string_list(parse_report.get("missing_accounting_ids"))),
        "obligation_omission_count": sum(len(_string_list(ids)) for ids in _dict(parse_report.get("obligation_omissions")).values()),
        "issues": issues or [],
    }


def _compact_decision_model_repair_report(repair: dict[str, Any]) -> dict[str, Any]:
    return {
        key: repair.get(key)
        for key in (
            "schema_id",
            "status",
            "accepted",
            "parse_status",
            "valid",
            "covered_evidence_item_count",
            "missing_accounting_count",
            "obligation_omission_count",
            "before_warning_score",
            "after_warning_score",
            "issues",
        )
        if key in repair
    }


def build_analyst_decision_context(*, ledger: dict[str, Any], adjudication: dict[str, Any]) -> dict[str, Any]:
    rows = [_context_row(row, adjudication) for row in _ledger_rows(ledger)]
    ids = [str(row.get("evidence_item_id") or "") for row in rows]
    texts = [str(row.get("claim") or "") for row in rows]
    duplicate_pairs = tfidf_near_duplicate_pairs(texts, ids, threshold=0.42)
    clusters = _duplicate_clusters(duplicate_pairs)
    centrality = _ledger_centrality(rows)
    for row in rows:
        row["centrality_score"] = centrality.get(str(row.get("evidence_item_id") or ""), 0.0)
        cluster_id = clusters.get(str(row.get("evidence_item_id") or ""))
        if cluster_id:
            row["similarity_cluster_id"] = cluster_id
    retention_obligations = _retention_obligation_context(ledger, rows)
    return {
        "schema_id": "analyst_decision_context_v1",
        "decision_question": str(ledger.get("decision_question") or "").strip(),
        "row_count": len(rows),
        "evidence_rows": rows,
        "retention_obligations": retention_obligations,
        "obligation_group_skeleton": _obligation_group_skeleton(retention_obligations),
        "model_hints": {
            "method": "tfidf_near_duplicate_hints_plus_relation_graph_centrality",
            "near_duplicate_pairs": [
                {"left": left, "right": right, "score": score}
                for left, right, score in duplicate_pairs[:60]
            ],
            "similarity_clusters": _cluster_rows(clusters),
            "top_central_evidence_item_ids": [
                row_id
                for row_id, _score in sorted(centrality.items(), key=lambda item: (-item[1], item[0]))[:20]
            ],
            "memo_use_counts": dict(Counter(str(row.get("adjudicated_memo_use") or "unknown") for row in rows)),
        },
    }


def build_analyst_decision_model_prompt(context: dict[str, Any]) -> str:
    packet = {
        "decision_question": context.get("decision_question"),
        "task": [
            "Construct a global decision model from the evidence ledger.",
            "Use evidence IDs to form higher-level evidence groups; do not merely classify rows one by one.",
            "Start from obligation_group_skeleton before inventing other groups. Each skeleton group lists evidence that needs an explicit home in the argument.",
            "You may merge skeleton groups or move an item to a better group when the reasoning calls for it, but every skeleton evidence_item_id should either be covered by an evidence_group or explicitly dispositioned.",
            "Rank groups by how much they should affect the answer.",
            "Use model_hints as clues only: centrality and similarity are not semantic decisions.",
            "Treat candidate_decision_edge rows as provisional analytic links; use their anchors, confidence, failure conditions, and endpoint claims to decide whether they reconcile, bound, weaken, or should be backgrounded.",
            "Do not preserve a proposed relation label when its rationale or anchors imply a different decision role; explain downgrades in evidence_dispositions or group rationale.",
            "Put redundant or subordinate rows into the same group when they support the same proposition.",
            "Include counterweights, scope boundaries, cruxes, mechanisms, and quantitative anchors when they materially change the decision read.",
            "Before compressing evidence, check retention_obligations and obligation_group_skeleton. Quantitative anchors, counterweights, cruxes, and scope boundaries listed there should normally appear in evidence_groups; if one is backgrounded or excluded, make that decision explicit in evidence_dispositions with a rationale.",
            "Keep support and counterweight evidence analytically separate unless the proposition explicitly explains how the tension is resolved. Do not bury contrary evidence inside a support group.",
            "Preserve actionable quantities as quantities, not just as generic prose.",
            "Use covered_evidence_item_ids inside evidence_groups for foreground accounting.",
            "Keep evidence_dispositions short: include only rows not covered by any evidence group or rows whose exclusion/backgrounding/review status needs to be explicit.",
            "Use ordinary analyst language for direct_answer, proposition, rationale, answer_impact, and decision_logic.",
            "Return strict JSON only.",
        ],
        "allowed_memo_role": [
            "load_bearing_primary_support",
            "load_bearing_counterweight",
            "quantitative_anchor",
            "scope_or_applicability",
            "decision_crux",
            "mechanism_or_context",
            "background_only",
            "needs_human_or_model_review",
        ],
        "allowed_disposition": [
            "foreground",
            "background",
            "not_decision_relevant",
            "covered_by_group",
            "needs_review",
        ],
        "required_output_schema": {
            "schema_id": "analyst_decision_model_v1",
            "decision_question": context.get("decision_question"),
            "direct_answer": "one sentence answering the decision question",
            "confidence": "low | medium | high | not_specified",
            "overall_rationale": "why the evidence groups support this answer",
            "evidence_groups": [
                {
                    "group_id": "stable group label",
                    "proposition": "decision-relevant proposition synthesized across covered evidence",
                    "memo_role": "one allowed_memo_role value",
                    "importance_rank": "integer 1-100; 1 is most important globally",
                    "covered_evidence_item_ids": ["evidence IDs from context"],
                    "rationale": "why this group matters to the decision",
                    "evidence_strength": "brief strength assessment",
                    "answer_impact": "how this group supports, weakens, bounds, or changes the answer",
                    "uncertainty_type": "measurement, external validity, confounding, missing evidence, implementation, none, or other",
                    "applicability_limits": ["scope/population/context limits"],
                    "conflict_note": "how this group relates to conflicting evidence, if any",
                }
            ],
            "evidence_dispositions": [
                {
                    "evidence_item_id": "evidence ID from context",
                    "disposition": "one allowed_disposition value",
                    "group_id": "group that uses or covers this item, if applicable",
                    "rationale": "why it is backgrounded, excluded, or needs review; omit rows already covered by evidence_groups unless there is a special reason",
                }
            ],
            "quantitative_anchors": ["quantities that should survive final synthesis"],
            "what_would_change_the_answer": ["cruxes or missing evidence that would change the answer"],
            "decision_logic": {
                "bounded_bottom_line": "specific answer with confidence boundary",
                "support_summary": "load-bearing support in one or two sentences",
                "strongest_counterweight": "strongest contrary or limiting consideration",
                "counterweight_weighting": "why it changes, weakens, or only bounds the answer",
                "reconciled_cruxes": ["cruxes written as resolved analyst guidance where possible"],
                "scope_boundaries": ["where the answer applies or does not apply"],
                "practical_implications": ["decision implications"],
                "do_not_overstate": ["claims the memo must not imply"],
            },
            "argument_plan": [
                {
                    "step_id": "stable step label",
                    "section": "memo section",
                    "writing_goal": "what this paragraph must accomplish",
                    "required_points": ["claims, quantities, caveats, or comparisons to include"],
                    "evidence_item_ids": ["evidence IDs this step uses"],
                    "transition_from_previous": "how this reasoning step should connect",
                }
            ],
        },
        "context": context,
    }
    return (
        "You are a senior decision analyst building the intermediate decision model for a later memo writer.\n"
        "Your job is global evidence organization, weighting, and argument construction.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def deterministic_decision_model_scaffold(
    *,
    ledger: dict[str, Any],
    adjudication: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = _adjudication_rows(adjudication) or _list(deterministic_adjudication_scaffold(ledger).get("rows"))
    ledger_by_id = {str(row.get("evidence_item_id") or ""): row for row in _ledger_rows(ledger)}
    groups = []
    dispositions = []
    for index, row in enumerate(rows, start=1):
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        if not evidence_id:
            continue
        memo_use = str(row.get("memo_use") or "background_only")
        ledger_row = ledger_by_id.get(evidence_id, {})
        if memo_use == "not_decision_relevant":
            dispositions.append(
                {
                    "evidence_item_id": evidence_id,
                    "disposition": "not_decision_relevant",
                    "group_id": "",
                    "rationale": str(row.get("downgrade_reason") or row.get("rationale") or "Outside the decision question."),
                }
            )
            continue
        if memo_use == "covered_by_group":
            dispositions.append(
                {
                    "evidence_item_id": evidence_id,
                    "disposition": "covered_by_group",
                    "group_id": "",
                    "rationale": str(row.get("rationale") or "Covered by another evidence group."),
                }
            )
            continue
        group_id = f"analyst_decision_group_{len(groups) + 1:03d}"
        groups.append(
            {
                "group_id": group_id,
                "proposition": _short_text(str(ledger_row.get("claim") or row.get("rationale") or evidence_id), 520),
                "memo_role": memo_use,
                "importance_rank": int(row.get("importance_rank", 100) or 100),
                "covered_evidence_item_ids": [evidence_id],
                "rationale": _short_text(str(row.get("rationale") or ledger_row.get("why_it_matters") or "Adjudicated as relevant."), 320),
                "evidence_strength": "",
                "answer_impact": "",
                "uncertainty_type": "",
                "applicability_limits": [],
                "conflict_note": "",
            }
        )
        dispositions.append(
            {
                "evidence_item_id": evidence_id,
                "disposition": "foreground" if memo_use in _foreground_memo_uses() else "background",
                "group_id": group_id,
                "rationale": str(row.get("rationale") or ""),
            }
        )
    question = str(ledger.get("decision_question") or "").strip()
    direct = _scaffold_direct_answer(groups, question)
    return {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": question,
        "direct_answer": direct,
        "confidence": "not_specified",
        "overall_rationale": "Scaffold only; live global analyst decision modeling was not accepted.",
        "evidence_groups": groups,
        "evidence_dispositions": dispositions,
        "quantitative_anchors": _dedupe(
            [
                quantity
                for row in _ledger_rows(ledger)
                for quantity in _string_list(row.get("quantity_values"))
            ]
        )[:12],
        "what_would_change_the_answer": [
            str(group.get("proposition") or "")
            for group in groups
            if group.get("memo_role") == "decision_crux"
        ][:6],
        "decision_logic": {
            "bounded_bottom_line": direct,
            "support_summary": _first_group(groups, "load_bearing_primary_support"),
            "strongest_counterweight": _first_group(groups, "load_bearing_counterweight"),
            "counterweight_weighting": "Use counterweights to bound the answer if they do not overturn the primary support.",
            "reconciled_cruxes": [str(group.get("proposition") or "") for group in groups if group.get("memo_role") == "decision_crux"][:4],
            "scope_boundaries": [str(group.get("proposition") or "") for group in groups if group.get("memo_role") == "scope_or_applicability"][:4],
            "practical_implications": [],
            "do_not_overstate": [],
        },
        "argument_plan": _scaffold_argument_plan(groups),
    }


def _context_row(row: dict[str, Any], adjudication: dict[str, Any]) -> dict[str, Any]:
    evidence_id = str(row.get("evidence_item_id") or "").strip()
    adjudicated = _adjudication_by_id(adjudication).get(evidence_id, {})
    return {
        "evidence_item_id": evidence_id,
        "claim_id": row.get("claim_id"),
        "input_kind": row.get("input_kind"),
        "current_role": row.get("current_role"),
        "current_priority": row.get("current_priority"),
        "current_weight": row.get("current_weight"),
        "directionality": row.get("directionality"),
        "relation_semantic_role": row.get("relation_semantic_role"),
        "relation_contract": row.get("relation_contract", {}),
        "candidate_pair": row.get("candidate_pair", {}),
        "endpoint_claims": row.get("endpoint_claims", []),
        "adjudicated_memo_use": adjudicated.get("memo_use"),
        "adjudicated_importance_rank": adjudicated.get("importance_rank"),
        "source_labels": row.get("source_labels", []),
        "source_ids": row.get("source_ids", []),
        "claim": _short_text(str(row.get("claim") or ""), 620),
        "source_excerpt": _short_text(str(row.get("source_excerpt") or ""), 360),
        "quantity_values": row.get("quantity_values", []),
        "why_it_matters": _short_text(str(row.get("why_it_matters") or adjudicated.get("rationale") or ""), 280),
        "failure_condition": _short_text(str(row.get("failure_condition") or ""), 220),
        "relation_context": _compact_relation_context(row.get("relation_context", [])),
        "existing_warning_codes": row.get("existing_warning_codes", []),
    }


def _retention_obligation_context(ledger: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    obligations = analyst_decision_retention_obligations(ledger)
    row_by_id = {str(row.get("evidence_item_id") or ""): row for row in rows}
    for row in rows:
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        if not evidence_id:
            continue
        adjudicated = str(row.get("adjudicated_memo_use") or "").strip()
        if adjudicated == "quantitative_anchor":
            obligations.setdefault("quantitative_anchor_ids", []).append(evidence_id)
        elif adjudicated == "load_bearing_counterweight":
            obligations.setdefault("counterweight_ids", []).append(evidence_id)
        elif adjudicated == "decision_crux":
            obligations.setdefault("crux_ids", []).append(evidence_id)
        elif adjudicated == "scope_or_applicability":
            obligations.setdefault("scope_boundary_ids", []).append(evidence_id)
    obligations = {key: _dedupe(values) for key, values in obligations.items()}
    return {
        "quantitative_anchors": [_obligation_row(row_by_id.get(evidence_id, {})) for evidence_id in obligations["quantitative_anchor_ids"]],
        "counterweights": [_obligation_row(row_by_id.get(evidence_id, {})) for evidence_id in obligations["counterweight_ids"]],
        "cruxes": [_obligation_row(row_by_id.get(evidence_id, {})) for evidence_id in obligations["crux_ids"]],
        "scope_boundaries": [_obligation_row(row_by_id.get(evidence_id, {})) for evidence_id in obligations["scope_boundary_ids"]],
    }


def _obligation_group_skeleton(retention_obligations: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    obligation_types = (
        ("cruxes", "must_account_decision_cruxes", "decision_crux", "Evidence that would most change or resolve the answer."),
        ("counterweights", "must_account_counterweights", "load_bearing_counterweight", "Evidence that weakens, reverses, or materially bounds the answer."),
        ("quantitative_anchors", "must_account_quantitative_anchors", "quantitative_anchor", "Actionable quantities, thresholds, effect sizes, or numeric guidance that should survive synthesis."),
        ("scope_boundaries", "must_account_scope_boundaries", "scope_or_applicability", "Evidence that determines where the answer applies or does not apply."),
    )
    assignments: dict[str, list[str]] = {}
    row_lookup: dict[str, dict[str, Any]] = {}
    for obligation_type, *_unused in obligation_types:
        for row in retention_obligations.get(obligation_type, []):
            if not isinstance(row, dict):
                continue
            evidence_id = str(row.get("evidence_item_id") or "").strip()
            if not evidence_id:
                continue
            assignments.setdefault(evidence_id, []).append(obligation_type)
            row_lookup.setdefault(evidence_id, row)

    used: set[str] = set()
    skeleton: list[dict[str, Any]] = []
    for obligation_type, group_id, memo_role, purpose in obligation_types:
        selected_ids = [
            evidence_id
            for evidence_id, types in assignments.items()
            if evidence_id not in used and types and types[0] == obligation_type
        ]
        if not selected_ids:
            continue
        used.update(selected_ids)
        skeleton.append(
            {
                "skeleton_group_id": group_id,
                "target_memo_role": memo_role,
                "primary_obligation_type": obligation_type,
                "purpose": purpose,
                "evidence_item_ids": selected_ids,
                "evidence_summaries": [_obligation_skeleton_row(row_lookup[evidence_id], assignments[evidence_id]) for evidence_id in selected_ids],
                "model_action": "Use this as a starting group, merge into a better group, or explicitly disposition each item with rationale.",
            }
        )
    return skeleton


def _obligation_skeleton_row(row: dict[str, Any], obligation_types: list[str]) -> dict[str, Any]:
    return _drop_empty(
        {
            "evidence_item_id": row.get("evidence_item_id"),
            "obligation_types": obligation_types,
            "claim": _short_text(str(row.get("claim") or ""), 220),
            "quantity_values": row.get("quantity_values", []),
            "why_it_matters": _short_text(str(row.get("why_it_matters") or ""), 160),
        }
    )


def _obligation_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "evidence_item_id": row.get("evidence_item_id"),
            "claim_id": row.get("claim_id"),
            "adjudicated_memo_use": row.get("adjudicated_memo_use"),
            "current_role": row.get("current_role"),
            "quantity_values": row.get("quantity_values", []),
            "claim": _short_text(str(row.get("claim") or ""), 260),
            "why_it_matters": _short_text(str(row.get("why_it_matters") or ""), 180),
        }
    )


def _ledger_centrality(rows: list[dict[str, Any]]) -> dict[str, float]:
    claim_to_evidence = {
        str(row.get("claim_id") or ""): str(row.get("evidence_item_id") or "")
        for row in rows
        if str(row.get("claim_id") or "").strip() and str(row.get("evidence_item_id") or "").strip()
    }
    edges = []
    for row in rows:
        left = str(row.get("evidence_item_id") or "")
        for relation in _list(row.get("relation_context")):
            if not isinstance(relation, dict):
                continue
            other = claim_to_evidence.get(str(relation.get("other_claim_id") or ""))
            if left and other:
                edges.append((left, other, relation_edge_weight(str(relation.get("relation_type") or ""))))
    return weighted_pagerank([str(row.get("evidence_item_id") or "") for row in rows], edges) if edges else {
        str(row.get("evidence_item_id") or ""): 0.0 for row in rows
    }


def _cluster_rows(clusters: dict[str, str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for evidence_id, cluster_id in clusters.items():
        grouped.setdefault(cluster_id, []).append(evidence_id)
    return [
        {"cluster_id": cluster_id, "evidence_item_ids": sorted(ids), "size": len(ids)}
        for cluster_id, ids in sorted(grouped.items())
        if len(ids) > 1
    ]


def _duplicate_clusters(pairs: list[tuple[str, str, float]]) -> dict[str, str]:
    parent: dict[str, str] = {}
    for left, right, _score in pairs:
        _union(parent, left, right)
    roots = {evidence_id: _find(parent, evidence_id) for pair in pairs for evidence_id in pair[:2]}
    ordered_roots = {root: f"similarity_cluster_{index:03d}" for index, root in enumerate(sorted(set(roots.values())), start=1)}
    return {evidence_id: ordered_roots[root] for evidence_id, root in roots.items()}


def _union(parent: dict[str, str], left: str, right: str) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root != right_root:
        parent[max(left_root, right_root)] = min(left_root, right_root)


def _find(parent: dict[str, str], value: str) -> str:
    parent.setdefault(value, value)
    while parent[value] != value:
        parent[value] = parent[parent[value]]
        value = parent[value]
    return value


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        return json.loads(_repair_json(text))
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(_repair_json(fenced.group(1).strip()))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(_repair_json(text[start : end + 1]))
        except json.JSONDecodeError:
            return {}
    return {}


def _repair_json(text: str) -> str:
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r":\s*null\b", ": []", text)
    return text


def _report(status: str, parse_report: dict[str, Any], *, issues: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_id": "analyst_decision_model_report_v1",
        "status": status,
        "accepted": status.startswith("accepted") or status == "prompt_backend_scaffold",
        "parse_status": parse_report.get("status"),
        "valid": parse_report.get("valid", False),
        "ledger_row_count": parse_report.get("ledger_row_count", 0),
        "group_count": parse_report.get("group_count", 0),
        "covered_evidence_item_count": parse_report.get("covered_evidence_item_count", 0),
        "issues": _dedupe([*(issues or []), *[str(issue) for issue in _list(parse_report.get("issues"))]]),
    }


def _ledger_rows(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(ledger.get("rows")) if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()]


def _adjudication_rows(adjudication: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(adjudication.get("rows")) if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()]


def _adjudication_by_id(adjudication: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("evidence_item_id") or ""): row for row in _adjudication_rows(adjudication)}


def _compact_relation_context(rows: Any) -> list[dict[str, Any]]:
    compact = []
    for row in _list(rows)[:6]:
        if not isinstance(row, dict):
            continue
        compact.append(
            {
                "relation_type": row.get("relation_type"),
                "relation_confidence": row.get("relation_confidence"),
                "relation_contract": row.get("relation_contract", {}),
                "candidate_pair": row.get("candidate_pair", {}),
                "other_claim_id": row.get("other_claim_id"),
                "other_claim": _short_text(str(row.get("other_claim") or ""), 180),
                "rationale": _short_text(str(row.get("rationale") or ""), 180),
            }
        )
    return compact


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if value not in ("", None, [], {})
    }


def _foreground_memo_uses() -> set[str]:
    return {
        "load_bearing_primary_support",
        "load_bearing_counterweight",
        "quantitative_anchor",
        "scope_or_applicability",
        "decision_crux",
        "mechanism_or_context",
    }


def _scaffold_direct_answer(groups: list[dict[str, Any]], question: str) -> str:
    primary = _first_group(groups, "load_bearing_primary_support")
    counter = _first_group(groups, "load_bearing_counterweight")
    if primary and counter:
        return _short_text(f"The evidence supports a bounded answer to '{question}': {primary} The main limiting consideration is {counter}", 420)
    return _short_text(primary or counter or f"Use the grouped evidence to answer: {question}", 420)


def _first_group(groups: list[dict[str, Any]], memo_role: str) -> str:
    for group in groups:
        if group.get("memo_role") == memo_role:
            return str(group.get("proposition") or "").strip()
    return ""


def _scaffold_argument_plan(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = []
    for role, step_id, goal in (
        ("load_bearing_primary_support", "answer_and_support", "State the direct answer and main support."),
        ("load_bearing_counterweight", "counterweight", "Weigh the strongest counterweight against the support."),
        ("scope_or_applicability", "scope", "Bound the answer to the right population or context."),
        ("decision_crux", "crux", "State what would change the answer."),
    ):
        selected = [group for group in groups if group.get("memo_role") == role][:4]
        if not selected:
            continue
        steps.append(
            {
                "step_id": step_id,
                "section": "Decision Brief",
                "writing_goal": goal,
                "required_points": [str(group.get("proposition") or "") for group in selected],
                "evidence_item_ids": [
                    evidence_id
                    for group in selected
                    for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
                ],
                "transition_from_previous": "Connect this reasoning step to the weighted answer.",
            }
        )
    return steps
