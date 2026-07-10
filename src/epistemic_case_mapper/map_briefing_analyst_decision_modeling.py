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
        parse_report = build_analyst_decision_model_parse_report(scaffold, ledger)
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
        parse_report = build_analyst_decision_model_parse_report(scaffold, ledger)
        return {
            "analyst_decision_context": context,
            "analyst_decision_model": scaffold,
            "analyst_decision_model_prompt": prompt,
            "analyst_decision_model_raw": "",
            "analyst_decision_model_parse_report": parse_report,
            "analyst_decision_model_report": _report("backend_error_scaffold", parse_report, issues=[str(exc)]),
        }
    payload = _extract_json(result.text)
    parse_report = build_analyst_decision_model_parse_report(payload, ledger)
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
    return {
        "analyst_decision_context": context,
        "analyst_decision_model": parsed,
        "analyst_decision_model_prompt": prompt,
        "analyst_decision_model_raw": result.text,
        "analyst_decision_model_parse_report": parse_report,
        "analyst_decision_model_report": _report("accepted" if parse_report.get("status") == "ready" else "accepted_with_warnings", parse_report),
    }


def analyst_decision_model_num_predict(context: dict[str, Any] | None = None) -> int:
    del context
    try:
        return max(2048, int(os.environ.get("ECM_ANALYST_DECISION_MODEL_NUM_PREDICT", DEFAULT_DECISION_MODEL_NUM_PREDICT)))
    except ValueError:
        return DEFAULT_DECISION_MODEL_NUM_PREDICT


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
    return {
        "schema_id": "analyst_decision_context_v1",
        "decision_question": str(ledger.get("decision_question") or "").strip(),
        "row_count": len(rows),
        "evidence_rows": rows,
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
            "Rank groups by how much they should affect the answer.",
            "Use model_hints as clues only: centrality and similarity are not semantic decisions.",
            "Treat candidate_decision_edge rows as provisional analytic links; use their anchors, confidence, failure conditions, and endpoint claims to decide whether they reconcile, bound, weaken, or should be backgrounded.",
            "Do not preserve a proposed relation label when its rationale or anchors imply a different decision role; explain downgrades in evidence_dispositions or group rationale.",
            "Put redundant or subordinate rows into the same group when they support the same proposition.",
            "Include counterweights, scope boundaries, cruxes, mechanisms, and quantitative anchors when they materially change the decision read.",
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
