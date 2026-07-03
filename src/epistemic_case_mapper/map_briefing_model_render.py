from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_evidence_partition import repair_briefing_payload
from epistemic_case_mapper.map_briefing_evidence_tables import _extract_json_string_field_local
from epistemic_case_mapper.map_briefing_map_utils import calibrate_confidence
from epistemic_case_mapper.map_briefing_validation import _confidence_label, _looks_like_structured_attempt, model_parse_diagnostics
from epistemic_case_mapper.synthesis_uplift_packet import _parse_json, _render_synthesis_packet


def render_model_briefing_output(
    *,
    result: Any,
    prompt: str,
    quality_report: dict[str, Any],
    scaffold: dict[str, Any],
    source_lookup: dict[str, str],
    prioritized_map: dict[str, Any],
    fallback_payload: Any,
) -> dict[str, Any]:
    if result.prompt_only:
        model_confidence = "not specified"
        calibration = calibrate_confidence(model_confidence, quality_report)
        return {
            "rendered": prompt,
            "model_confidence": model_confidence,
            "calibrated": calibration["calibrated_confidence"],
            "calibration": calibration,
            "parse_ok": False,
            "parse_diagnostics": model_parse_diagnostics(result.text, parse_ok=False),
        }
    payload = _parse_json(result.text)
    parse_ok = isinstance(payload, dict)
    parse_diagnostics = model_parse_diagnostics(result.text, parse_ok=parse_ok)
    model_confidence = _confidence_label(payload.get("confidence")) if payload is not None else "not specified"
    calibration = calibrate_confidence(model_confidence, quality_report)
    calibrated = calibration["calibrated_confidence"]
    if payload is None and _looks_like_structured_attempt(result.text):
        payload = fallback_payload(
            scaffold,
            extracted_brief=_extract_json_string_field_local(result.text, "decision_brief"),
            parse_failure=True,
        )
    if payload is not None:
        payload = repair_briefing_payload(payload, scaffold, source_lookup, prioritized_map)
        payload["confidence"] = calibrated
        rendered = _render_synthesis_packet(payload, map_payload=prioritized_map, requirements=())
    else:
        rendered = result.text.strip()
    return {
        "rendered": rendered,
        "model_confidence": model_confidence,
        "calibrated": calibrated,
        "calibration": calibration,
        "parse_ok": parse_ok,
        "parse_diagnostics": parse_diagnostics,
    }
