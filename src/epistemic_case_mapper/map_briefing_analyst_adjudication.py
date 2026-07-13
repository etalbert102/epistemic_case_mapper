from __future__ import annotations

import json
import os
import re
from typing import Any

from epistemic_case_mapper.map_briefing_analyst_schemas import (
    AnalystAdjudication,
    EvidenceAdjudicationRow,
    build_analyst_adjudication_parse_report,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import model_parallelism, run_model_backend, run_parallel

DEFAULT_CHUNK_SIZE = 6


def run_analyst_adjudication(
    ledger: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_analyst_adjudication_prompt(ledger)
    scaffold = deterministic_adjudication_scaffold(ledger)
    if backend.strip() == "prompt":
        parse_report = build_analyst_adjudication_parse_report(scaffold, ledger)
        return {
            "analyst_adjudication": scaffold,
            "analyst_adjudication_prompt": prompt,
            "analyst_adjudication_raw": "",
            "analyst_adjudication_parse_report": parse_report,
            "analyst_adjudication_chunk_reports": _chunk_report_bundle(
                [_chunk_report(1, 1, "prompt_backend_scaffold", parse_report)],
                scaffold_chunk_count=1,
            ),
            "analyst_adjudication_report": _report("prompt_backend_scaffold", parse_report),
        }
    return _run_live_adjudication(
        ledger,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        scaffold=scaffold,
    )


def _run_live_adjudication(
    ledger: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    scaffold: dict[str, Any],
) -> dict[str, Any]:
    ledger_rows = [row for row in _list(ledger.get("rows")) if isinstance(row, dict)]
    all_ids = [str(row.get("evidence_item_id")) for row in ledger_rows if str(row.get("evidence_item_id") or "")]
    chunks = _chunks(ledger_rows, _chunk_size())
    chunk_results = run_parallel(
        list(enumerate(chunks, start=1)),
        lambda item: _run_adjudication_chunk(
            item,
            ledger=ledger,
            total=len(chunks),
            all_ids=all_ids,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
        ),
        max_workers=model_parallelism(backend),
    )
    prompts = [str(row.get("prompt") or "") for row in chunk_results]
    raws = [str(row.get("raw_block") or "") for row in chunk_results]
    merged_rows = [
        merged_row
        for row in chunk_results
        for merged_row in _list(row.get("rows"))
        if isinstance(merged_row, dict)
    ]
    chunk_reports = [
        row.get("chunk_report")
        for row in chunk_results
        if isinstance(row.get("chunk_report"), dict)
    ]
    scaffold_chunk_count = sum(1 for row in chunk_results if row.get("used_scaffold"))
    merged = {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": ledger.get("decision_question", ""),
        "rows": _order_rows_by_ledger(_dedupe_adjudication_rows(merged_rows), all_ids),
        "overall_rationale": _merged_rationale(chunk_reports),
    }
    parse_report = build_analyst_adjudication_parse_report(merged, ledger)
    status = "accepted" if parse_report.get("valid") and scaffold_chunk_count == 0 else (
        "accepted_with_chunk_scaffold" if parse_report.get("valid") else "model_output_invalid_scaffold"
    )
    return {
        "analyst_adjudication": merged if parse_report.get("valid") else scaffold,
        "analyst_adjudication_prompt": "\n\n".join(prompts),
        "analyst_adjudication_raw": "\n\n".join(raws),
        "analyst_adjudication_parse_report": parse_report,
        "analyst_adjudication_chunk_reports": {
            "schema_id": "analyst_adjudication_chunk_reports_v1",
            "chunk_count": len(chunks),
            "scaffold_chunk_count": scaffold_chunk_count,
            "parallelism": model_parallelism(backend),
            "chunks": chunk_reports,
        },
        "analyst_adjudication_report": _report(
            status,
            parse_report,
            issues=["one_or_more_chunks_used_scaffold"] if scaffold_chunk_count else [],
        ),
    }


def _run_adjudication_chunk(
    item: tuple[int, list[dict[str, Any]]],
    *,
    ledger: dict[str, Any],
    total: int,
    all_ids: list[str],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    index, rows = item
    chunk_ledger = _chunk_ledger(ledger, rows, index=index, total=total)
    chunk_prompt = build_analyst_adjudication_prompt(chunk_ledger)
    prompt_block = f"<!-- analyst adjudication chunk {index}/{total} -->\n{chunk_prompt}"
    try:
        result = run_model_backend(chunk_prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
        raw = result.text
    except RuntimeError as exc:
        chunk_scaffold = deterministic_adjudication_scaffold(chunk_ledger)
        parse_report = build_analyst_adjudication_parse_report(chunk_scaffold, chunk_ledger)
        return {
            "prompt": prompt_block,
            "raw_block": f"<!-- chunk {index} backend error: {exc} -->",
            "rows": chunk_scaffold.get("rows", []),
            "used_scaffold": True,
            "chunk_report": _chunk_report(index, total, "backend_error_scaffold", parse_report, issues=[str(exc)]),
        }
    payload = _repair_covered_by_aliases(_extract_json(raw), all_ids)
    expected_ids = [str(row.get("evidence_item_id")) for row in rows if str(row.get("evidence_item_id") or "")]
    parse_report = build_analyst_adjudication_parse_report(
        payload,
        chunk_ledger,
        expected_evidence_item_ids=expected_ids,
        known_evidence_item_ids=all_ids,
    )
    if parse_report.get("valid"):
        parsed = AnalystAdjudication.model_validate(payload).model_dump()
        return {
            "prompt": prompt_block,
            "raw_block": f"<!-- analyst adjudication chunk {index}/{total} -->\n{raw}",
            "rows": parsed.get("rows", []),
            "used_scaffold": False,
            "chunk_report": _chunk_report(index, total, "accepted", parse_report),
        }
    salvaged_rows, salvage_report = _salvage_adjudication_chunk_rows(
        payload,
        chunk_ledger=chunk_ledger,
        expected_ids=expected_ids,
        all_ids=all_ids,
    )
    if salvage_report["salvaged_model_row_count"]:
        chunk_parse_report = build_analyst_adjudication_parse_report(
            {
                "schema_id": "analyst_adjudication_v1",
                "decision_question": chunk_ledger.get("decision_question", ""),
                "rows": salvaged_rows,
                "overall_rationale": "Invalid chunk payload was salvaged row by row; scaffold rows fill missing or invalid model rows.",
            },
            chunk_ledger,
            expected_evidence_item_ids=expected_ids,
            known_evidence_item_ids=all_ids,
        )
        report = _chunk_report(
            index,
            total,
            "model_output_invalid_salvaged_with_scaffold",
            chunk_parse_report,
            issues=["chunk failed whole-payload validation; valid model rows were salvaged"],
        )
        report.update(salvage_report)
        report["original_parse_report"] = parse_report
        return {
            "prompt": prompt_block,
            "raw_block": f"<!-- analyst adjudication chunk {index}/{total} -->\n{raw}",
            "rows": salvaged_rows,
            "used_scaffold": True,
            "chunk_report": report,
        }
    chunk_scaffold = deterministic_adjudication_scaffold(chunk_ledger)
    return {
        "prompt": prompt_block,
        "raw_block": f"<!-- analyst adjudication chunk {index}/{total} -->\n{raw}",
        "rows": chunk_scaffold.get("rows", []),
        "used_scaffold": True,
        "chunk_report": _chunk_report(
            index,
            total,
            "model_output_invalid_scaffold",
            parse_report,
            issues=["chunk failed schema or ledger accounting checks"],
        ),
    }


def _salvage_adjudication_chunk_rows(
    payload: Any,
    *,
    chunk_ledger: dict[str, Any],
    expected_ids: list[str],
    all_ids: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scaffold_rows = deterministic_adjudication_scaffold(chunk_ledger).get("rows", [])
    scaffold_by_id = {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(scaffold_rows)
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "")
    }
    accepted: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    known_ids = set(all_ids) | set(expected_ids)
    for index, row in enumerate(_list(payload.get("rows") if isinstance(payload, dict) else None)):
        if not isinstance(row, dict):
            rejected.append({"row_index": index, "reason": "row_not_object"})
            continue
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        if not evidence_id:
            rejected.append({"row_index": index, "reason": "missing_evidence_item_id"})
            continue
        if evidence_id not in expected_ids:
            rejected.append({"row_index": index, "evidence_item_id": evidence_id, "reason": "unexpected_evidence_item_id"})
            continue
        if evidence_id in accepted:
            rejected.append({"row_index": index, "evidence_item_id": evidence_id, "reason": "duplicate_evidence_item_id"})
            continue
        candidate = _adjudication_row_candidate(row, scaffold_by_id.get(evidence_id, {}), known_ids=known_ids)
        try:
            accepted[evidence_id] = EvidenceAdjudicationRow.model_validate(candidate).model_dump()
        except ValueError as exc:
            rejected.append({"row_index": index, "evidence_item_id": evidence_id, "reason": type(exc).__name__})
    ordered = [
        accepted.get(row_id) or scaffold_by_id[row_id]
        for row_id in expected_ids
        if row_id in accepted or row_id in scaffold_by_id
    ]
    scaffolded = [row_id for row_id in expected_ids if row_id not in accepted]
    return ordered, {
        "salvaged_model_row_count": len(accepted),
        "scaffolded_row_count": len(scaffolded),
        "invalid_model_row_count": len(rejected),
        "scaffolded_evidence_item_ids": scaffolded,
        "invalid_model_rows": rejected[:20],
    }


def _adjudication_row_candidate(row: dict[str, Any], scaffold: dict[str, Any], *, known_ids: set[str]) -> dict[str, Any]:
    allowed_keys = {
        "evidence_item_id",
        "memo_use",
        "importance_rank",
        "rationale",
        "answer_relation",
        "covered_by",
        "source_ids",
        "quantity_values",
        "target_answer_option",
        "effect_on_final_answer",
        "tension_type",
        "downgrade_reason",
    }
    candidate = {key: scaffold.get(key) for key in allowed_keys if key in scaffold}
    candidate.update({key: row.get(key) for key in allowed_keys if key in row})
    candidate["covered_by"] = [target for target in _string_list(candidate.get("covered_by")) if target in known_ids]
    return candidate


def run_analyst_adjudication_single_call_for_test(
    ledger: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_analyst_adjudication_prompt(ledger)
    scaffold = deterministic_adjudication_scaffold(ledger)
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        parse_report = build_analyst_adjudication_parse_report(scaffold, ledger)
        return {
            "analyst_adjudication": scaffold,
            "analyst_adjudication_prompt": prompt,
            "analyst_adjudication_raw": "",
            "analyst_adjudication_parse_report": parse_report,
            "analyst_adjudication_chunk_reports": _chunk_report_bundle(
                [_chunk_report(1, 1, "backend_error_scaffold", parse_report, issues=[str(exc)])],
                scaffold_chunk_count=1,
            ),
            "analyst_adjudication_report": _report("backend_error_scaffold", parse_report, issues=[str(exc)]),
        }
    raw = result.text
    payload = _repair_covered_by_aliases(_extract_json(raw), _ledger_ids(ledger))
    parse_report = build_analyst_adjudication_parse_report(payload, ledger)
    if not parse_report.get("valid"):
        return {
            "analyst_adjudication": scaffold,
            "analyst_adjudication_prompt": prompt,
            "analyst_adjudication_raw": raw,
            "analyst_adjudication_parse_report": parse_report,
            "analyst_adjudication_chunk_reports": _chunk_report_bundle(
                [_chunk_report(1, 1, "model_output_invalid_scaffold", parse_report)],
                scaffold_chunk_count=1,
            ),
            "analyst_adjudication_report": _report(
                "model_output_invalid_scaffold",
                parse_report,
                issues=["model adjudication failed schema or ledger accounting checks"],
            ),
        }
    parsed = AnalystAdjudication.model_validate(payload).model_dump()
    return {
        "analyst_adjudication": parsed,
        "analyst_adjudication_prompt": prompt,
        "analyst_adjudication_raw": raw,
        "analyst_adjudication_parse_report": parse_report,
        "analyst_adjudication_chunk_reports": _chunk_report_bundle(
            [_chunk_report(1, 1, "accepted", parse_report)],
            scaffold_chunk_count=0,
        ),
        "analyst_adjudication_report": _report("accepted", parse_report),
    }


def build_analyst_adjudication_prompt(ledger: dict[str, Any]) -> str:
    packet = {
        "decision_question": ledger.get("decision_question"),
        "stable_final_answer_frame": _dict(ledger.get("stable_final_answer_frame")),
        "instructions": [
            "Classify every evidence row for its actual use in a decision memo.",
            "Use semantic judgment: decide whether the item is load-bearing, background, covered by another item, or not decision-relevant.",
            "Use stable_final_answer_frame.classification_target_policy to decide the target for answer_relation and effect_on_final_answer labels.",
            "When answer_status is selected or provisional and current_best_answer is present, classify relative to current_best_answer while preserving the affected live option in target_answer_option.",
            "When answer_status is multi_option or unresolved, do not force evidence into support or counterweight for a nonexistent final answer; classify relative to the live answer option, condition, or crux the row bears on.",
            "Do not call evidence a counterweight merely because it argues against a feared, rejected, or alternative answer. Use challenges_answer only when the row weakens, overturns, or materially lowers confidence in the selected/provisional current_best_answer or the named target_answer_option.",
            "When a row rebuts an alternative answer but supports the selected/provisional current_best_answer, use supports_answer or contextualizes_answer and explain that in effect_on_final_answer.",
            "For candidate_decision_edge rows, treat relation labels as provisional model proposals; audit the rationale, anchors, confidence, and failure condition before assigning memo_use.",
            "Downgrade, background, or mark a candidate_decision_edge for review when its relation label, rationale, anchors, or endpoint claims do not support its proposed decision use.",
            "Do not drop rows. Return one row for every evidence_item_id.",
            "Use covered_by only when another evidence item or future group explicitly covers the item.",
            "Do not invent source IDs, quantities, or claims.",
            "Use [] for empty covered_by, source_ids, and quantity_values. Do not use null.",
            "Do not use trailing commas.",
        ],
        "chunk": ledger.get("adjudication_chunk", {}),
        "allowed_memo_use": [
            "load_bearing_primary_support",
            "load_bearing_counterweight",
            "quantitative_anchor",
            "scope_or_applicability",
            "decision_crux",
            "mechanism_or_context",
            "background_only",
            "covered_by_group",
            "not_decision_relevant",
            "needs_human_or_model_review",
        ],
        "allowed_answer_relation": [
            "supports_answer",
            "challenges_answer",
            "bounds_scope",
            "identifies_crux",
            "contextualizes_answer",
            "not_decision_relevant",
            "uncertain_relation",
        ],
        "required_output_schema": {
            "schema_id": "analyst_adjudication_v1",
            "decision_question": ledger.get("decision_question"),
            "rows": [
                {
                    "evidence_item_id": "stable ID from the ledger",
                    "memo_use": "one allowed_memo_use value",
                    "answer_relation": "one allowed_answer_relation value",
                    "importance_rank": "integer 1-100, where 1 is most important",
                    "rationale": "short source-grounded reason",
                    "target_answer_option": "the answer option or stance this row most directly bears on",
                    "effect_on_final_answer": "supports current_best_answer | weakens current_best_answer | bounds current_best_answer | supports target answer | weakens target answer | bounds target answer | rebuts alternative | distinguishes live options | explains tension | background",
                    "tension_type": "none | clinical_outcome_vs_biomarker | subgroup_scope | dose_scope | study_conflict | mechanism | other",
                    "covered_by": ["optional evidence_item_id or group_id"],
                    "source_ids": ["optional source IDs copied from ledger"],
                    "quantity_values": ["optional quantities copied from ledger"],
                    "downgrade_reason": "required when memo_use is background_only or not_decision_relevant",
                }
            ],
            "overall_rationale": "brief explanation of the adjudication strategy",
        },
        "evidence_ledger_rows": [_prompt_row(row) for row in _list(ledger.get("rows")) if isinstance(row, dict)],
    }
    return (
        "You are an analyst adjudicating evidence for a decision-support memo.\n"
        "Return strict JSON only. Do not return Markdown.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def deterministic_adjudication_scaffold(ledger: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for index, row in enumerate(_list(ledger.get("rows"))):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "evidence_item_id": str(row.get("evidence_item_id") or ""),
                "memo_use": _memo_use_for_row(row),
                "answer_relation": _answer_relation_for_row(row),
                "importance_rank": min(100, index + 1),
                "rationale": _scaffold_rationale(row),
                "target_answer_option": "",
                "effect_on_final_answer": _effect_for_relation(_answer_relation_for_row(row)),
                "tension_type": "",
                "covered_by": [],
                "source_ids": _string_list(row.get("source_ids")),
                "quantity_values": _string_list(row.get("quantity_values")),
                "downgrade_reason": "scaffold only; live model adjudication not run" if _memo_use_for_row(row) == "background_only" else "",
            }
        )
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": ledger.get("decision_question", ""),
        "rows": rows,
        "overall_rationale": "Prompt-backend scaffold preserves one adjudication row per ledger item; it is not a semantic substitute for live model adjudication.",
    }


def _prompt_row(row: dict[str, Any]) -> dict[str, Any]:
    prompt = {
        "evidence_item_id": row.get("evidence_item_id"),
        "input_kind": row.get("input_kind"),
        "current_role": row.get("current_role"),
        "current_priority": row.get("current_priority"),
        "current_weight": row.get("current_weight"),
        "directionality": row.get("directionality"),
        "relation_semantic_role": row.get("relation_semantic_role"),
        "source_labels": row.get("source_labels", []),
        "source_quality": _source_quality_summary(row),
        "quantity_values": row.get("quantity_values", []),
        "claim": _short_text(str(row.get("claim") or ""), 360),
        "why_it_matters": _short_text(str(row.get("why_it_matters") or ""), 180),
        "failure_condition": _short_text(str(row.get("failure_condition") or ""), 180),
        "claim_ids": row.get("claim_ids") or _string_list(row.get("claim_id")),
        "relation_ids": row.get("relation_ids", []),
        "existing_warning_codes": row.get("existing_warning_codes", []),
    }
    if str(row.get("input_kind") or "") == "candidate_decision_edge":
        prompt.update(
            {
                "relation_contract": _relation_contract_for_prompt(row.get("relation_contract", {})),
                "candidate_pair": _candidate_pair_for_prompt(row.get("candidate_pair", {})),
                "endpoint_claims": _endpoint_claims_for_prompt(row.get("endpoint_claims", [])),
            }
        )
    return {key: value for key, value in prompt.items() if value not in (None, "", [], {})}


def _source_quality_summary(row: dict[str, Any]) -> dict[str, Any]:
    appraisal = _dict(row.get("source_appraisal"))
    return {
        key: value
        for key, value in {
            "quality": row.get("quality"),
            "warnings": _string_list(row.get("source_use_warnings"))[:4],
            "decision_directness": appraisal.get("decision_directness"),
            "evidence_proximity": _string_list(appraisal.get("evidence_proximity"))[:4],
            "recommended_uses": _string_list(appraisal.get("recommended_uses"))[:4],
        }.items()
        if value not in (None, "", [], {})
    }


def _relation_contract_for_prompt(value: Any) -> dict[str, Any]:
    contract = _dict(value)
    return {
        key: _short_text(str(contract.get(key) or ""), 220)
        for key in ("edge_basis", "source_anchor_a", "source_anchor_b", "why_decision_relevant", "failure_condition")
        if contract.get(key)
    }


def _candidate_pair_for_prompt(value: Any) -> dict[str, Any]:
    pair = _dict(value)
    return {
        key: pair.get(key)
        for key in ("pair_id", "decision_edge_contract", "reason", "score")
        if pair.get(key) not in (None, "", [], {})
    }


def _endpoint_claims_for_prompt(value: Any) -> list[dict[str, Any]]:
    rows = []
    for row in _list(value):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                key: _short_text(str(row.get(key) or ""), 260) if key == "claim" else row.get(key)
                for key in ("endpoint", "claim_id", "decision_edge_role", "decision_function", "question_relevance", "claim")
                if row.get(key) not in (None, "", [], {})
            }
        )
    return rows[:4]


def _memo_use_for_row(row: dict[str, Any]) -> str:
    role = str(row.get("current_role") or "").lower()
    input_kind = str(row.get("input_kind") or "")
    if input_kind == "memo_warning":
        return "needs_human_or_model_review"
    if "quant" in role:
        return "quantitative_anchor"
    if "counter" in role:
        return "load_bearing_counterweight"
    if "scope" in role or "boundary" in role:
        return "scope_or_applicability"
    if "crux" in role:
        return "decision_crux"
    if "support" in role or "answer_bearing" in role or "main_map" in role or role == "core":
        return "load_bearing_primary_support"
    if "mechanism" in role or "context" in role:
        return "mechanism_or_context"
    if "appendix" in role or "background" in role:
        return "background_only"
    return "background_only"


def _answer_relation_for_row(row: dict[str, Any]) -> str:
    memo_use = _memo_use_for_row(row)
    return {
        "load_bearing_primary_support": "supports_answer",
        "quantitative_anchor": "supports_answer",
        "load_bearing_counterweight": "challenges_answer",
        "scope_or_applicability": "bounds_scope",
        "decision_crux": "identifies_crux",
        "mechanism_or_context": "contextualizes_answer",
        "background_only": "contextualizes_answer",
        "covered_by_group": "contextualizes_answer",
        "not_decision_relevant": "not_decision_relevant",
        "needs_human_or_model_review": "uncertain_relation",
    }.get(memo_use, "uncertain_relation")


def _effect_for_relation(relation: str) -> str:
    return {
        "supports_answer": "supports current_best_answer",
        "challenges_answer": "weakens current_best_answer",
        "bounds_scope": "bounds current_best_answer",
        "identifies_crux": "explains tension",
        "contextualizes_answer": "background",
        "not_decision_relevant": "background",
    }.get(str(relation or ""), "")


def _scaffold_rationale(row: dict[str, Any]) -> str:
    role = str(row.get("current_role") or "unknown role")
    priority = str(row.get("current_priority") or "unknown priority")
    return f"Scaffold assignment from current role {role} and priority {priority}."


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    for candidate in (text, _repair_json_syntax(text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {}


def _repair_json_syntax(text: str) -> str:
    return re.sub(r",\s*([\]}])", r"\1", text)


def _repair_covered_by_aliases(payload: Any, known_ids: list[str]) -> Any:
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return payload
    aliases: dict[str, str] = {}
    for known_id in known_ids:
        aliases.setdefault(_id_alias(known_id), known_id)
    for row in payload["rows"]:
        if not isinstance(row, dict) or not isinstance(row.get("covered_by"), list):
            continue
        repaired = []
        for target in row["covered_by"]:
            text = str(target).strip()
            repaired.append(aliases.get(_id_alias(text), text))
        row["covered_by"] = repaired
    return payload


def _id_alias(value: str) -> str:
    return _norm(str(value).replace("-", "_"))


def _report(status: str, parse_report: dict[str, Any], *, issues: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_id": "analyst_adjudication_report_v1",
        "status": status,
        "accepted": status in {"accepted", "accepted_with_chunk_scaffold"},
        "parse_status": parse_report.get("status"),
        "row_count": parse_report.get("row_count", 0),
        "ledger_row_count": parse_report.get("ledger_row_count", 0),
        "issues": [*(issues or []), *[str(issue) for issue in parse_report.get("issues", [])]],
    }


def _chunk_size() -> int:
    try:
        return max(1, int(os.environ.get("ECM_ANALYST_ADJUDICATION_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)))
    except ValueError:
        return DEFAULT_CHUNK_SIZE


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)] or [[]]


def _chunk_ledger(ledger: dict[str, Any], rows: list[dict[str, Any]], *, index: int, total: int) -> dict[str, Any]:
    return {
        **ledger,
        "row_count": len(rows),
        "rows": rows,
        "adjudication_chunk": {"index": index, "total": total, "row_count": len(rows)},
    }


def _chunk_report(
    index: int,
    total: int,
    status: str,
    parse_report: dict[str, Any],
    *,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "chunk_index": index,
        "chunk_count": total,
        "status": status,
        "parse_status": parse_report.get("status"),
        "valid": parse_report.get("valid", False),
        "row_count": parse_report.get("row_count", 0),
        "ledger_row_count": parse_report.get("ledger_row_count", 0),
        "missing_evidence_item_ids": parse_report.get("missing_evidence_item_ids", []),
        "unknown_evidence_item_ids": parse_report.get("unknown_evidence_item_ids", []),
        "invalid_covered_by": parse_report.get("invalid_covered_by", []),
        "errors": parse_report.get("errors", []),
        "issues": [*(issues or []), *[str(issue) for issue in parse_report.get("issues", [])]],
    }


def _chunk_report_bundle(chunks: list[dict[str, Any]], *, scaffold_chunk_count: int) -> dict[str, Any]:
    return {
        "schema_id": "analyst_adjudication_chunk_reports_v1",
        "chunk_count": len(chunks),
        "scaffold_chunk_count": scaffold_chunk_count,
        "chunks": chunks,
    }


def _dedupe_adjudication_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for row in rows:
        row_id = str(row.get("evidence_item_id") or "")
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        result.append(row)
    return result


def _order_rows_by_ledger(rows: list[dict[str, Any]], ledger_ids: list[str]) -> list[dict[str, Any]]:
    by_id = {str(row.get("evidence_item_id")): row for row in rows if str(row.get("evidence_item_id") or "")}
    return [by_id[row_id] for row_id in ledger_ids if row_id in by_id]


def _merged_rationale(chunk_reports: list[dict[str, Any]]) -> str:
    accepted = sum(1 for row in chunk_reports if row.get("status") == "accepted")
    scaffolded = sum(1 for row in chunk_reports if "scaffold" in str(row.get("status")))
    return f"Chunked analyst adjudication merged {accepted} accepted chunks and {scaffolded} scaffold fallback chunks."


def _ledger_ids(ledger: dict[str, Any]) -> list[str]:
    return [
        str(row.get("evidence_item_id"))
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "")
    ]
