from __future__ import annotations

from typing import Any


COHERENCE_EDIT_TYPES = {
    "tighten_bluf",
    "deduplicate_caveat",
    "rebalance_emphasis",
    "clarify_section_role",
    "remove_redundant_sentence",
    "align_scope_with_answer",
}

PROSE_EDIT_TYPES = {
    "smooth_transition",
    "shorten_sentence",
    "fix_awkward_phrase",
    "remove_internal_process_language",
    "improve_reader_voice",
    "clarify_local_sentence",
}


def model_facing_reader_memo_edit_context(contract: dict[str, Any]) -> dict[str, Any]:
    """Return only the compact context needed by the optional final edit pass.

    The full rewrite contract remains available to deterministic validators. The
    model-facing editor should not see answer frames, option comparisons, slot
    models, or required evidence rows because those can make a local prose pass
    behave like a second synthesis pass.
    """
    return {
        "schema_id": "reader_memo_final_edit_context_v1",
        "question": str(contract.get("question", "")).strip(),
        "confidence": str(contract.get("confidence", "")).strip(),
        "target_sections": [
            str(section).strip()
            for section in contract.get("target_sections", [])
            if str(section).strip()
        ],
        "editorial_lints": [
            str(lint).strip()
            for lint in contract.get("editorial_lints", [])
            if str(lint).strip()
        ],
        "protected_content_rules": [
            "Do not edit the decision question line.",
            "Do not edit section headings.",
            "Do not edit the confidence label.",
            "Do not edit source labels, source names, evidence identifiers, or the final source list.",
            "Do not edit numbers, measured quantities, confidence intervals, or dose/frequency thresholds.",
            "Do not remove uncertainty, missing-evidence, or bounded-answer wording.",
        ],
        "edit_scope": "Suggest local prose edits only; do not synthesize new evidence or change the recommendation.",
    }


def model_facing_pass_edit_context(
    *,
    contract: dict[str, Any],
    diagnosis: dict[str, Any],
    protected_spans: dict[str, Any],
    pass_name: str,
) -> dict[str, Any]:
    """Build compact, pass-specific context for final memo editing."""
    allowed = sorted(COHERENCE_EDIT_TYPES if pass_name == "coherence" else PROSE_EDIT_TYPES)
    pass_diagnosis = diagnosis.get(pass_name, {}) if isinstance(diagnosis.get(pass_name), dict) else {}
    return {
        "schema_id": "reader_memo_final_edit_context_v2",
        "pass": pass_name,
        "question": str(contract.get("question", "")).strip(),
        "confidence": str(contract.get("confidence", "")).strip(),
        "allowed_edit_types": allowed,
        "diagnosis": pass_diagnosis,
        "diagnostic_metrics": diagnosis.get("metrics", {}) if isinstance(diagnosis.get("metrics"), dict) else {},
        "protected_spans": _compact_protected_spans(protected_spans),
        "protected_content_rules": protected_spans.get("rules", []) if isinstance(protected_spans.get("rules"), list) else [],
        "edit_scope": _pass_scope(pass_name),
    }


def _compact_protected_spans(protected_spans: dict[str, Any]) -> dict[str, Any]:
    spans = protected_spans.get("spans", []) if isinstance(protected_spans.get("spans"), list) else []
    compact: list[dict[str, str]] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        kind = str(span.get("kind", "")).strip()
        text = str(span.get("text", "")).strip()
        if not kind or not text:
            continue
        if kind == "sources_section" and len(text) > 220:
            text = "Final Sources section is protected as a block."
        elif len(text) > 220:
            text = text[:217].rstrip() + "..."
        compact.append({"kind": kind, "text": text})
    return {
        "schema_id": protected_spans.get("schema_id", "memo_protected_spans_v1"),
        "span_count": protected_spans.get("span_count", len(spans)),
        "spans": compact[:40],
    }


def _pass_scope(pass_name: str) -> str:
    if pass_name == "coherence":
        return "Improve BLUF/body alignment, caveat weighting, section redundancy, and decision-flow issues without adding evidence."
    return (
        "Improve local readability, transitions, sentence length, reader voice, raw diagnostic leakage, "
        "and dense paragraphs without changing argument structure or evidence."
    )
