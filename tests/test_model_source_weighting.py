from __future__ import annotations

import json

from epistemic_case_mapper.pipeline.briefing import map_briefing_model_source_weighting as source_weighting
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_model_source_weighting_builds_source_local_prompts_and_attaches(monkeypatch) -> None:
    monkeypatch.setenv("ECM_MODEL_SOURCE_WEIGHTING_MODE", "on")
    packet = _packet()
    calls: list[str] = []

    def fake_backend(prompt, backend, **kwargs):
        calls.append(prompt)
        source_id = "s1" if '"source_id": "s1"' in prompt else "s2"
        return ModelBackendResult(
            text=json.dumps(
                {
                    "schema_id": "model_source_weight_judgment_v1",
                    "source_id": source_id,
                    "source_type": "observational_primary" if source_id == "s1" else "guidance_or_advisory",
                    "main_use": "drives_answer" if source_id == "s1" else "defines_scope",
                    "why_weight_this_way": f"{source_id} is useful for its source-local decision role.",
                    "reader_facing_limit": "Use as association evidence, not standalone causal proof." if source_id == "s1" else "Use as guidance, not independent empirical proof.",
                    "what_not_to_use_it_for": "",
                    "memo_weight_sentence": f"Use {source_id} for its direct contribution to the decision.",
                    "confidence_effect": "narrows_scope" if source_id == "s2" else "neutral",
                    "evidence_item_ids": [f"{source_id}_item"],
                }
            ),
            backend=backend,
        )

    monkeypatch.setattr(source_weighting, "run_model_backend", fake_backend)
    bundle = source_weighting.run_model_source_weight_judgments(
        packet,
        backend="ollama:test",
        backend_timeout=30,
        backend_retries=0,
    )
    updated = source_weighting.attach_model_source_weighting_to_packet(packet, bundle)

    assert len(calls) == 2
    assert "s2_item" not in calls[0]
    assert "analyst_source_hierarchy" in calls[0]
    assert "recommended_main_use" in calls[0]
    assert bundle["model_source_weighting_report"]["status"] == "ready"
    assert updated["canonical_decision_writer_packet"]["source_weight_judgments"][0]["method"] == "model_adjudicated_per_source"
    assert updated["canonical_decision_writer_packet"]["quality_report"]["source_weight_judgment_count"] == 2


def test_model_source_weighting_removes_invalid_evidence_ids(monkeypatch) -> None:
    monkeypatch.setenv("ECM_MODEL_SOURCE_WEIGHTING_MODE", "on")
    packet = _packet()

    def fake_backend(prompt, backend, **kwargs):
        return ModelBackendResult(
            text=json.dumps(
                {
                    "schema_id": "model_source_weight_judgment_v1",
                    "source_id": "s1" if '"source_id": "s1"' in prompt else "s2",
                    "source_type": "review",
                    "main_use": "support",
                    "why_weight_this_way": "The source supports the decision read.",
                    "reader_facing_limit": "",
                    "what_not_to_use_it_for": "",
                    "memo_weight_sentence": "Use this source for the main decision read.",
                    "confidence_effect": "neutral",
                    "evidence_item_ids": ["wrong_item"],
                }
            ),
            backend=backend,
        )

    monkeypatch.setattr(source_weighting, "run_model_backend", fake_backend)
    bundle = source_weighting.run_model_source_weight_judgments(
        packet,
        backend="ollama:test",
        backend_timeout=30,
        backend_retries=0,
    )

    assert bundle["model_source_weighting_report"]["status"] == "warning"
    assert "invalid_evidence_item_ids_removed" in bundle["model_source_weighting_report"]["warnings"]
    assert all("wrong_item" not in row.get("evidence_item_ids", []) for row in bundle["model_source_weight_judgments"])


def test_model_source_weighting_cannot_override_manifest_provenance_and_independence_limits(monkeypatch) -> None:
    monkeypatch.setenv("ECM_MODEL_SOURCE_WEIGHTING_MODE", "on")
    packet = _packet()
    packet["evidence_items"][0]["source_appraisal"] = {
        "status": "ready",
        "recommended_uses": ["human_review_needed"],
        "interpretation_caveats": ["This source may overlap the declared evidence cluster."],
    }
    packet["evidence_items"][0]["source_use_warnings"] = [
        "source_needs_upgrade",
        "independence_not_established",
    ]

    def fake_backend(prompt, backend, **kwargs):
        source_id = "s1" if '"source_id": "s1"' in prompt else "s2"
        return ModelBackendResult(
            text=json.dumps(
                {
                    "schema_id": "model_source_weight_judgment_v1",
                    "source_id": source_id,
                    "source_type": "observational_primary",
                    "main_use": "drives_answer",
                    "why_weight_this_way": "The source independently confirms the answer.",
                    "reader_facing_limit": "",
                    "what_not_to_use_it_for": "",
                    "memo_weight_sentence": "This source independently confirms the decision.",
                    "confidence_effect": "raises_confidence",
                    "evidence_item_ids": [f"{source_id}_item"],
                }
            ),
            backend=backend,
        )

    monkeypatch.setattr(source_weighting, "run_model_backend", fake_backend)
    bundle = source_weighting.run_model_source_weight_judgments(
        packet,
        backend="ollama:test",
        backend_timeout=30,
        backend_retries=0,
    )

    constrained = next(row for row in bundle["model_source_weight_judgments"] if row["source_ids"] == ["s1"])
    assert constrained["main_use"] == "contextualizes"
    assert constrained["confidence_effect"] == "neutral"
    assert constrained["method"] == "model_adjudicated_per_source"
    assert constrained["constraint_method"] == "deterministic_manifest_source_use_guard"
    assert set(constrained["source_appraisal_constraints"]) == {
        "human_review_needed_not_load_bearing",
        "independence_not_established",
    }
    assert "independent confirmation" in constrained["what_not_to_use_it_for"][1]
    assert "only as context" in constrained["memo_weight_sentence"]
    assert bundle["model_source_weighting_report"]["source_appraisal_constraint_count"] == 2


def test_model_source_weighting_skips_prompt_backend(monkeypatch) -> None:
    monkeypatch.setenv("ECM_MODEL_SOURCE_WEIGHTING_MODE", "on")
    bundle = source_weighting.run_model_source_weight_judgments(
        _packet(),
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
    )

    assert bundle["model_source_weight_judgments"] == []
    assert bundle["model_source_weighting_report"]["status"] == "skipped"
    assert bundle["model_source_weighting_report"]["reason"] == "prompt_backend"


def test_model_source_weighting_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ECM_MODEL_SOURCE_WEIGHTING_MODE", raising=False)

    bundle = source_weighting.run_model_source_weight_judgments(
        _packet(),
        backend="ollama:test",
        backend_timeout=30,
        backend_retries=0,
    )

    assert bundle["model_source_weight_judgments"] == []
    assert bundle["model_source_weighting_report"]["status"] == "skipped"
    assert bundle["model_source_weighting_report"]["reason"] == "disabled_by_ecm_model_source_weighting_mode"


def _packet() -> dict:
    return {
        "decision_question": "Should option A be adopted?",
        "answer_spine": {"default_read": "Adopt option A with monitoring."},
        "source_trail": [
            {"source_id": "s1", "source_label": "Outcome Study 2025"},
            {"source_id": "s2", "source_label": "Guidance Note 2024"},
        ],
        "evidence_items": [
            {
                "item_id": "s1_item",
                "source_ids": ["s1"],
                "reader_claim": "Outcome evidence favors option A.",
                "decision_relevance": "Direct outcome evidence.",
                "role": "strongest_support",
            },
            {
                "item_id": "s2_item",
                "source_ids": ["s2"],
                "reader_claim": "Guidance defines implementation scope.",
                "decision_relevance": "Scope guidance.",
                "role": "scope_boundary",
            },
        ],
        "canonical_decision_writer_packet": {
            "decision_question": "Should option A be adopted?",
            "decision_brief_skeleton": {"direct_answer": "Adopt option A.", "scope": "Matched settings.", "confidence": "medium", "main_reason": "Outcome evidence.", "strongest_counterweight": "Scope uncertainty.", "counterweight_disposition": "Monitor."},
            "decision_answer_classification": {"answer_shape": "single_stance"},
            "source_weight_judgments": [
                {"source_ids": ["s1"], "main_use": "drives_answer", "why_weight_this_way": "Fallback support.", "evidence_item_ids": ["s1_item"]},
                {"source_ids": ["s2"], "main_use": "defines_scope", "why_weight_this_way": "Fallback scope.", "evidence_item_ids": ["s2_item"]},
            ],
            "source_weight_judgment_report": {"status": "ready"},
            "source_hierarchy": {
                "schema_id": "source_weight_hierarchy_v1",
                "hierarchy_thesis": "Outcome evidence drives; guidance bounds.",
                "lanes": {
                    "primary_answer_drivers": [{"source_ids": ["s1"], "rationale": "Outcome source."}],
                    "scope_boundary_sources": [{"source_ids": ["s2"], "rationale": "Guidance source."}],
                },
                "source_accounting": [
                    {"source_id": "s1", "primary_lane": "primary_answer_drivers", "rationale": "Outcome source."},
                    {"source_id": "s2", "primary_lane": "scope_boundary_sources", "rationale": "Guidance source."},
                ],
            },
            "source_hierarchy_report": {"status": "ready"},
            "source_weighted_answer_frame": {"lanes": {"primary_answer_drivers": [{"source_ids": ["s1"]}]}},
            "source_weight_notes": [{"source_ids": ["s1"], "decision_directness": "direct"}],
            "priority_evidence": [{"source_ids": ["s1"]}],
            "counterweight_dispositions": [{"source_ids": ["s2"]}],
            "mandatory_retention_checklist": [],
            "organized_evidence_inventory": {"items": [{"source_ids": ["s1"]}]},
            "evidence_language_contracts": [{"source_ids": ["s1"]}],
            "evidence_weighted_argument_spine": {"steps": [{"source_ids": ["s1"]}], "quality_report": {"status": "ready"}},
        },
    }
