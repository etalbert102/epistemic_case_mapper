from __future__ import annotations

from typing import Any


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
