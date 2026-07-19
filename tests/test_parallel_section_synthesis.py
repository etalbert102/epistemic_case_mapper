from __future__ import annotations

import re

import pytest

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_writer_packet import (
    build_decision_writer_packet_bundle,
    decision_writer_packet_to_memo_ready_packet,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import run_memo_ready_packet_synthesis
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_prompt import build_memo_ready_section_synthesis_plan, build_memo_ready_section_synthesis_prompt
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_section_synthesis import (
    _repair_near_miss_source_ids,
    _repair_section_synthesis_logic,
    _section_has_blocking_failure,
    _section_synthesis_logic_issues,
    _unknown_section_source_ids,
    run_parallel_memo_ready_section_generation,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_evidence_anchoring import (
    build_evidence_tagged_section_prompt,
    build_evidence_expression_contracts,
    build_section_local_evidence_jobs,
    render_evidence_tagged_memo,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_prompt import _quantity_collision_warnings
from epistemic_case_mapper.model_backends import ModelBackendResult

from test_decision_briefing_packet import _scaffold
from test_decision_writer_packet import _global_model, _ledger


def test_synthesis_logic_rejects_unreconciled_opposing_signals_and_thresholds() -> None:
    packet = {
        "synthesis_constraints": {
            "opposing_signals_require_reconciliation": True,
            "study_specific_exposure_surfaces": ["<1/day", ">4/week"],
        }
    }
    markdown = (
        "## What Could Change or Bound the Answer\n\n"
        "One study found lower risk; however, another found higher risk at high-consumption thresholds."
    )

    issues = _section_synthesis_logic_issues(
        markdown,
        section_id="counterweights",
        contracts=[],
        packet=packet,
    )

    assert "missing_conflict_reconciliation" in issues
    assert "unreconciled_dose_thresholds" in issues


def test_synthesis_logic_accepts_explicit_study_specific_reconciliation() -> None:
    packet = {
        "synthesis_constraints": {
            "opposing_signals_require_reconciliation": True,
            "study_specific_exposure_surfaces": ["<1/day", ">4/week"],
        }
    }
    markdown = (
        "## What Could Change or Bound the Answer\n\n"
        "The findings differ by population and endpoint, and the study-specific exposure ranges are not directly comparable; "
        "they do not establish one consumption threshold."
    )

    issues = _section_synthesis_logic_issues(
        markdown,
        section_id="counterweights",
        contracts=[],
        packet=packet,
    )

    assert issues == []


def test_synthesis_logic_rejects_duration_missing_from_source_excerpt() -> None:
    issues = _section_synthesis_logic_issues(
        "## Limits\n\nThe intervention increased the marker over longer periods {E:e1}.",
        section_id="counterweights",
        contracts=[
            {
                "evidence_id": "e1",
                "source_evidence": [
                    {"source_id": "s1", "excerpts": ["The intervention group had a higher marker concentration."]}
                ],
            }
        ],
        packet={},
    )

    assert issues == ["unsupported_temporal_qualifier:e1:long_term"]


def test_synthesis_logic_repair_removes_unsupported_rationale_and_reconciles_ranges() -> None:
    packet = {
        "synthesis_constraints": {
            "opposing_signals_require_reconciliation": True,
            "study_specific_exposure_surfaces": ["<1/day", ">4/week"],
            "surrogate_or_mechanistic_evidence_ids": ["e1"],
        }
    }
    markdown = (
        "## What Could Change or Bound the Answer\n\n"
        "The broad answer is neutral because a single dose did not change a marker. "
        "Other evidence identifies high-dose thresholds and a higher marker over longer periods {E:e1}."
    )
    contracts = [
        {
            "evidence_id": "e1",
            "source_evidence": [{"source_id": "s1", "excerpts": ["The intervention group had a higher marker."]}],
        }
    ]

    repaired = _repair_section_synthesis_logic(
        markdown,
        section_id="counterweights",
        contracts=contracts,
        packet=packet,
    )

    assert "because a single dose" not in repaired
    assert "over longer periods" not in repaired
    assert "study-specific higher-exposure findings" in repaired
    assert "differ by population, endpoint, and study design" in repaired
    assert "not directly comparable" in repaired
    assert _section_synthesis_logic_issues(
        repaired,
        section_id="counterweights",
        contracts=contracts,
        packet=packet,
    ) == []


def test_synthesis_logic_failures_are_blocking_after_retries() -> None:
    assert _section_has_blocking_failure(
        {
            "accepted": False,
            "markdown": "## Limits\n\nUnreconciled prose.",
            "issues": ["missing_conflict_reconciliation"],
        }
    ) is True


def test_live_memo_ready_synthesis_runs_sections_in_parallel_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    calls: list[str] = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        assert kwargs["json_mode"] is False
        assert kwargs["num_predict"] == 4096
        heading = _heading_from_section_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        if ids:
            tag = " ".join(f"{{E:{evidence_id}}}" for evidence_id in ids)
        else:
            tag = ""
        if heading == "Why This Is the Best Current Read":
            body = f"Outcome Study reports that Option A reduced flood losses by 25% in comparable river cities {tag}."
        elif heading == "How to Weight the Evidence":
            body = "Weight Outcome Study most for the main read, while using Counter Study and Boundary Report to bound the answer [s1, s2, s3]."
        elif heading == "What Could Change or Bound the Answer":
            body = f"Counter Study and Boundary Report bound the 25% benefit because maintenance cuts and a narrower setting could erase it {tag}."
        else:
            body = f"Use Option A where the 25% loss-reduction evidence applies and maintenance protection is credible {tag}."
        return ModelBackendResult(text=f"## {heading}\n\n{body}\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert len(calls) == 4
    assert all("markdown analyst notes" in prompt for prompt in calls)
    assert all("### Section job" in prompt for prompt in calls)
    assert all("### Decision argument for this section" in prompt for prompt in calls)
    assert all("Use the Decision argument for this section as the governing structure" in prompt for prompt in calls)
    assert all("### Suggested paragraph flow" in prompt for prompt in calls)
    assert all("Current read:" in prompt for prompt in calls)
    assert all("Use parentheses" in prompt for prompt in calls)
    assert all("Reader question:" in prompt for prompt in calls)
    assert all("### Calibration limits" in prompt for prompt in calls)
    assert all("### Source language and use limits" in prompt for prompt in calls)
    assert any("### Reader-facing judgments to surface" in prompt for prompt in calls)
    assert any("### Required evidence points" in prompt for prompt in calls)
    assert any("### Source weighting notes" in prompt for prompt in calls)
    assert any("required contracts still keep their own tags and listed quantities" in prompt for prompt in calls)
    assert any("Translate the settled answer and its limits into what guidance should say" in prompt for prompt in calls)
    assert all("section_packet:" not in prompt for prompt in calls)
    assert any("### Evidence expression contracts" in prompt for prompt in calls)
    assert result["report"]["synthesis_mode"] == "unified_section_synthesis"
    assert result["report"]["section_count"] == 4
    assert result["report"]["num_predict"] == 4096
    assert all(row["accepted"] for row in result["report"]["section_reports"])
    assert all(row["num_predict"] == 4096 for row in result["report"]["section_reports"])
    assert result["report"]["reader_judgment_surface_report"]["schema_id"] == "reader_judgment_surface_report_v1"
    assert result["report"]["decision_usefulness_surface_report"]["schema_id"] == "decision_usefulness_surface_report_v1"
    assert result["report"]["analyst_judgment_utilization_report"]["schema_id"] == "analyst_judgment_utilization_report_v1"
    assert result["report"]["reader_judgment_surface_report"]["judgment_count"] >= 1
    assert result["report"]["priority_quantity_contract_coverage_report"]["schema_id"] == "priority_quantity_contract_coverage_report_v1"
    assert "## How to Weight the Evidence" in result["memo"]
    assert "## Why This Is the Best Current Read" in result["memo"]
    assert "## What Could Change or Bound the Answer" in result["memo"]
    assert "## Practical Implication" in result["memo"]
    assert "25%" in result["memo"]


def test_section_synthesis_retries_when_required_quantity_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECM_MODEL_STAGE_ATTEMPTS", "2")
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "must_use": True,
                "obligation_level": "must_include",
                "reader_claim": "Option A reduced losses by 25%.",
                "role": "strongest_support",
                "quantities": [{"value": "25%", "interpretation": "loss reduction"}],
                "source_ids": ["s1"],
            }
        ],
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {"evidence_item_ids": ["e1"], "statement": "Option A reduced losses.", "source_ids": ["s1"]}
            ]
        },
    }
    section_plan = {
        "title": "Decision Memo",
        "decision_question": "Should option A be adopted?",
        "bottom_line": "Adopt option A in scope.",
        "known_source_ids": ["s1"],
        "known_source_aliases": {},
        "sections": [
            {
                "section_id": "answer_evidence",
                "heading": "Why This Is the Best Current Read",
                "packet": {
                    "section_id": "answer_evidence",
                    "heading": "Why This Is the Best Current Read",
                    "section_job": "Explain the evidence.",
                    "evidence_context": [{"item_id": "e1"}],
                },
            }
        ],
    }
    calls: list[str] = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        if len(calls) == 1:
            return ModelBackendResult(
                text="## Why This Is the Best Current Read\n\nThe study supports option A {E:e1}.\n",
                backend="fake",
            )
        assert "missing_required_quantities" in prompt
        return ModelBackendResult(
            text="## Why This Is the Best Current Read\n\nThe study reports a 25% loss reduction for option A {E:e1}.\n",
            backend="fake",
        )

    result = run_parallel_memo_ready_section_generation(
        section_plan,
        memo_ready_packet=packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        whole_prompt="whole memo reference",
        run_model=fake_backend,
    )

    assert len(calls) == 2
    assert result["report"]["status"] == "accepted"
    assert result["report"]["section_reports"][0]["validation_attempts"] == 2
    assert "25% loss reduction" in result["memo"]


def test_counterweight_prompt_groups_section_local_evidence_jobs() -> None:
    section_packet = {
        "section_id": "counterweights",
        "heading": "What Could Change or Bound the Answer",
        "section_job": "Explain limiting evidence.",
        "decision_argument_section": {
            "section_id": "counterweights",
            "section_job": "Explain what bounds the answer.",
            "reader_question": "What could make the answer too broad?",
            "why_this_section_matters": "It ties limits to the decision.",
            "owned_moves": [
                {
                    "move_id": "counterweights",
                    "move_type": "counterweight_disposition",
                    "point": "Higher dose, subgroup, and comparator evidence bound the answer.",
                    "writing_job": "Explain the boundary without rebuilding the affirmative case.",
                    "evidence_item_ids": ["dose_item", "subgroup_item", "comparator_item"],
                }
            ],
        },
        "evidence_context": [
            {"item_id": "dose_item", "claim": "Higher dose evidence changes the endpoint boundary."},
            {"item_id": "subgroup_item", "claim": "A subgroup has a different baseline risk."},
            {"item_id": "comparator_item", "claim": "The comparator matters for interpretation."},
        ],
        "analyst_argument_moves": [
            {
                "step_id": "bound_answer",
                "writing_goal": "Explain why the counterweight bounds rather than overturns the answer.",
                "required_points": ["Separate dose, subgroup, and comparator boundaries."],
                "evidence_item_ids": ["dose_item", "subgroup_item", "comparator_item"],
            }
        ],
        "decision_usefulness_moves": {
            "tradeoffs": [
                {
                    "tradeoff": "Population-level answer versus subgroup caution.",
                    "choose_a_if": "The reader is deciding for generally healthy adults.",
                    "choose_b_if": "The reader is deciding for a high-risk subgroup.",
                    "evidence_item_ids": ["subgroup_item"],
                }
            ]
        },
    }
    contracts = [
        {
            "evidence_id": "dose_item",
            "claim": "Higher intake changes the biomarker endpoint.",
            "role": "scope_boundary",
            "required": True,
            "source_ids": ["s1"],
            "required_quantity_atoms": [{"value": "1.25", "interpretation": "effect estimate"}],
        },
        {
            "evidence_id": "subgroup_item",
            "claim": "Participants with a baseline condition have a different risk profile.",
            "role": "scope_boundary",
            "required": True,
            "source_ids": ["s2"],
        },
        {
            "evidence_id": "comparator_item",
            "claim": "The result depends on the comparator and background context.",
            "role": "scope_boundary",
            "required": True,
            "source_ids": ["s3"],
        },
    ]

    jobs = build_section_local_evidence_jobs(section_packet, contracts)
    prompt = build_evidence_tagged_section_prompt(section_packet, known_source_ids=["s1", "s2", "s3"], contracts=contracts)

    assert jobs[0]["job_id"] == "counterweights"
    assert jobs[0]["argument_move_type"] == "counterweight_disposition"
    assert jobs[0]["allowed_evidence_ids"] == ["dose_item", "subgroup_item", "comparator_item"]
    assert "### Section-local evidence jobs" in prompt
    assert "### Analyst argument moves" in prompt
    assert "Explain why the counterweight bounds rather than overturns the answer." in prompt
    assert "### Decision-usefulness moves" in prompt
    assert "Population-level answer versus subgroup caution." in prompt
    assert "### Decision argument for this section" in prompt
    assert '"allowed_evidence_ids"' in prompt
    assert '"required_quantities_by_evidence_id"' in prompt
    assert '"dose_item": [' in prompt
    assert '"1.25"' in prompt
    assert "attach tags from each job's allowed evidence IDs" in prompt


def test_section_synthesis_retry_restates_missing_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECM_MODEL_STAGE_ATTEMPTS", "2")
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "must_use": True,
                "obligation_level": "must_include",
                "reader_claim": "Comparator evidence changes the boundary.",
                "role": "strongest_counterweight",
                "quantities": [{"value": "1.15", "interpretation": "hazard ratio"}],
                "source_ids": ["s1"],
            }
        ],
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {"evidence_item_ids": ["e1"], "statement": "Comparator evidence changes the boundary.", "source_ids": ["s1"]}
            ]
        },
    }
    section_plan = {
        "title": "Decision Memo",
        "decision_question": "Should option A be adopted?",
        "bottom_line": "Adopt option A only in scope.",
        "known_source_ids": ["s1"],
        "known_source_aliases": {},
        "sections": [
            {
                "section_id": "counterweights",
                "heading": "What Could Change or Bound the Answer",
                "packet": {
                    "section_id": "counterweights",
                    "heading": "What Could Change or Bound the Answer",
                    "section_job": "Explain limiting evidence.",
                    "evidence_context": [{"item_id": "e1"}],
                },
            }
        ],
    }
    calls: list[str] = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        if len(calls) == 1:
            return ModelBackendResult(
                text="## What Could Change or Bound the Answer\n\nThe boundary depends on comparator evidence.\n",
                backend="fake",
            )
        assert "missing_required_contracts" in prompt
        assert "Comparator evidence changes the boundary" in prompt
        return ModelBackendResult(
            text="## What Could Change or Bound the Answer\n\nComparator evidence reports a hazard ratio of 1.15 and changes the boundary {E:e1}.\n",
            backend="fake",
        )

    result = run_parallel_memo_ready_section_generation(
        section_plan,
        memo_ready_packet=packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        whole_prompt="whole memo reference",
        run_model=fake_backend,
    )

    assert len(calls) == 2
    assert result["report"]["status"] == "accepted"
    assert "1.15" in result["memo"]


def test_section_packets_are_section_local_and_practical_gets_evidence() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    packet["canonical_decision_writer_packet"]["decision_usefulness_packet"] = {
        "schema_id": "decision_usefulness_packet_v1",
        "recommended_stance": {
            "stance": "Adopt option A where monitoring can be maintained.",
            "confidence": "medium",
            "scope": "Sites matching the evidence base.",
        },
        "tradeoffs": [{"tradeoff": "Protection versus implementation burden."}],
        "monitoring_triggers": [{"trigger": "New implementation failure evidence."}],
    }
    inventory = packet["canonical_decision_writer_packet"]["organized_evidence_inventory"]["lanes"]
    inventory.setdefault("interpretive_context", []).append(
        {
            "item_id": "practical_context",
            "role": "mechanism_or_explanation",
            "answer_relation": "contextualizes_answer",
            "claim": "Monitoring feasibility determines how the answer should be applied.",
            "source_ids": ["s1"],
            "decision_relevance": "Translates the answer into a concrete operating boundary.",
        }
    )

    plan = build_memo_ready_section_synthesis_plan(packet)
    sections = {row["section_id"]: row["packet"] for row in plan["sections"]}
    practical = sections["practical_implication"]

    assert practical["section_focus"]["use_current_read_as"] == "background_only"
    assert practical["section_focus"]["reader_question"] == "Given the answer and its limits, what should the decision-maker do next?"
    assert practical["section_focus"]["prose_lead"] == "Open with the usable stance inside scope, then name the condition that changes application."
    assert practical["section_focus"]["paragraph_shape"]
    assert "The decision-maker should" in practical["section_focus"]["stock_phrases_to_replace"]
    assert practical["source_bound_evidence_atoms"]
    assert all("excluded_quantity_tuples" not in atom for atom in practical["source_bound_evidence_atoms"])
    assert practical["evidence_context"]
    assert practical["source_weighting"]
    assert "balanced_answer_frame" not in practical["top_context"]
    assert "bluf_contract" not in practical["top_context"]
    assert "current_read_reference" not in practical["top_context"]
    assert "confidence" not in practical["top_context"]
    assert "decision_question" in practical["top_context"]
    assert practical["top_context"]["decision_action_contract"]["default_action"] == "Adopt option A where monitoring can be maintained."
    assert practical["top_context"]["decision_action_contract"]["scope"] == "Sites matching the evidence base."
    assert practical["top_context"]["decision_action_contract"]["tradeoff"] == "Protection versus implementation burden."
    assert practical["top_context"]["decision_action_contract"]["update_trigger"] == "New implementation failure evidence."
    assert practical["section_job"] == "Translate the settled answer and its limits into what guidance should say; keep evidence basis short."
    assert all(
        atom.get("section_specific_job") == "Use this evidence only to translate the answer into advice, exceptions, monitoring, or wording; keep the evidence recap brief."
        for atom in practical["source_bound_evidence_atoms"]
    )
    assert all(
        row.get("section_specific_job") == "Use this evidence only to translate the answer into advice, exceptions, monitoring, or wording; keep the evidence recap brief."
        for row in practical["evidence_context"]
    )
    assert practical["section_role_contract"]["do"][0] == "state the practical recommendation in ordinary decision language"

    source_weighting = sections["source_weighting"]
    assert source_weighting["section_job"] == "Explain the source hierarchy and source-use limits only; do not reargue the answer or preview practical advice."
    assert "current_read_reference" not in source_weighting["top_context"]
    assert "confidence" not in source_weighting["top_context"]
    assert "main_support" not in source_weighting["top_context"]
    assert "main_counterweight" not in source_weighting["top_context"]
    assert source_weighting["section_focus"]["paragraph_shape"][0] == "one sentence source hierarchy thesis"


def test_evidence_tag_renderer_uses_role_appropriate_citation_sources() -> None:
    packet = {
        "source_trail": [
            {"source_id": "support_source", "source_label": "Support Study"},
            {"source_id": "boundary_source", "source_label": "Boundary Study"},
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["support_source"],
                    "main_use": "drives_answer",
                    "why_weight_this_way": "Directly supports the answer.",
                },
                {
                    "source_ids": ["boundary_source"],
                    "main_use": "bounds_answer",
                    "why_weight_this_way": "Bounds the recommendation in a subgroup.",
                },
            ],
            "mandatory_retention_checklist": [],
        },
        "evidence_items": [
            {
                "item_id": "support_item",
                "role": "strongest_support",
                "reader_claim": "Option A is not associated with increased risk in the general population.",
                "source_ids": ["support_source", "boundary_source"],
            },
            {
                "item_id": "boundary_item",
                "role": "scope_boundary",
                "reader_claim": "The answer is bounded in high-risk subgroups.",
                "source_ids": ["support_source", "boundary_source"],
            },
        ],
    }

    contracts = build_evidence_expression_contracts(packet)
    by_id = {row["evidence_id"]: row for row in contracts}

    assert by_id["support_item"]["citation_source_ids"] == ["support_source"]
    assert by_id["boundary_item"]["citation_source_ids"] == ["boundary_source"]

    rendered = render_evidence_tagged_memo(
        "Support claim {E:support_item} [support_source, boundary_source]. "
        "Boundary claim [support_source, boundary_source] {E:boundary_item}.",
        contracts,
    )

    assert "Support claim [support_source]." in rendered["memo"]
    assert "Boundary claim [boundary_source]." in rendered["memo"]
    assert "Support claim [support_source, boundary_source]." not in rendered["memo"]


def test_section_prompt_renders_sparse_top_context_markdown_notes() -> None:
    prompt = build_memo_ready_section_synthesis_prompt(
        {
            "heading": "What Could Change or Bound the Answer",
            "section_job": "Handle limiting evidence and cruxes.",
            "section_role_contract": {
                "role": "bound_or_change_the_answer",
                "do": ["explain what narrows the answer"],
                "avoid": ["repeating the full affirmative case"],
            },
            "section_focus": {
                "reader_question": "What could make this answer too broad?",
                "paragraph_shape": ["main limitation", "update trigger"],
            },
            "top_context": {
                "decision_question": "Should option A be adopted?",
                "current_read_reference": "Adopt option A in the supported population.",
                "confidence": "medium",
                "must_not_overstate": ["Do not ignore the lipid ratio concerns entirely."],
                "lightweight_writer_guidance": {
                    "quantity_wording_risks": [
                        {
                            "risk": "Mixing concentration and ratio endpoints.",
                            "safe_wording": "Use mean difference in LDL-c concentration for 8.14 mg/dL and mean difference in LDL-c/HDL-c ratio for 0.14.",
                            "quantities": ["8.14 mg/dL", "0.14"],
                            "source_ids": ["s_li"],
                        }
                    ],
                    "evidence_quality_caveats": [
                        {"caveat": "Study excludes some treated populations.", "source_ids": ["s_li"]}
                    ],
                },
                "decision_usefulness": {
                    "cruxes_and_thresholds": [
                        {
                            "crux": "Metabolic condition threshold",
                            "threshold": "Type 2 diabetes or high LDL",
                            "would_change_if": "Risk subgroup evidence strengthens.",
                            "source_ids": ["s_bmj"],
                        }
                    ],
                    "monitoring_triggers": [
                        {
                            "trigger": "New longitudinal data on subgroup outcomes.",
                            "would_update": "The conditional boundary.",
                            "source_ids": ["s_bmj"],
                        }
                    ],
                },
            },
        },
        known_source_ids=["s_li", "s_bmj"],
    )

    assert "section_packet:" not in prompt
    assert "### Writing guidance, caveats, and quantity risks" in prompt
    assert "8.14 mg/dL" in prompt
    assert "0.14" in prompt
    assert "mean difference in LDL-c/HDL-c ratio" in prompt
    assert "### Decision cruxes, thresholds, and update triggers" in prompt
    assert "Metabolic condition threshold" in prompt
    assert "[s_li]" in prompt
    assert "[s_bmj]" in prompt


def test_section_prompt_prioritizes_applied_reader_guidance() -> None:
    prompt = build_memo_ready_section_synthesis_prompt(
        {
            "heading": "Why This Is the Best Current Read",
            "section_job": "Explain the affirmative case.",
            "section_role_contract": {"do": ["explain what carries the read"]},
            "section_focus": {"reader_question": "Why this read?", "paragraph_shape": ["driver", "calibration"]},
            "reader_guidance_application": {
                "section_strategy": "Use the guidance to make the affirmative case concrete.",
                "foreground": "Start with the quantity that resolves the choice.",
                "caveat_handling": "State the observational caveat once after the main evidence.",
                "repeat_control": "Do not repeat the source-weighting caveat after every claim.",
                "matched_reader_guidance": [
                    {
                        "instruction": "Frame the claim as association, not proof.",
                        "why_it_matters": "Prevents overstatement.",
                        "source_ids": ["s1"],
                    }
                ],
            },
            "top_context": {
                "decision_question": "Should option A be adopted?",
                "current_read_reference": "Adopt option A in scope.",
                "confidence": "medium",
                "lightweight_writer_guidance": {
                    "reader_guidance": [
                        {
                            "instruction": "This generic row should be suppressed when applied guidance exists.",
                            "source_ids": ["s1"],
                        }
                    ]
                },
            },
        },
        known_source_ids=["s1"],
    )

    assert "### Reader guidance applied to this section" in prompt
    assert "Start with the quantity that resolves the choice." in prompt
    assert "Frame the claim as association, not proof." in prompt
    assert "### Writing guidance, caveats, and quantity risks" not in prompt
    assert "This generic row should be suppressed" not in prompt


def test_practical_section_prompt_renders_decision_action_contract() -> None:
    prompt = build_memo_ready_section_synthesis_prompt(
        {
            "heading": "Practical Implication",
            "section_job": "Translate the answer into advice.",
            "section_role_contract": {"do": ["state the action"]},
            "top_context": {
                "decision_question": "Should option A be adopted?",
                "decision_action_contract": {
                    "default_action": "Adopt option A in matched settings.",
                    "scope": "Matched settings only.",
                    "exception_handling": "Pause when monitoring fails.",
                    "confidence": "medium",
                    "tradeoff": "Benefit versus implementation burden.",
                    "update_trigger": "New failure evidence.",
                    "what_not_to_say": ["Do not claim unconditional adoption."],
                },
            },
        },
        known_source_ids=["s1"],
    )

    assert "### Decision action contract" in prompt
    assert "Default action: Adopt option A in matched settings." in prompt
    assert "Exception handling: Pause when monitoring fails." in prompt
    assert "Do not overstate: Do not claim unconditional adoption." in prompt


def test_section_synthesis_num_predict_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    seen: list[int] = []
    monkeypatch.setenv("ECM_MEMO_READY_SECTION_NUM_PREDICT", "6144")

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        seen.append(kwargs["num_predict"])
        heading = _heading_from_section_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        tag_or_citation = f"{{E:{ids[0]}}}" if ids else "[s1]"
        return ModelBackendResult(text=f"## {heading}\n\nOutcome evidence supports the section {tag_or_citation}.\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert seen and set(seen) == {6144}
    assert result["report"]["num_predict"] == 6144


def test_quantity_collision_warnings_keep_same_surface_scopes_separate() -> None:
    warnings = _quantity_collision_warnings(
        [
            {
                "claim": "Effect is larger in one subgroup.",
                "source_ids": ["s1"],
                "quantity_tuples": [
                    {
                        "value": "1.25 (HR)",
                        "interpretation": "risk in lower baseline group",
                        "source_ids": ["s1"],
                        "applicability_scope": "participants with lower baseline values",
                    }
                ],
            },
            {
                "claim": "Effect is larger in another subgroup.",
                "source_ids": ["s2"],
                "quantity_tuples": [
                    {
                        "value": "1.25 (0.99 to 1.59)",
                        "interpretation": "relative risk in diagnosed participants",
                        "source_ids": ["s2"],
                        "applicability_scope": "people with diagnosis",
                    }
                ],
            },
        ]
    )

    assert warnings
    assert warnings[0]["quantity_surface"] == "1.25"
    assert "Keep these entries separate" in warnings[0]["instruction"]


def test_section_synthesis_preserves_belief_question_use_read_heading() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="What should an investigator believe about option A?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    plan = build_memo_ready_section_synthesis_plan(packet)
    headings = [row["heading"] for row in plan["sections"]]

    assert "How to Use This Read" in headings
    assert "Why This Is the Best current answer" not in headings


def test_live_memo_ready_section_synthesis_rejects_unknown_source_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_from_section_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        if ids:
            return ModelBackendResult(text=f"## {heading}\n\nA claim with anchored evidence {{E:{ids[0]}}}.\n", backend="fake")
        return ModelBackendResult(text=f"## {heading}\n\nA claim with a made-up source [not_a_source].\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["memo"] == ""
    assert result["report"]["status"] == "section_synthesis_failed"
    assert result["report"]["accepted"] is False
    failed = [row for row in result["report"]["section_reports"] if row["unknown_source_ids"]]
    assert len(failed) == 1
    assert failed[0]["unknown_source_ids"] == ["not_a_source"]


def test_live_memo_ready_section_synthesis_normalizes_statistical_brackets(monkeypatch: pytest.MonkeyPatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_from_section_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        tag_or_citation = " ".join(f"{{E:{evidence_id}}}" for evidence_id in ids) if ids else "[s1]"
        return ModelBackendResult(
            text=f"## {heading}\n\nOutcome evidence reports a 25% improvement with a subgroup estimate [95% CI, 1.12-1.39] {tag_or_citation}.\n",
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] in {"accepted", "accepted_with_retention_warnings", "accepted_with_evidence_tag_warnings"}
    assert "[95% CI, 1.12-1.39]" not in result["memo"]
    assert "(95% CI, 1.12-1.39)" in result["memo"]
    assert "{E:" not in result["memo"]
    assert "[Outcome Study]" in result["memo"]


def test_section_synthesis_repairs_long_near_miss_source_id_but_not_unknowns() -> None:
    known = {"aha_2019_dietary_cholesterol_pubmed"}
    markdown = "The advisory supports the read [aha_2019_itary_cholesterol_pubmed]. Unknown remains [not_a_source]."

    repaired = _repair_near_miss_source_ids(markdown, known)

    assert "[aha_2019_dietary_cholesterol_pubmed]" in repaired
    assert "[aha_2019_itary_cholesterol_pubmed]" not in repaired
    assert _unknown_section_source_ids(repaired, known) == ["not_a_source"]


def test_decision_writer_packet_section_citation_failures_are_not_marked_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )
    packet.setdefault("memo_obligations", {}).setdefault("obligations", []).append(
        {
            "obligation_id": "memo_obligation_test_unmet",
            "obligation_type": "must_address_crux",
            "required": True,
            "role": "decision_crux",
            "statement": "Name the seasonal maintenance crux before adoption.",
            "validation_mode": "claim_terms",
            "validation_terms": ["seasonal", "maintenance", "crux"],
            "evidence_item_ids": ["decision_writer_item_002"],
        }
    )

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_from_section_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        if ids and heading == "Why This Is the Best Current Read":
            tag_or_citation = "{E:decision_writer_item_001}"
        else:
            tag_or_citation = " ".join(f"{{E:{evidence_id}}}" for evidence_id in ids) if ids else "[s1]"
        return ModelBackendResult(
            text=(
                f"## {heading}\n\n"
                f"Outcome Review reports that Option A improves the main outcome by 20% improvement {tag_or_citation}."
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["contract_mode"] == "strict_writer_packet"
    assert result["report"]["synthesis_mode"] == "unified_section_synthesis"
    assert result["report"]["status"] == "section_synthesis_failed"
    assert result["report"]["accepted"] is False
    assert len(result["report"]["section_reports"]) == 4
    assert any(not row["accepted"] for row in result["report"]["section_reports"])
    assert any(
        issue.startswith("citation_claim_entailment_mismatch:")
        for row in result["report"]["section_reports"]
        for issue in row["issues"]
    )


def _heading_from_section_prompt(prompt: str) -> str:
    match = re.search(r"exactly(?: with)?: ## (.+)", prompt)
    if not match:
        match = re.search(r"Output starts exactly with: ## (.+)", prompt)
    if not match:
        match = re.search(r"Output must start exactly with: ## (.+)", prompt)
    return match.group(1).strip() if match else "Why This Is the Best Current Read"
