from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing import (
    apply_reader_memo_edit_suggestions,
    build_reader_memo_practical_actions,
    build_reader_memo_rewrite_contract,
    build_reader_memo_rewrite_prompt,
    parse_reader_memo_rewrite_payload,
    repair_reader_memo_rewrite_candidate,
    rewrite_reader_memo_with_contract,
)
from epistemic_case_mapper.map_briefing_final_memo_editor import (
    build_full_memo_polish_obligation_packet,
    build_full_memo_polish_prompt,
    full_memo_polish_judge_issues,
    full_memo_polish_preservation_issues,
    run_full_memo_polish_editor,
)
from epistemic_case_mapper.map_briefing_full_memo_polish import restore_full_memo_protected_content
from epistemic_case_mapper.map_briefing_final_memo_diagnosis import build_memo_protected_spans
from epistemic_case_mapper.map_briefing_practical_text import reader_facing_practical_items
from epistemic_case_mapper.map_briefing_memo_slots import _replace_internal_reader_phrases
from epistemic_case_mapper.map_briefing_warning_repair import build_warning_repair_packet
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
    assert "Final edit context" in prompt
    assert "Evidence contract" not in prompt
    assert '"answer_frame"' not in prompt
    assert '"option_comparison"' not in prompt
    assert '"required_evidence"' not in prompt
    assert '"required_gaps"' not in prompt


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


def test_apply_reader_memo_edit_suggestions_rejects_protected_span_edits() -> None:
    memo = """## Decision Brief

Decision question: Should this be used?

The answer is cautious.
"""
    payload = {
        "edits": [
            {
                "target": "Decision question: Should this be used?",
                "replacement": "Decision question: Should this be avoided?",
                "reason": "Do not allow question edits.",
                "edit_type": "tighten_bluf",
            }
        ]
    }
    protected = {
        "spans": [
            {"kind": "decision_question", "text": "Should this be used?"},
        ]
    }

    result = apply_reader_memo_edit_suggestions(memo, payload, protected_spans=protected, allowed_edit_types={"tighten_bluf"})

    assert result["applied_edits"] == []
    assert result["skipped_edits"][0]["reason"] == "edit touches protected memo content"
    assert "Should this be avoided" not in result["memo"]


def test_apply_reader_memo_edit_suggestions_rejects_new_numbers_and_sources() -> None:
    memo = """## Practical Read

This is a practical sentence.
"""
    payload = {
        "edits": [
            {
                "target": "This is a practical sentence.",
                "replacement": "This is a practical sentence at 10 mg (Source A).",
                "reason": "Would add unsupported specifics.",
                "edit_type": "smooth_transition",
            }
        ]
    }

    result = apply_reader_memo_edit_suggestions(memo, payload, allowed_edit_types={"smooth_transition"})

    assert result["applied_edits"] == []
    assert result["skipped_edits"][0]["reason"] == "edit changes or introduces protected numbers"


def test_apply_reader_memo_edit_suggestions_allows_preserved_numbers_and_sources() -> None:
    memo = """## Practical Read

This finding involved 10 mg per day (Source A), though the sentence is awkward.
"""
    payload = {
        "edits": [
            {
                "target": "This finding involved 10 mg per day (Source A), though the sentence is awkward.",
                "replacement": "This finding involved 10 mg per day (Source A), but the sentence is clearer.",
                "reason": "Improve prose while preserving protected tokens.",
                "edit_type": "fix_awkward_phrase",
            }
        ]
    }
    protected = {
        "spans": [
            {"kind": "quantity", "text": "10 mg"},
            {"kind": "source_label", "text": "(Source A)"},
        ]
    }

    result = apply_reader_memo_edit_suggestions(memo, payload, protected_spans=protected, allowed_edit_types={"fix_awkward_phrase"})

    assert len(result["applied_edits"]) == 1
    assert "the sentence is clearer" in result["memo"]


def test_apply_reader_memo_edit_suggestions_does_not_treat_identifier_years_as_quantities() -> None:
    memo = """## Limits of the Current Map

fail: missing_source_claim_coverage - No accepted claim from required source dga_2020_2025_pmc_summary.
"""
    payload = {
        "edits": [
            {
                "target": "fail: missing_source_claim_coverage - No accepted claim from required source dga_2020_2025_pmc_summary.",
                "replacement": "The map lacks a specific accepted claim from one required source.",
                "reason": "Convert machine diagnostic to reader-facing prose.",
                "edit_type": "remove_internal_process_language",
            }
        ]
    }

    result = apply_reader_memo_edit_suggestions(memo, payload, allowed_edit_types={"remove_internal_process_language"})

    assert len(result["applied_edits"]) == 1
    assert "dga_2020_2025" not in result["memo"]


def test_reader_memo_repair_replaces_raw_source_ids_with_display_names() -> None:
    memo = """## Decision Brief

Moderate egg consumption is not clearly harmful in this source packet.

**Confidence:** medium

## Limits of the Current Map

The following sources did not provide accepted claims: dga_2020_2025_pmc_summary and aha_2019_dietary_cholesterol_pubmed.
"""
    scaffold = {
        "confidence_cap": "medium",
        "source_display_names": {
            "dga_2020_2025_pmc_summary": "DGA 2020-2025 PMC Summary",
            "aha_2019_dietary_cholesterol_pubmed": "AHA 2019 Dietary Cholesterol PubMed",
        },
    }
    contract = build_reader_memo_rewrite_contract(memo, scaffold)

    repaired = repair_reader_memo_rewrite_candidate(memo, scaffold, contract)

    assert "dga_2020_2025_pmc_summary" not in repaired
    assert "aha_2019_dietary_cholesterol_pubmed" not in repaired
    assert "DGA 2020-2025 PMC Summary" in repaired
    assert "AHA 2019 Dietary Cholesterol PubMed" in repaired


def test_reader_memo_repair_does_not_replace_source_id_substrings() -> None:
    memo = """## Decision Brief

Moderate egg consumption is not clearly harmful in this source packet.

**Confidence:** medium

## Limits of the Current Map

not_dga_2020_2025_pmc_summary_suffix is an unrelated identifier.
"""
    scaffold = {
        "confidence_cap": "medium",
        "source_display_names": {
            "dga_2020_2025_pmc_summary": "DGA 2020-2025 PMC Summary",
        },
    }
    contract = build_reader_memo_rewrite_contract(memo, scaffold)

    repaired = repair_reader_memo_rewrite_candidate(memo, scaffold, contract)

    assert "not_dga_2020_2025_pmc_summary_suffix" in repaired
    assert "DGA 2020-2025 PMC Summary" not in repaired


def test_full_memo_polish_preservation_flags_dropped_required_information() -> None:
    memo = """## Decision Brief

**Decision question:** Should the intervention be used?

The current read is neutral at 10 mg per day (Source A).

**Confidence:** medium

## Practical Read

- Keep the 10 mg per day boundary visible.

## Limits of the Current Map

The map lacks comparator evidence.

## Sources

- Source A
"""
    scaffold = {
        "question": "Should the intervention be used?",
        "confidence_cap": "medium",
        "source_display_names": {"source_a": "Source A"},
        "decision_memo_slots": {"slots": []},
    }
    contract = build_reader_memo_rewrite_contract(memo, scaffold)
    protected = build_memo_protected_spans(memo, contract)
    obligations = build_full_memo_polish_obligation_packet(memo, scaffold, contract, protected)

    issues = full_memo_polish_preservation_issues(
        """## Decision Brief

The current read is neutral.

**Confidence:** medium
""",
        original_memo=memo,
        evidence_appendix="## Evidence Appendix\n",
        scaffold=scaffold,
        candidate_map={"claims": [], "relations": []},
        contract=contract,
        obligation_packet=obligations,
        validate_candidate=lambda *args: [],
    )

    assert "polish dropped or changed the exact decision question" in issues
    assert "polish dropped required source: Source A" in issues
    assert "polish dropped required number: 10 mg" in issues


def test_full_memo_polish_allows_original_optional_numbers_without_requiring_them() -> None:
    memo = """## Decision Brief

**Decision question:** Should the intervention be used?

The required dose is 10 mg. A secondary appendix detail mentions 20 mg.

**Confidence:** medium

## Sources

- Source A
"""
    scaffold = {"question": "Should the intervention be used?", "confidence_cap": "medium", "decision_memo_slots": {"slots": []}}
    contract = {
        "question": "Should the intervention be used?",
        "confidence": "medium",
        "required_evidence": [{"claim": "The required dose is 10 mg.", "source": "Source A", "anchor_terms": ["10 mg"]}],
    }
    obligations = build_full_memo_polish_obligation_packet(memo, scaffold, contract)

    issues = full_memo_polish_preservation_issues(
        memo.replace("A secondary appendix detail mentions 20 mg.", ""),
        original_memo=memo,
        evidence_appendix="",
        scaffold=scaffold,
        candidate_map={"claims": [], "relations": []},
        contract=contract,
        obligation_packet=obligations,
        validate_candidate=lambda *args: [],
    )

    assert "polish dropped required number: 20 mg" not in issues
    assert not [issue for issue in issues if issue.startswith("polish introduced unsupported number")]


def test_full_memo_polish_prompt_curates_checklist_without_off_question_noise() -> None:
    memo = """## Decision Brief

**Decision question:** How should a synthesis preserve observational outcome evidence and randomized marker evidence for egg consumption and CVD?

The memo mentions 0.98, 0.99, and 08 as extracted quantities.

**Confidence:** medium
"""
    obligation_packet = {
        "question": "How should a synthesis preserve observational outcome evidence and randomized marker evidence for egg consumption and CVD?",
        "confidence": "medium",
        "required_numbers": ["0.98"],
        "optional_numbers": ["0.99", "08"],
        "required_evidence": [
            {"slot": "Main support", "claim": "Moderate egg consumption is not associated with cardiovascular disease risk overall."},
            {"slot": "Counterevidence or tension", "claim": "Higher daily egg consumption may increase marker ratios in randomized studies."},
            {"slot": "Scope and boundary conditions", "claim": "In an egg consumption and CVD subgroup analysis, the relative risk was 1.25 (95% confidence interval 0.99 to 1.59) and the pooled estimate was..."},
            {"slot": "Safety and downside risk", "claim": "Higher relative risks of bladder cancer were associated with fried egg intake compared to boiled egg intake."},
        ],
        "required_gaps": ["The current map does not cleanly establish randomized intervention evidence for disease incidence."],
        "answer_frame": {"direct_answer": "Treat the answer as conditional on named risks and missing evidence.", "near_term_recommendation": "Moderate use is not associated with the main outcome overall, and is associated with..."},
    }

    prompt = build_full_memo_polish_prompt(memo, obligation_packet)
    assert "bladder cancer" not in prompt
    assert "0.99, 08" not in prompt
    assert "Preserve bottom-line support" in prompt
    assert "Preserve main counterweight" in prompt
    assert "Preserve evidence-family limit" in prompt
    assert "0.99 to 1.59" in prompt
    assert "0.99 to 1.\n" not in prompt
    assert "and is." not in prompt


def test_full_memo_polish_restoration_drops_plain_duplicate_question() -> None:
    original = """## Decision Brief

**Decision question:** Should the intervention be used?

**Confidence:** medium
"""
    candidate = """## Decision Brief

**Should the intervention be used?**

The answer is conditional.

**Confidence:** Medium
"""

    restored = restore_full_memo_protected_content(candidate, original_memo=original, contract={"confidence": "medium"})

    assert restored.count("Should the intervention be used?") == 1
    assert "**Confidence:** medium" in restored


def test_full_memo_polish_judge_issues_rejects_semantic_drops() -> None:
    payload = {
        "accepted": False,
        "dropped_information": ["Dropped comparator evidence limit."],
        "unsupported_additions": ["Added a stronger recommendation."],
        "changed_stance": True,
        "limits_preserved": False,
    }

    issues = full_memo_polish_judge_issues(payload)

    assert "judge did not accept polished memo" in issues
    assert "judge dropped_information: Dropped comparator evidence limit." in issues
    assert "judge unsupported_additions: Added a stronger recommendation." in issues
    assert "judge found changed stance" in issues
    assert "judge found limits were not preserved" in issues


def test_warning_repair_packet_supplies_missing_atoms_from_original_memo() -> None:
    original = """## Decision Brief

The cohort included 60 candidate evidence cards and 11 source anchors.
The subgroup had 204 exposed participants and 299 controls.

## Sources

- Source A
"""
    packet = build_warning_repair_packet(
        original,
        [
            "polish dropped required source: Source A",
            "polish dropped required number: 204",
            "polish dropped required source label: (Source A)",
            "judge dropped_information: The subgroup had 204 exposed participants and 299 controls.",
        ],
        {
            "required_sources": ["Source A"],
            "required_numbers": ["204", "299"],
            "required_source_labels": ["(Source A)"],
            "required_evidence": [{"claim": "The subgroup had 204 exposed participants and 299 controls.", "source": "Source A"}],
        },
    )

    assert packet["final_source_list"] == ["Source A"]
    assert packet["missing_number_contexts"][0]["number"] == "204"
    assert "204 exposed participants and 299 controls" in packet["missing_number_contexts"][0]["original_context"]
    assert packet["judge_dropped_information"] == ["The subgroup had 204 exposed participants and 299 controls."]
    assert packet["suggested_insertions"]
    assert packet["required_evidence"][0]["claim"] == "The subgroup had 204 exposed participants and 299 controls."


def test_apply_reader_memo_edit_suggestions_records_typed_metadata() -> None:
    memo = """## Practical Read

This section begins awkwardly.
"""
    payload = {
        "edits": [
            {
                "target": "This section begins awkwardly.",
                "replacement": "This section opens directly.",
                "reason": "Smoother local prose.",
                "target_section": "Practical Read",
                "edit_type": "smooth_transition",
            }
        ]
    }

    result = apply_reader_memo_edit_suggestions(
        memo,
        payload,
        allowed_edit_types={"smooth_transition"},
        pass_name="prose",
    )

    assert result["applied_edits"][0]["target_section"] == "Practical Read"
    assert result["applied_edits"][0]["edit_type"] == "smooth_transition"
    assert result["applied_edits"][0]["pass"] == "prose"
    assert result["pass"] == "prose"


def test_apply_reader_memo_edit_suggestions_rejects_wrong_pass_edit_type() -> None:
    memo = """## Practical Read

This section begins awkwardly.
"""
    payload = {
        "edits": [
            {
                "target": "This section begins awkwardly.",
                "replacement": "This section opens directly.",
                "edit_type": "tighten_bluf",
            }
        ]
    }

    result = apply_reader_memo_edit_suggestions(memo, payload, allowed_edit_types={"smooth_transition"})

    assert result["applied_edits"] == []
    assert result["skipped_edits"][0]["reason"] == "edit_type is not allowed for this pass"


def test_whole_memo_rewrite_accepts_safe_full_polish(monkeypatch) -> None:
    memo = _long_memo()
    appendix = "## Evidence Appendix\n\nThe source supports the read."
    scaffold = {
        "confidence_cap": "medium",
        "map_sufficiency_report": {"status": "sufficient_for_scaffolded_briefing"},
        "decision_memo_slots": {"slots": []},
    }
    candidate_map = {"claims": [], "relations": []}
    polished = memo.replace("The language is awkward and awkwardly repeated.", "The decision read is bounded and clear.")
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        calls.append(prompt)
        if "strict preservation judge" in prompt:
            return ModelBackendResult(
                text=json.dumps(
                    {
                        "accepted": True,
                        "dropped_information": [],
                        "unsupported_additions": [],
                        "changed_stance": False,
                        "limits_preserved": True,
                        "reason": "Preserved obligations.",
                    }
                ),
                backend=backend,
            )
        assert "polished, coherent, natural briefing memo" in prompt
        assert '"edits"' not in prompt
        return ModelBackendResult(text=polished, backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_final_memo_editor.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_warning_repair.run_model_backend", fake_backend)

    result = rewrite_reader_memo_with_contract(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert len(calls) == 2
    assert result["report"]["status"] == "full_polish_accepted"
    assert result["report"]["full_polish_status"] == "accepted"
    assert "The decision read is bounded and clear." in result["memo"]


def test_whole_memo_rewrite_accepts_full_polish_with_validation_warnings(monkeypatch) -> None:
    memo = _long_memo()
    appendix = "## Evidence Appendix\n\nThe source supports the read."
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        calls.append(prompt)
        if "polished, coherent, natural briefing memo" in prompt:
            return ModelBackendResult(text="## Decision Brief\n\nToo short.\n", backend=backend)
        if "repairing a polished decision memo after validation produced warnings" in prompt:
            return ModelBackendResult(text="## Decision Brief\n\nToo short.\n", backend=backend)
        if "strict preservation judge" in prompt:
            return ModelBackendResult(
                text=json.dumps(
                    {
                        "accepted": True,
                        "dropped_information": [],
                        "unsupported_additions": [],
                        "changed_stance": False,
                        "limits_preserved": True,
                        "reason": "Style is not judged.",
                    }
                ),
                backend=backend,
            )
        raise AssertionError("full-polish validation warnings should not fall back to local edit passes")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_final_memo_editor.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_warning_repair.run_model_backend", fake_backend)

    result = rewrite_reader_memo_with_contract(
        memo,
        appendix,
        {"confidence_cap": "medium", "map_sufficiency_report": {"status": "sufficient_for_scaffolded_briefing"}, "decision_memo_slots": {"slots": []}},
        {"claims": [], "relations": []},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert len(calls) == 4
    assert result["report"]["status"] == "full_polish_accepted_with_warnings"
    assert result["report"]["full_polish_status"] == "accepted_with_warnings"
    assert len(result["report"]["full_polish_attempts"]) == 1
    assert result["report"]["pass_count"] == 1
    assert result["report"]["accepted_pass_count"] == 1
    assert result["report"]["warnings"]
    assert result["report"]["full_polish_attempts"][0]["warning_repair"]["status"] == "no_warning_reduction_kept_original"
    assert "Too short." in result["memo"]


def test_whole_memo_rewrite_repairs_validation_warnings_when_possible(monkeypatch) -> None:
    memo = """## Decision Brief

**Decision question:** Should the evidence be treated as decision-ready?

The current read is bounded: the intervention may help the target outcome, but the inference depends on observational follow-up and the comparator evidence.

**Confidence:** medium

## Practical Read

Use the intervention only when the target population matches the evidence base. Comparator evidence matters because studies often lack data on replacement foods and substitution options, which can change the observed outcome association.

## Why This Read

The strongest support comes from a cohort estimate of 1.25 with a 95% confidence interval from 0.99 to 1.59, while implementation remains conditional on whether replacement foods or substitution options are measured.

## Decision Cruxes

| Crux | Why it matters | Current read | Would change if |
|---|---|---|---|
| Comparator measurement | It determines whether the observed association is attributable to the exposure or what it replaces. | Replacement foods are incompletely measured. | Direct comparator evidence showed the association was unchanged across replacement options. |

## Limits of the Current Map

The map does not cleanly establish randomized intervention evidence for disease incidence.

## Sources

- [Long Source Title About Comparator Evidence](https://example.test/source)
"""
    concise_without_required_evidence = """## Decision Brief

**Decision Question:** Should the evidence be treated as decision-ready?

The evidence supports a bounded read for the target outcome, but the inference remains observational and uncertain.

**Confidence:** Medium

## What the Evidence Supports

The strongest support comes from a cohort estimate of 1.25 with a 95% confidence interval from 0.99 to 1.59.

## What Limits the Inference

The map does not cleanly establish randomized intervention evidence for disease incidence.

## Sources

- [Short Source](https://example.test/source)
"""
    concise_with_required_evidence = concise_without_required_evidence.replace(
        "The evidence supports a bounded read for the target outcome, but the inference remains observational and uncertain.",
        "The evidence supports a bounded read for the target outcome, but the inference remains observational and uncertain; comparator evidence matters because studies often lack data on replacement foods and substitution options.",
    )
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        calls.append(prompt)
        if "repairing a polished decision memo after validation produced warnings" in prompt:
            assert "Targeted repair packet" in prompt
            assert "Comparator evidence matters because studies often lack data on replacement foods and substitution options" in prompt
            assert "Long Source Title About Comparator Evidence" in prompt
            return ModelBackendResult(text=concise_with_required_evidence, backend=backend)
        if "strict preservation judge" in prompt:
            return ModelBackendResult(
                text=json.dumps(
                    {
                        "accepted": True,
                        "dropped_information": [],
                        "unsupported_additions": [],
                        "changed_stance": False,
                        "limits_preserved": True,
                        "reason": "Required evidence restored.",
                    }
                ),
                backend=backend,
            )
        return ModelBackendResult(text=concise_without_required_evidence, backend=backend)

    contract = {
        "schema_id": "reader_memo_rewrite_contract_v1",
        "question": "Should the evidence be treated as decision-ready?",
        "confidence": "medium",
        "required_evidence": [
            {
                "claim": "Comparator evidence matters because studies often lack data on replacement foods and substitution options, which can change the observed outcome association.",
                "source": "Long Source Title About Comparator Evidence",
                "anchor_terms": ["comparator", "replacement", "foods", "substitution", "options"],
            }
        ],
        "required_gaps": [],
        "practical_actions": [],
        "answer_frame": {},
    }
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_final_memo_editor.run_model_backend", fake_backend)
    monkeypatch.setattr("epistemic_case_mapper.map_briefing_warning_repair.run_model_backend", fake_backend)

    result = run_full_memo_polish_editor(
        memo,
        "## Evidence Appendix\n",
        {},
        {"claims": [], "relations": []},
        contract,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        repair_candidate=lambda markdown, _scaffold, _contract: markdown,
        validate_candidate=lambda rewritten, *_args: []
        if "replacement foods and substitution options" in rewritten
        else ["rewrite dropped required evidence: comparator replacement foods"],
    )

    assert any("repairing a polished decision memo after validation produced warnings" in call for call in calls)
    assert result["report"]["status"] == "full_polish_accepted"
    assert not result["report"]["warnings"]
    assert result["report"]["full_polish_attempts"][0]["patches"] == []
    assert result["report"]["full_polish_attempts"][0]["warning_repair"]["status"] == "accepted"
    assert "**Decision question:** Should the evidence be treated as decision-ready?" in result["memo"]
    assert "**Confidence:** medium" in result["memo"]
    assert "- [Long Source Title About Comparator Evidence](https://example.test/source)" in result["memo"]
    assert "replacement foods and substitution options" in result["memo"]


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


def test_reader_memo_repair_structures_practical_sections() -> None:
    memo = """## Decision Brief

The default answer is conditional.

**Confidence:** medium

## Practical Read

However, this recommendation includes important exceptions.

## Practical Scope and Exceptions

The recommendation changes based on the following factors: Comparator effects matter. Exception groups matter.

## Evidence Trail

The structured evidence trail is in `EVIDENCE_APPENDIX.md`.
"""
    contract = {
        "confidence": "medium",
        "practical_actions": [
            "State the default as acceptable under the stated conditions; do not frame the default as beneficial",
            "Name this subgroup separately from the default case: higher-risk participants",
        ],
        "required_evidence": [
            {"claim": "Comparator evidence changes the recommendation.", "source": "Source A"},
            {"claim": "Higher-risk participants should be treated as a separate exception.", "source": "Source B"},
        ],
    }

    repaired = repair_reader_memo_rewrite_candidate(memo, {"confidence_cap": "medium"}, contract)

    practical = repaired.split("## Practical Read", 1)[1].split("## Practical Scope and Exceptions", 1)[0]
    scope = repaired.split("## Practical Scope and Exceptions", 1)[1].split("## Evidence Trail", 1)[0]
    assert not practical.strip().lower().startswith("however")
    assert "- The default practical read is acceptable" in practical
    assert "- **Comparator effects:**" in scope
    assert "- **Exception groups:**" in scope


def test_reader_memo_repair_removes_unbalanced_bold_markers() -> None:
    memo = """## Decision Brief

This guidance is conditional on the following: **People with higher risk should be handled separately.

**Confidence:** medium

## Practical Read

- Keep the decision bounded.
"""

    repaired = repair_reader_memo_rewrite_candidate(memo, {"confidence_cap": "medium"}, {"confidence": "medium"})

    assert "following: People with higher risk" in repaired
    assert repaired.count("**") % 2 == 0


def test_practical_actions_filter_low_relevance_downside_from_primary_read() -> None:
    actions = build_reader_memo_practical_actions(
        {"question": "Should the intervention be used to reduce cardiovascular disease risk?"},
        [
            {"slot": "Main support", "claim": "The intervention reduced cardiovascular disease risk."},
            {"slot": "Safety and downside risk", "claim": "The intervention was associated with increased unrelated endpoint risk."},
            {"slot": "Scope and boundary conditions", "claim": "People with higher baseline risk should be considered separately."},
        ],
    )

    joined = " ".join(actions).lower()
    assert "unrelated endpoint" not in joined
    assert "higher baseline risk" in joined


def test_whole_memo_rewrite_rejects_legacy_full_memo_payload(monkeypatch) -> None:
    memo = _long_memo()
    appendix = "## Evidence Appendix\n\nThe source supports the read."

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        return ModelBackendResult(text=json.dumps({"memo_markdown": memo.replace("awkward", "smooth")}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_final_memo_editor.run_model_backend", fake_backend)

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
    text = "The study enrolled participants WHO were free of the condition. People with a risk factor WHO should adjust. Those with a marker WHO may need caution. Those WHO do not qualify should wait."

    assert _replace_internal_reader_phrases(text) == "The study enrolled participants who were free of the condition. People with a risk factor who should adjust. Those with a marker who may need caution. Those who do not qualify should wait."


def test_internal_phrase_cleanup_repairs_conversational_second_person() -> None:
    text = "The source says you really cannot isolate one input from the larger bundle."

    assert _replace_internal_reader_phrases(text) == "The source says it is difficult to isolate one input from the larger bundle."


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
