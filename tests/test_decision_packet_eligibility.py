from __future__ import annotations

from copy import deepcopy

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_packet_eligibility import question_content_terms, question_overlap_count
from test_decision_briefing_packet import _scaffold


def test_decision_packet_excludes_appendix_only_candidates_from_main_bundles() -> None:
    scaffold = _scaffold()
    scaffold["candidate_evidence_cards"]["cards"].append(
        {
            "candidate_card_id": "ec_appendix",
            "source_card_ids": ["sc_appendix"],
            "claim_ids": ["c_appendix"],
            "source_ids": ["s1"],
            "source_titles": ["Outcome Study"],
            "claim": "Appendix-only contextual detail about option A maintenance procurement history.",
            "role": "scope",
            "evidence_roles": ["scope"],
            "decision_relevance_score": 10,
            "inclusion_recommendation": "appendix_only",
            "anchor_confidence": "exact",
            "section_candidates": ["Practical Scope and Exceptions"],
        }
    )
    scaffold["source_evidence_cards"]["cards"].append(
        {
            "source_card_id": "sc_appendix",
            "claim_ids": ["c_appendix"],
            "source_id": "s1",
            "source_quote_or_excerpt": "Appendix-only contextual detail about option A maintenance procurement history.",
            "anchor_confidence": "exact",
        }
    )

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    packet = result["decision_briefing_packet"]

    assert "Appendix-only contextual detail" not in str(packet["evidence_bundles"])
    assert "Appendix-only contextual detail" not in str(packet["must_retain_ledger"])
    assert result["decision_briefing_packet_report"]["main_memo_suppressed_reason_counts"]["appendix_only_candidate"] >= 1


def test_decision_packet_excludes_table_caption_and_fragment_candidates() -> None:
    scaffold = _scaffold()
    noisy = deepcopy(scaffold["candidate_evidence_cards"]["cards"][0])
    noisy.update(
        {
            "candidate_card_id": "ec_table",
            "source_card_ids": ["sc_table"],
            "claim_ids": ["c_table"],
            "claim": "eTable 14. Association Between Each Additional 300 mg Exposure and Outcome",
            "role": "counterweight",
            "evidence_roles": ["counterweight"],
            "decision_relevance_score": 10,
            "quantity_values": ["300 mg"],
        }
    )
    scaffold["candidate_evidence_cards"]["cards"].append(noisy)
    scaffold["source_evidence_cards"]["cards"].append(
        {
            "source_card_id": "sc_table",
            "claim_ids": ["c_table"],
            "source_id": "s1",
            "source_quote_or_excerpt": noisy["claim"],
            "quantity_values": ["300 mg"],
            "anchor_confidence": "exact",
        }
    )

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])

    assert "eTable 14" not in str(result["decision_briefing_packet"]["evidence_bundles"])
    assert "table_or_figure_caption" in result["decision_briefing_packet_report"]["main_memo_suppressed_reason_counts"]


def test_decision_packet_warns_without_blocking_question_mismatched_quantity_rows() -> None:
    scaffold = _scaffold()
    scaffold["quantity_ledger"]["evidence_cards"].append(
        {
            "card_id": "qc_off_question",
            "claim_id": "c_off_question",
            "claim": "Unrelated cancer incidence was higher in a subgroup analysis.",
            "context": "Unrelated cancer incidence was higher in a subgroup analysis.",
            "key_quantities": ["RR 1.57", "95% CI 0.55-1.81"],
            "effect_estimates": ["RR 1.57"],
            "source": "Outcome Study",
            "card_score": 40,
        }
    )

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    bundles = result["decision_briefing_packet"]["evidence_bundles"]
    warning_counts = result["decision_briefing_packet_report"]["main_memo_warning_counts"]

    assert "Unrelated cancer incidence" in str(bundles)
    assert "quantity_anchor_question_mismatch" in warning_counts


def test_question_overlap_ignores_connective_stopwords_for_quantities() -> None:
    question = (
        "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, "
        "or beneficial in dietary advice, especially with respect to cardiovascular risk?"
    )
    off_question_claim = (
        "While the overall relative risk for brain cancer is 1.00, a significantly higher risk "
        "is observed in studies with larger sample sizes."
    )

    question_terms = question_content_terms(question)

    assert "with" not in question_terms
    assert question_overlap_count(off_question_claim, question_terms) == 0
