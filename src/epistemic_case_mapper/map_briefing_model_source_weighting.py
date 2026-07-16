from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import (
    build_canonical_decision_writer_packet_quality_report,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_source_identity import source_ids_for_labels
from epistemic_case_mapper.map_briefing_source_weight_judgments import build_source_weight_judgment_report
from epistemic_case_mapper.model_backends import model_parallelism, run_model_backend, run_parallel
from epistemic_case_mapper.model_outputs import canonical_json_output


SOURCE_TYPES = {
    "observational_primary",
    "trial_or_intervention",
    "evidence_synthesis",
    "guidance_or_advisory",
    "contextual_summary",
    "mixed_or_unclear",
}

MAIN_USES = {
    "drives_answer",
    "calibrates_magnitude",
    "bounds_answer",
    "defines_scope",
    "identifies_crux",
    "contextualizes",
}

CONFIDENCE_EFFECTS = {"raises_confidence", "lowers_confidence", "narrows_scope", "mixed", "neutral"}


class ModelSourceWeightJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["model_source_weight_judgment_v1"] = "model_source_weight_judgment_v1"
    source_id: str
    source_type: Literal[
        "observational_primary",
        "trial_or_intervention",
        "evidence_synthesis",
        "guidance_or_advisory",
        "contextual_summary",
        "mixed_or_unclear",
    ] = "mixed_or_unclear"
    main_use: Literal[
        "drives_answer",
        "calibrates_magnitude",
        "bounds_answer",
        "defines_scope",
        "identifies_crux",
        "contextualizes",
    ] = "contextualizes"
    why_weight_this_way: str = Field(min_length=1)
    reader_facing_limit: str = ""
    what_not_to_use_it_for: str = ""
    memo_weight_sentence: str = Field(min_length=1)
    confidence_effect: Literal["raises_confidence", "lowers_confidence", "narrows_scope", "mixed", "neutral"] = "neutral"
    evidence_item_ids: list[str] = Field(default_factory=list)

    @field_validator("source_id", "why_weight_this_way", "reader_facing_limit", "what_not_to_use_it_for", "memo_weight_sentence", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("evidence_item_ids", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return _string_list(value)

    @field_validator("source_type", mode="before")
    @classmethod
    def _source_type_alias(cls, value: Any) -> str:
        return _enum_alias(value, SOURCE_TYPES, default="mixed_or_unclear")

    @field_validator("main_use", mode="before")
    @classmethod
    def _main_use_alias(cls, value: Any) -> str:
        return _enum_alias(value, MAIN_USES, default="contextualizes")

    @field_validator("confidence_effect", mode="before")
    @classmethod
    def _confidence_alias(cls, value: Any) -> str:
        return _enum_alias(value, CONFIDENCE_EFFECTS, default="neutral")


def run_model_source_weight_judgments(
    memo_ready_packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    packet = memo_ready_packet if isinstance(memo_ready_packet, dict) else {}
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    source_contexts = build_model_source_weight_inputs(packet)
    prompt_preview = build_model_source_weight_prompt(source_contexts[0]) if source_contexts else ""
    if _source_weighting_disabled():
        return _bundle(
            [],
            prompt_preview=prompt_preview,
            reports=[],
            status="skipped",
            reason="disabled_by_ecm_model_source_weighting_mode",
        )
    if backend.strip() == "prompt":
        return _bundle([], prompt_preview=prompt_preview, reports=[], status="skipped", reason="prompt_backend")
    if not source_contexts:
        return _bundle([], prompt_preview="", reports=[], status="skipped", reason="no_sources")
    fallback_by_source = _fallback_judgments_by_source(canonical)

    def run_one(context: dict[str, Any]) -> dict[str, Any]:
        source_id = str(context.get("source_id") or "").strip()
        prompt = build_model_source_weight_prompt(context)
        try:
            raw = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
                response_schema=ModelSourceWeightJudgment.model_json_schema(),
                num_predict=1536,
                json_mode=True,
            ).text
            row = normalize_model_source_weight_judgment(
                raw,
                source_id=source_id,
                known_evidence_ids=set(_string_list(context.get("evidence_item_ids"))),
                fallback=fallback_by_source.get(source_id),
            )
            report = {
                "source_id": source_id,
                "status": "parsed" if not row.get("fallback_reason") else "fallback",
                "prompt_chars": len(prompt),
                "raw_chars": len(raw),
                "fallback_reason": row.get("fallback_reason", ""),
                "invalid_evidence_item_ids": row.pop("_invalid_evidence_item_ids", []),
            }
            return {"judgment": row, "report": report, "raw": raw}
        except (RuntimeError, ValidationError, ValueError, json.JSONDecodeError) as exc:
            row = _fallback_judgment(source_id, fallback_by_source.get(source_id), reason=type(exc).__name__)
            return {
                "judgment": row,
                "report": {
                    "source_id": source_id,
                    "status": "fallback",
                    "prompt_chars": len(prompt),
                    "raw_chars": 0,
                    "fallback_reason": str(exc)[:300],
                    "invalid_evidence_item_ids": [],
                },
                "raw": "",
            }

    results = run_parallel(source_contexts, run_one, max_workers=model_parallelism(backend))
    judgments = [row["judgment"] for row in results if isinstance(row.get("judgment"), dict)]
    reports = [row["report"] for row in results if isinstance(row.get("report"), dict)]
    return _bundle(judgments, prompt_preview=prompt_preview, reports=reports, status="ready")


def attach_model_source_weighting_to_packet(memo_ready_packet: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(memo_ready_packet, dict):
        return memo_ready_packet
    judgments = _list(bundle.get("model_source_weight_judgments"))
    report = _dict(bundle.get("model_source_weighting_report"))
    memo_ready_packet["model_source_weight_judgments"] = judgments
    memo_ready_packet["model_source_weighting_report"] = report
    if not judgments:
        return memo_ready_packet
    canonical = _dict(memo_ready_packet.get("canonical_decision_writer_packet"))
    if canonical:
        canonical["source_weight_judgments"] = judgments
        canonical["source_weight_judgment_report"] = build_source_weight_judgment_report(judgments, _list(memo_ready_packet.get("source_trail")))
        canonical["model_source_weighting_report"] = report
        canonical["quality_report"] = build_canonical_decision_writer_packet_quality_report(canonical)
        memo_ready_packet["canonical_decision_writer_packet"] = canonical
        memo_ready_packet["canonical_decision_writer_packet_quality_report"] = canonical["quality_report"]
        memo_ready_packet["source_weight_judgment_report"] = canonical["source_weight_judgment_report"]
    return memo_ready_packet


def build_model_source_weight_inputs(memo_ready_packet: dict[str, Any]) -> list[dict[str, Any]]:
    packet = memo_ready_packet if isinstance(memo_ready_packet, dict) else {}
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    source_trail = [row for row in _list(packet.get("source_trail")) if isinstance(row, dict)]
    evidence_items = [row for row in _list(packet.get("evidence_items")) if isinstance(row, dict)]
    fallback_by_source = _fallback_judgments_by_source(canonical)
    rows = []
    for source in source_trail:
        source_id = str(source.get("source_id") or source.get("source_label") or "").strip()
        if not source_id:
            continue
        items = [_compact_evidence_item(row) for row in evidence_items if source_id in _item_source_ids(row, source_trail)]
        rows.append(
            {
                "decision_question": packet.get("decision_question") or canonical.get("decision_question"),
                "source_id": source_id,
                "source": _compact_source(source),
                "existing_source_weight_judgment": fallback_by_source.get(source_id, {}),
                "analyst_source_hierarchy": _source_hierarchy_context(canonical, source_id),
                "answer_spine": _dict(packet.get("answer_spine")),
                "decision_logic": _dict(packet.get("analyst_decision_logic")),
                "evidence_item_ids": [str(row.get("item_id") or "").strip() for row in items if row.get("item_id")],
                "source_evidence_items": items,
            }
        )
    return rows


def build_model_source_weight_prompt(context: dict[str, Any]) -> str:
    schema = ModelSourceWeightJudgment.model_json_schema()
    return (
        "You are judging how one source should be weighted in a source-grounded decision memo.\n"
        "Use the decision question and the source-local evidence below. Return exactly one JSON object matching the schema.\n"
        "Use source_id exactly as provided. Use only evidence_item_ids from the provided source evidence items.\n"
        "When analyst_source_hierarchy is present, treat it as the global source-role decision; set main_use to match that lane unless the source-local evidence clearly contradicts it.\n"
        "Write memo_weight_sentence as one natural reader-facing sentence that explains this source's role and main limitation if it has one.\n\n"
        "Allowed main_use values: drives_answer, calibrates_magnitude, bounds_answer, defines_scope, identifies_crux, contextualizes.\n"
        "Allowed source_type values: observational_primary, trial_or_intervention, evidence_synthesis, guidance_or_advisory, contextual_summary, mixed_or_unclear.\n\n"
        "Required JSON schema:\n"
        f"{json.dumps(schema, indent=2, ensure_ascii=False)}\n\n"
        "Source-local context:\n"
        f"{json.dumps(context, indent=2, ensure_ascii=False)}\n"
    )


def normalize_model_source_weight_judgment(
    raw: str | dict[str, Any],
    *,
    source_id: str,
    known_evidence_ids: set[str],
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else json.loads(canonical_json_output(str(raw or "")))
    if isinstance(payload, dict) and isinstance(payload.get("model_source_weight_judgment"), dict):
        payload = payload["model_source_weight_judgment"]
    row = ModelSourceWeightJudgment.model_validate(payload).model_dump()
    if row["source_id"] != source_id:
        raise ValueError(f"model returned source_id={row['source_id']!r}, expected {source_id!r}")
    invalid_evidence = [item_id for item_id in row["evidence_item_ids"] if known_evidence_ids and item_id not in known_evidence_ids]
    row["evidence_item_ids"] = [item_id for item_id in row["evidence_item_ids"] if not known_evidence_ids or item_id in known_evidence_ids]
    normalized = {
        "judgment_id": f"model_source_weight_{source_id}",
        "source_ids": [source_id],
        "source_type": row["source_type"],
        "main_use": row["main_use"],
        "why_weight_this_way": _short_text(row["why_weight_this_way"], 700),
        "reader_facing_limit": _short_text(row["reader_facing_limit"], 360),
        "what_not_to_use_it_for": [_short_text(row["what_not_to_use_it_for"], 360)] if row["what_not_to_use_it_for"] else [],
        "memo_weight_sentence": _short_text(row["memo_weight_sentence"], 520),
        "confidence_effect": row["confidence_effect"],
        "evidence_item_ids": row["evidence_item_ids"],
        "method": "model_adjudicated_per_source",
        "_invalid_evidence_item_ids": invalid_evidence,
    }
    if invalid_evidence:
        normalized["validation_warning"] = "invalid_evidence_item_ids_removed"
    if not normalized["evidence_item_ids"] and fallback:
        normalized["evidence_item_ids"] = _string_list(fallback.get("evidence_item_ids"))
    return _drop_empty(normalized)


def _bundle(
    judgments: list[dict[str, Any]],
    *,
    prompt_preview: str,
    reports: list[dict[str, Any]],
    status: str,
    reason: str = "",
) -> dict[str, Any]:
    fallback_count = sum(1 for row in judgments if row.get("fallback_reason"))
    warning_count = sum(1 for row in reports if row.get("status") == "fallback" or row.get("invalid_evidence_item_ids"))
    report = {
        "schema_id": "model_source_weighting_report_v1",
        "status": status if warning_count == 0 else "warning",
        "method": "parallel_schema_constrained_per_source_source_weighting",
        "source_count": len(judgments) if judgments else len(reports),
        "judgment_count": len(judgments),
        "fallback_count": fallback_count,
        "warning_count": warning_count,
        "prompt_preview_chars": len(prompt_preview),
        "reports": reports,
        "warnings": _model_source_weighting_warnings(reports, reason=reason),
    }
    if reason:
        report["reason"] = reason
    return {
        "model_source_weight_judgments": judgments,
        "model_source_weighting_prompt_preview": prompt_preview,
        "model_source_weighting_report": report,
    }


def _model_source_weighting_warnings(reports: list[dict[str, Any]], *, reason: str) -> list[str]:
    warnings = []
    if reason:
        warnings.append(reason)
    if any(row.get("status") == "fallback" for row in reports):
        warnings.append("source_weighting_model_fallback_rows")
    if any(row.get("invalid_evidence_item_ids") for row in reports):
        warnings.append("invalid_evidence_item_ids_removed")
    return warnings


def _source_weighting_disabled() -> bool:
    return os.environ.get("ECM_MODEL_SOURCE_WEIGHTING_MODE", "auto").strip().lower() in {"off", "skip", "false", "0"}


def _fallback_judgments_by_source(canonical: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_source = {}
    for row in _list(canonical.get("source_weight_judgments")):
        if not isinstance(row, dict):
            continue
        for source_id in _string_list(row.get("source_ids")):
            by_source[source_id] = row
    return by_source


def _source_hierarchy_context(canonical: dict[str, Any], source_id: str) -> dict[str, Any]:
    hierarchy = _dict(canonical.get("source_hierarchy"))
    lanes = _dict(hierarchy.get("lanes"))
    matches = []
    primary_lane = ""
    for row in _list(hierarchy.get("source_accounting")):
        if isinstance(row, dict) and source_id == str(row.get("source_id") or "").strip():
            primary_lane = str(row.get("primary_lane") or "").strip()
            break
    for lane, rows in lanes.items():
        for row in _list(rows):
            if isinstance(row, dict) and source_id in _string_list(row.get("source_ids")):
                matches.append(
                    {
                        "lane": lane,
                        "role": row.get("role"),
                        "rationale": row.get("rationale"),
                        "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                    }
                )
    return _drop_empty(
        {
            "primary_lane": primary_lane,
            "recommended_main_use": _lane_to_main_use(primary_lane),
            "hierarchy_thesis": hierarchy.get("hierarchy_thesis"),
            "lane_memberships": matches,
        }
    )


def _lane_to_main_use(lane: str) -> str:
    return {
        "primary_answer_drivers": "drives_answer",
        "quantitative_calibrators": "calibrates_magnitude",
        "counterweight_sources": "bounds_answer",
        "scope_boundary_sources": "defines_scope",
        "contextual_sources": "contextualizes",
    }.get(str(lane or ""), "")


def _fallback_judgment(source_id: str, fallback: dict[str, Any] | None, *, reason: str) -> dict[str, Any]:
    if fallback:
        row = dict(fallback)
    else:
        row = {
            "judgment_id": f"model_source_weight_{source_id}",
            "source_ids": [source_id],
            "main_use": "contextualizes",
            "source_type": "mixed_or_unclear",
            "why_weight_this_way": "Use this source for context or traceability unless other packet evidence makes its decision role clear.",
            "evidence_item_ids": [],
        }
    row["method"] = "model_source_weighting_fallback"
    row["fallback_reason"] = reason
    return _drop_empty(row)


def _compact_source(source: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "source_id": source.get("source_id"),
            "source_label": source.get("source_label"),
            "citation_label": source.get("citation_label"),
            "display_label": source.get("display_label"),
            "used_for": _string_list(source.get("used_for")),
        }
    )


def _compact_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "item_id": item.get("item_id"),
            "role": item.get("role"),
            "source_role": item.get("source_role"),
            "answer_relation": item.get("answer_relation"),
            "reader_claim": _short_text(item.get("reader_claim") or item.get("claim"), 420),
            "decision_relevance": _short_text(item.get("decision_relevance"), 360),
            "caveat": _short_text(item.get("caveat"), 260),
            "quantities": [
                _drop_empty(
                    {
                        "value": row.get("value"),
                        "interpretation": _short_text(row.get("interpretation"), 220),
                        "quantity_role": row.get("quantity_role"),
                    }
                )
                for row in _list(item.get("quantities"))
                if isinstance(row, dict)
            ],
            "source_appraisal": _dict(item.get("source_appraisal")),
            "source_use_warnings": _string_list(item.get("source_use_warnings")),
            "obligation_level": item.get("obligation_level"),
            "memo_function": item.get("memo_function"),
            "must_use": item.get("must_use"),
        }
    )


def _item_source_ids(item: dict[str, Any], source_trail: list[Any]) -> list[str]:
    explicit = _string_list(item.get("source_ids") or item.get("source_id"))
    labels = _string_list(item.get("source_labels") or item.get("source_label"))
    return _dedupe([*explicit, *source_ids_for_labels(labels, source_trail)])


def _enum_alias(value: Any, allowed: set[str], *, default: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "observational": "observational_primary",
        "cohort": "observational_primary",
        "primary_observational": "observational_primary",
        "trial": "trial_or_intervention",
        "intervention": "trial_or_intervention",
        "rct": "trial_or_intervention",
        "review": "evidence_synthesis",
        "meta_analysis": "evidence_synthesis",
        "synthesis": "evidence_synthesis",
        "guidance": "guidance_or_advisory",
        "guideline": "guidance_or_advisory",
        "advisory": "guidance_or_advisory",
        "context": "contextual_summary",
        "background": "contextual_summary",
        "support": "drives_answer",
        "primary": "drives_answer",
        "driver": "drives_answer",
        "calibrate": "calibrates_magnitude",
        "magnitude": "calibrates_magnitude",
        "bound": "bounds_answer",
        "counterweight": "bounds_answer",
        "scope": "defines_scope",
        "applicability": "defines_scope",
        "crux": "identifies_crux",
        "contextualize": "contextualizes",
        "context_only": "contextualizes",
        "raise": "raises_confidence",
        "raises": "raises_confidence",
        "lower": "lowers_confidence",
        "lowers": "lowers_confidence",
        "narrows": "narrows_scope",
    }
    text = aliases.get(text, text)
    return text if text in allowed else default


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}
