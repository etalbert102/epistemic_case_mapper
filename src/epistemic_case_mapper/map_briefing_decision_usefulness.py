from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


ANSWER_SHAPES = {
    "single_stance",
    "multi_option",
    "threshold",
    "classification",
    "insufficient_information",
}
OPTION_STATUSES = {"live", "dominated", "insufficiently_supported", "context_only"}
CRITERION_TYPES = {
    "benefit",
    "harm",
    "certainty",
    "scope",
    "feasibility",
    "cost",
    "values",
    "equity",
    "implementation",
    "other",
}
ASSESSMENTS = {"favors", "weakens", "mixed", "uncertain", "not_applicable"}
DIAGNOSTICITY = {"high", "medium", "low"}
PRIORITIES = {"high", "medium", "low"}


class DecisionUsefulnessStance(BaseModel):
    stance: str = ""
    confidence: str = ""
    scope: str = ""
    why_this_stance: str = ""
    source_ids: list[str] = Field(default_factory=list)
    evidence_item_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", "evidence_item_ids", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class DecisionOption(BaseModel):
    option_id: str
    label: str
    description: str = ""
    status: Literal["live", "dominated", "insufficiently_supported", "context_only"] = "live"
    source_ids: list[str] = Field(default_factory=list)
    evidence_item_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", "evidence_item_ids", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class DecisionCriterion(BaseModel):
    criterion_id: str
    label: str
    why_it_matters: str = ""
    criterion_type: Literal[
        "benefit",
        "harm",
        "certainty",
        "scope",
        "feasibility",
        "cost",
        "values",
        "equity",
        "implementation",
        "other",
    ] = "other"
    source_ids: list[str] = Field(default_factory=list)
    evidence_item_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", "evidence_item_ids", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class OptionCriterionCell(BaseModel):
    option_id: str
    criterion_id: str
    assessment: Literal["favors", "weakens", "mixed", "uncertain", "not_applicable"] = "uncertain"
    rationale: str = ""
    source_ids: list[str] = Field(default_factory=list)
    evidence_item_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", "evidence_item_ids", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class DiagnosticEvidenceRow(BaseModel):
    evidence_item_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    distinguishes: list[str] = Field(default_factory=list)
    diagnosticity: Literal["high", "medium", "low"] = "medium"
    why_diagnostic: str = ""

    @field_validator("source_ids", "evidence_item_ids", "distinguishes", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class TradeoffRow(BaseModel):
    tradeoff: str
    choose_a_if: str = ""
    choose_b_if: str = ""
    source_ids: list[str] = Field(default_factory=list)
    evidence_item_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", "evidence_item_ids", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class CruxThresholdRow(BaseModel):
    crux: str
    current_read: str = ""
    would_change_if: str = ""
    threshold: str = ""
    source_ids: list[str] = Field(default_factory=list)
    evidence_item_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", "evidence_item_ids", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class PremortemRow(BaseModel):
    failure_mode: str
    why_plausible: str = ""
    mitigation_or_monitoring: str = ""
    source_ids: list[str] = Field(default_factory=list)
    evidence_item_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", "evidence_item_ids", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class MonitoringTriggerRow(BaseModel):
    trigger: str
    would_update: str = ""
    priority: Literal["high", "medium", "low"] = "medium"
    source_ids: list[str] = Field(default_factory=list)
    evidence_item_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", "evidence_item_ids", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class DecisionUsefulnessPacket(BaseModel):
    schema_id: Literal["decision_usefulness_packet_v1"] = "decision_usefulness_packet_v1"
    decision_question: str = ""
    answer_shape: Literal["single_stance", "multi_option", "threshold", "classification", "insufficient_information"] = "single_stance"
    recommended_stance: DecisionUsefulnessStance = Field(default_factory=DecisionUsefulnessStance)
    decision_options: list[DecisionOption] = Field(default_factory=list)
    decision_criteria: list[DecisionCriterion] = Field(default_factory=list)
    option_criteria_matrix: list[OptionCriterionCell] = Field(default_factory=list)
    diagnostic_evidence: list[DiagnosticEvidenceRow] = Field(default_factory=list)
    tradeoffs: list[TradeoffRow] = Field(default_factory=list)
    cruxes_and_thresholds: list[CruxThresholdRow] = Field(default_factory=list)
    premortem: list[PremortemRow] = Field(default_factory=list)
    monitoring_triggers: list[MonitoringTriggerRow] = Field(default_factory=list)


def empty_decision_usefulness_packet(reason: str = "") -> dict[str, Any]:
    return {
        "schema_id": "decision_usefulness_packet_v1",
        "decision_question": "",
        "answer_shape": "insufficient_information",
        "recommended_stance": {"stance": "", "confidence": "", "scope": "", "why_this_stance": ""},
        "decision_options": [],
        "decision_criteria": [],
        "option_criteria_matrix": [],
        "diagnostic_evidence": [],
        "tradeoffs": [],
        "cruxes_and_thresholds": [],
        "premortem": [],
        "monitoring_triggers": [],
        "summary": {"status": "empty", "reason": reason},
    }


def build_decision_usefulness_context(canonical_packet: dict[str, Any]) -> dict[str, Any]:
    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    spine = _dict(packet.get("evidence_weighted_argument_spine"))
    return {
        "schema_id": "decision_usefulness_context_v1",
        "decision_question": packet.get("decision_question", ""),
        "decision_answer_classification": _dict(packet.get("decision_answer_classification")),
        "decision_brief_skeleton": _dict(packet.get("decision_brief_skeleton")),
        "source_weighting": {
            "judgments": _trim_rows(_list(packet.get("source_weight_judgments")), 12),
            "notes": _trim_rows(_list(packet.get("source_weight_notes")), 12),
        },
        "argument_spine": {
            "section_plan": _trim_rows(_list(spine.get("section_plan")), 6),
            "steps": _trim_rows(_list(spine.get("steps")), 14),
        },
        "priority_evidence": _trim_rows(_list(packet.get("priority_evidence")), 18),
        "counterweight_dispositions": _trim_rows(_list(packet.get("counterweight_dispositions")), 12),
        "scope_boundaries": _trim_rows(_list(packet.get("scope_boundaries")), 10),
        "decision_cruxes": _trim_rows(_list(packet.get("decision_cruxes")), 10),
        "organized_evidence_inventory": _compact_inventory(_dict(packet.get("organized_evidence_inventory"))),
        "model_task": {
            "goal": "Convert the canonical decision writer packet into explicit decision-support structure.",
            "must_decide": [
                "answer shape",
                "live options or stances",
                "decision criteria",
                "diagnostic evidence",
                "tradeoffs",
                "crux thresholds",
                "premortem failure modes",
                "monitoring triggers",
            ],
            "do_not_force_multi_option": True,
        },
    }


def normalize_decision_usefulness_packet(payload: Any, *, canonical_packet: dict[str, Any] | None = None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    if isinstance(data.get("decision_usefulness_packet"), dict):
        data = data["decision_usefulness_packet"]
    normalized = {
        "schema_id": "decision_usefulness_packet_v1",
        "decision_question": str(data.get("decision_question") or _dict(canonical_packet).get("decision_question") or "").strip(),
        "answer_shape": _enum_value(data.get("answer_shape"), ANSWER_SHAPES, default="single_stance"),
        "recommended_stance": _stance_row(_dict(data.get("recommended_stance"))),
        "decision_options": _numbered_rows(
            [_option_row(row) for row in _list(data.get("decision_options")) if isinstance(row, dict)],
            id_key="option_id",
            prefix="option",
        ),
        "decision_criteria": _numbered_rows(
            [_criterion_row(row) for row in _list(data.get("decision_criteria")) if isinstance(row, dict)],
            id_key="criterion_id",
            prefix="criterion",
        ),
        "option_criteria_matrix": [_matrix_row(row) for row in _list(data.get("option_criteria_matrix")) if isinstance(row, dict)],
        "diagnostic_evidence": [_diagnostic_row(row) for row in _list(data.get("diagnostic_evidence")) if isinstance(row, dict)],
        "tradeoffs": [_tradeoff_row(row) for row in _list(data.get("tradeoffs")) if isinstance(row, dict)],
        "cruxes_and_thresholds": [_crux_row(row) for row in _list(data.get("cruxes_and_thresholds")) if isinstance(row, dict)],
        "premortem": [_premortem_row(row) for row in _list(data.get("premortem")) if isinstance(row, dict)],
        "monitoring_triggers": [_trigger_row(row) for row in _list(data.get("monitoring_triggers")) if isinstance(row, dict)],
    }
    try:
        packet = DecisionUsefulnessPacket.model_validate(normalized).model_dump()
    except ValidationError:
        packet = empty_decision_usefulness_packet("schema_validation_failed")
        packet["decision_question"] = normalized["decision_question"]
    report = build_decision_usefulness_quality_report(packet, canonical_packet=canonical_packet or {})
    return {**packet, "summary": _packet_summary(packet), "quality_report": report}


def build_decision_usefulness_quality_report(
    packet: dict[str, Any],
    *,
    canonical_packet: dict[str, Any],
) -> dict[str, Any]:
    known_source_ids = set(_known_source_ids(canonical_packet))
    known_evidence_ids = set(_known_evidence_item_ids(canonical_packet))
    option_ids = {str(row.get("option_id") or "") for row in _list(packet.get("decision_options")) if isinstance(row, dict)}
    criterion_ids = {str(row.get("criterion_id") or "") for row in _list(packet.get("decision_criteria")) if isinstance(row, dict)}
    invalid_rows = []
    for path, row in _iter_referenced_rows(packet):
        bad_sources = [source_id for source_id in _string_list(row.get("source_ids")) if known_source_ids and source_id not in known_source_ids]
        bad_evidence = [item_id for item_id in _string_list(row.get("evidence_item_ids")) if known_evidence_ids and item_id not in known_evidence_ids]
        if bad_sources or bad_evidence:
            invalid_rows.append({"path": path, "invalid_source_ids": bad_sources, "invalid_evidence_item_ids": bad_evidence})
    invalid_matrix = [
        {
            "path": f"option_criteria_matrix.{index}",
            "option_id": row.get("option_id"),
            "criterion_id": row.get("criterion_id"),
        }
        for index, row in enumerate(_list(packet.get("option_criteria_matrix")))
        if isinstance(row, dict)
        and (
            (option_ids and str(row.get("option_id") or "") not in option_ids)
            or (criterion_ids and str(row.get("criterion_id") or "") not in criterion_ids)
        )
    ]
    thin_criteria = sorted(
        criterion_id
        for criterion_id in criterion_ids
        if not any(str(row.get("criterion_id") or "") == criterion_id and _string_list(row.get("evidence_item_ids")) for row in _list(packet.get("option_criteria_matrix")) if isinstance(row, dict))
    )
    warnings = []
    if not _list(packet.get("decision_options")) and str(packet.get("answer_shape")) == "multi_option":
        warnings.append("multi_option_without_options")
    if not _list(packet.get("decision_criteria")):
        warnings.append("missing_decision_criteria")
    if not _list(packet.get("diagnostic_evidence")):
        warnings.append("missing_diagnostic_evidence")
    if not _list(packet.get("tradeoffs")):
        warnings.append("missing_tradeoffs")
    if not _list(packet.get("cruxes_and_thresholds")):
        warnings.append("missing_crux_thresholds")
    if invalid_rows:
        warnings.append("invalid_source_or_evidence_references")
    if invalid_matrix:
        warnings.append("invalid_option_or_criterion_references")
    if thin_criteria:
        warnings.append("criteria_without_matrix_evidence")
    return {
        "schema_id": "decision_usefulness_quality_report_v1",
        "status": "ready" if not warnings else "warning",
        "warnings": _dedupe(warnings),
        "answer_shape": packet.get("answer_shape", ""),
        "option_count": len(_list(packet.get("decision_options"))),
        "criterion_count": len(_list(packet.get("decision_criteria"))),
        "matrix_cell_count": len(_list(packet.get("option_criteria_matrix"))),
        "diagnostic_evidence_count": len(_list(packet.get("diagnostic_evidence"))),
        "tradeoff_count": len(_list(packet.get("tradeoffs"))),
        "crux_threshold_count": len(_list(packet.get("cruxes_and_thresholds"))),
        "premortem_count": len(_list(packet.get("premortem"))),
        "monitoring_trigger_count": len(_list(packet.get("monitoring_triggers"))),
        "invalid_reference_count": len(invalid_rows),
        "invalid_matrix_reference_count": len(invalid_matrix),
        "criteria_without_matrix_evidence": thin_criteria,
        "invalid_reference_rows": invalid_rows[:20],
        "invalid_matrix_rows": invalid_matrix[:20],
    }


def compact_decision_usefulness_for_prompt(packet: dict[str, Any] | None) -> dict[str, Any]:
    row = packet if isinstance(packet, dict) else {}
    if row.get("schema_id") != "decision_usefulness_packet_v1":
        return {}
    return {
        "schema_id": "decision_usefulness_packet_v1",
        "answer_shape": row.get("answer_shape", ""),
        "recommended_stance": _dict(row.get("recommended_stance")),
        "decision_options": _trim_rows(_list(row.get("decision_options")), 5),
        "decision_criteria": _trim_rows(_list(row.get("decision_criteria")), 7),
        "option_criteria_matrix": _trim_rows(_list(row.get("option_criteria_matrix")), 12),
        "diagnostic_evidence": _trim_rows(_list(row.get("diagnostic_evidence")), 8),
        "tradeoffs": _trim_rows(_list(row.get("tradeoffs")), 6),
        "cruxes_and_thresholds": _trim_rows(_list(row.get("cruxes_and_thresholds")), 6),
        "premortem": _trim_rows(_list(row.get("premortem")), 4),
        "monitoring_triggers": _trim_rows(_list(row.get("monitoring_triggers")), 5),
    }


def _stance_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stance": _short(row.get("stance") or row.get("answer") or row.get("recommendation"), 420),
        "confidence": _short(row.get("confidence"), 120),
        "scope": _short(row.get("scope"), 420),
        "why_this_stance": _short(row.get("why_this_stance") or row.get("rationale"), 700),
        "source_ids": _string_list(row.get("source_ids"))[:8],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
    }


def _option_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "option_id": _short(row.get("option_id"), 80),
        "label": _short(row.get("label") or row.get("option"), 180),
        "description": _short(row.get("description") or row.get("rationale"), 420),
        "status": _enum_value(row.get("status"), OPTION_STATUSES, default="live"),
        "source_ids": _string_list(row.get("source_ids"))[:8],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
    }


def _criterion_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "criterion_id": _short(row.get("criterion_id"), 80),
        "label": _short(row.get("label") or row.get("criterion"), 180),
        "why_it_matters": _short(row.get("why_it_matters") or row.get("rationale"), 520),
        "criterion_type": _enum_value(row.get("criterion_type") or row.get("type"), CRITERION_TYPES, default="other"),
        "source_ids": _string_list(row.get("source_ids"))[:8],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
    }


def _matrix_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "option_id": _short(row.get("option_id"), 80),
        "criterion_id": _short(row.get("criterion_id"), 80),
        "assessment": _enum_value(row.get("assessment"), ASSESSMENTS, default="uncertain"),
        "rationale": _short(row.get("rationale") or row.get("assessment_rationale"), 520),
        "source_ids": _string_list(row.get("source_ids"))[:8],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
    }


def _diagnostic_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
        "source_ids": _string_list(row.get("source_ids"))[:8],
        "distinguishes": _string_list(row.get("distinguishes") or row.get("option_ids"))[:6],
        "diagnosticity": _enum_value(row.get("diagnosticity"), DIAGNOSTICITY, default="medium"),
        "why_diagnostic": _short(row.get("why_diagnostic") or row.get("rationale"), 520),
    }


def _tradeoff_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "tradeoff": _short(row.get("tradeoff") or row.get("criterion"), 520),
        "choose_a_if": _short(row.get("choose_a_if"), 420),
        "choose_b_if": _short(row.get("choose_b_if"), 420),
        "source_ids": _string_list(row.get("source_ids"))[:8],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
    }


def _crux_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "crux": _short(row.get("crux") or row.get("question"), 520),
        "current_read": _short(row.get("current_read"), 420),
        "would_change_if": _short(row.get("would_change_if"), 520),
        "threshold": _short(row.get("threshold"), 420),
        "source_ids": _string_list(row.get("source_ids"))[:8],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
    }


def _premortem_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "failure_mode": _short(row.get("failure_mode") or row.get("risk"), 520),
        "why_plausible": _short(row.get("why_plausible") or row.get("rationale"), 520),
        "mitigation_or_monitoring": _short(row.get("mitigation_or_monitoring") or row.get("monitoring"), 520),
        "source_ids": _string_list(row.get("source_ids"))[:8],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
    }


def _trigger_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "trigger": _short(row.get("trigger"), 520),
        "would_update": _short(row.get("would_update") or row.get("update"), 520),
        "priority": _enum_value(row.get("priority"), PRIORITIES, default="medium"),
        "source_ids": _string_list(row.get("source_ids"))[:8],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
    }


def _enum_value(value: Any, allowed: set[str], *, default: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in allowed else default


def _short(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return _short_text(value, limit)


def _numbered_rows(rows: list[dict[str, Any]], *, id_key: str, prefix: str) -> list[dict[str, Any]]:
    output = []
    seen_labels = set()
    for index, row in enumerate(rows, start=1):
        label_key = str(row.get("label") or row.get("tradeoff") or row.get("crux") or "").strip().lower()
        if label_key and label_key in seen_labels:
            continue
        if label_key:
            seen_labels.add(label_key)
        if not str(row.get(id_key) or "").strip():
            row = {**row, id_key: f"{prefix}_{index:03d}"}
        output.append(row)
    return output


def _compact_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    lanes = _dict(inventory.get("lanes"))
    compact = {}
    for lane, rows in lanes.items():
        compact_rows = _trim_rows(_list(rows), 8)
        if compact_rows:
            compact[str(lane)] = compact_rows
    return {"item_count": inventory.get("item_count", 0), "lanes": compact}


def _trim_rows(rows: list[Any], limit: int) -> list[Any]:
    return [_trim_value(row) for row in rows[:limit]]


def _trim_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_trim_value(row) for row in value[:20]]
    if isinstance(value, dict):
        return {str(key): _trim_value(row) for key, row in value.items() if _keep_context_key(str(key), row)}
    if isinstance(value, str):
        return _short_text(value, 900)
    return value


def _keep_context_key(key: str, value: Any) -> bool:
    if key.endswith("_raw") or "prompt" in key or "parse_report" in key or "quality_report" in key:
        return False
    if value in (None, "", [], {}):
        return False
    return True


def _known_source_ids(canonical: dict[str, Any]) -> list[str]:
    ids = _collect_string_values_for_keys(canonical, {"source_id", "source_ids"})
    citation_ids = [
        str(row.get("source_id") or "").strip()
        for row in _list(canonical.get("citation_registry"))
        if isinstance(row, dict) and str(row.get("source_id") or "").strip()
    ]
    return _dedupe([*ids, *citation_ids])


def _known_evidence_item_ids(canonical: dict[str, Any]) -> list[str]:
    return _dedupe(_collect_string_values_for_keys(canonical, {"item_id", "evidence_item_ids"}))


def _collect_string_values_for_keys(value: Any, keys: set[str]) -> list[str]:
    rows: list[str] = []
    if isinstance(value, list):
        for row in value:
            rows.extend(_collect_string_values_for_keys(row, keys))
    elif isinstance(value, dict):
        for key, row in value.items():
            if key in keys:
                rows.extend(_string_list(row))
            else:
                rows.extend(_collect_string_values_for_keys(row, keys))
    return rows


def _iter_referenced_rows(packet: dict[str, Any]):
    for field in (
        "decision_options",
        "decision_criteria",
        "option_criteria_matrix",
        "diagnostic_evidence",
        "tradeoffs",
        "cruxes_and_thresholds",
        "premortem",
        "monitoring_triggers",
    ):
        for index, row in enumerate(_list(packet.get(field))):
            if isinstance(row, dict):
                yield f"{field}.{index}", row
    stance = _dict(packet.get("recommended_stance"))
    if stance:
        yield "recommended_stance", stance


def _packet_summary(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ready",
        "option_count": len(_list(packet.get("decision_options"))),
        "criterion_count": len(_list(packet.get("decision_criteria"))),
        "diagnostic_evidence_count": len(_list(packet.get("diagnostic_evidence"))),
        "tradeoff_count": len(_list(packet.get("tradeoffs"))),
        "crux_threshold_count": len(_list(packet.get("cruxes_and_thresholds"))),
        "monitoring_trigger_count": len(_list(packet.get("monitoring_triggers"))),
    }
