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


def test_decision_memo_slots_force_core_evidence_into_memo() -> None:
    scaffold = {
        "confidence_cap": "medium",
        "quality_status": "usable_with_review",
        "map_sufficiency_report": {"status": "sufficient_for_scaffolded_briefing"},
        "concept_evidence_packets": {
            "packets": [
                {
                    "concept": "default_population",
                    "rows": [
                        {
                            "claim": "The study included generally healthy adults without cardiovascular disease at baseline.",
                            "source": "demo_sources_population_2020_full",
                            "section": "scope_limits",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
                {
                    "concept": "dose_or_threshold",
                    "rows": [
                        {
                            "claim": "Moderate intake up to one egg per day was the mapped dose boundary.",
                            "source": "demo_sources_dose_2020_full",
                            "section": "main_support",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
                {
                    "concept": "hard_outcome_endpoint",
                    "rows": [
                        {
                            "claim": "A cohort study found no increase in cardiovascular mortality at moderate intake.",
                            "source": "demo_sources_outcome_2020_full",
                            "section": "main_support",
                            "weight": "high",
                            "score": 8,
                        },
                        {
                            "claim": "A pooled cohort found higher all-cause mortality at higher egg intake.",
                            "source": "demo_sources_counter_2019_full",
                            "section": "conflicting_evidence",
                            "weight": "high",
                            "score": 8,
                        },
                    ],
                },
                {
                    "concept": "mechanism_ldl_apob",
                    "rows": [
                        {
                            "claim": "LDL and ApoB biomarkers determine whether the neutral outcome read is biologically plausible.",
                            "source": "demo_sources_lipid_2025_full",
                            "section": "method_limits",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
                {
                    "concept": "substitution_or_comparator",
                    "rows": [
                        {
                            "claim": "Replacing whole eggs with egg whites or other protein sources can change practical dietary advice.",
                            "source": "demo_sources_substitution_2021_full",
                            "section": "main_support",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
                {
                    "concept": "subgroup_diabetes_or_metabolic_risk",
                    "rows": [
                        {
                            "claim": "People with type 2 diabetes may not inherit the default-population answer.",
                            "source": "demo_sources_diabetes_2020_full",
                            "section": "scope_limits",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
            ]
        },
    }
    rendered = "## Decision Brief\n\nNeutral at moderate intake.\n\n**Confidence:** medium\n"

    package = compose_final_reader_memo_package(rendered, scaffold)
    slots = build_decision_memo_slots(package["scaffold"], rendered=rendered)
    memo = package["memo"]

    assert slots["coverage"]["missing_required_slots"] == []
    assert "LDL and ApoB" in memo
    assert "Replacing whole eggs" in memo
    assert "type 2 diabetes" in memo
    assert "higher all-cause mortality" in memo


def test_slot_extraction_recognizes_population_and_comparator_without_verbs() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The study included participants who were free of cardiovascular disease, type 2 diabetes, and cancer at baseline.",
                "source_id": "cohort",
                "role": "scope_limit",
            },
            {
                "claim_id": "c002",
                "claim": "Egg whites and plant protein are relevant replacement options for interpreting practical dietary advice.",
                "source_id": "diet",
                "role": "implementation_constraint",
            },
        ],
        "relations": [],
    }
    source_lookup = {"cohort": "Cohort", "diet": "Diet"}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(
        candidate_map,
        partition,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
    )
    slots = build_decision_slots(ledger)

    assert slots["default_population"]
    assert slots["substitution_or_comparator"]


def test_typed_evidence_slots_option_comparison_and_crux_contract_are_built() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Protected bike lanes reduced cyclist injury crashes by 34% on high-injury arterial corridors.",
                "source_id": "evaluation",
                "role": "conclusion_support",
                "entailed_by_excerpt": "yes",
            },
            {
                "claim_id": "c002",
                "claim": "Painted lanes are quicker and cheaper to implement but may not prevent encroachment on arterial streets.",
                "source_id": "paint",
                "role": "implementation_constraint",
                "entailed_by_excerpt": "yes",
            },
            {
                "claim_id": "c003",
                "claim": "Protected lane safety benefits depend on intersection design, turning conflicts, and maintenance capacity.",
                "source_id": "design",
                "role": "crux",
                "entailed_by_excerpt": "yes",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c003",
                "target_claim": "c001",
                "relation_type": "depends_on",
                "rationale": "The observed safety benefit depends on intersection design and maintenance capacity.",
            },
            {
                "relation_id": "r002",
                "source_claim": "c002",
                "target_claim": "c001",
                "relation_type": "in_tension_with",
                "rationale": "Paint is easier to deploy, while protection has stronger safety logic on arterials.",
            },
        ],
    }
    source_lookup = {"evaluation": "Evaluation", "paint": "Paint Memo", "design": "Design Guidance"}

    enriched = annotate_map_with_evidence_slots(candidate_map)
    assert "evidence_slots" in enriched["claims"][0]
    assert "outcome_or_endpoint" in enriched["claims"][0]["evidence_slots"]
    assert "cost_or_feasibility" in enriched["claims"][1]["evidence_slots"]
    assert "implementation_condition" in enriched["claims"][2]["evidence_slots"]

    partition = partition_map_evidence(enriched, source_lookup)
    ledger = build_evidence_weighting_ledger(
        enriched,
        partition,
        {"status": "usable_with_review", "score": 95, "issues": []},
        source_lookup,
    )
    slot_ledger = build_evidence_slot_ledger(ledger)
    option_comparison = build_option_comparison(
        "Should a city prioritize protected bike lanes over painted bike lanes?",
        ledger,
        enriched,
    )
    crux_contract = build_crux_contract(enriched, ledger, option_comparison)

    assert slot_ledger["slot_counts"]["implementation_condition"] >= 1
    assert [row["option"] for row in option_comparison["options"]] == ["protected bike lanes", "painted bike lanes"]
    assert any(row["criterion"] == "cost_feasibility" for row in option_comparison["tradeoffs"])
    cost_tradeoff = next(row for row in option_comparison["tradeoffs"] if row["criterion"] == "cost_feasibility")
    assert cost_tradeoff["evidence_by_option"]["painted bike lanes"]
    assert cost_tradeoff["evidence_by_option"]["protected bike lanes"] == []
    crux_text = json.dumps(crux_contract).lower()
    assert "maintenance" in crux_text or "intersection" in crux_text
    assert crux_contract["crux_count"] >= 2


def test_briefing_scaffold_exposes_option_comparison_and_crux_contract() -> None:
    candidate_map = annotate_map_with_evidence_slots(
        {
            "claims": [
                {
                    "claim_id": "c001",
                    "claim": "Protected lanes are most relevant where traffic stress makes paint insufficient.",
                    "source_id": "design",
                    "role": "conclusion_support",
                    "entailed_by_excerpt": "yes",
                },
                {
                    "claim_id": "c002",
                    "claim": "Maintenance capacity determines whether protected lanes remain usable after installation.",
                    "source_id": "ops",
                    "role": "crux",
                    "entailed_by_excerpt": "yes",
                },
            ],
            "relations": [
                {
                    "relation_id": "r001",
                    "source_claim": "c002",
                    "target_claim": "c001",
                    "relation_type": "crux_for",
                    "rationale": "Maintenance capacity gates whether physical protection can deliver the intended effect.",
                }
            ],
        }
    )

    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 95, "issues": []},
        {"design": "Design Guidance", "ops": "Operations Memo"},
        {"items": []},
        question="Should a city prioritize protected lanes over painted lanes?",
    )

    assert scaffold["option_comparison"]["options"]
    assert scaffold["crux_contract"]["cruxes"]
    assert scaffold["evidence_slot_ledger"]["slot_counts"]
    slots = build_decision_memo_slots(scaffold, rendered="## Decision Brief\n\nPrioritize protected lanes.\n")
    assert "alternatives_or_comparators" not in slots["coverage"]["missing_required_slots"]
    comparator_slot = next(slot for slot in slots["slots"] if slot["slot_id"] == "alternatives_or_comparators")
    assert len(comparator_slot["rows"]) == 1
    assert "Compared" in comparator_slot["rows"][0]["claim"]
    assert "protected lanes versus painted lanes" in comparator_slot["rows"][0]["claim"]
    assert "..." not in comparator_slot["rows"][0]["claim"]
    crux_rows = scaffold["crux_contract"]["cruxes"]
    assert any("Maintenance" in row["crux"] for row in crux_rows)


def test_repair_briefing_payload_replaces_source_only_evidence_roles() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Portable cleaners should be supplemental when targeted filtration is needed.",
                "source_id": "epa_school",
                "role": "crux",
            },
            {
                "claim_id": "c002",
                "claim": "HVAC systems must still meet ventilation code requirements.",
                "source_id": "cdc_school",
                "role": "implementation_constraint",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c002",
                "target_claim": "c001",
                "relation_type": "depends_on",
                "rationale": "Portable cleaner deployment depends on maintaining baseline HVAC ventilation.",
            }
        ],
    }
    source_lookup = {"epa_school": "EPA School Guidance", "cdc_school": "CDC School Guidance"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 95, "issues": []},
        source_lookup,
        {"items": []},
    )
    payload = {
        "decision_brief": "Use portable cleaners as supplements.",
        "confidence": "medium",
        "evidence_roles": {
            "main_support": ["EPA School Guidance"],
            "conflicting_evidence": [],
            "scope_limits": [],
            "method_limits": ["CDC School Guidance"],
        },
        "audit_trail": [],
    }

    repaired = repair_briefing_payload(payload, scaffold, source_lookup)

    assert repaired["evidence_roles"]["main_support"] != ["EPA School Guidance"]
    role_text = "\n".join(repaired["evidence_roles"]["scope_limits"] + repaired["evidence_roles"]["method_limits"])
    assert "HVAC systems must still meet ventilation code requirements" in role_text
    assert "Portable cleaner deployment depends on maintaining baseline HVAC ventilation" in "\n".join(
        repaired["audit_trail"]
    )


def test_partition_map_evidence_keeps_concern_out_of_main_support() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "eggs_c001",
                "claim": "Higher consumption of dietary cholesterol or eggs was associated with higher risk of incident CVD.",
                "source_id": "zhong_jama_2019",
                "role": "conclusion_support",
            },
            {
                "claim_id": "eggs_c002",
                "claim": "Moderate egg consumption was not associated with cardiovascular disease risk.",
                "source_id": "drouin_bmj_2020",
                "role": "conclusion_support",
            },
            {
                "claim_id": "eggs_c003",
                "claim": "The diabetes subgroup has a more uncertain risk profile.",
                "source_id": "li_2013",
                "role": "scope_limit",
            },
            {
                "claim_id": "eggs_c004",
                "claim": "The source document contains PubMed abstract text rather than the full article.",
                "source_id": "abstract_record",
                "role": "background",
            },
            {
                "claim_id": "eggs_c005",
                "claim": "Daily egg consumption was associated with lower risk among Chinese middle-aged adults.",
                "source_id": "qin_2018",
                "role": "measurement_validity",
            },
            {
                "claim_id": "eggs_c006",
                "claim": "High egg consumption was associated with higher cardiovascular risk among people with type 2 diabetes.",
                "source_id": "diabetes_meta",
                "role": "scope_limit",
            },
        ],
        "relations": [
            {
                "relation_id": "eggs_r001",
                "source_claim": "eggs_c001",
                "target_claim": "eggs_c002",
                "relation_type": "in_tension_with",
                "rationale": "Positive US cohort findings remain in tension with neutral adjusted/meta-analytic evidence.",
            }
        ],
    }

    partition = partition_map_evidence(
        candidate_map,
        {
            "zhong_jama_2019": "Zhong JAMA 2019",
            "drouin_bmj_2020": "Drouin BMJ 2020",
            "li_2013": "Li 2013",
            "abstract_record": "Abstract Record",
            "qin_2018": "Qin 2018",
            "diabetes_meta": "Diabetes Meta-analysis",
        },
    )

    main_support = "\n".join(partition["evidence_roles"]["main_support"])
    conflicts = "\n".join(partition["evidence_roles"]["conflicting_evidence"])
    scope = "\n".join(partition["evidence_roles"]["scope_limits"])
    methods = "\n".join(partition["evidence_roles"]["method_limits"])
    assert "Higher consumption" not in main_support
    assert "Higher consumption" in conflicts
    assert "not associated" in main_support
    assert "lower risk among Chinese" in main_support
    assert "High egg consumption" in conflicts
    assert "diabetes subgroup" in scope
    assert "abstract text" in methods
    assert "Daily egg consumption" not in methods


def test_repair_briefing_payload_moves_missectioned_concern_evidence() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "eggs_c001",
                "claim": "Higher egg consumption was associated with increased CVD risk.",
                "source_id": "zhong",
                "role": "conclusion_support",
            },
            {
                "claim_id": "eggs_c002",
                "claim": "Moderate egg consumption was not associated with CVD risk.",
                "source_id": "bmj",
                "role": "conclusion_support",
            },
        ],
        "relations": [],
    }
    source_lookup = {"zhong": "Zhong", "bmj": "BMJ"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        {"items": []},
    )
    payload = {
        "confidence": "medium",
        "evidence_roles": {
            "main_support": ["Higher egg consumption was associated with increased CVD risk. (Zhong)"],
            "conflicting_evidence": [],
            "scope_limits": [],
            "method_limits": ["Higher egg consumption was associated with increased CVD risk. (Zhong)"],
        },
    }

    repaired = repair_briefing_payload(payload, scaffold, source_lookup, candidate_map)

    assert "Higher egg consumption" not in "\n".join(repaired["evidence_roles"]["main_support"])
    assert "Higher egg consumption" not in "\n".join(repaired["evidence_roles"]["method_limits"])
    assert "Higher egg consumption" in "\n".join(repaired["evidence_roles"]["conflicting_evidence"])


def test_briefing_contract_is_domain_neutral_and_flags_overstatement_risks() -> None:
    partition = {
        "evidence_roles": {
            "main_support": [
                "The intervention was not associated with worse long-term outcomes.",
                "The short trial showed no adverse biomarker effects.",
            ],
            "conflicting_evidence": ["A cohort found higher risk in one subgroup."],
            "scope_limits": ["The evidence applies to high-intensity use in adults over 4 months."],
            "method_limits": ["The source contains abstract text and surrogate biomarker endpoints."],
        },
        "audit_trail": [],
    }

    contract = build_briefing_contract(
        partition,
        {"status": "usable_with_review", "score": 88, "issues": [{"severity": "risk", "issue_type": "abstract_only"}]},
    )

    lint_ids = {item["lint_id"] for item in contract["overstatement_lint"]}
    assert "null_evidence_not_benefit" in lint_ids
    assert "counterposition_visibility" in lint_ids
    assert "subgroup_to_generalization" in lint_ids
    assert "surrogate_to_hard_outcome" in lint_ids
    assert contract["scope_ledger"]["population_or_actor"]
    assert contract["scope_ledger"]["measurement_endpoint"]
    assert "low-concern" in contract["answer_frame"]["default_stance_instruction"]


def test_evidence_weighting_ledger_and_plan_prioritize_direct_evidence() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The intervention reduced hospitalization risk in adults.",
                "source_id": "trial_full",
                "source_span": "lines 1-1",
                "excerpt": "The intervention reduced hospitalization risk in adults.",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
                "supporting_sources": ["trial_full", "replication_full"],
            },
            {
                "claim_id": "c002",
                "claim": "The intervention improved a biomarker in a short abstract-only report.",
                "source_id": "abstract_only",
                "source_span": "lines 1-1",
                "excerpt": "The intervention improved a biomarker in a short abstract-only report.",
                "entailed_by_excerpt": "yes",
                "role": "measurement_validity",
                "extraction_method": "deterministic_coverage_backfill",
            },
        ],
        "relations": [],
    }
    source_lookup = {
        "trial_full": "Trial Full Text",
        "replication_full": "Replication Full Text",
        "abstract_only": "Abstract Only PubMed",
    }
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    scaffold = briefing_scaffold(candidate_map, quality_report, source_lookup, {"items": []})

    support_rows = ledger["top_evidence_by_section"]["main_support"]
    method_rows = ledger["top_evidence_by_section"]["method_limits"]
    assert support_rows[0]["claim_id"] == "c001"
    assert support_rows[0]["weight"] == "high"
    assert method_rows[0]["claim_id"] == "c002"
    assert method_rows[0]["weight"] in {"low", "medium"}
    assert "coverage_backfill_lower_weight" in method_rows[0]["modifiers"]
    assert scaffold["briefing_plan"]["paragraph_order"][0]["section"] == "bottom_line"
    assert "evidence_weighting_ledger" in scaffold


def test_decision_slots_extract_thresholds_subgroups_and_families() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "For generally healthy adults, moderate use up to 1 per day was not associated with worse CVD outcomes in a cohort study.",
                "source_id": "cohort_full",
                "source_span": "lines 1-1",
                "excerpt": "For generally healthy adults, moderate use up to 1 per day was not associated with worse CVD outcomes in a cohort study.",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "People with type 2 diabetes may have higher risk at high intake due to LDL cholesterol homeostasis.",
                "source_id": "mechanism_full",
                "source_span": "lines 1-1",
                "excerpt": "People with type 2 diabetes may have higher risk at high intake due to LDL cholesterol homeostasis.",
                "entailed_by_excerpt": "yes",
                "role": "scope_limit",
            },
            {
                "claim_id": "c003",
                "claim": "Guideline recommendations should focus on healthy dietary patterns rather than a single food.",
                "source_id": "guideline",
                "source_span": "lines 1-1",
                "excerpt": "Guideline recommendations should focus on healthy dietary patterns rather than a single food.",
                "entailed_by_excerpt": "yes",
                "role": "implementation_constraint",
            },
        ],
        "relations": [],
    }
    source_lookup = {"cohort_full": "Cohort Full", "mechanism_full": "Mechanism Full", "guideline": "Guideline"}
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    slots = build_decision_slots(ledger)
    scaffold = briefing_scaffold(candidate_map, quality_report, source_lookup, {"items": []})

    assert ledger["family_counts"]["cohort_or_observational"] >= 1
    assert ledger["family_counts"]["guideline_or_recommendation"] >= 1
    assert slots["dose_or_intensity_threshold"]
    assert slots["high_risk_subgroup"]
    assert slots["mechanism"]
    assert scaffold["decision_model"]["decision_slots"]["dose_or_intensity_threshold"]
    assert "evidence_families" in scaffold["decision_model"]


def test_map_sufficiency_report_tracks_present_and_missing_decision_contract() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "For generally healthy adults, moderate use up to one per day was not associated with worse CVD outcomes in a cohort study.",
                "source_id": "cohort_full",
                "source_span": "lines 1-1",
                "excerpt": "For generally healthy adults, moderate use up to one per day was not associated with worse CVD outcomes in a cohort study.",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    source_lookup = {"cohort_full": "Cohort Full"}
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    partition = partition_map_evidence(candidate_map, source_lookup)
    contract = build_briefing_contract(partition, quality_report)
    ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    clusters = build_proposition_clusters(candidate_map, ledger, source_lookup)
    decision_model = build_decision_model(clusters, contract, quality_report, ledger)

    report = build_map_sufficiency_report(
        candidate_map,
        question="For generally healthy adults, should this exposure be recommended compared with alternatives?",
        evidence_ledger=ledger,
        decision_model=decision_model,
        quality_report=quality_report,
    )

    assert report["schema_id"] == "map_sufficiency_report_v1"
    assert "dose_or_intensity_threshold" in report["present_decision_slots"]
    assert "substitution_or_comparator" in report["missing_expected_decision_slots"]
    assert any(item["kind"] == "acknowledge_missing_slot" for item in report["output_obligations"])
    assert report["status"] == "usable_with_named_gaps"


def test_briefing_validation_checks_sufficiency_obligations() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "For generally healthy adults, moderate use up to one per day was not associated with worse CVD outcomes in a cohort study.",
                "source_id": "cohort_full",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    source_lookup = {"cohort_full": "Cohort Full"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        {"items": []},
        question="For generally healthy adults, should this exposure be recommended compared with alternatives?",
    )

    incomplete = validate_briefing_against_scaffold("## Decision Brief\n\nUse it.\n", scaffold, candidate_map)
    complete = validate_briefing_against_scaffold(
        "## Decision Brief\n\nUse it only up to one per day. The map does not expose a substitution or comparator.\n\n## Evidence Roles\n\n### Main Support\n\n- Evidence.",
        scaffold,
        candidate_map,
    )

    assert incomplete["status"] in {"passes_with_warnings", "needs_review"}
    assert incomplete["issues"]
    assert complete["score"] > incomplete["score"]


def test_map_briefing_prompt_uses_compact_model_contract() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Moderate use up to one per day was not associated with worse outcomes.",
                "source_id": "doc",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    source_lookup = {"doc": "Doc"}
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    scaffold = briefing_scaffold(candidate_map, quality_report, source_lookup, {"items": []}, question="Should this be recommended?")

    prompt = build_map_briefing_prompt(
        candidate_map=candidate_map,
        quality_report=quality_report,
        question="Should this be recommended?",
        source_lookup=source_lookup,
        erosion_audit={"items": []},
        scaffold=scaffold,
    )

    assert "Return valid compact JSON only" in prompt
    assert "Do not return evidence_roles or audit_trail" in prompt
    assert "Prioritized map artifact:" not in prompt
    assert "evidence_roles_for_deterministic_attachment" in prompt


def test_model_parse_diagnostics_flags_truncated_fenced_json() -> None:
    diagnostics = model_parse_diagnostics('```json\n{"decision_brief": "x", "audit_trail": ["unfinished"', parse_ok=False)

    assert diagnostics["starts_with_json_fence"] is True
    assert diagnostics["looks_truncated"] is True
    assert diagnostics["brace_balance"] > 0


def test_decision_model_clusters_claims_into_neutral_default_with_subgroup_caution() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Moderate use was not associated with worse long-term outcomes in generally healthy adults.",
                "source_id": "cohort_full",
                "source_span": "lines 1-1",
                "excerpt": "Moderate use was not associated with worse long-term outcomes in generally healthy adults.",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "High use was associated with higher risk in people with a pre-existing condition.",
                "source_id": "subgroup_full",
                "source_span": "lines 1-1",
                "excerpt": "High use was associated with higher risk in people with a pre-existing condition.",
                "entailed_by_excerpt": "yes",
                "role": "scope_limit",
            },
            {
                "claim_id": "c003",
                "claim": "The trial measured a biomarker rather than hard outcome events.",
                "source_id": "trial_full",
                "source_span": "lines 1-1",
                "excerpt": "The trial measured a biomarker rather than hard outcome events.",
                "entailed_by_excerpt": "yes",
                "role": "measurement_validity",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c002",
                "target_claim": "c001",
                "relation_type": "in_tension_with",
                "rationale": "The subgroup risk limits how broadly the neutral general-population finding should be applied.",
            }
        ],
    }
    source_lookup = {"cohort_full": "Cohort Full", "subgroup_full": "Subgroup Full", "trial_full": "Trial Full"}
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    partition = partition_map_evidence(candidate_map, source_lookup)
    contract = build_briefing_contract(partition, quality_report)
    ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    clusters = build_proposition_clusters(candidate_map, ledger, source_lookup)
    decision_model = build_decision_model(clusters, contract, quality_report)

    assert clusters["cluster_count"] >= 2
    assert decision_model["default_answer"]["classification"] == "neutral_or_low_concern_under_stated_conditions"
    assert decision_model["main_reasons"]
    assert decision_model["strongest_counterarguments"]
    assert any("Do not" in item or "Avoid" in item for item in decision_model["prose_requirements"])


def test_decision_model_lint_softens_benefit_framing_for_neutral_default() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The intervention was not associated with worse outcomes.",
                "source_id": "trial",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "High-intensity use was associated with higher risk in one subgroup.",
                "source_id": "cohort",
                "role": "scope_limit",
            },
        ],
        "relations": [],
    }
    source_lookup = {"trial": "Trial", "cohort": "Cohort"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        {"items": []},
    )
    payload = {
        "decision_brief": "The intervention is associated with potentially lower long-term risk in the default case.",
        "confidence": "medium",
        "decision_implications": ["Treat it as a beneficial default."],
        "evidence_roles": {"main_support": [], "conflicting_evidence": [], "scope_limits": [], "method_limits": []},
    }

    repaired = repair_briefing_payload(payload, scaffold, source_lookup, candidate_map)

    joined = json.dumps(repaired).lower()
    assert "potentially lower" not in joined
    assert "beneficial default" not in joined
    assert "neutral or low-concern" in joined


def test_repair_briefing_payload_applies_contract_lint_to_final_prose() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The intervention was not associated with worse outcomes.",
                "source_id": "trial",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    source_lookup = {"trial": "Trial"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 88, "issues": [{"severity": "risk", "issue_type": "limited_followup"}]},
        source_lookup,
        {"items": []},
    )
    payload = {
        "decision_brief": "The intervention is neutral to potentially beneficial and clearly safe.",
        "confidence": "high",
        "decision_implications": ["Patients can safely use it."],
        "evidence_roles": {"main_support": [], "conflicting_evidence": [], "scope_limits": [], "method_limits": []},
    }

    repaired = repair_briefing_payload(payload, scaffold, source_lookup, candidate_map)

    joined = json.dumps(repaired)
    assert "potentially beneficial" not in joined
    assert "clearly safe" not in joined
    assert "low-concern under the stated conditions" in repaired["decision_brief"]


def test_expand_reader_map_references_removes_short_claim_ids() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "school_hepa_priority_c026",
                "claim": "HEPA classrooms had lower PM 2.5 than comparison classrooms.",
                "source_id": "trial",
            },
            {
                "claim_id": "school_hepa_priority_c029",
                "claim": "The health benefit of the small PM reduction remains unclear.",
                "source_id": "trial",
            },
        ],
        "relations": [
            {
                "relation_id": "school_hepa_priority_r001",
                "source_claim": "school_hepa_priority_c029",
                "target_claim": "school_hepa_priority_c026",
                "relation_type": "in_tension_with",
                "rationale": "Claim c029 limits the interpretation of Claim c026.",
            }
        ],
    }

    expanded = expand_reader_map_references(
        "Claim c026 supports the intervention, but Claim C029 limits it. Supported by trial (c026). Relation r001 matters.",
        candidate_map,
    )

    assert "Claim c026" not in expanded
    assert "Claim C029" not in expanded
    assert "(c026)" not in expanded
    assert "Relation r001" not in expanded
    assert "the mapped claim that" not in expanded
    assert "HEPA classrooms had lower PM 2.5" in expanded
    assert "This supports the intervention" in expanded
    assert "health benefit of the small PM reduction remains unclear" in expanded


def test_run_map_briefing_renders_readable_packet_without_raw_source_ids(tmp_path: Path) -> None:
    map_path = tmp_path / "generated_map.json"
    quality_path = tmp_path / "map_quality_report.json"
    map_path.write_text(
        json.dumps(
            {
                "title": "COVID map",
                "sources": ["flf_covid_case_brief"],
                "claims": [
                    {
                        "claim_id": "covid_c001",
                        "claim": "The case turns on whether priors or likelihood updates explain the disagreement.",
                        "source_id": "flf_covid_case_brief",
                        "source_span": "lines 1-2",
                        "excerpt": "Priors and likelihoods both matter.",
                        "entailed_by_excerpt": "yes",
                        "role": "crux",
                    }
                ],
                "relations": [],
            }
        ),
        encoding="utf-8",
    )
    quality_path.write_text(
        json.dumps(
            {
                "status": "usable_with_review",
                "score": 90,
                "summary": {"claim_count": 1, "relation_count": 0},
                "issues": [{"severity": "risk", "issue_type": "low_relation_type_diversity", "message": "Few relations."}],
            }
        ),
        encoding="utf-8",
    )
    fake_model = tmp_path / "fake_briefing_model.py"
    fake_model.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({\n"
        "  'decision_brief': 'flf_covid_case_brief says the decision depends on priors and likelihood updates.',\n"
        "  'confidence': 'high',\n"
        "  'decision_implications': ['Use flf_covid_case_brief as a crux source, not a settled conclusion.'],\n"
        "  'top_cruxes': [{'crux': 'covid_c001', 'why_it_matters': 'It controls interpretation.', 'current_read': 'Mixed.', 'would_change_if': 'New evidence separated priors from likelihoods.'}],\n"
        "  'evidence_roles': {'main_support': [], 'conflicting_evidence': [], 'scope_limits': ['flf_covid_case_brief has a scope boundary.'], 'method_limits': []},\n"
        "  'stress_caveats': [],\n"
        "  'audit_trail': ['Claim A states that covid_c001 matters while Claim B is missing.']\n"
        "}))\n",
        encoding="utf-8",
    )

    result = run_map_briefing(
        repo_root=tmp_path,
        map_path=map_path,
        quality_report_path=quality_path,
        question="What should a decision-maker conclude?",
        backend=f"command:{sys.executable} {fake_model}",
        output_dir=tmp_path / "briefing",
        source_titles={"flf_covid_case_brief": "FLF COVID Case Brief"},
    )

    rendered = result.briefing_path.read_text(encoding="utf-8")
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    sufficiency = json.loads(result.sufficiency_report_path.read_text(encoding="utf-8"))
    validation = json.loads(result.briefing_validation_path.read_text(encoding="utf-8"))
    assert "**Confidence:** medium" in rendered
    assert "flf_covid_case_brief" not in rendered
    assert "FLF COVID Case Brief" in rendered
    assert "The case turns on whether priors or likelihood updates explain the disagreement." in rendered
    assert "Claim A" not in rendered
    assert "Claim B" not in rendered
    assert "mapped claim" not in rendered
    assert "source-grounded finding" not in rendered
    assert summary["model_confidence"] == "high"
    assert summary["calibrated_confidence"] == "medium"
    assert summary["paths"]["map_sufficiency_report"].endswith("map_sufficiency_report.json")
    assert summary["paths"]["briefing_validation_report"].endswith("briefing_validation_report.json")
    assert sufficiency["schema_id"] == "map_sufficiency_report_v1"
    assert validation["schema_id"] == "briefing_validation_report_v1"
    assert summary["briefing_validation_status"] == validation["status"]


def test_synthesize_map_briefing_cli(monkeypatch, tmp_path: Path) -> None:
    map_path = tmp_path / "map.json"
    quality_path = tmp_path / "quality.json"
    map_path.write_text(
        json.dumps(
            {
                "sources": ["doc_a"],
                "claims": [{"claim_id": "demo_c001", "claim": "Alpha matters.", "source_id": "doc_a", "role": "crux"}],
                "relations": [],
            }
        ),
        encoding="utf-8",
    )
    quality_path.write_text(json.dumps({"status": "needs_repair", "score": 50, "issues": []}), encoding="utf-8")
    fake_model = tmp_path / "fake_model.py"
    fake_model.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'decision_brief': 'doc_a says Alpha matters.', 'confidence': 'high', 'decision_implications': [], 'top_cruxes': [], 'evidence_roles': {'main_support': [], 'conflicting_evidence': [], 'scope_limits': [], 'method_limits': []}, 'stress_caveats': [], 'audit_trail': []}))\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "missing_manifest_but_prompt_backend_needs_default.yaml",
            "synthesize",
            "map-briefing",
            "--map",
            str(map_path),
            "--quality-report",
            str(quality_path),
            "--question",
            "What follows?",
            "--backend",
            f"command:{sys.executable} {fake_model}",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    (tmp_path / "missing_manifest_but_prompt_backend_needs_default.yaml").write_text(
        "package_label: Demo\ncases: []\nworked_regions: []\ndefault_model_backend: prompt\n",
        encoding="utf-8",
    )

    assert cli.main() == 0
    rendered = (tmp_path / "out/BRIEFING.md").read_text(encoding="utf-8")
    assert "**Confidence:** low" in rendered
    assert "doc_a" not in rendered
    assert "Doc A" in rendered


def test_semantic_staged_brief_cli_runs_full_path(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
    fake_model = tmp_path / "fake_staged_brief_model.py"
    fake_model.write_text(
        "import json, sys\n"
        "prompt = sys.stdin.read()\n"
        f"if {CLAIM_EXTRACTION_PROMPT_VERSION!r} in prompt:\n"
        "    if 'Source ID: demo_case_doc_a' in prompt:\n"
        "        payload = {'claims': [{'claim': 'Alpha supports the decision.', 'span_id': 'demo_case_doc_a_s0001', 'entailed_by_excerpt': 'yes', 'role': 'conclusion_support'}]}\n"
        "    else:\n"
        "        payload = {'claims': [{'claim': 'Gamma is the key crux.', 'span_id': 'demo_case_doc_b_s0001', 'entailed_by_excerpt': 'yes', 'role': 'crux'}]}\n"
        f"elif {RELATION_PROMPT_VERSION!r} in prompt:\n"
        "    payload = {'pair_id': 'pair_001', 'source_claim': 'demo_case_c002', 'target_claim': 'demo_case_c001', 'relation_type': 'crux_for', 'rationale': 'Gamma changes whether Alpha should guide the decision.', 'crux_candidates': ['Gamma is a crux.'], 'similar_but_not_identical': []}\n"
        "elif 'Deterministic briefing scaffold:' in prompt:\n"
        "    payload = {'decision_brief': 'Demo Case Doc A and Demo Case Doc B jointly make Gamma the crux.', 'confidence': 'high', 'decision_implications': ['Treat Gamma as the first review target.'], 'top_cruxes': [], 'evidence_roles': {'main_support': [], 'conflicting_evidence': [], 'scope_limits': [], 'method_limits': []}, 'stress_caveats': [], 'audit_trail': []}\n"
        "else:\n"
        "    payload = {}\n"
        "print(json.dumps(payload))\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "package.yaml",
            "semantic",
            "staged",
            "brief",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
            "--briefing-dir",
            str(tmp_path / "brief"),
            "--artifact-dir",
            str(tmp_path / "map_artifacts"),
            "--output",
            str(tmp_path / "generated_map.json"),
            "--backend-retries",
            "0",
        ],
    )

    assert cli.main() == 0
    assert (tmp_path / "generated_map.json").exists()
    rendered = (tmp_path / "brief/BRIEFING.md").read_text(encoding="utf-8")
    assert "## Decision Brief" in rendered
    assert "Demo Case Doc A" in rendered
    assert "demo_case_doc_a" not in rendered


def _init_demo_case(monkeypatch, tmp_path: Path) -> None:
    doc_a = tmp_path / "doc_a.txt"
    doc_b = tmp_path / "doc_b.txt"
    doc_a.write_text("Alpha line.\nBeta line.\n", encoding="utf-8")
    doc_b.write_text("Gamma line.\nDelta line.\n", encoding="utf-8")
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "package.yaml",
            "case",
            "init",
            "--case-id",
            "demo_case",
            "--title",
            "Demo Case",
            "--question",
            "Can this package be initialized from arbitrary docs?",
            "--docs",
            str(doc_a),
            str(doc_b),
        ],
    )
    assert cli.main() == 0
