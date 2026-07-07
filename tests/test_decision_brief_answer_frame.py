from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_brief_last import decision_brief_last_issues
from epistemic_case_mapper.map_briefing_section_rewrite import _decision_brief_bluf_prompt
from epistemic_case_mapper.map_briefing_answer_frame import arbitrate_answer_frame


def test_decision_brief_bluf_prompt_uses_free_form_answer_frame() -> None:
    contract = {
        "question": "Should the committee change the default policy?",
        "confidence": "medium",
        "_section_synthesis_scaffold": {
            "decision_synthesis_model": {
                "bottom_line": {
                    "current_read": "The answer is conditional: keep the default unless the implementation constraint is resolved."
                }
            },
            "decision_model": {
                "default_answer": {
                    "plain_language_instruction": "State that the answer is context-dependent, then identify the default case and the conditions that change it.",
                    "why_this_frame": "Support and counterevidence are both live.",
                },
                "prose_requirements": ["Separate the default case from conditions where uncertainty dominates."],
            },
        },
    }
    body = "## Practical Read\n\nKeep the default unless the implementation constraint is resolved."
    fallback = "## Decision Brief\n\nFallback."

    prompt = _decision_brief_bluf_prompt(contract, body, fallback)

    assert "Controlling answer frame" in prompt
    assert "The answer is conditional" in prompt
    assert "classify the default answer" not in prompt
    assert "Do not force the answer into generic labels" in prompt


def test_decision_brief_rejects_favorable_upgrade_for_conditional_frame() -> None:
    contract = {
        "question": "Should the default advice change?",
        "confidence": "medium",
        "_section_synthesis_scaffold": {
            "decision_synthesis_model": {
                "bottom_line": {
                    "classification": "mixed_or_context_dependent",
                    "current_read": "Treat the current answer as conditional and separate the default case from exceptions.",
                }
            },
            "decision_model": {
                "default_answer": {
                    "classification": "mixed_or_context_dependent",
                    "plain_language_instruction": "State that the answer is context-dependent, then identify the default case and the conditions that change it.",
                    "why_this_frame": "Support and counterevidence are both live.",
                },
                "prose_requirements": ["Avoid benefit framing unless explicitly scoped."],
            },
        },
    }
    body = "## Practical Read\n\nThe current answer is conditional and depends on whether the exception applies."
    section = (
        "## Decision Brief\n\n"
        "**Decision question:** Should the default advice change?\n\n"
        "Treat the option as beneficial for the default case because the body has some favorable evidence, with exceptions handled later.\n\n"
        "**Confidence:** medium"
    )

    issues = decision_brief_last_issues(section, contract, body)

    assert "final brief upgrades the controlling answer frame into an unsupported favorable verdict" in issues


def test_decision_brief_allows_negated_benefit_language_for_conditional_frame() -> None:
    contract = {
        "question": "Should the default advice change?",
        "confidence": "medium",
        "_section_synthesis_scaffold": {
            "decision_synthesis_model": {
                "bottom_line": {
                    "classification": "mixed_or_context_dependent",
                    "current_read": "Treat the current answer as conditional and separate the default case from exceptions.",
                }
            },
            "decision_model": {
                "default_answer": {
                    "classification": "mixed_or_context_dependent",
                    "plain_language_instruction": "State that the answer is context-dependent, then identify the default case and the conditions that change it.",
                    "why_this_frame": "Support and counterevidence are both live.",
                },
            },
        },
    }
    body = "## Practical Read\n\nThe current answer is conditional and depends on whether the exception applies."
    section = (
        "## Decision Brief\n\n"
        "**Decision question:** Should the default advice change?\n\n"
        "Treat the current answer as conditional; the default case should not be framed as beneficial.\n\n"
        "**Confidence:** medium"
    )

    issues = decision_brief_last_issues(section, contract, body)

    assert "final brief upgrades the controlling answer frame into an unsupported favorable verdict" not in issues


def test_answer_frame_arbitration_separates_default_from_exception() -> None:
    result = arbitrate_answer_frame(
        {
            "decision_model": {
                "default_answer": {
                    "plain_language_instruction": "For the default case, keep the policy neutral unless a named risk condition applies.",
                    "why_this_frame": "General evidence supports the default while subgroup evidence creates exceptions.",
                },
                "main_reasons": [
                    {"proposition": "The default population evidence does not show worse outcomes."}
                ],
            }
        },
        bottom_line={
            "classification": "caution_or_harm_under_specific_conditions",
            "current_read": "Caution is warranted under the named conditions, and separate those conditions from the general case.",
            "confidence": "medium",
            "why_this_frame": "Counterevidence is strong enough to drive caution in the named conditions.",
        },
        evidence_lines=[],
        exceptions=[{"condition": "high-risk subgroup", "current_read": "the subgroup needs separate caution"}],
    )

    assert result["status"] == "reframed"
    assert result["bottom_line"]["current_read"].startswith("For the default case")
    assert "Treat the named exception separately" in result["bottom_line"]["current_read"]


def test_answer_frame_arbitration_does_not_use_counterevidence_rationale_as_default() -> None:
    result = arbitrate_answer_frame(
        {
            "decision_model": {
                "default_answer": {
                    "plain_language_instruction": "State that caution is warranted under the named conditions, and separate those conditions from the general case.",
                    "why_this_frame": "Counterevidence is strong enough to drive caution in the named conditions.",
                },
                "main_reasons": [
                    {"proposition": "Moderate use was not associated with worse outcomes in the default population."}
                ],
            }
        },
        bottom_line={
            "classification": "caution_or_harm_under_specific_conditions",
            "current_read": "State that caution is warranted under the named conditions, and separate those conditions from the general case.",
            "confidence": "medium",
            "why_this_frame": "Counterevidence is strong enough to drive caution in the named conditions.",
        },
        evidence_lines=[],
        exceptions=[{"condition": "named exception", "current_read": "higher-risk users need separate caution"}],
    )

    assert result["status"] == "reframed"
    assert result["bottom_line"]["current_read"].startswith("Moderate use was not associated")
    assert "Counterevidence is strong enough" not in result["bottom_line"]["current_read"]
