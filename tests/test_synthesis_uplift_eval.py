from __future__ import annotations

from scripts.run_synthesis_uplift_eval import (
    Loss,
    _compile_rewrite_requirements,
    _dedupe_text_items,
    _deterministic_requirement_coverage,
    _deterministic_patch_synthesis,
    _needs_repair,
    _packet_scaffold,
    _packet_scaffold_prompt_block,
    _phrase_present_in_synthesis,
    _render_unparsed_structured_packet,
    _render_synthesis_packet,
)


def test_compile_rewrite_requirements_links_losses_to_map_ids_and_sources() -> None:
    losses = [
        Loss(
            loss_id="demo_loss_001",
            loss_type="scope collapse",
            lost_item="The baseline merges subgroup caveats instead of separating high LDL and diabetes.",
            flat_baseline_omission="High LDL and diabetes appear only in a final caveat list.",
            case_map_preserves="`demo_c001`, `demo_c002`, `demo_r001`.",
        )
    ]
    map_payload = {
        "worked_map": {
            "claims": [
                {
                    "claim_id": "demo_c001",
                    "claim": "High LDL changes how the recommendation should be applied.",
                    "source_id": "aha_guidance",
                    "source_span": "lines 10-12",
                    "excerpt": "People with high LDL should limit dietary cholesterol.",
                },
                {
                    "claim_id": "demo_c002",
                    "claim": "Diabetes evidence has a separate source basis.",
                    "source_id": "bmj_cohort",
                    "source_span": "lines 20-22",
                    "excerpt": "Diabetes subgroup estimates were uncertain.",
                },
            ],
            "relations": [
                {
                    "relation_id": "demo_r001",
                    "source_claim": "demo_c001",
                    "target_claim": "demo_c002",
                    "relation_type": "similar_to",
                    "rationale": "Both are subgroup caveats but they should not be merged.",
                }
            ],
        }
    }
    stress_report = {"findings": [], "reference_issues": []}

    requirements = _compile_rewrite_requirements(losses, map_payload, stress_report)

    assert len(requirements) == 1
    requirement = requirements[0]
    assert requirement.loss_id == "demo_loss_001"
    assert requirement.claim_ids == ("demo_c001", "demo_c002")
    assert requirement.relation_ids == ("demo_r001",)
    assert "aha_guidance lines 10-12" in requirement.source_refs
    assert "bmj_cohort lines 20-22" in requirement.source_refs
    assert any("High LDL changes" in anchor for anchor in requirement.claim_anchors)
    assert any("similar_to" in anchor for anchor in requirement.relation_anchors)
    assert "diabetes" in requirement.required_terms
    assert "omission" not in requirement.required_terms
    assert requirement.claim_roles == ()
    assert requirement.relation_types == ("similar_to",)
    assert "Both are subgroup caveats but they should not be merged." in requirement.reader_anchors


def test_deterministic_requirement_coverage_scores_clear_partial_and_missing() -> None:
    losses = [
        Loss(
            loss_id="demo_loss_001",
            loss_type="endpoint collapse",
            lost_item="Randomized trials measured LDL-c and HDL-c biomarkers rather than cardiovascular events.",
            flat_baseline_omission="The baseline mentions biomarkers without the endpoint boundary.",
            case_map_preserves="`demo_c001`.",
        )
    ]
    map_payload = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "The trial measured LDL-c and HDL-c biomarkers rather than cardiovascular events.",
                "source_id": "trial",
                "source_span": "lines 1-3",
                "excerpt": "LDL-c and HDL-c were endpoints.",
            }
        ],
        "relations": [],
    }
    requirements = _compile_rewrite_requirements(losses, map_payload, {"findings": [], "reference_issues": []})

    clear = _deterministic_requirement_coverage(
        "The trial measured LDL-c and HDL-c biomarkers rather than cardiovascular events.",
        requirements,
    )
    partial = _deterministic_requirement_coverage("This mentions biomarkers only.", requirements)
    missing = _deterministic_requirement_coverage("This discusses unrelated source quality.", requirements)

    assert clear["clear_count"] == 1
    assert partial["partial_count"] == 1
    assert missing["missing_count"] == 1


def test_directional_phrase_must_be_preserved_for_clear_coverage() -> None:
    losses = [
        Loss(
            loss_id="demo_loss_001",
            loss_type="direction reversed",
            lost_item="The baseline loses that LHC products may be slower than cosmic-ray products.",
            flat_baseline_omission="The baseline mentions velocity without direction.",
            case_map_preserves="`demo_c001`.",
        )
    ]
    map_payload = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "LHC products may be slower than cosmic-ray products.",
                "source_id": "safety_review",
                "source_span": "lines 1-2",
                "excerpt": "LHC products may be slower.",
            }
        ],
        "relations": [],
    }
    requirements = _compile_rewrite_requirements(losses, map_payload, {"findings": [], "reference_issues": []})

    preserved = _deterministic_requirement_coverage(
        "The key caveat is that LHC products may be slower than cosmic-ray products.",
        requirements,
    )
    reversed_direction = _deterministic_requirement_coverage(
        "The key caveat is that cosmic-ray products may be slower than LHC products.",
        requirements,
    )

    assert preserved["clear_count"] == 1
    assert reversed_direction["clear_count"] == 0
    assert reversed_direction["partial_count"] == 1
    assert _needs_repair(preserved) is False
    assert _needs_repair(reversed_direction) is True

    patched = _deterministic_patch_synthesis(
        "The key caveat is that cosmic-ray products may be slower than LHC products.",
        reversed_direction,
        requirements,
    )
    patched_coverage = _deterministic_requirement_coverage(patched, requirements)

    assert "## Decision Brief" in patched
    assert "## What Could Change the Decision" in patched
    assert "## Evidence Roles" in patched
    assert "## Audit Trail" in patched
    assert "LHC products may be slower than cosmic-ray products" in patched
    assert "cosmic-ray products may be slower than LHC products" not in patched
    assert patched_coverage["clear_count"] == 1


def test_render_synthesis_packet_structures_decision_support_before_audit() -> None:
    rendered = _render_synthesis_packet(
        {
            "decision_brief": "The better decision posture is conditional caution.",
            "confidence": "medium",
            "decision_implications": ["Do not treat biomarker evidence as outcome evidence."],
            "top_cruxes": [
                {
                    "crux": "Endpoint boundary",
                    "why_it_matters": "It changes how much the RCTs should move the decision.",
                    "current_read": "The trials measure lipid markers.",
                    "would_change_if": "A long-term outcome trial showed the same direction.",
                }
            ],
            "evidence_roles": {
                "main_support": ["Guidelines support a diet-pattern recommendation."],
                "conflicting_evidence": ["Observational results differ across studies."],
                "scope_limits": ["The advice is weaker for high-risk subgroups."],
                "method_limits": ["Replacement models are statistical, not observed swaps."],
            },
            "stress_caveats": ["Check whether uncertainty is overstated."],
            "audit_trail": ["Endpoint evidence is not event evidence."],
        }
    )

    assert rendered.startswith("## Decision Brief")
    assert "The better decision posture is conditional caution." in rendered
    assert "**Confidence:** medium" in rendered
    assert "## Decision Implications" in rendered
    assert "- Do not treat biomarker evidence as outcome evidence." in rendered
    assert "## What Could Change the Decision" in rendered
    assert "| Endpoint boundary | It changes how much the RCTs should move the decision." in rendered
    assert "## Evidence Roles" in rendered
    assert "### Main Support" in rendered
    assert "- Guidelines support a diet-pattern recommendation." in rendered
    assert "## Decision-Relevant Caveats" in rendered
    assert "- Check whether uncertainty is overstated." in rendered
    assert "## Audit Trail" in rendered
    assert "- Endpoint evidence is not event evidence." in rendered


def test_render_synthesis_packet_expands_bare_map_ids_in_reader_sections() -> None:
    rendered = _render_synthesis_packet(
        {
            "decision_brief": "The decision depends on the endpoint boundary.",
            "confidence": "medium",
            "decision_implications": ["demo_c001"],
            "top_cruxes": [
                {
                    "crux": "demo_c001",
                    "why_it_matters": "demo_r001",
                    "current_read": "Current evidence is limited.",
                    "would_change_if": "Outcomes matched biomarkers.",
                }
            ],
            "evidence_roles": {
                "main_support": ["demo_c001"],
                "conflicting_evidence": ["demo_r001"],
                "scope_limits": [],
                "method_limits": [],
            },
            "stress_caveats": [],
            "audit_trail": ["demo_c001"],
        },
        map_payload={
            "claims": [
                {
                    "claim_id": "demo_c001",
                    "claim": "The trial measured biomarkers rather than cardiovascular outcomes.",
                    "role": "method_limit",
                }
            ],
            "relations": [
                {
                    "relation_id": "demo_r001",
                    "source_claim": "demo_c001",
                    "target_claim": "demo_c002",
                    "relation_type": "limits",
                    "rationale": "Biomarkers do not settle long-term outcomes.",
                }
            ],
        },
    )

    assert "- The trial measured biomarkers rather than cardiovascular outcomes." in rendered
    assert "role=method_limit" not in rendered
    assert "demo_c001" not in rendered
    assert "demo_r001" not in rendered
    assert "Biomarkers do not settle long-term outcomes." in rendered


def test_render_synthesis_packet_backfills_empty_evidence_roles_from_requirements() -> None:
    requirement = Loss(
        loss_id="demo_loss_001",
        loss_type="endpoint collapse",
        lost_item="The synthesis loses that randomized evidence measured biomarkers rather than events.",
        flat_baseline_omission="The baseline mentions trials but not the endpoint boundary.",
        case_map_preserves="`demo_c001`.",
    )
    map_payload = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "The trial measured LDL-c biomarkers rather than cardiovascular events.",
                "source_id": "trial",
                "source_span": "lines 1-3",
                "excerpt": "LDL-c was the endpoint.",
            }
        ],
        "relations": [],
    }
    requirements = _compile_rewrite_requirements([requirement], map_payload, {"findings": [], "reference_issues": []})

    rendered = _render_synthesis_packet(
        {
            "decision_brief": "The decision should treat trial evidence as indirect.",
            "confidence": "medium",
            "decision_implications": [],
            "top_cruxes": [],
            "evidence_roles": {
                "main_support": [],
                "conflicting_evidence": [],
                "scope_limits": [],
                "method_limits": [],
            },
            "stress_caveats": [],
            "audit_trail": [],
        },
        map_payload=map_payload,
        requirements=requirements,
    )

    assert "### Method Limits" in rendered
    assert "- The trial measured LDL-c biomarkers rather than cardiovascular events" in rendered
    assert "### Main Support" in rendered
    assert "source=trial lines 1-3" not in rendered


def test_evidence_role_backfill_uses_map_content_not_baseline_loss_text() -> None:
    loss = Loss(
        loss_id="demo_loss_001",
        loss_type="study-design tension flattened",
        lost_item="The flat baseline states BMJ and JAMA findings sequentially but loses their tension.",
        flat_baseline_omission="The baseline reports both results without an explicit conflict edge.",
        case_map_preserves="`demo_c001`, `demo_c002`, `demo_r001`.",
    )
    map_payload = {
        "claims": [
            {"claim_id": "demo_c001", "claim": "BMJ reports no overall association for moderate intake."},
            {"claim_id": "demo_c002", "claim": "JAMA reports a positive dose-response association."},
        ],
        "relations": [
            {
                "relation_id": "demo_r001",
                "source_claim": "demo_c002",
                "target_claim": "demo_c001",
                "relation_type": "in_tension_with",
                "rationale": "JAMA and BMJ point in different directions and require method comparison.",
            }
        ],
    }
    requirements = _compile_rewrite_requirements([loss], map_payload, {"findings": [], "reference_issues": []})

    rendered = _render_synthesis_packet(
        {
            "decision_brief": "The decision depends on study design.",
            "confidence": "medium",
            "decision_implications": [],
            "top_cruxes": [],
            "evidence_roles": {
                "main_support": [],
                "conflicting_evidence": [],
                "scope_limits": [],
                "method_limits": [],
            },
            "stress_caveats": [],
            "audit_trail": [],
        },
        map_payload=map_payload,
        requirements=requirements,
    )

    assert "JAMA and BMJ point in different directions and require method comparison." in rendered
    assert "The flat baseline states" not in rendered
    assert "The baseline reports" not in rendered


def test_backfill_routes_by_relation_type_without_loss_keywords() -> None:
    loss = Loss(
        loss_id="demo_loss_001",
        loss_type="lost distinction",
        lost_item="The synthesis loses a map relation.",
        flat_baseline_omission="The baseline compresses it.",
        case_map_preserves="`demo_c001`, `demo_c002`, `demo_r001`.",
    )
    map_payload = {
        "claims": [
            {"claim_id": "demo_c001", "claim": "Source A reports benefit."},
            {"claim_id": "demo_c002", "claim": "Source B reports no benefit."},
        ],
        "relations": [
            {
                "relation_id": "demo_r001",
                "source_claim": "demo_c001",
                "target_claim": "demo_c002",
                "relation_type": "in_tension_with",
                "rationale": "Source A and Source B point in different directions.",
            }
        ],
    }
    requirements = _compile_rewrite_requirements([loss], map_payload, {"findings": [], "reference_issues": []})

    rendered = _render_synthesis_packet(
        {
            "decision_brief": "The decision is unsettled.",
            "confidence": "low",
            "decision_implications": [],
            "top_cruxes": [],
            "evidence_roles": {
                "main_support": [],
                "conflicting_evidence": [],
                "scope_limits": [],
                "method_limits": [],
            },
            "stress_caveats": [],
            "audit_trail": [],
        },
        map_payload=map_payload,
        requirements=requirements,
    )

    conflict_section = rendered.split("### Conflicting Evidence", 1)[1].split("### Scope Limits", 1)[0]
    assert "Source A and Source B point in different directions." in conflict_section


def test_packet_scaffold_guides_model_with_sectioned_map_content() -> None:
    loss = Loss(
        loss_id="demo_loss_001",
        loss_type="lost distinction",
        lost_item="The flat baseline loses a map relation.",
        flat_baseline_omission="The baseline compresses it.",
        case_map_preserves="`demo_c001`, `demo_c002`, `demo_r001`.",
    )
    map_payload = {
        "claims": [
            {"claim_id": "demo_c001", "claim": "Source A reports benefit."},
            {"claim_id": "demo_c002", "claim": "Source B reports no benefit."},
        ],
        "relations": [
            {
                "relation_id": "demo_r001",
                "source_claim": "demo_c001",
                "target_claim": "demo_c002",
                "relation_type": "in_tension_with",
                "rationale": "Source A and Source B point in different directions.",
            }
        ],
    }
    requirements = _compile_rewrite_requirements([loss], map_payload, {"findings": [], "reference_issues": []})

    scaffold = _packet_scaffold(requirements)
    scaffold_text = _packet_scaffold_prompt_block(requirements)

    assert scaffold["evidence_roles"]["conflicting_evidence"] == [
        "Source A and Source B point in different directions."
    ]
    assert scaffold["crux_candidates"][0]["candidate_crux"] == "Source A and Source B point in different directions."
    assert scaffold["audit_trail"] == ["demo_loss_001: Source A and Source B point in different directions."]
    assert "flat baseline" in scaffold["forbidden_reader_language"]
    required_scaffold_text = "\n".join(
        [
            *scaffold["evidence_roles"]["conflicting_evidence"],
            *[item["candidate_crux"] for item in scaffold["crux_candidates"]],
            *scaffold["audit_trail"],
        ]
    )
    assert "flat baseline" not in required_scaffold_text
    assert "baseline compresses" not in scaffold_text


def test_backfill_routes_by_claim_role_without_loss_keywords() -> None:
    loss = Loss(
        loss_id="demo_loss_001",
        loss_type="lost distinction",
        lost_item="The synthesis loses a map claim.",
        flat_baseline_omission="The baseline compresses it.",
        case_map_preserves="`demo_c001`.",
    )
    map_payload = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "The trial measured a proxy endpoint rather than patient outcomes.",
                "role": "measurement_validity_caveat",
            }
        ],
        "relations": [],
    }
    requirements = _compile_rewrite_requirements([loss], map_payload, {"findings": [], "reference_issues": []})

    rendered = _render_synthesis_packet(
        {
            "decision_brief": "The decision should treat the evidence as indirect.",
            "confidence": "medium",
            "decision_implications": [],
            "top_cruxes": [],
            "evidence_roles": {
                "main_support": [],
                "conflicting_evidence": [],
                "scope_limits": [],
                "method_limits": [],
            },
            "stress_caveats": [],
            "audit_trail": [],
        },
        map_payload=map_payload,
        requirements=requirements,
    )

    method_section = rendered.split("### Method Limits", 1)[1].split("## Decision-Relevant Caveats", 1)[0]
    assert "The trial measured a proxy endpoint rather than patient outcomes." in method_section


def test_deterministic_patch_uses_structured_slot_not_requirement_instruction() -> None:
    loss = Loss(
        loss_id="demo_loss_001",
        loss_type="lost distinction",
        lost_item="The synthesis loses a map claim.",
        flat_baseline_omission="The baseline compresses it.",
        case_map_preserves="`demo_c001`.",
    )
    map_payload = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "The decision turns on whether the measured endpoint is a proxy.",
                "role": "measurement_validity_caveat",
            }
        ],
        "relations": [],
    }
    requirements = _compile_rewrite_requirements([loss], map_payload, {"findings": [], "reference_issues": []})
    coverage = _deterministic_requirement_coverage("Unrelated synthesis.", requirements)

    patched = _deterministic_patch_synthesis("Unrelated synthesis.", coverage, requirements)

    assert "The decision turns on whether the measured endpoint is a proxy." in patched
    assert "Explicitly avoid this baseline failure" not in patched
    assert "The baseline compresses it" not in patched


def test_render_filters_meta_audit_and_backfills_map_audit() -> None:
    loss = Loss(
        loss_id="demo_loss_001",
        loss_type="lost distinction",
        lost_item="The synthesis loses a map claim.",
        flat_baseline_omission="The baseline compresses it.",
        case_map_preserves="`demo_c001`.",
    )
    map_payload = {
        "claims": [
            {
                "claim_id": "demo_c001",
                "claim": "The endpoint is a proxy rather than a patient outcome.",
            }
        ],
        "relations": [],
    }
    requirements = _compile_rewrite_requirements([loss], map_payload, {"findings": [], "reference_issues": []})

    rendered = _render_synthesis_packet(
        {
            "decision_brief": "The endpoint boundary matters.",
            "confidence": "medium",
            "decision_implications": [],
            "top_cruxes": [],
            "evidence_roles": {
                "main_support": [],
                "conflicting_evidence": [],
                "scope_limits": [],
                "method_limits": [],
            },
            "stress_caveats": [],
            "audit_trail": [
                "The flat baseline loses the endpoint distinction.",
                "Independent audit item worth keeping.",
            ],
        },
        map_payload=map_payload,
        requirements=requirements,
    )

    audit_section = rendered.split("## Audit Trail", 1)[1]
    assert "Independent audit item worth keeping." in audit_section
    assert "demo_loss_001: The endpoint is a proxy rather than a patient outcome." in audit_section
    assert "flat baseline" not in audit_section


def test_overlap_dedupe_removes_near_duplicate_scaffold_items() -> None:
    items = _dedupe_text_items(
        [
            "Regional and diabetes heterogeneity qualifies BMJ's overall null finding.",
            "Regional and diabetes heterogeneity qualifies the BMJ null finding.",
            "Replacement context affects what egg risk means in actual dietary choices.",
        ]
    )

    assert items == [
        "Regional and diabetes heterogeneity qualifies BMJ's overall null finding.",
        "Replacement context affects what egg risk means in actual dietary choices.",
    ]


def test_phrase_coverage_accepts_close_reader_paraphrase() -> None:
    phrase = "The guideline cholesterol recommendation depends on a policy process using preponderance of evidence, not on one study alone"
    synthesis = (
        "Guideline recommendations are policy processes based on preponderance of evidence, "
        "not single studies."
    )

    assert _phrase_present_in_synthesis(phrase, synthesis) is True
    assert _phrase_present_in_synthesis(phrase, "Guidelines mention eggs briefly.") is False


def test_render_unparsed_structured_packet_hides_truncated_json_from_reader() -> None:
    rendered = _render_unparsed_structured_packet(
        '```json\n{"decision_brief": "The decision brief survived truncation.", '
        '"confidence": "medium", "evidence_roles": {"main_support": ["BMJ 20'
    )

    assert rendered.startswith("## Decision Brief")
    assert "The decision brief survived truncation." in rendered
    assert "**Confidence:** medium" in rendered
    assert "```json" not in rendered
    assert '"evidence_roles"' not in rendered
    assert "## Audit Trail" in rendered
    assert "truncated or invalid structured packet" in rendered
