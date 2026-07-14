from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_decision_usefulness import (
    build_decision_usefulness_context,
    build_decision_usefulness_prompt,
    build_decision_usefulness_quality_report,
    compact_decision_usefulness_for_prompt,
    normalize_decision_usefulness_packet,
    run_decision_usefulness_builder,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle

from test_decision_briefing_packet import _scaffold


def _canonical_packet() -> dict:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    memo_ready = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    return memo_ready["canonical_decision_writer_packet"]


def test_decision_usefulness_context_uses_canonical_packet_without_debug_surfaces() -> None:
    canonical = _canonical_packet()

    context = build_decision_usefulness_context(canonical)

    assert context["schema_id"] == "decision_usefulness_context_v1"
    assert context["decision_question"] == "Should the city adopt option A for flood protection?"
    assert context["decision_brief_skeleton"]
    assert context["source_weighting"]["judgments"]
    assert context["argument_spine"]["steps"]
    assert context["organized_evidence_inventory"]["lanes"]
    assert "parse_report" not in str(context)
    assert "prompt" not in str(context)


def test_decision_usefulness_prompt_instructs_model_not_to_force_options() -> None:
    context = build_decision_usefulness_context(_canonical_packet())

    prompt = build_decision_usefulness_prompt(context)

    assert "decision_usefulness_packet_v1" in prompt
    assert "do not force fake alternatives" in prompt
    assert "diagnostic evidence" in prompt
    assert "Canonical decision context" in prompt


def test_decision_usefulness_packet_normalizes_and_validates_references() -> None:
    canonical = _canonical_packet()
    evidence_id = canonical["priority_evidence"][0]["item_id"]
    source_id = canonical["priority_evidence"][0]["source_ids"][0]

    packet = normalize_decision_usefulness_packet(
        {
            "decision_question": canonical["decision_question"],
            "answer_shape": "multi option",
            "recommended_stance": {
                "stance": "Adopt option A if implementation risk is bounded.",
                "confidence": "medium",
                "source_ids": [source_id],
                "evidence_item_ids": [evidence_id],
            },
            "decision_options": [
                {"label": "adopt option A", "source_ids": [source_id], "evidence_item_ids": [evidence_id]},
                {"label": "delay adoption"},
            ],
            "decision_criteria": [
                {"label": "flood protection", "criterion_type": "benefit", "evidence_item_ids": [evidence_id]}
            ],
            "option_criteria_matrix": [
                {
                    "option_id": "option_001",
                    "criterion_id": "criterion_001",
                    "assessment": "favors",
                    "rationale": "Outcome evidence favors option A.",
                    "source_ids": [source_id],
                    "evidence_item_ids": [evidence_id],
                }
            ],
            "diagnostic_evidence": [
                {
                    "evidence_item_ids": [evidence_id],
                    "source_ids": [source_id],
                    "distinguishes": ["option_001", "option_002"],
                    "diagnosticity": "high",
                    "why_diagnostic": "It distinguishes adoption from delay.",
                }
            ],
            "tradeoffs": [{"tradeoff": "More immediate protection versus implementation risk."}],
            "cruxes_and_thresholds": [{"crux": "Whether implementation risk is bounded."}],
            "premortem": [{"failure_mode": "Implementation risk overwhelms expected protection."}],
            "monitoring_triggers": [{"trigger": "New implementation failure evidence.", "priority": "high"}],
        },
        canonical_packet=canonical,
    )

    assert packet["schema_id"] == "decision_usefulness_packet_v1"
    assert packet["answer_shape"] == "multi_option"
    assert packet["decision_options"][0]["option_id"] == "option_001"
    assert packet["decision_criteria"][0]["criterion_id"] == "criterion_001"
    assert packet["quality_report"]["status"] == "ready"
    assert packet["summary"]["tradeoff_count"] == 1


def test_decision_usefulness_quality_report_flags_bad_ids_and_sparse_matrix() -> None:
    canonical = _canonical_packet()
    packet = normalize_decision_usefulness_packet(
        {
            "decision_question": canonical["decision_question"],
            "decision_options": [{"option_id": "option_001", "label": "adopt", "source_ids": ["missing_source"]}],
            "decision_criteria": [{"criterion_id": "criterion_001", "label": "outcomes"}],
            "option_criteria_matrix": [
                {
                    "option_id": "missing_option",
                    "criterion_id": "criterion_001",
                    "evidence_item_ids": ["missing_evidence"],
                }
            ],
        },
        canonical_packet=canonical,
    )

    report = build_decision_usefulness_quality_report(packet, canonical_packet=canonical)

    assert report["status"] == "warning"
    assert "invalid_source_or_evidence_references" in report["warnings"]
    assert "invalid_option_or_criterion_references" in report["warnings"]
    assert report["invalid_reference_count"] >= 1
    assert report["invalid_matrix_reference_count"] == 1


def test_compact_decision_usefulness_for_prompt_keeps_decision_critical_fields() -> None:
    canonical = _canonical_packet()
    packet = normalize_decision_usefulness_packet(
        {
            "decision_question": canonical["decision_question"],
            "recommended_stance": {"stance": "Adopt option A conditionally."},
            "decision_options": [{"label": "adopt option A"}],
            "decision_criteria": [{"label": "flood protection"}],
            "tradeoffs": [{"tradeoff": "Protection versus implementation burden."}],
            "cruxes_and_thresholds": [{"crux": "Whether burden crosses the acceptable threshold."}],
            "monitoring_triggers": [{"trigger": "New burden evidence."}],
        },
        canonical_packet=canonical,
    )

    compact = compact_decision_usefulness_for_prompt(packet)

    assert compact["schema_id"] == "decision_usefulness_packet_v1"
    assert compact["recommended_stance"]["stance"] == "Adopt option A conditionally."
    assert compact["decision_options"][0]["label"] == "adopt option A"
    assert compact["tradeoffs"][0]["tradeoff"] == "Protection versus implementation burden."


def test_run_decision_usefulness_builder_skips_on_prompt_backend() -> None:
    canonical = _canonical_packet()

    result = run_decision_usefulness_builder(
        canonical_packet=canonical,
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["decision_usefulness_report"]["status"] == "skipped_prompt_backend"
    assert result["decision_usefulness_prompt"]
    assert result["decision_usefulness_packet"]["answer_shape"] == "insufficient_information"


def test_run_decision_usefulness_builder_parses_fake_backend(monkeypatch) -> None:
    canonical = _canonical_packet()
    evidence_id = canonical["priority_evidence"][0]["item_id"]
    source_id = canonical["priority_evidence"][0]["source_ids"][0]

    class FakeResult:
        text = f"""
        {{
          "schema_id": "decision_usefulness_packet_v1",
          "decision_question": "{canonical['decision_question']}",
          "answer_shape": "single_stance",
          "recommended_stance": {{"stance": "Adopt option A conditionally.", "source_ids": ["{source_id}"], "evidence_item_ids": ["{evidence_id}"]}},
          "decision_options": [{{"option_id": "option_001", "label": "adopt option A", "source_ids": ["{source_id}"], "evidence_item_ids": ["{evidence_id}"]}}],
          "decision_criteria": [{{"criterion_id": "criterion_001", "label": "flood protection", "criterion_type": "benefit", "evidence_item_ids": ["{evidence_id}"]}}],
          "option_criteria_matrix": [{{"option_id": "option_001", "criterion_id": "criterion_001", "assessment": "favors", "evidence_item_ids": ["{evidence_id}"]}}],
          "diagnostic_evidence": [{{"evidence_item_ids": ["{evidence_id}"], "source_ids": ["{source_id}"], "distinguishes": ["option_001"], "diagnosticity": "high", "why_diagnostic": "Distinguishes action from delay."}}],
          "tradeoffs": [{{"tradeoff": "protection versus implementation risk"}}],
          "cruxes_and_thresholds": [{{"crux": "whether implementation risk is bounded"}}],
          "premortem": [{{"failure_mode": "implementation risk dominates"}}],
          "monitoring_triggers": [{{"trigger": "new implementation failure evidence", "priority": "high"}}]
        }}
        """

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_decision_usefulness.run_model_backend", lambda *args, **kwargs: FakeResult())

    result = run_decision_usefulness_builder(
        canonical_packet=canonical,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["decision_usefulness_report"]["status"] == "parsed"
    assert result["decision_usefulness_packet"]["recommended_stance"]["stance"] == "Adopt option A conditionally."
    assert result["decision_usefulness_quality_report"]["status"] == "ready"


def test_run_decision_usefulness_builder_repairs_bad_references(monkeypatch) -> None:
    canonical = _canonical_packet()
    evidence_id = canonical["priority_evidence"][0]["item_id"]
    source_id = canonical["priority_evidence"][0]["source_ids"][0]
    calls = {"count": 0}

    class FakeResult:
        def __init__(self, text: str) -> None:
            self.text = text

    def fake_backend(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return FakeResult(
                """
                {
                  "schema_id": "decision_usefulness_packet_v1",
                  "decision_options": [{"option_id": "option_001", "label": "adopt", "source_ids": ["missing_source"]}],
                  "decision_criteria": [{"criterion_id": "criterion_001", "label": "outcomes"}],
                  "option_criteria_matrix": [{"option_id": "missing_option", "criterion_id": "criterion_001", "evidence_item_ids": ["missing_evidence"]}]
                }
                """
            )
        return FakeResult(
            f"""
            {{
              "schema_id": "decision_usefulness_packet_v1",
              "decision_question": "{canonical['decision_question']}",
              "answer_shape": "single_stance",
              "recommended_stance": {{"stance": "Adopt option A conditionally.", "source_ids": ["{source_id}"], "evidence_item_ids": ["{evidence_id}"]}},
              "decision_options": [{{"option_id": "option_001", "label": "adopt", "source_ids": ["{source_id}"], "evidence_item_ids": ["{evidence_id}"]}}],
              "decision_criteria": [{{"criterion_id": "criterion_001", "label": "outcomes", "evidence_item_ids": ["{evidence_id}"]}}],
              "option_criteria_matrix": [{{"option_id": "option_001", "criterion_id": "criterion_001", "assessment": "favors", "source_ids": ["{source_id}"], "evidence_item_ids": ["{evidence_id}"]}}],
              "diagnostic_evidence": [{{"evidence_item_ids": ["{evidence_id}"], "source_ids": ["{source_id}"], "distinguishes": ["option_001"], "diagnosticity": "high", "why_diagnostic": "It distinguishes adoption from delay."}}],
              "tradeoffs": [{{"tradeoff": "protection versus risk"}}],
              "cruxes_and_thresholds": [{{"crux": "implementation risk threshold"}}],
              "monitoring_triggers": [{{"trigger": "new evidence"}}]
            }}
            """
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_decision_usefulness.run_model_backend", fake_backend)

    result = run_decision_usefulness_builder(
        canonical_packet=canonical,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert calls["count"] == 2
    assert result["decision_usefulness_report"]["status"] == "accepted_after_repair"
    assert result["decision_usefulness_repair_report"]["status"] == "accepted"
    assert result["decision_usefulness_quality_report"]["invalid_reference_count"] == 0
