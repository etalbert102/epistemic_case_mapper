from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import run_memo_ready_presentation_normalization


def test_presentation_preserves_single_citation_when_role_alignment_is_uncertain() -> None:
    packet = {
        "decision_question": "Should advice change?",
        "source_trail": [
            {"source_id": "context_2020", "source_label": "Context Guidance 2020"},
            {"source_id": "boundary_2019", "source_label": "Boundary Cohort 2019"},
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["context_2020"],
                    "main_use": "contextualizes_answer",
                    "why_weight_this_way": "Use for decision context.",
                },
                {
                    "source_ids": ["boundary_2019"],
                    "main_use": "bounds_answer",
                    "why_weight_this_way": "Use for residual-risk boundaries.",
                },
            ]
        },
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "To contextualize the answer, the intervention sits inside broader guidance [context_2020] "
        "and the risk is explained as background [boundary_2019]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)
    body = result["memo"].split("\n## How to Weight the Evidence", 1)[0]

    assert "[Context 2020]" in body
    assert "[Boundary 2019]" in body
    assert "aligned_inline_citations" not in result["report"]["changes"]


def test_presentation_keeps_clause_separated_support_and_calibration_citations() -> None:
    packet = {
        "decision_question": "Should advice change?",
        "source_trail": [
            {"source_id": "support_a_2020", "source_label": "Support Study A 2020"},
            {"source_id": "support_b_2023", "source_label": "Support Study B 2023"},
            {"source_id": "calibration_2020", "source_label": "Calibration Trial 2020"},
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {"source_ids": ["support_a_2020"], "main_use": "drives_answer"},
                {"source_ids": ["support_b_2023"], "main_use": "drives_answer"},
                {"source_ids": ["calibration_2020"], "main_use": "calibrates_magnitude"},
            ]
        },
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "The evidence supports a moderate threshold [support_a_2020, support_b_2023] "
        "while identifying a ratio signal of 0.14 [calibration_2020]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)
    body = result["memo"].split("\n## How to Weight the Evidence", 1)[0]

    assert "[A 2020]" in body
    assert "[B 2023]" in body
    assert "[Calibration 2020]" in body
    assert "aligned_inline_citations" not in result["report"]["changes"]


def test_presentation_removes_mismatched_source_from_mixed_citation_group() -> None:
    packet = {
        "decision_question": "Should advice change?",
        "source_trail": [
            {"source_id": "support_2025", "source_label": "Support Study 2025"},
            {"source_id": "boundary_2025", "source_label": "Boundary Study 2025"},
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {"source_ids": ["support_2025"], "main_use": "drives_answer"},
                {"source_ids": ["boundary_2025"], "main_use": "bounds_answer"},
            ]
        },
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nModerate use was not associated with increased risk [support_2025, boundary_2025]."

    result = run_memo_ready_presentation_normalization(memo, packet)
    body = result["memo"].split("\n## How to Weight the Evidence", 1)[0]

    assert "[Support 2025]" in body
    assert "[Boundary 2025]" not in body
    assert "aligned_inline_citations" in result["report"]["changes"]


def test_presentation_preserves_quantity_citation_when_role_filter_is_uncertain() -> None:
    packet = {
        "decision_question": "Should advice change?",
        "source_trail": [{"source_id": "li_2020", "source_label": "Li et al. 2020"}],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {"source_ids": ["li_2020"], "main_use": "calibrates_magnitude"}
            ]
        },
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "The subgroup consuming 2 eggs per day had a higher LDL-c/HDL-c ratio "
        "(MD = 0.13; 95% CI: 0.01 to 0.26; I2 = 13%) [li_2020]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)
    body = result["memo"].split("\n## How to Weight the Evidence", 1)[0]

    assert "MD = 0.13" in body
    assert "[Li 2020]" in body


def test_presentation_prefers_calibration_source_for_quantitative_clause() -> None:
    packet = {
        "decision_question": "Should advice change?",
        "source_trail": [
            {"source_id": "li_2020", "source_label": "Li et al. 2020"},
            {"source_id": "support_2020", "source_label": "Support Study 2020"},
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {"source_ids": ["li_2020"], "main_use": "calibrates_magnitude"},
                {"source_ids": ["support_2020"], "main_use": "drives_answer"},
            ]
        },
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Higher quantities correlate with elevated ratios in healthy subjects "
        "(MD = 0.14; 95% CI: 0.05 to 0.22) [li_2020, support_2020]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)
    body = result["memo"].split("\n## How to Weight the Evidence", 1)[0]

    assert "[Li 2020]" in body
    assert "[Support 2020]" not in body
    assert "aligned_inline_citations" in result["report"]["changes"]
