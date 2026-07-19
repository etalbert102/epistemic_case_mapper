from epistemic_case_mapper.pipeline.briefing.map_briefing_synthesis_logic import (
    repair_section_synthesis_logic,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_section_synthesis import (
    _normalize_relative_risk_surface,
)


def test_synthesis_logic_does_not_repeat_exposure_reconciliation_in_support_section() -> None:
    repaired = repair_section_synthesis_logic(
        "## Why This Is the Best Current Read\n\nSupported prose.",
        section_id="answer_evidence",
        contracts=[],
        packet={"synthesis_constraints": {"study_specific_exposure_surfaces": ["<1/day", ">4/week"]}},
    )

    assert "reported exposure ranges" not in repaired.lower()


def test_synthesis_logic_adds_required_evidence_hierarchy_thesis() -> None:
    packet = {
        "synthesis_constraints": {
            "required_decision_effect_sentence": (
                "Because the support is observational, it supports the bounded default but not a stronger conclusion."
            )
        }
    }

    repaired = repair_section_synthesis_logic(
        "## Why This Is the Best Current Read\n\nAn association was reported {E:e1}.",
        section_id="answer_evidence",
        contracts=[],
        packet=packet,
    )

    assert "Because the support is observational" in repaired


def test_relative_risk_surface_labels_hazard_ratio_and_interval() -> None:
    repaired = _normalize_relative_risk_surface(
        "Exposure was associated with a 1.19 (1.16–1.22) higher risk of the outcome."
    )

    assert repaired == "Exposure was associated with higher risk (HR 1.19; 95% CI 1.16–1.22) of the outcome."
