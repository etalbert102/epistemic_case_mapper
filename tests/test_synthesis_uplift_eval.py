from __future__ import annotations

from scripts.run_synthesis_uplift_eval import (
    Loss,
    _compile_rewrite_requirements,
    _deterministic_requirement_coverage,
    _deterministic_patch_synthesis,
    _needs_repair,
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

    assert "## Readable Synthesis" in patched
    assert "## Mapped Distinctions Preserved" in patched
    assert "## Stress-Test Caveats" in patched
    assert "LHC products may be slower than cosmic-ray products" in patched
    assert "cosmic-ray products may be slower than LHC products" not in patched
    assert patched_coverage["clear_count"] == 1


def test_render_synthesis_packet_separates_prose_from_audit_sections() -> None:
    rendered = _render_synthesis_packet(
        {
            "synthesis": "This is readable prose.",
            "mapped_distinctions": ["Endpoint evidence is not event evidence."],
            "stress_caveats": ["Check whether uncertainty is overstated."],
        }
    )

    assert rendered.startswith("## Readable Synthesis")
    assert "This is readable prose." in rendered
    assert "## Mapped Distinctions Preserved" in rendered
    assert "- Endpoint evidence is not event evidence." in rendered
    assert "## Stress-Test Caveats" in rendered
    assert "- Check whether uncertainty is overstated." in rendered
