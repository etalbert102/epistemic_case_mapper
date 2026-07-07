from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_global_plan import (
    build_global_memo_plan,
    deterministic_global_memo_plan,
    section_plan_for_title,
    validate_global_memo_plan,
)
from epistemic_case_mapper.map_briefing_section_input_compiler import compile_model_section_packet
from epistemic_case_mapper.map_briefing_section_obligations import section_main_memo_obligations
from epistemic_case_mapper.model_backends import ModelBackendResult
from tests.test_section_rewrite import _memo_package


def test_deterministic_global_memo_plan_assigns_obligations_once() -> None:
    _memo, _appendix, scaffold, _candidate_map = _memo_package()
    result = build_global_memo_plan(scaffold, backend="prompt", backend_timeout=30, backend_retries=0)

    plan = result["plan"]
    validation = result["validation"]
    assigned = [
        item
        for section in plan["section_plans"]
        for item in section.get("owned_obligation_ids", [])
    ]

    assert plan["schema_id"] == "global_memo_plan_v1"
    assert validation["status"] in {"passes", "passes_with_warnings"}
    assert len(assigned) == len(set(assigned))
    assert section_plan_for_title({"global_memo_plan": plan}, "Evidence Carrying the Conclusion")


def test_global_memo_plan_repairs_duplicate_and_missing_assignments() -> None:
    _memo, _appendix, scaffold, _candidate_map = _memo_package()
    fallback = deterministic_global_memo_plan(scaffold, [], status="test")
    fallback["section_plans"][0]["owned_obligation_ids"] = ["unknown"]

    validation = validate_global_memo_plan(fallback, [])

    assert validation["status"] == "passes_with_warnings"
    assert validation["issues"][0]["issue_type"] == "unknown_obligation_id"


def test_global_memo_plan_falls_back_on_malformed_model_output(monkeypatch) -> None:
    _memo, _appendix, scaffold, _candidate_map = _memo_package()

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None):
        return ModelBackendResult(text="not json", backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_global_plan.run_model_backend", fake_backend)

    result = build_global_memo_plan(scaffold, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["plan"]["status"] == "deterministic_parse_fallback"
    assert result["validation"]["status"] in {"passes", "passes_with_warnings"}


def test_section_packet_includes_only_current_global_section_plan() -> None:
    _memo, _appendix, scaffold, _candidate_map = _memo_package()
    plan_result = build_global_memo_plan(scaffold, backend="prompt", backend_timeout=30, backend_retries=0)
    scaffold["global_memo_plan"] = plan_result["plan"]
    contract = {
        "_section_synthesis_scaffold": scaffold,
        "heading": "Why This Read",
        "section_synthesis_packet": {},
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
        "required_main_memo_obligations": [],
    }

    packet = compile_model_section_packet("Why This Read", contract)

    assert packet["global_section_plan"]["thesis"]
    assert packet["global_section_plan"]["target_words"]
    assert "Evidence Carrying" not in json.dumps(packet["global_section_plan"])


def test_section_packet_filters_global_plan_ids_to_actual_section_obligations() -> None:
    plan = {
        "section_plans": [
            {
                "section": "Practical Read",
                "thesis": "State the practical read.",
                "target_words": 120,
                "owned_obligation_ids": ["quantity_card_01", "scope_boundary_01"],
            }
        ]
    }
    contract = {
        "_section_synthesis_scaffold": {"global_memo_plan": plan},
        "heading": "Practical Read",
        "section_synthesis_packet": {},
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
        "required_main_memo_obligations": [
            {"obligation_id": "scope_boundary_01", "category": "scope_boundary", "statement": "Scope matters."}
        ],
    }

    packet = compile_model_section_packet("Practical Read", contract)

    assert packet["global_section_plan"]["owned_obligation_ids"] == ["scope_boundary_01"]


def test_section_packet_excludes_quantities_not_owned_by_section() -> None:
    contract = {
        "heading": "Practical Read",
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
        "required_main_memo_obligations": [
            {"obligation_id": "scope_boundary_01", "category": "scope_boundary", "statement": "Scope matters."}
        ],
        "section_synthesis_packet": {
            "quantitative_anchors": [
                {
                    "key_quantities": ["RR 0.98", "95% CI 0.93 to 1.03"],
                    "interpretation_hint": "Outcome estimate from another section.",
                    "source": "Outcome Meta Analysis",
                }
            ]
        },
    }

    packet = compile_model_section_packet("Practical Read", contract)

    assert "must_include_quantities" not in packet


def test_section_packet_keeps_section_owned_quantitative_obligations() -> None:
    contract = {
        "heading": "Evidence Carrying the Conclusion",
        "required_evidence": [
            {
                "slot": "Hard outcome support",
                "claim": "The pooled estimate was RR 0.98 with 95% CI 0.93 to 1.03.",
                "source": "Outcome Meta Analysis",
                "anchor_terms": ["pooled", "estimate", "RR", "0.98"],
            }
        ],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
        "required_main_memo_obligations": [
            {
                "obligation_id": "quantitative_anchor_01",
                "category": "quantitative_anchor",
                "statement": "The pooled estimate was RR 0.98 with 95% CI 0.93 to 1.03.",
                "search_terms": ["RR 0.98", "95% CI 0.93 to 1.03"],
            }
        ],
        "section_synthesis_packet": {
            "quantitative_anchors": [
                {
                    "key_quantities": ["RR 0.98", "95% CI 0.93 to 1.03"],
                    "interpretation_hint": "The pooled estimate included the null.",
                    "source": "Outcome Meta Analysis",
                }
            ]
        },
    }

    packet = compile_model_section_packet("Evidence Carrying the Conclusion", contract)

    assert packet["must_include_quantities"][0]["obligation_id"] == "quantitative_anchor_01"
    assert packet["must_include_quantities"][0]["key_terms"][0] == "RR 0.98"


def test_section_contract_intersects_global_plan_with_section_role() -> None:
    full_contract = {
        "_section_synthesis_scaffold": {
            "global_memo_plan": {
                "section_plans": [
                    {
                        "section": "Practical Read",
                        "owned_obligation_ids": ["quantitative_anchor_01"],
                    }
                ]
            }
        },
        "_main_memo_obligation_plan": [
            {
                "obligation_id": "quantitative_anchor_01",
                "category": "quantitative_anchor",
                "stage_owner": "decision_synthesis",
                "priority": 90,
                "statement": "The pooled estimate was RR 0.98.",
                "search_terms": ["RR 0.98"],
            }
        ],
    }

    obligations = section_main_memo_obligations("Practical Read", full_contract)

    assert obligations == []


def test_model_section_packet_keeps_plan_thesis_that_can_add_section_value() -> None:
    shared_claim = "Individuals with a borderline LDL-c/HDL-c ratio should limit egg consumption."
    contract = {
        "_section_synthesis_scaffold": {
            "global_memo_plan": {
                "section_plans": [
                    {
                        "section": "Practical Scope and Exceptions",
                        "thesis": "The section should foreground borderline LDL-c/HDL-c ratios.",
                        "transition_goal": "Explain why borderline LDL-c/HDL-c ratios change the practical answer.",
                    }
                ]
            }
        },
        "heading": "Practical Scope and Exceptions",
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [
            {
                "slot": "Mechanism and surrogate evidence",
                "claim": shared_claim,
                "reference_policy": {
                    "owner_section": "Evidence Carrying the Conclusion",
                    "reference_style": "do_not_repeat",
                },
            }
        ],
        "required_main_memo_obligations": [],
        "section_synthesis_packet": {},
    }

    packet = compile_model_section_packet("Practical Scope and Exceptions", contract)
    serialized = json.dumps(packet)

    assert "LDL" in serialized
    assert "borderline" in serialized


def test_model_facing_prompt_drops_practical_actions_owned_by_other_sections() -> None:
    from epistemic_case_mapper.map_briefing_section_prompt_contract import model_facing_section_contract

    owned_elsewhere = {
        "slot": "High-risk subgroup",
        "claim": "Short-term randomized interventions indicate that higher egg consumption does not negatively affect cardiovascular disease risk factors in people with diabetes.",
        "anchor_terms": ["short-term", "randomized", "interventions", "diabetes"],
        "reference_policy": {
            "owner_section": "Practical Scope and Exceptions",
            "reference_style": "do_not_repeat",
        },
    }
    contract = {
        "heading": "Practical Read",
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [owned_elsewhere],
        "required_main_memo_obligations": [],
        "required_gaps": [],
        "required_cruxes": [],
        "practical_actions": [
            owned_elsewhere["claim"],
            "Use one egg per day as the practical exposure boundary.",
        ],
        "section_synthesis_packet": {},
    }

    model_contract = model_facing_section_contract(contract)
    actions = model_contract["validation_obligations"]["practical_actions"]

    assert actions == ["Use one egg per day as the practical exposure boundary."]
