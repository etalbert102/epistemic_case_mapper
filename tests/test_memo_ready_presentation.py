from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import (
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


def test_presentation_omits_placeholder_source_limits() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "s1", "source_label": "Study 2025", "source_url": "https://example.test/study"}
        ],
        "evidence_items": [],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {"source_ids": ["s1"], "main_use": "drives_answer", "reader_facing_limit": "None"}
            ]
        },
    }

    result = run_memo_ready_presentation_normalization("# Decision Memo\n", packet)

    assert "use: drives answer" in result["memo"]
    assert "limit: None" not in result["memo"]


def test_presentation_normalization_converts_parenthetical_source_ids_to_citations() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "SRC_A", "source_label": "Study A 2025", "source_url": "https://example.test/a"},
            {"source_id": "SRC_B", "source_label": "Study B 2025", "source_url": "https://example.test/b"},
        ],
        "evidence_items": [],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "# Decision Memo\n\n**Bottom Line:** Option A is supported (SRC_A, SRC_B), with no change to ordinary parentheses (CVD)."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[Study A 2025]" in result["memo"]
    assert "[Study B 2025]" in result["memo"]
    assert "(SRC_A, SRC_B)" not in result["memo"]
    assert "(CVD)" in result["memo"]
    assert "normalized_parenthetical_source_id_citations" in result["report"]["changes"]


def test_presentation_preserves_sources_for_each_clause_in_compound_sentence() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "s_cohort", "source_label": "Cohort 2025", "source_url": "https://example.test/cohort"},
            {"source_id": "s_response", "source_label": "Response 2025", "source_url": "https://example.test/response"},
        ],
        "evidence_items": [
            {
                "item_id": "cohort",
                "source_ids": ["s_cohort"],
                "source_excerpt": "A 27% lower mortality risk was observed among weekly users.",
            },
            {
                "item_id": "response",
                "source_ids": ["s_response"],
                "source_excerpt": "High responders experienced increased serum cholesterol.",
            },
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo\n\nWeekly use was associated with 27% lower mortality; however, "
        "high responders experienced increased serum cholesterol [s_cohort, s_response]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "[Cohort 2025]" in result["memo"]
    assert "[Response 2025]" in result["memo"]


def test_presentation_normalization_removes_reader_internal_evidence_ids() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [{"source_id": "SRC_A", "source_label": "Study A 2025", "source_url": "https://example.test/a"}],
        "evidence_items": [
            {
                "item_id": "decision_writer_item_001",
                "reader_claim": "Study A supports option A.",
                "source_ids": ["SRC_A"],
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo\n\n"
        "**Bottom Line:** Study A supports option A (decision_writer_item_001) [SRC_A]. "
        "Do not alter ordinary parentheses (CVD)."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "decision_writer_item_001" not in result["memo"]
    assert "[Study A 2025]" in result["memo"]
    assert "(CVD)" in result["memo"]
    assert "removed_reader_internal_evidence_ids" in result["report"]["changes"]


def test_presentation_normalization_does_not_insert_source_weighting_when_embedded() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "SRC_A", "source_label": "Study A 2025", "source_url": "https://example.test/a"},
            {"source_id": "SRC_B", "source_label": "Study B 2025", "source_url": "https://example.test/b"},
            {"source_id": "SRC_C", "source_label": "Study C 2025", "source_url": "https://example.test/c"},
        ],
        "canonical_decision_writer_packet": {
            "source_weighted_answer_frame": {
                "lanes": {
                    "primary_answer_drivers": [{"source_ids": ["SRC_A"]}],
                    "scope_limiters": [{"source_ids": ["SRC_B"]}],
                    "quantitative_or_interpretive_calibrators": [{"source_ids": ["SRC_C"]}],
                }
            }
        },
    }
    memo = (
        "# Decision Memo: Option A\n\n"
        "**Decision Question:** Should option A be adopted?\n\n"
        "**Bottom Line:** Adopt option A with a narrow scope [SRC_A].\n\n"
        "## Evidence for the Decision\n\n"
        "The answer is driven by Study A [SRC_A]. Study B bounds the scope [SRC_B]. "
        "Study C calibrates the magnitude and identifies what would change the decision [SRC_C]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert result["memo"].count("How to Weight the Evidence") == 0
    assert "inserted_source_weighting" not in result["report"]["changes"]


def test_presentation_sources_use_active_source_trail_only() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "active_2025", "source_label": "Active Study 2025", "source_url": "https://example.test/active"}
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "must_use": True,
                "role": "strongest_support",
                "reader_claim": "Active evidence supports option A.",
                "source_labels": ["Active Study 2025", "Upstream Only 2024"],
            }
        ],
        "memo_obligations": {
            "obligations": [
                {
                    "required": True,
                    "statement": "Use only active evidence.",
                    "source_labels": ["Upstream Only 2024"],
                }
            ]
        },
        "memo_warning_packet": {"warnings": []},
    }
    memo = "# Decision Memo\n\n**Bottom Line:** Option A is supported [active_2025]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "* [Active 2025](https://example.test/active) — Active Study 2025" in result["memo"]
    assert "Upstream Only 2024" not in result["memo"].split("## Sources", 1)[-1]


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


def test_presentation_smooths_stock_phrasing_without_changing_citations() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [{"source_id": "outcome_2025", "source_label": "Outcome Study 2025"}],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo\n\n"
        "**Bottom Line:** Adopt option A when the setting matches.\n\n"
        "This nuanced view is balanced by implementation limits [outcome_2025]. "
        "To avoid over-applying this answer, use the setting boundary."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "This nuanced view" not in result["memo"]
    assert "To avoid over-applying this answer" not in result["memo"]
    assert "This reading is balanced by implementation limits [Outcome 2025]." in result["memo"]
    assert "In applying this answer, use the setting boundary." in result["memo"]
    assert "smoothed_stock_phrasing" in result["report"]["changes"]


def test_presentation_smooths_generic_model_prose_without_changing_sources() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [{"source_id": "outcome_2025", "source_label": "Outcome Study 2025"}],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo\n\n"
        "**Bottom Line:** Adopt option A conditionally.\n\n"
        "These sources provide the foundational basis for the neutral stance [outcome_2025]. "
        "Other sources serve to narrow the scope of the recommendation. "
        "To ensure practical application without overclaiming, use the boundary."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "provide the foundational basis" not in result["memo"]
    assert "the neutral stance" not in result["memo"]
    assert "serve to narrow the scope" not in result["memo"]
    assert "To ensure practical application without overclaiming" not in result["memo"]
    assert "That is the core of the answer" in result["memo"]
    assert "[Outcome 2025]" in result["memo"]
    assert "smoothed_stock_phrasing" in result["report"]["changes"]


def test_presentation_compacts_repeated_adjacent_sentence_citations() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [{"source_id": "outcome_2025", "source_label": "Outcome Study 2025"}],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo\n\n"
        "**Bottom Line:** Adopt option A when the setting matches.\n\n"
        "Outcome evidence supports adoption [outcome_2025]. "
        "The same source also bounds confidence [outcome_2025]. "
        "Different evidence should keep its own citation when it appears [outcome_2025]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    paragraph = result["memo"].split("**Bottom Line:**", maxsplit=1)[-1].split("## Sources", maxsplit=1)[0]
    assert paragraph.count("[Outcome 2025]") == 1
    assert "compacted_repeated_sentence_citations" in result["report"]["changes"]


def test_presentation_keeps_repeated_citations_in_mixed_source_paragraphs() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "outcome_2025", "source_label": "Outcome Study 2025"},
            {"source_id": "mechanism_2024", "source_label": "Mechanism Trial 2024"},
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "# Decision Memo\n\n"
        "**Bottom Line:** Adopt option A when the setting matches.\n\n"
        "Outcome evidence supports adoption [outcome_2025]. "
        "Mechanistic evidence calibrates the threshold [mechanism_2024]. "
        "The key effect estimate is 0.93 [outcome_2025]."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    paragraph = result["memo"].split("**Bottom Line:**", maxsplit=1)[-1].split("## Sources", maxsplit=1)[0]
    assert paragraph.count("[Outcome 2025]") == 2
    assert "[Mechanism 2024]" in paragraph


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

    assert "Read source weight by what each source can decide" in result["memo"]
    assert "where confidence should narrow" in result["memo"]
    assert "put the most weight on [Outcome 2025] for the core answer" in result["memo"]
    assert "use [RISK 2024] as the main check on how far the answer travels" in result["memo"]
    assert "[^source-weight-caveats]" not in result["memo"]
    assert "Use limits:" in result["memo"]
    assert "- Across cited sources: as implementation-risk evidence" in result["memo"]
    assert "implementation-risk evidence" in result["memo"]
    assert "Main answer drivers" not in result["memo"]
    assert "Counterweights" not in result["memo"]
    assert "not enough for unconditional adoption" not in result["memo"]
    assert "* [RISK 2024](https://example.test/risk) — Risk Review 2024 — use: bounds answer; limit: Use as implementation-risk evidence, not as proof against all adoption." in result["memo"]
    assert "[Outcome 2025](CITATION_TRACE.md#outcome-2025)" not in result["memo"]
    assert "[Outcome 2025]: CITATION_TRACE.md#outcome-2025" in result["memo"]


def test_presentation_source_weighting_uses_analyst_hierarchy_and_ignores_stale_guidance_hierarchy() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "outcome_2025", "source_label": "Outcome Study 2025", "source_url": "https://example.test/outcome"},
            {"source_id": "mechanism_2024", "source_label": "Mechanism Trial 2024", "source_url": "https://example.test/mechanism"},
            {"source_id": "guidance_2023", "source_label": "Guidance Note 2023", "source_url": "https://example.test/guidance"},
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["outcome_2025"],
                    "main_use": "drives_answer",
                    "why_weight_this_way": "Flat fallback wording should not be used.",
                }
            ],
            "source_hierarchy": {
                "schema_id": "source_weight_hierarchy_v1",
                "hierarchy_thesis": "Use the analyst hierarchy: outcome evidence drives, while guidance bounds scope.",
                "lanes": {
                    "primary_answer_drivers": [
                        {"source_ids": ["outcome_2025"], "rationale": "It is the analyst-selected driver"}
                    ],
                    "scope_boundary_sources": [
                        {"source_ids": ["guidance_2023"], "rationale": "It is the analyst-selected boundary"}
                    ],
                },
                "source_accounting": [],
            },
            "lightweight_writer_guidance": {
                "schema_id": "lightweight_writer_guidance_v1",
                "source_hierarchy": {
                    "schema_id": "source_weight_hierarchy_v1",
                    "hierarchy_thesis": "Start with outcome evidence, then use the trial and guidance to size and bound the read.",
                    "lanes": {
                        "primary_answer_drivers": [
                            {"source_ids": ["outcome_2025"], "rationale": "It is closest to the target outcome"}
                        ],
                        "quantitative_calibrators": [
                            {"source_ids": ["mechanism_2024"], "rationale": "It sizes the biomarker channel"}
                        ],
                        "scope_boundary_sources": [
                            {"source_ids": ["guidance_2023"], "rationale": "It defines the applicable setting"}
                        ],
                    },
                    "source_accounting": [],
                },
            },
        },
    }
    memo = "# Decision Memo\n\n**Bottom Line:** Adopt option A if risk is bounded."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "Use the analyst hierarchy" in result["memo"]
    assert "Start with outcome evidence" not in result["memo"]
    assert "- **Start with:** [Outcome 2025]" in result["memo"]
    assert "- **Use to bound scope:** [Guidance 2023]" in result["memo"]
    assert "Flat fallback wording should not be used" not in result["memo"]


def test_presentation_model_source_weighting_keeps_limits_source_local() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "cohort_2025", "source_label": "Cohort Study 2025"},
            {"source_id": "guidance_2024", "source_label": "Guidance Note 2024"},
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["cohort_2025"],
                    "main_use": "drives_answer",
                    "memo_weight_sentence": "Use this cohort for the outcome association closest to the decision.",
                    "reader_facing_limit": "Use as association evidence, not standalone causal proof.",
                    "method": "model_adjudicated_per_source",
                    "evidence_item_ids": ["item_001"],
                },
                {
                    "source_ids": ["guidance_2024"],
                    "main_use": "defines_scope",
                    "memo_weight_sentence": "Use this guidance to define implementation scope.",
                    "reader_facing_limit": "Use as guidance, not independent empirical proof.",
                    "method": "model_adjudicated_per_source",
                    "evidence_item_ids": ["item_002"],
                },
            ],
            "source_weighted_answer_frame": {"lanes": {}},
            "source_weight_notes": [],
        },
    }
    memo = "# Decision Memo\n\n**Bottom Line:** Adopt option A in matched settings.\n\n## Support\n\nOutcome evidence supports adoption [cohort_2025]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "- [Cohort 2025]: Use this cohort for the outcome association closest to the decision." in result["memo"]
    assert "Use limit: use as association evidence, not standalone causal proof." in result["memo"]
    assert "- [Guidance 2024]: Use this guidance to define implementation scope." in result["memo"]
    assert "Use limit: use as guidance, not independent empirical proof." in result["memo"]
    cohort_block = result["memo"].split("- [Guidance 2024]:", maxsplit=1)[0]
    assert "guidance, not independent empirical proof" not in cohort_block


def test_presentation_source_weighting_splits_different_caveat_families() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "cohort_2025", "source_label": "Cohort Study 2025"},
            {"source_id": "guidance_2024", "source_label": "Guidance Note 2024"},
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["cohort_2025"],
                    "main_use": "drives_answer",
                    "why_weight_this_way": "Use as the main outcome source.",
                    "reader_facing_limit": "Use as associational evidence, not standalone causal proof.",
                },
                {
                    "source_ids": ["guidance_2024"],
                    "main_use": "defines_scope",
                    "why_weight_this_way": "Use to define the applicable setting.",
                    "reader_facing_limit": "Use as guidance or interpretation, not independent empirical evidence.",
                },
            ],
        },
    }
    memo = "# Decision Memo\n\n**Bottom Line:** Adopt option A if risk is bounded."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "Use limits:" in result["memo"]
    assert "- [Cohort 2025]: as associational evidence" in result["memo"]
    assert "- [Guidance 2024]: as guidance or interpretation" in result["memo"]
    assert "The main caveat is" not in result["memo"]


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


def test_citation_trace_includes_sentence_role_and_source_id_matched_evidence() -> None:
    packet = {
        "source_trail": [
            {
                "source_id": "boundary_2025",
                "source_label": "Boundary Study 2025",
                "citation_label": "Boundary Study 2025",
                "source_url": "https://example.test/boundary",
            }
        ],
        "canonical_decision_writer_packet": {
            "source_weight_judgments": [
                {
                    "source_ids": ["boundary_2025"],
                    "main_use": "bounds_answer",
                    "why_weight_this_way": "Use this source to bound the answer.",
                }
            ]
        },
        "evidence_items": [
            {
                "item_id": "item_boundary",
                "role": "scope_boundary",
                "reader_claim": "The answer is bounded in high-risk subgroups.",
                "source_ids": ["boundary_2025"],
                "citation_role": "boundary",
                "use_for": "Use on boundary sentences.",
                "do_not_use_for": ["Do not cite as broad direct support."],
            }
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = "The answer is bounded in high-risk subgroups [boundary_2025]."

    result = run_memo_ready_presentation_normalization(memo, packet)
    trace = build_citation_trace_markdown(result["memo"], packet)

    assert "Source role for this citation: bounds answer" in trace
    assert "`item_boundary` (scope_boundary): The answer is bounded in high-risk subgroups." in trace
    assert "Citation job: boundary" in trace
    assert "Use for: Use on boundary sentences." in trace
    assert "Use limits: Do not cite as broad direct support." in trace


def test_citation_trace_includes_source_assertion_bundle_use_limits() -> None:
    packet = {
        "source_trail": [{"source_id": "cohort_2025", "source_label": "Cohort Study 2025"}],
        "evidence_items": [
            {
                "item_id": "item_risk",
                "role": "strongest_support",
                "reader_claim": "Higher exposure was associated with higher risk.",
                "source_ids": ["cohort_2025"],
                "assertion_bundles": [
                    {
                        "evidence_bundle_id": "bundle_risk_001",
                        "value": "RR 1.17 (95% CI 1.08 to 1.27)",
                        "endpoint": "cardiovascular disease",
                        "interval": "95% CI 1.08 to 1.27",
                        "allowed_inference": "Use as an observational association.",
                        "forbidden_inference": "Do not present as causal proof.",
                    }
                ],
            }
        ],
    }
    memo = "Higher exposure was associated with higher risk [cohort_2025]."

    trace = build_citation_trace_markdown(memo, packet)

    assert "Source assertion bundles:" in trace
    assert "`bundle_risk_001`: RR 1.17" in trace
    assert "Use as: Use as an observational association." in trace
    assert "Do not use as: Do not present as causal proof." in trace


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


def test_presentation_recognizes_punctuation_dropped_institutional_source_alias() -> None:
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
    memo = "## Decision Brief\n\nThe source weighting cites [U S 2020]."

    result = run_memo_ready_presentation_normalization(memo, packet)

    assert "The source weighting cites [DGA 2020]." in result["memo"]
    assert "[U S 2020]" not in result["memo"]
    assert "* [DGA 2020](https://example.test/dga)" in result["memo"]


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
    assert "[AHA 2023]" in result["memo"]
    assert "[American Heart Association News 2023](CITATION_TRACE.md#american-heart-association-news-2023)" not in result["memo"]
    assert "deduplicated_inline_citations" in result["report"]["changes"]


def test_presentation_deduplicates_adjacent_reference_citations() -> None:
    packet = {
        "source_trail": [
            {
                "source_id": "outcome_2025",
                "source_label": "Outcome 2025",
                "citation_label": "Outcome 2025",
            },
            {
                "source_id": "boundary_2025",
                "source_label": "Boundary 2025",
                "citation_label": "Boundary 2025",
            },
        ],
        "memo_warning_packet": {"warnings": []},
    }
    memo = (
        "## Decision Brief\n\n"
        "The practical threshold is one unit [Outcome 2025] [Outcome 2025]. "
        "The boundary remains live [Outcome 2025], [Boundary 2025] [Outcome 2025]. "
        "The next sentence keeps spacing [Outcome 2025] [Outcome 2025] and continues."
    )

    result = run_memo_ready_presentation_normalization(memo, packet)

    body = result["memo"].split("\n## Sources")[0]
    assert "[Outcome 2025] [Outcome 2025]" not in body
    assert "[Outcome 2025], [Boundary 2025], [Outcome 2025]" not in body
    assert "The practical threshold is one unit [Outcome 2025]." in body
    assert "The boundary remains live [Outcome 2025], [Boundary 2025]." in body
    assert "[Outcome 2025] and continues" in body
    assert "deduplicated_reference_citations" in result["report"]["changes"]


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
