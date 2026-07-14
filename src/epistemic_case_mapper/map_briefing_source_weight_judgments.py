from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_source_identity import source_ids_for_labels


def build_source_weight_judgment_bundle(interface: dict[str, Any], source_trail: list[Any]) -> dict[str, Any]:
    judgments = _source_weight_judgments(interface, source_trail)
    return {
        "source_weight_judgments": judgments,
        "source_weight_judgment_report": build_source_weight_judgment_report(judgments, source_trail),
    }


def build_source_weight_judgment_report(judgments: list[dict[str, Any]], source_trail: list[Any]) -> dict[str, Any]:
    source_ids = _dedupe(str(row.get("source_id") or "").strip() for row in source_trail if isinstance(row, dict))
    judged_ids = {source_id for row in judgments for source_id in _string_list(row.get("source_ids"))}
    generic = [row.get("judgment_id") for row in judgments if not _informative_rationale(row)]
    warnings = []
    if source_ids and not judgments:
        warnings.append("missing_source_weight_judgments")
    missing = sorted(source_id for source_id in source_ids if source_id not in judged_ids)
    if missing:
        warnings.append("source_ids_without_weight_judgment")
    if generic:
        warnings.append("generic_source_weight_rationale")
    return {
        "schema_id": "source_weight_judgment_report_v1",
        "status": "ready" if not warnings else "warning",
        "source_count": len(source_ids),
        "judgment_count": len(judgments),
        "judged_source_count": len(judged_ids),
        "missing_source_ids": missing[:20],
        "generic_judgment_ids": [str(value) for value in generic if value][:20],
        "main_use_counts": dict(Counter(str(row.get("main_use") or "unspecified") for row in judgments)),
        "warnings": warnings,
    }


def _source_weight_judgments(interface: dict[str, Any], source_trail: list[Any]) -> list[dict[str, Any]]:
    rows_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _list(interface.get("decision_evidence_table")):
        if not isinstance(row, dict):
            continue
        source_ids = _source_ids(row, source_trail)
        for source_id in source_ids:
            rows_by_source[source_id].append(row)
    appraisal_by_source = _appraisal_by_source(interface, source_trail)
    judgments = []
    for index, source_id in enumerate(sorted(rows_by_source), start=1):
        rows = rows_by_source[source_id]
        appraisal = appraisal_by_source.get(source_id, {})
        main_use = _main_use(rows)
        judgments.append(
            _drop_empty(
                {
                    "judgment_id": f"source_weight_{index:03d}",
                    "source_ids": [source_id],
                    "source_type": _source_type(appraisal),
                    "decision_directness": appraisal.get("decision_directness") or _common_value(rows, "decision_directness") or "unspecified",
                    "population_fit": _short_text(appraisal.get("population_fit") or _common_value(rows, "population_fit"), 220),
                    "endpoint_fit": _short_text(appraisal.get("endpoint_fit") or _common_value(rows, "endpoint_fit"), 220),
                    "main_use": main_use,
                    "why_weight_this_way": _why_weight_this_way(rows, appraisal, main_use),
                    "what_not_to_use_it_for": _not_enough_for(rows, appraisal),
                    "evidence_item_ids": _dedupe(str(row.get("item_id") or "").strip() for row in rows if row.get("item_id"))[:12],
                }
            )
        )
    return judgments


def _appraisal_by_source(interface: dict[str, Any], source_trail: list[Any]) -> dict[str, dict[str, Any]]:
    appraisals = {}
    for row in _list(interface.get("source_appraisal_summary")):
        if not isinstance(row, dict):
            continue
        for source_id in _source_ids(row, source_trail):
            appraisals[source_id] = row
    return appraisals


def _source_ids(row: dict[str, Any], source_trail: list[Any]) -> list[str]:
    explicit = _string_list(row.get("source_ids") or row.get("source_id"))
    labels = _string_list(row.get("source_labels") or row.get("source_label"))
    return _dedupe([*explicit, *source_ids_for_labels(labels, source_trail)])


def _main_use(rows: list[dict[str, Any]]) -> str:
    uses = [_row_main_use(row) for row in rows]
    if not uses:
        return "contextualizes"
    counts = Counter(uses)
    priority = ["drives_answer", "bounds_answer", "calibrates_magnitude", "defines_scope", "identifies_crux", "contextualizes"]
    return min(counts, key=lambda use: (-counts[use], priority.index(use) if use in priority else len(priority)))


def _row_main_use(row: dict[str, Any]) -> str:
    role = str(row.get("role") or "").strip()
    relation = str(row.get("answer_relation") or "").strip()
    function = str(row.get("memo_function") or "").strip()
    if role == "strongest_support" or relation == "supports_answer" or function == "answer_anchor":
        return "drives_answer"
    if role == "strongest_counterweight" or relation == "challenges_answer" or function == "counterweight":
        return "bounds_answer"
    if role == "quantitative_anchor" or function in {"quantity_anchor", "mechanism", "explanation"}:
        return "calibrates_magnitude"
    if role == "scope_boundary" or relation == "bounds_scope" or function == "scope_boundary":
        return "defines_scope"
    if role == "decision_crux" or relation == "identifies_crux" or function == "crux":
        return "identifies_crux"
    return "contextualizes"


def _why_weight_this_way(rows: list[dict[str, Any]], appraisal: dict[str, Any], main_use: str) -> str:
    directness = str(appraisal.get("decision_directness") or "").strip()
    claims = _dedupe(
        _short_text(_reader_relevant_reason(row), 180)
        for row in rows
        if _reader_relevant_reason(row)
    )
    parts = [f"Use primarily to {_main_use_verb(main_use)}"]
    if directness and directness not in {"unknown", "unspecified"}:
        parts.append(f"because upstream appraisal marks decision directness as {directness}")
    if claims:
        parts.append(f"and links the source to: {claims[0]}")
    return _short_text("; ".join(parts) + ".", 520)


def _reader_relevant_reason(row: dict[str, Any]) -> str:
    relevance = str(row.get("decision_relevance") or "").strip()
    if relevance and not relevance.lower().startswith("scaffold assignment"):
        return relevance
    return str(row.get("claim") or row.get("reader_claim") or "").strip()


def _main_use_verb(main_use: str) -> str:
    return {
        "drives_answer": "drive the answer",
        "bounds_answer": "bound the answer",
        "calibrates_magnitude": "calibrate magnitude or mechanism",
        "defines_scope": "define the scope",
        "identifies_crux": "identify what would change the answer",
        "contextualizes": "contextualize the answer",
    }.get(main_use, str(main_use or "contextualize").replace("_", " "))


def _not_enough_for(rows: list[dict[str, Any]], appraisal: dict[str, Any]) -> list[str]:
    warnings = _string_list(appraisal.get("source_use_warnings") or appraisal.get("interpretation_caveats"))
    for row in rows:
        warnings.extend(_string_list(row.get("source_use_warnings") or _dict(row.get("source_appraisal")).get("source_use_warnings")))
    return _dedupe(warnings)[:6]


def _source_type(appraisal: dict[str, Any]) -> str:
    return str(appraisal.get("source_type") or appraisal.get("evidence_type") or appraisal.get("study_design") or "unspecified").strip()


def _common_value(rows: list[dict[str, Any]], key: str) -> str:
    values = _dedupe(str(_dict(row.get("source_appraisal")).get(key) or row.get(key) or "").strip() for row in rows)
    return values[0] if values else ""


def _informative_rationale(row: dict[str, Any]) -> bool:
    text = str(row.get("why_weight_this_way") or "").lower()
    markers = ("directness", "endpoint", "population", "source", "appraisal", "links", "limitation", "scope")
    return any(marker in text for marker in markers)


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}
