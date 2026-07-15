from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
    build_citation_trace_markdown,
    build_memo_ready_packet_retention_report,
    run_memo_ready_presentation_normalization,
)


def test_presentation_normalization_uses_compact_inline_citations_with_full_sources() -> None:
    source = "Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, systematic review, and updated meta-analysis"
    packet = {
        "decision_question": "Should dietary advice treat eggs as neutral?",
        "source_trail": [
            {
                "source_id": "bmj_2020_egg_consumption_cvd",
                "source_label": source,
                "source_url": "https://example.test/bmj-2020",
            }
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "One egg per day was not associated with higher cardiovascular risk.",
                "source_label": source,
                "quantities": [{"value": "one egg per day"}],
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nOne egg per day was not associated with higher cardiovascular risk [bmj_2020_egg_consumption_cvd]."

    result = run_memo_ready_presentation_normalization(memo, packet)
    retention = build_memo_ready_packet_retention_report(result["memo"], packet)

    assert "[BMJ 2020]" in result["memo"]
    assert "[BMJ 2020](CITATION_TRACE.md#bmj-2020)" not in result["memo"]
    assert "[bmj_2020_egg_consumption_cvd]" not in result["memo"]
    assert "* [BMJ 2020](https://example.test/bmj-2020)" in result["memo"]
    assert "[BMJ 2020]: CITATION_TRACE.md#bmj-2020" in result["memo"]
    assert "](https://example.test/bmj-2020)" in result["memo"]
    assert retention["missing_mandatory_count"] == 0


def test_presentation_inserts_source_weighting_section_from_canonical_packet() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "outcome_2025", "source_label": "Outcome Study 2025", "source_url": "https://example.test/outcome"},
            {"source_id": "mechanism_2024", "source_label": "Mechanism Trial 2024", "source_url": "https://example.test/mechanism"},
            {"source_id": "guidance_2023", "source_label": "Guidance Note 2023", "source_url": "https://example.test/guidance"},
        ],
        "evidence_items": [],
        "canonical_decision_writer_packet": {
            "source_weighted_answer_frame": {
                "lanes": {
                    "primary_answer_drivers": [{"source_ids": ["outcome_2025"]}],
                    "quantitative_or_interpretive_calibrators": [{"source_ids": ["mechanism_2024"]}],
                    "context_only": [{"source_ids": ["guidance_2023"]}],
                }
            },
            "source_weight_notes": [
                {
                    "source_ids": ["outcome_2025"],
                    "decision_directness": "direct",
                    "not_enough_for": ["association_not_causation"],
                },
                {
                    "source_ids": ["guidance_2023"],
                    "decision_directness": "indirect",
                    "not_enough_for": ["guidance_not_independent_empirical_evidence"],
                },
            ],
        },
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo: Option A\n\n"
        "**Bottom Line:** Adopt option A if implementation risk is bounded.\n\n"
        "## Supporting Evidence\n\n"
        "Outcome evidence supports adoption [outcome_2025]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "## How to Weight the Evidence" in result["memo"]
    assert result["memo"].index("## How to Weight the Evidence") < result["memo"].index("## Supporting Evidence")
    assert "Use the evidence in layers" in result["memo"]
    assert "put the most weight on [Outcome 2025] for the core answer" in result["memo"]
    assert "use [Guidance 2023] for translation and background" in result["memo"]
    assert "Keep decision directness in view" in result["memo"]
    assert "Main answer drivers" not in result["memo"]
    assert "Context sources" not in result["memo"]
    assert "association not causation" in result["memo"]
    assert "[Outcome 2025](CITATION_TRACE.md#outcome-2025)" not in result["memo"]
    assert "[Outcome 2025]: CITATION_TRACE.md#outcome-2025" in result["memo"]
    assert "[outcome_2025]" not in result["memo"]
    assert "inserted_source_weighting" in result["report"]["changes"]


def test_presentation_source_weighting_section_is_idempotent() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [{"source_id": "outcome_2025", "source_label": "Outcome Study 2025"}],
        "canonical_decision_writer_packet": {
            "source_weighted_answer_frame": {"lanes": {"primary_answer_drivers": [{"source_ids": ["outcome_2025"]}]}},
            "source_weight_notes": [],
        },
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "**Decision question:** Should option A be adopted?\n\n"
        "**Bottom Line:** Adopt option A.\n\n"
        "## How to Weight the Evidence\n\n"
        "Use outcome evidence first [[Outcome Study 2025](CITATION_TRACE.md#outcome-study-2025)]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert result["memo"].count("## How to Weight the Evidence") == 1
    assert "inserted_source_weighting" not in result["report"]["changes"]


def test_presentation_repairs_truncated_decision_memo_title() -> None:
    packet = {
        "decision_question": "What should an investigator believe about the health effects of eating eggs?",
        "source_trail": [],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo: What should an investigator believe about the health effects of eatin...\n\n"
        "**Decision Question:** What should an investigator believe about the health effects of eating eggs?\n\n"
        "**Bottom Line:** Moderate consumption is bounded by subgroup risk."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert result["memo"].startswith("# Decision Memo: What should an investigator believe about the health effects of eating eggs")
    assert "eatin..." not in result["memo"]
    assert "normalized_decision_title" in result["report"]["changes"]


def test_presentation_source_weighting_section_uses_source_weight_judgments() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "outcome_2025", "source_label": "Outcome Study 2025", "source_url": "https://example.test/outcome"},
            {"source_id": "risk_2024", "source_label": "Risk Review 2024", "source_url": "https://example.test/risk"},
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["outcome_2025"],
                    "main_use": "drives_answer",
                    "why_weight_this_way": "Use primarily to drive the answer because upstream appraisal links it to target-population outcomes.",
                },
                {
                    "source_ids": ["risk_2024"],
                    "main_use": "bounds_answer",
                    "why_weight_this_way": "Use primarily to bound the answer because it identifies implementation risk.",
                    "reader_facing_limit": "Use as implementation-risk evidence, not as proof against all adoption.",
                    "what_not_to_use_it_for": ["not_enough_for_unconditional_adoption"],
                },
            ],
            "source_weighted_answer_frame": {"lanes": {}},
            "source_weight_notes": [],
        },
    }
    memo = "# Decision Memo\n\n**Bottom Line:** Adopt option A if risk is bounded.\n\n## Support\n\nOutcome evidence supports adoption [outcome_2025]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "Do not read the source count as a vote" in result["memo"]
    assert "where confidence should narrow" in result["memo"]
    assert "put the most weight on [Outcome 2025] for the core answer" in result["memo"]
    assert "use [RISK 2024] as the main check on how far the answer travels" in result["memo"]
    assert "[^source-weight-caveats]" not in result["memo"]
    assert "source-by-source limits are expanded in the citation trace" in result["memo"]
    assert "implementation-risk evidence" in result["memo"]
    assert "Main answer drivers" not in result["memo"]
    assert "Counterweights" not in result["memo"]
    assert "not enough for unconditional adoption" not in result["memo"]
    assert "* [RISK 2024](https://example.test/risk) — Risk Review 2024 — use: bounds answer; limit: Use as implementation-risk evidence, not as proof against all adoption." in result["memo"]
    assert "[Outcome 2025](CITATION_TRACE.md#outcome-2025)" not in result["memo"]
    assert "[Outcome 2025]: CITATION_TRACE.md#outcome-2025" in result["memo"]


def test_presentation_source_weighting_uses_lightweight_quality_caveats() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [{"source_id": "outcome_2025", "source_label": "Outcome Study 2025"}],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["outcome_2025"],
                    "main_use": "drives_answer",
                    "why_weight_this_way": "Use as the main outcome source.",
                    "what_not_to_use_it_for": ["quality_limit"],
                }
            ],
            "lightweight_writer_guidance": {
                "schema_id": "lightweight_writer_guidance_v1",
                "evidence_quality_caveats": [
                    {
                        "caveat": "This is observational evidence, so it should not be framed as causal proof.",
                        "source_ids": ["outcome_2025"],
                    }
                ],
            },
        },
    }
    memo = "# Decision Memo\n\n**Bottom Line:** Adopt option A if risk is bounded."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "this is observational evidence, so it should not be framed as causal proof" in result["memo"]
    assert "quality limit" not in result["memo"]


def test_citation_trace_includes_detailed_source_weight_judgments() -> None:
    packet = {
        "source_trail": [{"source_id": "outcome_2025", "source_label": "Outcome Study 2025"}],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["outcome_2025"],
                    "main_use": "drives_answer",
                    "why_weight_this_way": "Use this source to drive the answer because it directly measures the target outcome.",
                    "what_not_to_use_it_for": ["association_not_causation"],
                }
            ]
        },
    }
    memo = "Outcome evidence supports adoption [[Outcome 2025](CITATION_TRACE.md#outcome-2025)]."

    trace = build_citation_trace_markdown(memo, packet)

    assert "Source weight: drives answer" in trace
    assert "Weight rationale: Use this source to drive the answer" in trace
    assert "Use limits: association not causation" in trace


def test_presentation_prefers_citation_label_over_long_display_label() -> None:
    long_title = (
        "Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, "
        "systematic review, and updated meta-analysis"
    )
    packet = {
        "decision_question": "Should dietary advice treat eggs as neutral?",
        "source_trail": [
            {
                "source_id": "bmj_2020_egg_consumption_cvd",
                "source_label": "Drouin-Chartier et al. 2020",
                "citation_label": "Drouin-Chartier et al. 2020",
                "display_label": long_title,
                "source_url": "https://example.test/bmj-2020",
            }
        ],
        "evidence_items": [],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Moderate egg intake was not associated with cardiovascular risk [bmj_2020_egg_consumption_cvd]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)
    trace = build_citation_trace_markdown(result["memo"], packet)

    assert "[Drouin-Chartier et al. 2020]" in result["memo"]
    assert "* [Drouin-Chartier et al. 2020](https://example.test/bmj-2020)" in result["memo"]
    assert "[bmj_2020_egg_consumption_cvd]" not in result["memo"]
    assert long_title not in result["memo"].split("## Sources", 1)[0]
    assert long_title in result["memo"]
    assert f"- Source title: {long_title}" in trace


def test_presentation_compacts_overlong_citation_label_inline() -> None:
    packet = {
        "source_trail": [
            {
                "source_id": "dga_2020_2025_pmc_summary",
                "source_label": "U.S. Department of Agriculture and U.S. Department of Health and Human Services 2020",
                "citation_label": "U.S. Department of Agriculture and U.S. Department of Health and Human Services 2020",
                "display_label": "Dietary Guidelines for Americans, 2020-2025",
                "source_url": "https://example.test/dga",
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nThe scope boundary comes from [dga_2020_2025_pmc_summary]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "The scope boundary comes from [DGA 2020]." in result["memo"]
    assert "U.S. Department of Agriculture and U.S. Department of Health and Human Services 2020" not in result["memo"].split("## Sources", 1)[0]
    assert "[DGA 2020]: CITATION_TRACE.md#dga-2020" in result["memo"]


def test_presentation_compact_citations_title_case_short_names() -> None:
    packet = {
        "source_trail": [{"source_id": "li_2020_egg_cholesterol_rct_meta", "source_label": "Long Source"}],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nThe trial evidence changed LDL-c [li_2020_egg_cholesterol_rct_meta]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[Li 2020]" in result["memo"]
    assert "[LI 2020]" not in result["memo"]


def test_presentation_normalizes_malformed_source_id_and_evidence_item_citations() -> None:
    packet = {
        "source_trail": [
            {
                "source_id": "li_2020_egg_cholesterol_rct_meta",
                "source_label": "Li et al. 2020",
                "citation_label": "Li et al. 2020",
                "source_url": "https://example.test/li",
            },
            {
                "source_id": "nnr_2023_eggs_scoping_review",
                "source_label": "NNR 2023",
                "citation_label": "NNR 2023",
                "source_url": "https://example.test/nnr",
            },
        ],
        "evidence_items": [
            {
                "item_id": "analyst_item_004",
                "source_ids": ["nnr_2023_eggs_scoping_review"],
                "source_labels": ["NNR 2023"],
                "reader_claim": "Moderate egg intake did not increase stroke risk.",
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "LDL markers moved [Li et2020_egg_cholesterol_rct_meta]. "
        "Stroke evidence was neutral [analyst_item_004]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[Li et2020_egg_cholesterol_rct_meta]" not in result["memo"]
    assert "[analyst_item_004]" not in result["memo"]
    assert "[Li et al. 2020]" in result["memo"]
    assert "[NNR 2023]" in result["memo"]


def test_presentation_deduplicates_repeated_inline_citations() -> None:
    packet = {
        "source_trail": [
            {
                "source_id": "drouin_2020",
                "source_label": "Drouin-Chartier et al. 2020",
                "citation_label": "Drouin-Chartier et al. 2020",
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Moderate intake was neutral [Drouin-Chartier et al. 2020; Drouin-Chartier et al. 2020]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert result["memo"].count("[Drouin-Chartier et al. 2020]") == 2
    assert result["memo"].count("[Drouin-Chartier et al. 2020]:") == 1


def test_presentation_deduplicates_repeated_already_linked_citations() -> None:
    packet = {
        "source_trail": [
            {
                "source_id": "drouin_2020",
                "source_label": "Drouin-Chartier et al. 2020",
                "citation_label": "Drouin-Chartier et al. 2020",
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Moderate intake was neutral [[Drouin-Chartier et al. 2020](CITATION_TRACE.md#drouin-chartier-et-al-2020); "
        "[Drouin-Chartier et al. 2020](CITATION_TRACE.md#drouin-chartier-et-al-2020)]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert result["memo"].count("[Drouin-Chartier et al. 2020]") == 2
    assert result["memo"].count("[Drouin-Chartier et al. 2020]:") == 1
    assert "deduplicated_inline_citations" in result["report"]["changes"]


def test_presentation_unwraps_single_already_linked_citation_wrapper() -> None:
    packet = {
        "source_trail": [
            {
                "source_id": "aha_2023",
                "source_label": "American Heart Association News 2023",
                "citation_label": "American Heart Association News 2023",
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "The bottom line should be driven mainly by "
        "[[American Heart Association News 2023](CITATION_TRACE.md#american-heart-association-news-2023)]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[[American Heart Association News 2023]" not in result["memo"]
    assert "[American Heart Association News 2023]" in result["memo"]
    assert "[American Heart Association News 2023](CITATION_TRACE.md#american-heart-association-news-2023)" not in result["memo"]
    assert "deduplicated_inline_citations" in result["report"]["changes"]


def test_presentation_compacts_crowded_inline_citations_without_losing_sources() -> None:
    packet = {
        "decision_question": "Should eggs be treated as neutral?",
        "source_trail": [
            {"source_id": "nnr_2023_eggs_scoping_review", "source_label": "Eggs - a scoping review for Nordic Nutrition Recommendations 2023"},
            {"source_id": "bmj_2020_egg_consumption_cvd", "source_label": "Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, systematic review, and updated meta-analysis"},
            {"source_id": "aha_2023_dietary_cholesterol_news", "source_label": "Here's the latest on dietary cholesterol and how it fits in with a healthy diet"},
            {"source_id": "aha_2019_dietary_cholesterol_pubmed", "source_label": "Dietary Cholesterol and Cardiovascular Risk: A Science Advisory From the American Heart Association"},
            {"source_id": "jama_2019_dietary_cholesterol_eggs", "source_label": "Associations of Dietary Cholesterol or Egg Consumption With Incident Cardiovascular Disease and Mortality"},
            {"source_id": "dga_2020_2025_pmc_summary", "source_label": "Dietary Guidelines for Americans, 2020-2025"},
        ],
        "evidence_items": [],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Moderate intake is neutral [nnr_2023_eggs_scoping_review, bmj_2020_egg_consumption_cvd, "
        "aha_2023_dietary_cholesterol_news, aha_2019_dietary_cholesterol_pubmed, "
        "jama_2019_dietary_cholesterol_eggs, dga_2020_2025_pmc_summary]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[NNR 2023], [BMJ 2020], [AHA 2023]" in result["memo"]
    assert "[AHA 2019], [JAMA 2019], [DGA 2020]" in result["memo"]
    assert "[NNR 2023, BMJ 2020, AHA 2023" not in result["memo"]
    assert "* NNR 2023" in result["memo"]
    assert "* BMJ 2020" in result["memo"]
    assert "* AHA 2023" in result["memo"]
    assert "* AHA 2019" in result["memo"]
    assert "* JAMA 2019" in result["memo"]
    assert "* DGA 2020" in result["memo"]
    assert "compacted_crowded_citations" not in result["report"]["changes"]


def test_citation_trace_records_packet_evidence_without_replacing_source_urls() -> None:
    packet = {
        "decision_question": "Should advice change?",
        "source_trail": [
            {
                "source_id": "outcome_2025",
                "source_label": "Outcome Study 2025",
                "source_url": "https://example.test/outcome",
            }
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "role": "scope_boundary",
                "reader_claim": "The effect is limited to the studied population.",
                "source_labels": ["Outcome Study 2025"],
                "quantities": [{"value": "42%", "interpretation": "event rate in the studied group"}],
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "## Decision Brief\n\nThe effect is limited to the studied population [outcome_2025]."

    result = run_memo_ready_presentation_normalization(memo, packet)
    trace = build_citation_trace_markdown(result["memo"], packet)

    assert "[Outcome 2025]" in result["memo"]
    assert "* [Outcome 2025](https://example.test/outcome)" in result["memo"]
    assert "## Outcome 2025" in trace
    assert "- Short label: Outcome 2025" in trace
    assert "- Source ID: `outcome_2025`" in trace
    assert "- External URL: https://example.test/outcome" in trace
    assert "`item_001` (scope_boundary): The effect is limited to the studied population." in trace
    assert "42%: event rate in the studied group" in trace


def test_presentation_links_parenthetical_citations_and_records_memo_contexts() -> None:
    packet = {
        "decision_question": "Should advice change?",
        "source_trail": [
            {
                "source_id": "bmj_2020_egg_consumption_cvd",
                "source_label": "Egg consumption and risk of cardiovascular disease",
                "source_url": "https://example.test/bmj",
            },
            {
                "source_id": "nnr_2023_eggs_scoping_review",
                "source_label": "Nordic Nutrition Recommendations evidence review authors 2023",
                "source_url": "https://example.test/nnr",
            },
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "role": "strongest_support",
                "reader_claim": "Moderate egg consumption was not associated with higher cardiovascular risk.",
                "source_label": "Egg consumption and risk of cardiovascular disease",
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "Moderate intake was not associated with higher cardiovascular risk (BMJ 2020). "
        "The replacement-food question remains important (BMJ 2020; NNR 2023). "
        "The BMJ 2020 authors also framed this as a replacement-food problem."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)
    trace = build_citation_trace_markdown(result["memo"], packet)

    assert "([BMJ 2020])" in result["memo"]
    assert "([BMJ 2020]; [NNR 2023])" in result["memo"]
    assert "- Memo citation contexts:" in trace
    assert "Moderate intake was not associated with higher cardiovascular risk ([BMJ 2020])." in trace
    assert "The replacement-food question remains important ([BMJ 2020]; [NNR 2023])." in trace
    assert "authors also framed this" not in trace
    assert "* [BMJ 2020](https://example.test/bmj)" in result["memo"]
