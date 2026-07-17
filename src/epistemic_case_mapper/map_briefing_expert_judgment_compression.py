from __future__ import annotations

import json
import re
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from epistemic_case_mapper.map_briefing_decision_argument_contract import (
    build_decision_argument_contract,
    compact_decision_argument_contract_for_prompt,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import ModelBackendResult, run_model_backend


class ExpertJudgmentPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    point: str = ""
    decision_function: str = ""
    evidence_item_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    quantity_values: list[str] = Field(default_factory=list)

    @field_validator("evidence_item_ids", "source_ids", "quantity_values", mode="before")
    @classmethod
    def _coerce_string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class ExpertJudgmentQuantity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str = ""
    interpretation: str = ""
    evidence_item_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("evidence_item_ids", "source_ids", mode="before")
    @classmethod
    def _coerce_string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class ExpertJudgmentSectionBrief(BaseModel):
    model_config = ConfigDict(extra="ignore")

    section_id: str
    governing_point: str = ""
    paragraph_strategy: list[str] = Field(default_factory=list)
    lead_with: str = ""
    emphasize: list[str] = Field(default_factory=list)
    subordinate: list[str] = Field(default_factory=list)
    evidence_item_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    quantity_values: list[str] = Field(default_factory=list)

    @field_validator("paragraph_strategy", "emphasize", "subordinate", "evidence_item_ids", "source_ids", "quantity_values", mode="before")
    @classmethod
    def _coerce_string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


class ExpertJudgmentCompression(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_id: Literal["expert_judgment_compression_v1"] = "expert_judgment_compression_v1"
    governing_judgment: str = ""
    source_weighting_logic: list[ExpertJudgmentPoint] = Field(default_factory=list)
    primary_reasoning_chain: list[ExpertJudgmentPoint] = Field(default_factory=list)
    counterweight_dispositions: list[ExpertJudgmentPoint] = Field(default_factory=list)
    decision_boundaries: list[ExpertJudgmentPoint] = Field(default_factory=list)
    quantities_to_preserve: list[ExpertJudgmentQuantity] = Field(default_factory=list)
    what_to_subordinate: list[ExpertJudgmentPoint] = Field(default_factory=list)
    memo_voice_guidance: list[str] = Field(default_factory=list)
    section_briefs: list[ExpertJudgmentSectionBrief] = Field(default_factory=list)

    @field_validator("memo_voice_guidance", mode="before")
    @classmethod
    def _coerce_string_list(cls, value: Any) -> list[str]:
        return _string_list(value)


ModelRunner = Callable[..., ModelBackendResult]


def build_expert_judgment_compression_input(memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    packet = memo_ready_packet if isinstance(memo_ready_packet, dict) else {}
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    if not canonical:
        canonical = _dict(packet.get("canonical_decision_packet"))
    if not canonical:
        canonical = packet
    contract = _dict(canonical.get("decision_argument_contract")) or build_decision_argument_contract(canonical)
    evidence_items = _evidence_items(packet, canonical)
    source_ids = _source_ids(packet, canonical)
    quantity_rows = _quantity_rows(evidence_items, canonical)
    return _drop_empty(
        {
            "schema_id": "expert_judgment_compression_input_v1",
            "decision_question": packet.get("decision_question") or canonical.get("decision_question"),
            "answer_frame": _compact_answer_frame(packet, canonical),
            "decision_argument_contract": _compact_contract_for_compression(contract),
            "analyst_decision_spine": _compact_analyst_spine(canonical.get("analyst_decision_spine")),
            "source_weight_judgments": [_compact_judgment(row) for row in _list(canonical.get("source_weight_judgments")) if isinstance(row, dict)][:16],
            "source_hierarchy": _compact_source_hierarchy(canonical.get("source_hierarchy")),
            "evidence_items": evidence_items[:36],
            "mandatory_evidence_item_ids": _mandatory_evidence_ids(evidence_items, canonical),
            "quantities": quantity_rows[:24],
            "source_ids": source_ids,
            "sections": _section_inventory(canonical),
            "allowed_section_ids": ["source_weighting", "answer_evidence", "counterweights", "practical_implication"],
        }
    )


def build_expert_judgment_compression_prompt(compression_input: dict[str, Any]) -> str:
    return (
        "You are creating a compact expert-judgment brief for a decision memo writer.\n"
        "This is not the final memo. Compress the packet into the judgment the writer should use.\n\n"
        "Return JSON matching this schema:\n"
        "{\n"
        '  "schema_id": "expert_judgment_compression_v1",\n'
        '  "governing_judgment": "the crisp expert read in one or two sentences",\n'
        '  "source_weighting_logic": [{"point": "...", "decision_function": "...", "evidence_item_ids": [], "source_ids": [], "quantity_values": []}],\n'
        '  "primary_reasoning_chain": [{"point": "...", "decision_function": "...", "evidence_item_ids": [], "source_ids": [], "quantity_values": []}],\n'
        '  "counterweight_dispositions": [{"point": "...", "decision_function": "bounds, narrows, overturns, calibrates, or creates a crux", "evidence_item_ids": [], "source_ids": [], "quantity_values": []}],\n'
        '  "decision_boundaries": [{"point": "...", "decision_function": "...", "evidence_item_ids": [], "source_ids": [], "quantity_values": []}],\n'
        '  "quantities_to_preserve": [{"value": "...", "interpretation": "what this number changes for the decision", "evidence_item_ids": [], "source_ids": []}],\n'
        '  "what_to_subordinate": [{"point": "...", "decision_function": "why this can be brief", "evidence_item_ids": [], "source_ids": [], "quantity_values": []}],\n'
        '  "memo_voice_guidance": ["specific writing guidance"],\n'
        '  "section_briefs": [{"section_id": "source_weighting|answer_evidence|counterweights|practical_implication", "governing_point": "...", "paragraph_strategy": [], "lead_with": "...", "emphasize": [], "subordinate": [], "evidence_item_ids": [], "source_ids": [], "quantity_values": []}]\n'
        "}\n\n"
        "Use only evidence_item_ids, source_ids, and quantity_values present in the input. "
        "Decide what carries the answer, what only bounds or calibrates it, and what can be subordinated. "
        "Every mandatory_evidence_item_id should appear in a reasoning chain, counterweight, boundary, quantity, section brief, or what_to_subordinate entry. "
        "Use generic decision-analysis language that can apply to any domain.\n\n"
        f"Compression input:\n{json.dumps(compression_input, indent=2, ensure_ascii=False)}\n"
    )


def run_expert_judgment_compression(
    memo_ready_packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_model: ModelRunner = run_model_backend,
) -> dict[str, Any]:
    compression_input = build_expert_judgment_compression_input(memo_ready_packet)
    prompt = build_expert_judgment_compression_prompt(compression_input)
    report = {
        "schema_id": "expert_judgment_compression_run_report_v1",
        "status": "skipped_prompt_backend" if backend.strip() == "prompt" else "not_run",
        "accepted": False,
        "input_report": build_expert_judgment_compression_input_report(compression_input),
        "qa_report": {},
        "issues": [],
    }
    if backend.strip() == "prompt":
        return {"compression": {}, "input": compression_input, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            response_schema=ExpertJudgmentCompression.model_json_schema(),
            num_predict=4096,
            json_mode=True,
        )
    except RuntimeError as exc:
        report.update({"status": "backend_error", "issues": ["expert_judgment_compression_backend_error", str(exc)]})
        return {"compression": {}, "input": compression_input, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    parsed, parse_issues = parse_expert_judgment_compression(raw)
    if not parsed:
        report.update({"status": "parse_failed", "issues": ["expert_judgment_compression_parse_failed", *parse_issues]})
        return {"compression": {}, "input": compression_input, "prompt": prompt, "raw": raw, "report": report}
    qa = build_expert_judgment_compression_report(compression_input, parsed)
    accepted = qa.get("status") == "ready"
    report.update(
        {
            "status": "accepted" if accepted else "warning",
            "accepted": accepted,
            "backend": result.backend,
            "attempts": result.attempts,
            "qa_report": qa,
            "issues": [] if accepted else _string_list(qa.get("issues")),
        }
    )
    return {"compression": parsed, "input": compression_input, "prompt": prompt, "raw": raw, "report": report}


def parse_expert_judgment_compression(raw: str) -> tuple[dict[str, Any], list[str]]:
    payload = _parse_json(raw)
    if not isinstance(payload, dict):
        return {}, ["model_output_not_json_object"]
    try:
        model = ExpertJudgmentCompression.model_validate(payload)
    except ValidationError as exc:
        return {}, [f"schema_validation_failed:{exc.errors()[0].get('type') if exc.errors() else 'unknown'}"]
    return model.model_dump(mode="json"), []


def build_expert_judgment_compression_input_report(compression_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "expert_judgment_compression_input_report_v1",
        "status": "ready" if compression_input.get("decision_question") and compression_input.get("evidence_items") else "warning",
        "input_char_count": len(json.dumps(compression_input, ensure_ascii=False)),
        "evidence_item_count": len(_list(compression_input.get("evidence_items"))),
        "mandatory_evidence_item_count": len(_string_list(compression_input.get("mandatory_evidence_item_ids"))),
        "quantity_count": len(_list(compression_input.get("quantities"))),
        "source_count": len(_string_list(compression_input.get("source_ids"))),
        "issues": [] if compression_input.get("decision_question") and compression_input.get("evidence_items") else ["compression_input_missing_question_or_evidence"],
    }


def build_expert_judgment_compression_report(
    compression_input: dict[str, Any],
    compression: dict[str, Any],
) -> dict[str, Any]:
    allowed_evidence = {str(row.get("evidence_item_id") or "") for row in _list(compression_input.get("evidence_items")) if isinstance(row, dict)}
    allowed_sources = set(_string_list(compression_input.get("source_ids")))
    allowed_quantities = {_norm(str(row.get("value") or "")) for row in _list(compression_input.get("quantities")) if isinstance(row, dict)}
    mandatory = set(_string_list(compression_input.get("mandatory_evidence_item_ids")))
    used_evidence = set(_ids_from_compression(compression, "evidence_item_ids"))
    used_sources = set(_ids_from_compression(compression, "source_ids"))
    used_quantities = {_norm(value) for value in _ids_from_compression(compression, "quantity_values")}
    preserved_quantities = {_norm(str(row.get("value") or "")) for row in _list(compression.get("quantities_to_preserve")) if isinstance(row, dict)}
    used_quantities.update(preserved_quantities)
    unknown_evidence = sorted(eid for eid in used_evidence if eid and eid not in allowed_evidence)
    unknown_sources = sorted(source_id for source_id in used_sources if source_id and source_id not in allowed_sources)
    unknown_quantities = sorted(value for value in used_quantities if value and value not in allowed_quantities)
    missing_mandatory = sorted(eid for eid in mandatory if eid and eid not in used_evidence)
    section_ids = [str(row.get("section_id") or "") for row in _list(compression.get("section_briefs")) if isinstance(row, dict)]
    missing_sections = [section_id for section_id in _string_list(compression_input.get("allowed_section_ids")) if section_id not in section_ids]
    issues = []
    if not str(compression.get("governing_judgment") or "").strip():
        issues.append("missing_governing_judgment")
    if missing_mandatory:
        issues.append("mandatory_evidence_not_accounted")
    if unknown_evidence:
        issues.append("unknown_evidence_item_ids")
    if unknown_sources:
        issues.append("unknown_source_ids")
    if unknown_quantities:
        issues.append("unknown_quantity_values")
    if missing_sections:
        issues.append("missing_section_briefs")
    if _looks_generic(compression):
        issues.append("compression_too_generic")
    return {
        "schema_id": "expert_judgment_compression_report_v1",
        "status": "ready" if not issues else "warning",
        "governing_judgment_present": bool(str(compression.get("governing_judgment") or "").strip()),
        "mandatory_evidence_count": len(mandatory),
        "accounted_mandatory_evidence_count": len(mandatory - set(missing_mandatory)),
        "missing_mandatory_evidence_item_ids": missing_mandatory,
        "unknown_evidence_item_ids": unknown_evidence,
        "unknown_source_ids": unknown_sources,
        "unknown_quantity_values": unknown_quantities,
        "section_brief_count": len(section_ids),
        "missing_section_ids": missing_sections,
        "genericness_warning": _looks_generic(compression),
        "issues": issues,
    }


def compact_expert_judgment_for_prompt(compression: dict[str, Any]) -> dict[str, Any]:
    row = _dict(compression)
    if row.get("schema_id") != "expert_judgment_compression_v1":
        return {}
    return _drop_empty(
        {
            "schema_id": "expert_judgment_compression_v1",
            "governing_judgment": row.get("governing_judgment"),
            "source_weighting_logic": [_compact_point(point) for point in _list(row.get("source_weighting_logic"))][:6],
            "primary_reasoning_chain": [_compact_point(point) for point in _list(row.get("primary_reasoning_chain"))][:8],
            "counterweight_dispositions": [_compact_point(point) for point in _list(row.get("counterweight_dispositions"))][:8],
            "decision_boundaries": [_compact_point(point) for point in _list(row.get("decision_boundaries"))][:8],
            "quantities_to_preserve": [_compact_quantity(point) for point in _list(row.get("quantities_to_preserve"))][:12],
            "what_to_subordinate": [_compact_point(point) for point in _list(row.get("what_to_subordinate"))][:8],
            "memo_voice_guidance": _string_list(row.get("memo_voice_guidance"))[:8],
            "section_briefs": [compact_expert_judgment_section_for_prompt(point) for point in _list(row.get("section_briefs"))][:6],
        }
    )


def compact_expert_judgment_section_for_prompt(section: dict[str, Any]) -> dict[str, Any]:
    row = _dict(section)
    return _drop_empty(
        {
            "schema_id": "expert_judgment_section_brief_v1",
            "section_id": row.get("section_id"),
            "governing_point": row.get("governing_point"),
            "lead_with": row.get("lead_with"),
            "paragraph_strategy": _string_list(row.get("paragraph_strategy"))[:5],
            "emphasize": _string_list(row.get("emphasize"))[:6],
            "subordinate": _string_list(row.get("subordinate"))[:5],
            "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:16],
            "source_ids": _string_list(row.get("source_ids"))[:12],
            "quantity_values": _string_list(row.get("quantity_values"))[:10],
        }
    )


def expert_judgment_section(compression: dict[str, Any], section_id: str) -> dict[str, Any]:
    target = str(section_id or "").strip()
    for row in _list(_dict(compression).get("section_briefs")):
        if isinstance(row, dict) and str(row.get("section_id") or "") == target:
            return compact_expert_judgment_section_for_prompt(row)
    return {}


def build_expert_judgment_utilization_report(memo: str, compression: dict[str, Any]) -> dict[str, Any]:
    row = _dict(compression)
    if row.get("schema_id") != "expert_judgment_compression_v1":
        return {
            "schema_id": "expert_judgment_utilization_report_v1",
            "status": "not_available",
            "issues": ["expert_judgment_compression_unavailable"],
        }
    checks = []
    governing = str(row.get("governing_judgment") or "").strip()
    if governing:
        checks.append(_surface_status("governing_judgment", governing, memo))
    for section in _list(row.get("section_briefs")):
        if isinstance(section, dict) and str(section.get("governing_point") or "").strip():
            checks.append(_surface_status(f"section:{section.get('section_id')}", section.get("governing_point"), memo))
    for quantity in _list(row.get("quantities_to_preserve")):
        if isinstance(quantity, dict) and str(quantity.get("value") or "").strip():
            checks.append(_literal_status(f"quantity:{quantity.get('value')}", quantity.get("value"), memo))
    issues = [check for check in checks if not check.get("surfaced")]
    return {
        "schema_id": "expert_judgment_utilization_report_v1",
        "status": "ready" if not issues else "warning",
        "check_count": len(checks),
        "surfaced_count": sum(1 for check in checks if check.get("surfaced")),
        "missing_count": len(issues),
        "checks": checks,
        "issues": issues,
    }


def _evidence_items(packet: dict[str, Any], canonical: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or item.get("evidence_item_id") or "").strip()
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": item_id,
                    "claim": item.get("reader_claim") or item.get("claim") or item.get("statement"),
                    "role": item.get("role"),
                    "source_ids": _item_source_ids(item),
                    "quantity_values": _quantity_values(item),
                    "must_use": bool(item.get("must_use")) or str(item.get("obligation_level") or "") == "must_include",
                    "importance_rank": item.get("importance_rank"),
                }
            )
        )
    known_ids = {row.get("evidence_item_id") for row in rows}
    for section in _list(canonical.get("section_writing_packets")):
        if not isinstance(section, dict):
            continue
        for source_key in ("evidence_context", "retention_requirements"):
            for item in _list(section.get(source_key)):
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("item_id") or item.get("requirement_id") or item.get("evidence_item_id") or "").strip()
                if not item_id or item_id in known_ids:
                    continue
                known_ids.add(item_id)
                rows.append(
                    _drop_empty(
                        {
                            "evidence_item_id": item_id,
                            "claim": item.get("claim") or item.get("statement"),
                            "role": item.get("role") or source_key,
                            "source_ids": _string_list(item.get("source_ids")),
                            "quantity_values": _quantity_values(item),
                            "must_use": source_key == "retention_requirements",
                        }
                    )
                )
    return [row for row in rows if row.get("evidence_item_id") or row.get("claim")]


def _mandatory_evidence_ids(evidence_items: list[dict[str, Any]], canonical: dict[str, Any]) -> list[str]:
    ids = [str(row.get("evidence_item_id") or "") for row in evidence_items if row.get("must_use")]
    for section in _list(canonical.get("section_writing_packets")):
        if isinstance(section, dict):
            ids.extend(
                str(row.get("requirement_id") or row.get("item_id") or "")
                for row in _list(section.get("retention_requirements"))
                if isinstance(row, dict)
            )
    return _dedupe(value for value in ids if value)


def _source_ids(packet: dict[str, Any], canonical: dict[str, Any]) -> list[str]:
    ids = []
    for source in _list(packet.get("source_trail")):
        if isinstance(source, dict):
            ids.append(str(source.get("source_id") or source.get("source_label") or "").strip())
    registry = _dict(canonical.get("citation_registry"))
    for source in _list(registry.get("sources")):
        if isinstance(source, dict):
            ids.append(str(source.get("source_id") or "").strip())
    for item in _evidence_items(packet, canonical):
        ids.extend(_string_list(item.get("source_ids")))
    return _dedupe(value for value in ids if value)


def _quantity_rows(evidence_items: list[dict[str, Any]], canonical: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in evidence_items:
        for value in _string_list(item.get("quantity_values")):
            rows.append(
                _drop_empty(
                    {
                        "value": value,
                        "evidence_item_ids": [item.get("evidence_item_id")] if item.get("evidence_item_id") else [],
                        "source_ids": item.get("source_ids"),
                    }
                )
            )
    for section in _list(canonical.get("section_writing_packets")):
        if not isinstance(section, dict):
            continue
        for row in [*_list(section.get("evidence_context")), *_list(section.get("retention_requirements"))]:
            if not isinstance(row, dict):
                continue
            for value in _quantity_values(row):
                rows.append(
                    _drop_empty(
                        {
                            "value": value,
                            "evidence_item_ids": [row.get("item_id") or row.get("requirement_id")],
                            "source_ids": row.get("source_ids"),
                            "interpretation": row.get("interpretation"),
                        }
                    )
                )
    return _dedupe_rows(rows, "value")


def _section_inventory(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for section in _list(canonical.get("section_writing_packets")):
        if not isinstance(section, dict):
            continue
        rows.append(
            _drop_empty(
                {
                    "section": section.get("section"),
                    "writing_job": section.get("writing_job"),
                    "required_points": _string_list(section.get("required_points"))[:8],
                    "evidence_item_ids": _dedupe(
                        str(row.get("item_id") or row.get("requirement_id") or "")
                        for row in [*_list(section.get("evidence_context")), *_list(section.get("retention_requirements"))]
                        if isinstance(row, dict)
                    ),
                }
            )
        )
    return rows


def _compact_judgment(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "judgment_id": row.get("judgment_id"),
            "source_ids": _string_list(row.get("source_ids")),
            "main_use": row.get("main_use"),
            "memo_weight_sentence": row.get("memo_weight_sentence"),
            "why_weight_this_way": row.get("why_weight_this_way"),
            "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
        }
    )


def _compact_answer_frame(packet: dict[str, Any], canonical: dict[str, Any]) -> dict[str, Any]:
    balanced = _dict(canonical.get("balanced_answer_frame"))
    bluf = _dict(canonical.get("bluf_contract"))
    skeleton = _dict(canonical.get("decision_brief_skeleton"))
    classification = _dict(canonical.get("decision_answer_classification"))
    return _drop_empty(
        {
            "primary_answer": bluf.get("recommended_read") or skeleton.get("primary_answer") or balanced.get("best_current_read") or _dict(packet.get("answer_spine")).get("default_read"),
            "scope": bluf.get("who_it_applies_to") or balanced.get("scope"),
            "confidence": balanced.get("confidence"),
            "main_support": balanced.get("main_support"),
            "main_counterweight": bluf.get("main_exception_or_boundary") or balanced.get("main_counterweight"),
            "practical_read": bluf.get("practical_read") or balanced.get("practical_read"),
            "must_not_overstate": _string_list(balanced.get("must_not_overstate"))[:5],
            "answer_shape": classification.get("answer_shape"),
        }
    )


def _compact_contract_for_compression(contract: dict[str, Any]) -> dict[str, Any]:
    compact = compact_decision_argument_contract_for_prompt(_dict(contract))
    return _drop_empty(
        {
            "selected_answer": _dict(compact.get("selected_answer")),
            "answer_comparison": _dict(compact.get("answer_comparison")),
            "source_hierarchy_thesis": compact.get("source_hierarchy_thesis"),
            "argument_moves": [
                _drop_empty(
                    {
                        "move_id": row.get("move_id"),
                        "move_type": row.get("move_type"),
                        "section_id": row.get("section_id"),
                        "point": row.get("point"),
                        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:10],
                        "source_ids": _string_list(row.get("source_ids"))[:8],
                        "quantities": _string_list(row.get("quantities"))[:6],
                    }
                )
                for row in _list(compact.get("argument_moves"))
                if isinstance(row, dict)
            ][:12],
        }
    )


def _compact_analyst_spine(value: Any) -> dict[str, Any]:
    spine = _dict(value)
    return _drop_empty(
        {
            "primary_answer": spine.get("primary_answer"),
            "secondary_detail": spine.get("secondary_detail"),
            "source_weight_moves": [_compact_point(row) for row in _list(spine.get("source_weight_moves"))][:8],
            "decision_moves": [_compact_point(row) for row in _list(spine.get("decision_moves"))][:10],
        }
    )


def _compact_source_hierarchy(value: Any) -> dict[str, Any]:
    row = _dict(value)
    return _drop_empty(
        {
            "hierarchy_thesis": row.get("hierarchy_thesis") or row.get("thesis"),
            "primary_answer_drivers": _source_hierarchy_lane(row, "primary_answer_drivers"),
            "calibrators": _source_hierarchy_lane(row, "quantitative_or_interpretive_calibrators"),
            "counterweights": _source_hierarchy_lane(row, "counterweights_or_tensions"),
            "scope_limiters": _source_hierarchy_lane(row, "scope_limiters"),
        }
    )


def _source_hierarchy_lane(row: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = _list(_dict(row.get("lanes")).get(key)) or _list(row.get(key))
    return [
        _drop_empty(
            {
                "source_ids": _string_list(value.get("source_ids")) if isinstance(value, dict) else _string_list(value),
                "use": value.get("use") if isinstance(value, dict) else "",
                "limit": value.get("limit") if isinstance(value, dict) else "",
            }
        )
        for value in values[:6]
        if isinstance(value, dict) or _string_list(value)
    ]


def _compact_dict(value: Any, *, max_list: int) -> dict[str, Any]:
    row = _dict(value)
    if not row:
        return {}
    return {key: _compact_value(val, max_list=max_list) for key, val in row.items() if _compact_value(val, max_list=max_list) not in ({}, [], "")}


def _compact_value(value: Any, *, max_list: int) -> Any:
    if isinstance(value, dict):
        return _compact_dict(value, max_list=max_list)
    if isinstance(value, list):
        return [_compact_value(row, max_list=max_list) for row in value[:max_list]]
    return value


def _compact_point(value: Any) -> dict[str, Any]:
    row = _dict(value)
    return _drop_empty(
        {
            "point": row.get("point"),
            "decision_function": row.get("decision_function"),
            "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
            "source_ids": _string_list(row.get("source_ids"))[:10],
            "quantity_values": _string_list(row.get("quantity_values"))[:8],
        }
    )


def _compact_quantity(value: Any) -> dict[str, Any]:
    row = _dict(value)
    return _drop_empty(
        {
            "value": row.get("value"),
            "interpretation": row.get("interpretation"),
            "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:8],
            "source_ids": _string_list(row.get("source_ids"))[:8],
        }
    )


def _ids_from_compression(compression: dict[str, Any], key: str) -> list[str]:
    values: list[str] = []
    for container_key in (
        "source_weighting_logic",
        "primary_reasoning_chain",
        "counterweight_dispositions",
        "decision_boundaries",
        "quantities_to_preserve",
        "what_to_subordinate",
        "section_briefs",
    ):
        for row in _list(compression.get(container_key)):
            if isinstance(row, dict):
                values.extend(_string_list(row.get(key)))
    return _dedupe(values)


def _looks_generic(compression: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(compression.get("governing_judgment") or ""),
            *[
                str(row.get("point") or "")
                for key in ("source_weighting_logic", "primary_reasoning_chain", "counterweight_dispositions", "decision_boundaries")
                for row in _list(compression.get(key))
                if isinstance(row, dict)
            ],
        ]
    ).lower()
    generic_phrases = ["evidence is mixed", "more research is needed", "depends on context", "weigh the evidence carefully"]
    return any(phrase in text for phrase in generic_phrases) and len(text.split()) < 90


def _surface_status(label: str, expected: Any, memo: str) -> dict[str, Any]:
    expected_text = str(expected or "").strip()
    if not expected_text:
        return {"label": label, "expected_text": "", "surfaced": True}
    memo_norm = _token_text(memo)
    expected_norm = _token_text(expected_text)
    tokens = [token for token in expected_norm.split() if len(token) >= 4]
    hits = sum(1 for token in tokens if token in memo_norm)
    surfaced = bool(expected_norm and expected_norm in memo_norm) or (len(tokens) >= 4 and hits >= max(3, len(tokens) // 2))
    return {"label": label, "expected_text": expected_text, "surfaced": surfaced, "token_hits": hits, "token_count": len(tokens)}


def _literal_status(label: str, expected: Any, memo: str) -> dict[str, Any]:
    expected_text = str(expected or "").strip()
    return {"label": label, "expected_text": expected_text, "surfaced": bool(expected_text and expected_text in str(memo or ""))}


def _item_source_ids(item: dict[str, Any]) -> list[str]:
    ids = _string_list(item.get("source_ids"))
    if ids:
        return ids
    return _string_list(item.get("source_labels"))


def _quantity_values(item: dict[str, Any]) -> list[str]:
    values = []
    for quantity in _list(item.get("quantities")):
        if isinstance(quantity, dict):
            values.append(str(quantity.get("value") or "").strip())
        elif str(quantity or "").strip():
            values.append(str(quantity).strip())
    for quantity in _list(item.get("quantity_tuples")):
        if isinstance(quantity, dict):
            values.append(str(quantity.get("value") or "").strip())
    for quantity in _list(item.get("source_bound_quantity_atoms")):
        if isinstance(quantity, dict):
            values.append(str(quantity.get("value") or "").strip())
    values.extend(_string_list(item.get("quantity_values")))
    return _dedupe(value for value in values if value)


def _dedupe_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for row in rows:
        marker = _norm(str(row.get(key) or row))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(row)
    return out


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def _parse_json(text: str) -> Any:
    raw = str(text or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _token_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
