from epistemic_case_mapper.map_briefing_evidence_role_matrix import build_evidence_role_matrix_bundle


def test_evidence_role_matrix_allows_distinct_section_reuse() -> None:
    bundle = build_evidence_role_matrix_bundle(
        candidate_evidence_cards={
            "cards": [
                {
                    "candidate_card_id": "ec1",
                    "claim": "The pilot improved completion among eligible applicants.",
                    "source_excerpt": "Completion rose among eligible applicants in the pilot.",
                    "source_ids": ["s1"],
                    "source_titles": ["Pilot evaluation"],
                    "decision_relevance_score": 9,
                    "inclusion_recommendation": "main_text",
                    "quality": "usable",
                }
            ]
        },
        section_context_decision_packets={
            "sections": [
                {
                    "section": "Evidence Carrying the Conclusion",
                    "owned_evidence": [
                        {
                            "candidate_card_id": "ec1",
                            "claim": "The pilot improved completion among eligible applicants.",
                            "section_use": "Explain the strongest direct support.",
                            "source": "Pilot evaluation",
                        }
                    ],
                },
                {
                    "section": "Practical Scope and Exceptions",
                    "owned_evidence": [
                        {
                            "candidate_card_id": "ec1",
                            "claim": "The pilot improved completion among eligible applicants.",
                            "section_use": "Bound the read to eligible applicants.",
                            "intended_role": "scope boundary",
                            "source": "Pilot evaluation",
                        }
                    ],
                },
            ]
        },
    )

    matrix_row = bundle["evidence_role_matrix"]["rows"][0]
    assert matrix_row["section_uses"]["Evidence Carrying the Conclusion"]["role"] == "load_bearing"
    assert matrix_row["section_uses"]["Practical Scope and Exceptions"]["role"] == "boundary"
    working_sets = {section["section"]: section for section in bundle["section_evidence_working_sets"]["sections"]}
    assert working_sets["Evidence Carrying the Conclusion"]["primary_evidence"][0]["candidate_card_id"] == "ec1"
    assert working_sets["Practical Scope and Exceptions"]["boundary_evidence"][0]["candidate_card_id"] == "ec1"


def test_evidence_role_matrix_reports_omitted_high_priority_cards() -> None:
    bundle = build_evidence_role_matrix_bundle(
        candidate_evidence_cards={
            "cards": [
                {
                    "candidate_card_id": "ec1",
                    "claim": "The intervention reduced avoidable delays.",
                    "decision_relevance_score": 8,
                    "inclusion_recommendation": "main_text",
                    "anchor_confidence": "high",
                },
                {
                    "candidate_card_id": "ec2",
                    "claim": "The implementation memo is background only.",
                    "decision_relevance_score": 3,
                    "inclusion_recommendation": "supporting_context",
                },
            ]
        },
        section_context_decision_packets={
            "sections": [
                {
                    "section": "Why This Read",
                    "owned_evidence": [
                        {
                            "candidate_card_id": "ec1",
                            "claim": "The intervention reduced avoidable delays.",
                        }
                    ],
                }
            ]
        },
    )

    matrix = bundle["evidence_role_matrix"]
    assert matrix["assigned_card_count"] == 1
    assert matrix["omitted_cards"][0]["candidate_card_id"] == "ec2"
    assert "below_main_text_relevance" in matrix["omitted_cards"][0]["reasons"]


def test_section_working_sets_report_budget_pressure() -> None:
    cards = [
        {
            "candidate_card_id": f"ec{i}",
            "claim": f"Source-grounded claim {i} bears on the decision.",
            "decision_relevance_score": 9 - (i % 3),
            "inclusion_recommendation": "main_text",
        }
        for i in range(10)
    ]
    bundle = build_evidence_role_matrix_bundle(
        candidate_evidence_cards={"cards": cards},
        section_context_decision_packets={
            "sections": [
                {
                    "section": "Evidence Carrying the Conclusion",
                    "owned_evidence": [
                        {"candidate_card_id": card["candidate_card_id"], "claim": card["claim"]}
                        for card in cards
                    ],
                }
            ]
        },
    )

    section = bundle["section_evidence_working_sets"]["sections"][0]
    assert len(section["primary_evidence"]) == 8
    assert section["budget_report"]["primary_available"] == 10
    assert "section_working_set_budget_pressure" in bundle["section_evidence_working_sets"]["issues"]
