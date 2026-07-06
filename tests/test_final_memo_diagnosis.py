from __future__ import annotations

from epistemic_case_mapper.map_briefing_final_memo_diagnosis import (
    build_memo_final_diagnosis,
    build_memo_protected_spans,
    diagnosis_improved,
)


def test_protected_spans_include_question_headings_confidence_sources_and_quantities() -> None:
    memo = """## Decision Brief

Decision question: Should the option be used?

Default answer is cautious at 10 mg per day (Source A).

**Confidence:** medium

## Sources

- Source A: Trial report.
"""

    spans = build_memo_protected_spans(memo, {"question": "Should the option be used?"})
    kinds = {span["kind"] for span in spans["spans"]}
    texts = [span["text"] for span in spans["spans"]]

    assert "section_heading" in kinds
    assert "decision_question" in kinds
    assert "confidence_line" in kinds
    assert "sources_section" in kinds
    assert "quantity" in kinds
    assert "source_label" in kinds
    assert "Should the option be used?" in texts


def test_final_memo_diagnosis_separates_coherence_and_prose_issues() -> None:
    repeated = "This caveat is conditional on missing implementation evidence."
    memo = f"""## Decision Brief

It depends on how the option is implemented.

**Confidence:** medium

## Practical Read

However, the reader should keep the recommendation bounded because the map-backed read is incomplete and this sentence is intentionally long enough to trigger the readability detector for a prose issue in this final memo.

{repeated}

## Limits of the Current Map

fail: missing_source_claim_coverage - No accepted claim from required source source_without_clean_claim. This machine-style status should be rewritten for readers.

{repeated}

{repeated}
"""

    diagnosis = build_memo_final_diagnosis(memo, {"question": "Should the option be used?"})

    coherence_kinds = {issue["kind"] for issue in diagnosis["coherence"]["issues"]}
    prose_kinds = {issue["kind"] for issue in diagnosis["prose"]["issues"]}
    assert "decision_question_missing" in coherence_kinds
    assert "weak_opening_answer" in coherence_kinds
    assert "repeated_sentences" in coherence_kinds
    assert "repeated_caveat_terms" in coherence_kinds
    assert "awkward_section_openings" in prose_kinds
    assert "long_sentences" in prose_kinds
    assert "internal_process_language" in prose_kinds
    assert "diagnostic_leakage" in prose_kinds


def test_diagnosis_improved_uses_pass_specific_metrics() -> None:
    before = {
        "metrics": {
            "repeated_sentence_count": 2,
            "repeated_caveat_term_count": 1,
            "long_sentence_count": 3,
            "internal_phrase_count": 1,
            "diagnostic_leakage_count": 1,
            "raw_status_flag_count": 1,
            "dense_paragraph_count": 1,
        }
    }
    after_coherence = {
        "metrics": {
            "repeated_sentence_count": 1,
            "repeated_caveat_term_count": 1,
            "long_sentence_count": 3,
            "internal_phrase_count": 1,
            "diagnostic_leakage_count": 1,
            "raw_status_flag_count": 1,
            "dense_paragraph_count": 1,
        }
    }
    after_prose = {
        "metrics": {
            "repeated_sentence_count": 2,
            "repeated_caveat_term_count": 1,
            "long_sentence_count": 2,
            "internal_phrase_count": 1,
            "diagnostic_leakage_count": 1,
            "raw_status_flag_count": 0,
            "dense_paragraph_count": 1,
        }
    }

    assert diagnosis_improved(before, after_coherence, pass_name="coherence")
    assert not diagnosis_improved(before, after_coherence, pass_name="prose")
    assert diagnosis_improved(before, after_prose, pass_name="prose")


def test_final_memo_diagnosis_flags_dense_reader_paragraphs() -> None:
    dense = " ".join(["This paragraph preserves one local idea but is too dense for reader-facing prose"] * 7)
    memo = f"""## Decision Brief

Answer directly.

**Confidence:** medium

## Evidence Carrying the Conclusion

{dense}
"""

    diagnosis = build_memo_final_diagnosis(memo, {"question": ""})

    prose_kinds = {issue["kind"] for issue in diagnosis["prose"]["issues"]}
    assert "dense_paragraphs" in prose_kinds
    assert diagnosis["metrics"]["dense_paragraph_count"] == 1


def test_final_memo_diagnosis_flags_map_process_opening_language() -> None:
    memo = """## Decision Brief

The current map supports a neutral or low concern under stated conditions read.

**Confidence:** low
"""

    diagnosis = build_memo_final_diagnosis(memo, {"question": ""})

    coherence_kinds = {issue["kind"] for issue in diagnosis["coherence"]["issues"]}
    assert "weak_opening_answer" in coherence_kinds
