from __future__ import annotations

import json
import sys
from pathlib import Path

from epistemic_case_mapper import cli
from epistemic_case_mapper.map_briefing import (
    adaptive_briefing_claim_budget,
    append_evidence_by_decision_lever,
    append_map_coverage_snapshot,
    annotate_map_with_evidence_slots,
    briefing_scaffold,
    build_crux_contract,
    build_briefing_contract,
    build_map_briefing_prompt,
    build_decision_model,
    build_decision_slots,
    build_concept_evidence_packets,
    build_decision_memo_slots,
    build_evidence_compression_table,
    build_evidence_slot_ledger,
    build_evidence_weighting_ledger,
    build_map_sufficiency_report,
    build_option_comparison,
    build_reader_memo_rewrite_contract,
    build_proposition_clusters,
    build_curated_evidence_packets,
    calibrate_confidence,
    briefing_reader_polish_report,
    clean_reader_briefing_text,
    compose_final_reader_memo_package,
    expand_reader_map_references,
    model_parse_diagnostics,
    partition_map_evidence,
    polish_briefing_for_reader,
    prioritize_map_for_briefing,
    repair_briefing_payload,
    repair_reader_memo_rewrite_candidate,
    reader_memo_rewrite_issues,
    run_map_briefing,
    validate_briefing_against_scaffold,
    _rewrite_mentions_anchor_row,
)
from epistemic_case_mapper.map_briefing_memo_metadata import ensure_reader_memo_metadata
from epistemic_case_mapper.staged_semantic_pipeline import CLAIM_EXTRACTION_PROMPT_VERSION, RELATION_PROMPT_VERSION


def test_confidence_calibration_caps_high_when_map_has_risks() -> None:
    report = {
        "status": "usable_with_review",
        "score": 90,
        "issues": [{"severity": "risk", "issue_type": "high_claim_count", "message": "Dense map."}],
    }

    calibrated = calibrate_confidence("high", report)

    assert calibrated["calibrated_confidence"] == "medium"
    assert "risk_issue_caps_high_confidence" in calibrated["reasons"]


def test_prioritization_preserves_source_coverage() -> None:
    candidate_map = {
        "claims": [
            {"claim_id": "c001", "claim": "A crux.", "source_id": "source_a", "role": "crux"},
            {"claim_id": "c002", "claim": "A support.", "source_id": "source_a", "role": "conclusion_support"},
            {"claim_id": "c003", "claim": "B scope.", "source_id": "source_b", "role": "scope_limit"},
            {"claim_id": "c004", "claim": "C background.", "source_id": "source_c", "role": "background"},
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c001",
                "target_claim": "c003",
                "relation_type": "crux_for",
                "rationale": "The crux determines whether the scope limit matters.",
            }
        ],
    }

    prioritized, report = prioritize_map_for_briefing(candidate_map, quality_report={"status": "usable_with_review"}, max_claims=3)

    assert report["changed"] is True
    assert report["ranking_method"] == "source_coverage_family_concept_coverage_then_role_priority_weighted_pagerank_with_tfidf_duplicate_suppression"
    assert report["source_coverage_preserved"] is True
    assert report["family_coverage_preserved"] is False
    assert report["centrality_scores"]["c001"] > 0
    assert {claim["source_id"] for claim in prioritized["claims"]} == {"source_a", "source_b", "source_c"}
    assert "c002" in report["dropped_claim_ids"]


def test_prioritization_reports_tfidf_duplicate_pairs() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The trial measured LDL cholesterol biomarkers rather than cardiovascular events.",
                "source_id": "source_a",
                "role": "crux",
            },
            {
                "claim_id": "c002",
                "claim": "The trial measured LDL biomarkers instead of cardiovascular event outcomes.",
                "source_id": "source_a",
                "role": "crux",
            },
            {
                "claim_id": "c003",
                "claim": "Guideline policy judgment uses a broader evidence process.",
                "source_id": "source_b",
                "role": "scope_limit",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c001",
                "target_claim": "c003",
                "relation_type": "crux_for",
                "rationale": "Endpoint interpretation changes the policy read.",
            }
        ],
    }

    _prioritized, report = prioritize_map_for_briefing(
        candidate_map,
        quality_report={"status": "usable_with_review"},
        max_claims=2,
    )

    pairs = {(row["left"], row["right"]) for row in report["duplicate_claim_pairs"]}
    assert ("c001", "c002") in pairs
    assert report["centrality_scores"]["c001"] > report["centrality_scores"]["c002"]


def test_prioritization_preserves_decision_evidence_families() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "A cohort found moderate use was not associated with worse cardiovascular outcomes.",
                "source_id": "source_a",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "A randomized trial measured LDL biomarker changes rather than hard outcome events.",
                "source_id": "source_a",
                "role": "measurement_validity",
            },
            {
                "claim_id": "c003",
                "claim": "Guideline recommendations focus on healthy dietary patterns.",
                "source_id": "source_b",
                "role": "implementation_constraint",
            },
            {
                "claim_id": "c004",
                "claim": "People with type 2 diabetes may have higher risk at high intake.",
                "source_id": "source_b",
                "role": "scope_limit",
            },
            {"claim_id": "c005", "claim": "This background sentence is less central.", "source_id": "source_a", "role": "background"},
        ],
        "relations": [
            {"relation_id": "r001", "source_claim": "c004", "target_claim": "c001", "relation_type": "in_tension_with", "rationale": "Subgroup risk limits generalization."}
        ],
    }

    prioritized, report = prioritize_map_for_briefing(
        candidate_map,
        quality_report={"status": "usable_with_review"},
        max_claims=4,
    )

    kept_text = " ".join(claim["claim"] for claim in prioritized["claims"])
    assert "cohort" in kept_text.lower()
    assert "randomized trial" in kept_text.lower()
    assert "guideline" in kept_text.lower()
    assert "type 2 diabetes" in kept_text.lower()
    assert {
        "cohort_or_observational",
        "rct_or_intervention",
        "guideline_or_recommendation",
        "subgroup_or_scope",
    }.issubset(set(report["kept_evidence_families"]))
    assert report["dropped_claim_ids"] == ["c005"]


def test_adaptive_briefing_claim_budget_expands_for_complex_maps() -> None:
    concept_claims = [
        "Generally healthy adults were followed for cardiovascular disease outcomes in a prospective cohort.",
        "Moderate intake up to one egg per day was the relevant dose threshold.",
        "LDL cholesterol and ApoB biomarkers are mechanistic lipid evidence.",
        "Saturated fat and dietary pattern may change how dietary cholesterol is interpreted.",
        "Replacing eggs with plant protein is a comparator question.",
        "People with type 2 diabetes are a high-risk subgroup.",
        "A randomized trial measured biomarkers rather than hard outcome events.",
        "Guideline recommendations focus on practical dietary advice.",
    ]
    claims = []
    for index in range(96):
        claims.append(
            {
                "claim_id": f"c{index:03d}",
                "claim": concept_claims[index % len(concept_claims)],
                "source_id": f"source_{index % 12}",
                "role": "conclusion_support" if index % 3 else "scope_limit",
            }
        )
    candidate_map = {"claims": claims, "relations": []}

    budget = adaptive_briefing_claim_budget(candidate_map, {"status": "usable_with_review"}, requested_max_claims=0)

    assert budget > 28
    assert budget <= 90
    assert adaptive_briefing_claim_budget(candidate_map, requested_max_claims=17) == 17


def test_evidence_compression_table_preserves_concepts_and_suppresses_boilerplate() -> None:
    disclosure = (
        "Professor Example received research grants, speaker fees, honoraria, funding and travel support, "
        "served on a scientific advisory board, and reports conflict of interest disclosures. "
    ) * 6
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "LDL and ApoB biomarker changes are mechanistic evidence, but they are surrogate endpoints rather than hard cardiovascular outcomes.",
                "source_id": "mechanism",
                "role": "measurement_validity",
            },
            {
                "claim_id": "c002",
                "claim": "Replacing eggs with plant protein is a comparator question that can change practical dietary advice.",
                "source_id": "comparator",
                "role": "implementation_constraint",
            },
            {
                "claim_id": "c003",
                "claim": disclosure,
                "source_id": "disclosure",
                "role": "background",
            },
        ],
        "relations": [],
    }
    source_lookup = {"mechanism": "Mechanism", "comparator": "Comparator", "disclosure": "Disclosure"}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(
        candidate_map,
        partition,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
    )

    table = build_evidence_compression_table(candidate_map, ledger, source_lookup)

    assert table["coverage"]["concept_coverage_preserved"] is True
    assert "mechanism_ldl_apob" in table["coverage"]["selected_concepts"]
    assert "substitution_or_comparator" in table["coverage"]["selected_concepts"]
    row_text = json.dumps(table["rows"]).lower()
    assert "professor example received research grants" not in row_text
    assert "funding or conflict-of-interest disclosures" in row_text or "c003" not in row_text


def test_coverage_snapshot_appends_retained_decision_concepts() -> None:
    scaffold = {
        "evidence_compression_table": {
            "rows": [
                {
                    "claim_id": "c001",
                    "source": "Mechanism Source",
                    "score": 7,
                    "concepts": ["mechanism_ldl_apob", "surrogate_or_biomarker_endpoint"],
                    "claim": "LDL and ApoB are biomarker mechanisms, not hard cardiovascular outcomes.",
                    "why_it_matters": "Mechanistic evidence bounds how far a neutral outcome read should travel.",
                },
                {
                    "claim_id": "c002",
                    "source": "Guideline Source",
                    "score": 5,
                    "concepts": ["guideline_or_policy"],
                    "claim": "Guidelines frame advice around overall dietary patterns.",
                    "why_it_matters": "Guidance evidence affects the practical recommendation.",
                },
            ]
        }
    }

    rendered = append_map_coverage_snapshot("## Decision Brief\n\nUse a neutral frame.", scaffold)

    assert "## Map Coverage Snapshot" in rendered
    assert "LDL/ApoB mechanism" in rendered
    assert "Guidance or policy" in rendered
    assert "Mechanism Source" in rendered


def test_concept_evidence_packets_render_decision_lever_section() -> None:
    ledger = {
        "all_evidence": [
            {
                "claim_id": "c001",
                "claim": "Replacing eggs with plant protein is associated with lower cardiovascular risk.",
                "source": "Comparator Study",
                "section": "main_support",
                "weight": "high",
                "score": 8,
                "decision_concepts": ["substitution_or_comparator", "hard_outcome_endpoint"],
                "evidence_family": "substitution_or_comparator",
                "noise": {"kind": "none"},
            },
            {
                "claim_id": "c002",
                "claim": "ApoB and LDL biomarkers did not worsen with higher egg intake.",
                "source": "Biomarker Study",
                "section": "method_limits",
                "weight": "medium",
                "score": 7,
                "decision_concepts": ["mechanism_ldl_apob", "surrogate_or_biomarker_endpoint"],
                "evidence_family": "mechanism_or_biomarker",
                "noise": {"kind": "none"},
            },
        ]
    }

    packets = build_concept_evidence_packets(ledger)
    rendered = append_evidence_by_decision_lever("## Decision Brief\n\nNeutral.\n\n## Evidence Roles\n", {"concept_evidence_packets": packets})
    validation = validate_briefing_against_scaffold(rendered, {"concept_evidence_packets": packets}, {"claims": [], "relations": []})

    assert "## Evidence by Decision Lever" in rendered
    assert "Comparator or substitution" in rendered
    assert "plant protein" in rendered
    assert "LDL/ApoB mechanism" in rendered
    assert validation["status"] == "passes_contract"


def test_reader_polish_creates_executive_brief_and_appendix() -> None:
    scaffold = {
        "question": "Should generally healthy adults treat moderate egg intake as acceptable?",
        "source_display_names": {"demo_sources_dehghan_2020_full": "Dehghan 2020"},
        "quality_status": "usable_with_review",
        "confidence_cap": "medium",
        "decision_model": {
            "default_answer": {
                "why_this_frame": "The mapped evidence supports a neutral default rather than a strong benefit or harm claim.",
            },
            "main_reasons": [
                {
                    "proposition": "Moderate use is not associated with worse hard outcomes in the mapped cohort evidence.",
                    "sources": ["Cohort Study"],
                }
            ],
            "strongest_counterarguments": [
                {
                    "proposition": "Higher-risk metabolic subgroups may not follow the default-population read.",
                    "sources": ["Subgroup Study"],
                }
            ],
            "what_would_change_answer": ["A direct trial showing worse hard outcomes at moderate use would change the decision."],
        },
        "concept_evidence_packets": {
            "packets": [
                {
                    "concept": "substitution_or_comparator",
                    "label": "Comparator or substitution",
                    "must_surface_terms": ["plant protein"],
                    "rows": [
                        {
                            "claim": "Replacing eggs with plant protein is associated with lower cardiovascular risk.",
                            "source": "Comparator Study",
                        }
                    ],
                }
            ]
        },
        "map_sufficiency_report": {"status": "usable_with_named_gaps"},
        "evidence_roles": {
            "main_support": ["Moderate use was neutral in the mapped cohort evidence. (Cohort Study)"],
            "conflicting_evidence": ["Metabolic-risk subgroups may require separate treatment. (Subgroup Study)"],
            "scope_limits": [],
            "method_limits": [],
        },
    }
    rendered = """## Decision Brief

Neutral default. Dose/threshold evidence:.utations that should not survive the reader pass.

**Confidence:** medium

## Decision Implications

- Keep the default answer scoped to moderate use.

## Evidence Roles

### Main Support

- Moderate use was neutral in the mapped cohort evidence. (Cohort Study)

## Evidence by Decision Lever

### Comparator or substitution

| Evidence | Source | Role |
|---|---|---|
| Replacing eggs with plant protein is associated with lower cardiovascular risk. | Comparator Study | Comparator evidence affects the practical recommendation. |
"""

    polished = polish_briefing_for_reader(rendered, scaffold)
    report = briefing_reader_polish_report(polished, scaffold)

    assert "## Evidence Appendix" in polished
    assert "## Why This Is the Right Default" in polished
    assert "## Evidence Roles" in polished
    assert "## Evidence by Decision Lever" in polished
    assert "plant protein" in polished
    assert ".utations" not in polished
    assert report["status"] == "polished"


def test_clean_reader_briefing_text_removes_extraction_fragments() -> None:
    cleaned = clean_reader_briefing_text(
        "Dose/threshold evidence:.utations that cause confusion. Subgroup/scope evidence:.ommon in the elderly."
    )

    assert ".utations" not in cleaned
    assert ".ommon" not in cleaned
    assert "Dose/threshold evidence" not in cleaned


def test_final_reader_memo_separates_beautiful_brief_from_appendix() -> None:
    scaffold = {
        "question": "Should generally healthy adults treat moderate egg intake as acceptable?",
        "source_display_names": {"demo_sources_dehghan_2020_full": "Dehghan 2020"},
        "quality_status": "usable_with_review",
        "confidence_cap": "medium",
        "quality_issues": ["risk: high_claim_count - Accepted many claims."],
        "map_sufficiency_report": {"status": "usable_with_named_gaps"},
        "concept_evidence_packets": {
            "packets": [
                {
                    "concept": "dose_or_threshold",
                    "label": "Dose or threshold",
                    "synthesis_job": "State the dose boundary.",
                    "must_surface_terms": ["per day"],
                    "rows": [
                        {
                            "claim": "Moderate intake up to one egg per day was not associated with worse cardiovascular outcomes.",
                            "source": "demo_sources_dehghan_2020_full",
                            "section": "main_support",
                            "weight": "high",
                            "score": 8,
                            "why_it_matters": "Dose boundaries prevent overgeneralization.",
                        },
                        {
                            "claim": "...utations that cause reduced LDL receptor function are a copied fragment.",
                            "source": "fragment",
                            "section": "main_support",
                            "weight": "medium",
                            "score": 6,
                            "why_it_matters": "Fragment.",
                        },
                    ],
                },
                {
                    "concept": "subgroup_diabetes_or_metabolic_risk",
                    "label": "Metabolic-risk subgroup",
                    "synthesis_job": "State subgroup limits.",
                    "must_surface_terms": ["diabetes"],
                    "rows": [
                        {
                            "claim": "People with type 2 diabetes may require separate advice because subgroup evidence can diverge from the default-population read.",
                            "source": "demo_sources_subgroup_2021_full",
                            "section": "scope_limits",
                            "weight": "high",
                            "score": 8,
                            "why_it_matters": "Subgroup evidence narrows the default answer.",
                        }
                    ],
                },
            ]
        },
    }
    rendered = """## Decision Brief

Neutral default for generally healthy adults.

**Confidence:** medium

## Decision Implications

- Keep the answer scoped to moderate intake.

## Evidence Roles

### Main Support

- Moderate intake up to one egg per day was not associated with worse cardiovascular outcomes. (Dehghan 2020)

## Evidence by Decision Lever

### Dose or threshold

| Evidence | Source | Role |
|---|---|---|
| Moderate intake up to one egg per day was not associated with worse cardiovascular outcomes. | Dehghan 2020 | Dose boundaries prevent overgeneralization. |
"""

    package = compose_final_reader_memo_package(rendered, scaffold)

    assert "## Evidence Trail" in package["memo"]
    assert "**Decision question:**" in package["memo"]
    assert "## Sources" in package["memo"]
    assert "Dehghan 2020" in package["memo"]
    assert "## Evidence Appendix" not in package["memo"]
    assert "## Evidence by Decision Lever" in package["appendix"]
    assert "Extraction Artifacts Excluded From Reader Brief" in package["appendix"]
    assert "copied fragment" not in package["memo"]
    assert "copied fragment" in package["appendix"]
    assert "Dehghan 2020" in package["memo"] or "Dehghan 2020" in package["appendix"]
    lowered = package["memo"].lower()
    assert "mapped support" not in lowered
    assert "map-backed read" not in lowered
    assert "decision role" not in lowered


def test_reader_memo_metadata_removes_duplicate_question_paragraph() -> None:
    question = "Should generally healthy adults treat moderate egg intake as acceptable?"
    memo = f"""## Decision Brief

{question}

Moderate intake is acceptable within the stated scope.

**Confidence:** medium
"""

    updated = ensure_reader_memo_metadata(memo, {"question": question})

    assert updated.count("**Decision question:**") == 1
    assert updated.count(question) == 1
    assert f"**Decision question:** {question}\n\nModerate intake" in updated
    assert "Moderate intake is acceptable" in updated


def test_rewrite_candidate_repair_salvages_generic_crux_and_source_label_noise() -> None:
    scaffold = {
        "confidence_cap": "medium",
        "source_display_names": {"nacto": "Nacto Protected Bikeways"},
    }
    contract = {
        "confidence": "medium",
        "required_evidence": [],
        "required_gaps": [],
        "required_cruxes": [
            {
                "crux": "Maintenance capacity",
                "current_read": "This condition changes how strongly the recommendation holds.",
                "would_change_if": "The named condition no longer affected the practical recommendation.",
            },
            {
                "crux": "Attribution of results",
                "current_read": "This condition changes how strongly the recommendation holds.",
                "would_change_if": "The named condition no longer affected the practical recommendation.",
            },
        ],
    }
    rewrite = """## Decision Brief

Prefer protected lanes where the city can maintain them (Nacto Protected_Protected Bikeways).

**Confidence:** medium

## Decision Cruxes

| Crux | Why it matters | Current read | Would change if |
|---|---|---|---|
| Maintenance capacity | Separators need upkeep. | This condition changes how strongly the recommendation holds. | The named condition no longer affected the practical recommendation. |
| Attribution of results | The before-after evaluation was not randomized. | This condition changes how strongly the recommendation holds. | The named condition no longer affected the practical recommendation. |
"""

    repaired = repair_reader_memo_rewrite_candidate(rewrite, scaffold, contract)

    assert "Nacto Protected_Protected Bikeways" not in repaired
    assert "Nacto Protected Bikeways" in repaired
    assert "This condition changes how strongly" not in repaired
    assert "named condition no longer affected" not in repaired
    assert "causal-attribution limits" in repaired
    assert "keep the intervention usable" in repaired


def test_rewrite_repair_can_clear_duplicate_crux_rejection_without_fallback() -> None:
    scaffold = {
        "confidence_cap": "medium",
        "source_display_names": {"nacto": "Nacto Protected Bikeways"},
        "map_sufficiency_report": {"status": "sufficient_for_scaffolded_briefing"},
        "decision_memo_slots": {
            "slots": [
                {
                    "id": "main_support",
                    "label": "Main support",
                    "status": "filled",
                    "rows": [
                        {
                            "claim": "Protected lanes are most relevant where traffic stress makes paint insufficient.",
                            "source": "Nacto Protected Bikeways",
                        }
                    ],
                }
            ]
        },
        "crux_candidates": [
            {
                "crux": "Maintenance capacity",
                "why_it_matters": "Cities should choose protection types they can maintain.",
                "current_read": "This condition changes how strongly the recommendation holds.",
                "would_change_if": "The named condition no longer affected the practical recommendation.",
            },
            {
                "crux": "Attribution of results",
                "why_it_matters": "The before-after evidence was not randomized.",
                "current_read": "This condition changes how strongly the recommendation holds.",
                "would_change_if": "The named condition no longer affected the practical recommendation.",
            },
            {
                "crux": "Site constraints",
                "why_it_matters": "Street geometry and access conflicts can change feasibility.",
                "current_read": "This condition changes how strongly the recommendation holds.",
                "would_change_if": "The named condition no longer affected the practical recommendation.",
            },
            {
                "crux": "Rider volume changes",
                "why_it_matters": "Exposure changes affect interpretation of injury trends.",
                "current_read": "This condition changes how strongly the recommendation holds.",
                "would_change_if": "The named condition no longer affected the practical recommendation.",
            },
        ],
    }
    original = """## Decision Brief

The deterministic memo contains many repeated phrases and source-grounded detail.

**Confidence:** medium

## Practical Read

- Keep the answer bounded by implementation capacity.

## Evidence Carrying the Conclusion

Protected lanes are most relevant where traffic stress makes paint insufficient. (Nacto Protected Bikeways)
""" + ("Extra deterministic detail. " * 130)
    appendix = "## Evidence Appendix\n\nProtected lanes are most relevant where traffic stress makes paint insufficient. (Nacto Protected Bikeways)"
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Protected lanes are most relevant where traffic stress makes paint insufficient.",
                "source_id": "nacto",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    contract = build_reader_memo_rewrite_contract(original, scaffold)
    contract["required_cruxes"] = [
        {
            "crux": "Maintenance capacity",
            "current_read": "This condition changes how strongly the recommendation holds.",
            "would_change_if": "The named condition no longer affected the practical recommendation.",
        },
        {
            "crux": "Attribution of results",
            "current_read": "This condition changes how strongly the recommendation holds.",
            "would_change_if": "The named condition no longer affected the practical recommendation.",
        },
        {
            "crux": "Site constraints",
            "current_read": "This condition changes how strongly the recommendation holds.",
            "would_change_if": "The named condition no longer affected the practical recommendation.",
        },
        {
            "crux": "Rider volume changes",
            "current_read": "This condition changes how strongly the recommendation holds.",
            "would_change_if": "The named condition no longer affected the practical recommendation.",
        },
    ]
    rewrite = """## Decision Brief

The city should prefer protected lanes over paint on high-stress arterials when it can maintain the protection and handle operating constraints. Protected lanes are most relevant where traffic stress makes paint insufficient (Nacto Protected_Protected Bikeways).

**Confidence:** medium

## Practical Read

- Select protection types that match maintenance capacity.
- Use paint only where traffic stress is already low or protection is infeasible.
- Treat implementation constraints as conditions on the recommendation.

## Why This Read

- Protected lanes are most relevant where traffic stress makes paint insufficient (Nacto Protected Bikeways).
- Maintenance capacity determines whether physical protection remains usable after installation.
- The observational evidence should be read as a corridor-package signal rather than a clean single-cause estimate.

## Decision Cruxes

| Crux | Why it matters | Current read | Would change if |
|---|---|---|---|
| Maintenance capacity | Cities should choose protection types they can maintain. | This condition changes how strongly the recommendation holds. | The named condition no longer affected the practical recommendation. |
| Attribution of results | The before-after evidence was not randomized. | This condition changes how strongly the recommendation holds. | The named condition no longer affected the practical recommendation. |
| Site constraints | Street geometry and access conflicts can change feasibility. | This condition changes how strongly the recommendation holds. | The named condition no longer affected the practical recommendation. |
| Rider volume changes | Exposure changes affect interpretation of injury trends. | This condition changes how strongly the recommendation holds. | The named condition no longer affected the practical recommendation. |

## Limits of the Current Map

The packet does not settle every local design constraint. It also does not prove that physical protection alone caused the observed before-after change, because corridor projects can include intersection treatments, signal timing changes, loading changes, and other safety work. The recommendation should therefore be read as a practical program choice: use protection as the arterial default where the street can support it, keep paint for lower-stress gaps or infeasible corridors, and require operations planning before installation. The packet is strong enough to organize the decision, but it is not a substitute for corridor-level design review.

## Evidence Trail

The structured evidence trail is in `EVIDENCE_APPENDIX.md`.
"""

    issues = reader_memo_rewrite_issues(rewrite, original, appendix, scaffold, candidate_map, contract)
    repaired = repair_reader_memo_rewrite_candidate(rewrite, scaffold, contract)
    repaired_issues = reader_memo_rewrite_issues(repaired, original, appendix, scaffold, candidate_map, contract)

    assert "rewrite crux table contains non-human current-read language" in issues
    assert repaired_issues == []


def test_rewrite_accepts_synthetic_option_comparison_without_internal_source_label() -> None:
    row = {
        "slot": "Alternatives and comparators",
        "claim": (
            "Compared option alpha versus option beta on outcome effect: "
            "option alpha reduced failures by 34%; option beta left high-risk sites unchanged."
        ),
        "source": "structured option comparison",
        "anchor_terms": ["34", "compared", "option", "alpha", "versus", "beta"],
    }
    rewrite = (
        "Option alpha should be preferred over option beta because option alpha reduced failures by 34%, "
        "while option beta left high-risk sites unchanged."
    )

    assert _rewrite_mentions_anchor_row(rewrite, row)


def test_rewrite_still_requires_real_source_labels_for_source_backed_rows() -> None:
    row = {
        "slot": "Main support",
        "claim": "Option alpha reduced failures by 34% in the evaluation.",
        "source": "Evaluation Report",
        "anchor_terms": ["34", "option", "alpha", "reduced", "failures"],
    }

    assert not _rewrite_mentions_anchor_row("Option alpha reduced failures by 34%.", row)
    assert _rewrite_mentions_anchor_row("Option alpha reduced failures by 34% (Evaluation Report).", row)


def test_rewrite_repair_tones_down_generic_overclaim_language() -> None:
    rewrite = """## Decision Brief

The intervention has significant safety benefits, significantly reduced failures, and is proven safe.

**Confidence:** medium

## Why This Read

- **Proven Safety Impact:** The mapped evaluation reported fewer failures.
- **Proven Outcome:** The source reported a change.
"""

    repaired = repair_reader_memo_rewrite_candidate(rewrite, {}, {"confidence": "medium"})

    assert "significant safety benefits" not in repaired
    assert "proven safe" not in repaired.lower()
    assert "Proven Safety Impact" not in repaired
    assert "Proven Outcome" not in repaired
    assert "significantly reduced" not in repaired
    assert "source-supported safety benefits" in repaired
    assert "Mapped Safety Signal" in repaired
    assert "Mapped Outcome" in repaired


def test_rewrite_repair_fixes_near_miss_parenthetical_source_labels() -> None:
    rewrite = "The decision turns on access risk and timing issues (Method Separated Guidance)."
    contract = {
        "confidence": "medium",
        "required_evidence": [
            {
                "source": "Method Separation Guidance",
                "claim": "Access risk and timing issues affect the intervention.",
            }
        ],
    }

    repaired = repair_reader_memo_rewrite_candidate(rewrite, {}, contract)

    assert "(Method Separation Guidance)" in repaired


def test_curated_evidence_packets_drop_reference_debris() -> None:
    scaffold = {
        "concept_evidence_packets": {
            "packets": [
                {
                    "concept": "study_design_cohort",
                    "rows": [
                        {
                            "claim": "Nakamura K, Barzi F, Huxley R, et al. Heart. 2009;95(11):909-16. pmid:19196734",
                            "source": "reference",
                            "section": "scope_limits",
                            "weight": "medium",
                            "score": 5,
                        },
                        {
                            "claim": "A prospective cohort followed participants for cardiovascular outcomes over time.",
                            "source": "cohort_source",
                            "section": "main_support",
                            "weight": "high",
                            "score": 8,
                        },
                    ],
                }
            ]
        }
    }

    curated = build_curated_evidence_packets(scaffold)

    selected_text = json.dumps(curated["packets"])
    excluded_text = json.dumps(curated["curation_report"]["excluded_rows"])
    assert "prospective cohort" in selected_text
    assert "pmid" not in selected_text.lower()
    assert "pmid" in excluded_text.lower()
