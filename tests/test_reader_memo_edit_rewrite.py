from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing import (
    apply_reader_memo_edit_suggestions,
    build_reader_memo_rewrite_contract,
    build_reader_memo_rewrite_prompt,
    parse_reader_memo_rewrite_payload,
    repair_reader_memo_rewrite_candidate,
    rewrite_reader_memo_with_contract,
)
from epistemic_case_mapper.map_briefing_practical_text import reader_facing_practical_items
from epistemic_case_mapper.map_briefing_memo_slots import _replace_internal_reader_phrases
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_whole_memo_rewrite_prompt_requests_json_edits_not_full_rewrite() -> None:
    memo = """## Decision Brief

The language is awkward and awkwardly repeated.

**Confidence:** medium
"""
    contract = build_reader_memo_rewrite_contract(memo, {"confidence_cap": "medium"})

    prompt = build_reader_memo_rewrite_prompt(memo, contract)

    assert '"edits"' in prompt
    assert "Do not rewrite the memo" in prompt
    assert "memo_markdown" not in prompt


def test_apply_reader_memo_edit_suggestions_uses_only_exact_unambiguous_edits() -> None:
    memo = """## Decision Brief

The language is awkward and awkwardly repeated.

**Confidence:** medium

## Practical Read

- Keep the decision bounded.
"""
    payload = {
        "edits": [
            {
                "target": "The language is awkward and awkwardly repeated.",
                "replacement": "The language is repetitive.",
                "reason": "Remove awkward repetition.",
            },
            {
                "target": "not present",
                "replacement": "new text",
                "reason": "Should not apply.",
            },
        ]
    }

    result = apply_reader_memo_edit_suggestions(memo, payload)

    assert "The language is repetitive." in result["memo"]
    assert len(result["applied_edits"]) == 1
    assert result["skipped_edits"][0]["reason"] == "target text was not found exactly"


def test_whole_memo_rewrite_accepts_safe_edit_suggestions(monkeypatch) -> None:
    memo = _long_memo()
    appendix = "## Evidence Appendix\n\nThe source supports the read."
    scaffold = {
        "confidence_cap": "medium",
        "map_sufficiency_report": {"status": "sufficient_for_scaffolded_briefing"},
        "decision_memo_slots": {"slots": []},
    }
    candidate_map = {"claims": [], "relations": []}

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        assert '"edits"' in prompt
        assert "memo_markdown" not in prompt
        return ModelBackendResult(
            text=json.dumps(
                {
                    "edits": [
                        {
                            "target": "The language is awkward and awkwardly repeated.",
                            "replacement": "The language is repetitive.",
                            "reason": "Remove awkward wording.",
                        }
                    ]
                }
            ),
            backend=backend,
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_reader_contracts.run_model_backend", fake_backend)

    result = rewrite_reader_memo_with_contract(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] in {"accepted", "accepted_after_repair"}
    assert result["report"]["applied_edit_count"] == 1
    assert "The language is repetitive." in result["memo"]


def test_reader_memo_repair_preserves_practical_read_bullets() -> None:
    memo = """## Decision Brief

People with Type 2 Diabetes: High egg consumption has been associated with increased cardiovascular risk.
Individuals with High LDL Cholesterol: Consider reducing sources of saturated fat and dietary cholesterol.

**Confidence:** medium

## Practical Read

However, this recommendation includes two important exceptions:

- **People with Type 2 Diabetes:** High egg consumption has been associated with increased cardiovascular risk.
- **Individuals with High LDL Cholesterol:** Consider reducing sources of saturated fat and dietary cholesterol.

## Why This Read

The evidence is scoped.
"""

    repaired = repair_reader_memo_rewrite_candidate(memo, {"confidence_cap": "medium"}, {"confidence": "medium"})

    assert "- **People with Type 2 Diabetes:**" in repaired
    assert "- **Individuals with High LDL Cholesterol:**" in repaired


def test_whole_memo_rewrite_rejects_legacy_full_memo_payload(monkeypatch) -> None:
    memo = _long_memo()
    appendix = "## Evidence Appendix\n\nThe source supports the read."

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        return ModelBackendResult(text=json.dumps({"memo_markdown": memo.replace("awkward", "smooth")}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_reader_contracts.run_model_backend", fake_backend)

    result = rewrite_reader_memo_with_contract(
        memo,
        appendix,
        {"confidence_cap": "medium", "decision_memo_slots": {"slots": []}},
        {"claims": [], "relations": []},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert parse_reader_memo_rewrite_payload(json.dumps({"memo_markdown": memo}))["edits"]
    assert result["report"]["status"] == "no_safe_edits_fallback"
    assert result["memo"] == memo


def test_practical_items_are_reader_facing_and_conservative_about_boundaries() -> None:
    items = reader_facing_practical_items(
        [
            "State the default as neutral or low-concern under the stated conditions; do not frame the default as beneficial",
            "Preserve this dose/intensity boundary in practical guidance: up to one unit per day",
            "Preserve this dose/intensity boundary in practical guidance: at least one unit per day",
            "Name this subgroup separately from the default case: higher-risk participants",
        ]
    )

    assert items == [
        "The default practical read is neutral or low-concern under the stated conditions; it should not be treated as beneficial.",
        "The practical boundary to keep visible is up to one unit per day.",
        "Treat higher-risk participants as a separate subgroup rather than folding that group into the default case.",
    ]


def test_internal_phrase_cleanup_repairs_relative_pronoun_casing() -> None:
    text = "The study enrolled participants WHO were free of the condition."

    assert _replace_internal_reader_phrases(text) == "The study enrolled participants who were free of the condition."


def _long_memo() -> str:
    return (
        """## Decision Brief

The language is awkward and awkwardly repeated.

**Confidence:** medium

## Practical Read

- Keep the decision bounded.

## Why This Read

The evidence is scoped.

## Evidence Carrying the Conclusion

The source supports the read.

## Practical Scope and Exceptions

Exceptions remain possible.

## Limits of the Current Map

The map is limited.

## Evidence Trail

The structured evidence trail is in `EVIDENCE_APPENDIX.md`.
"""
        + ((" Additional source grounded context remains visible for the reviewer" * 45) + ".")
    )
