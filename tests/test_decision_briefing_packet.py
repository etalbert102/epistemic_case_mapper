from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.main_memo_obligations import build_main_memo_obligation_plan, section_obligations_for_title
from epistemic_case_mapper.map_briefing_artifacts import write_scaffold_artifacts
from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_packet_comparison import build_packet_first_comparison_report
from epistemic_case_mapper.map_briefing_packet_memo import (
    build_packet_memo_plan,
    build_reader_facing_packet_synthesis_prompt,
    render_packet_first_draft,
    write_packet_first_artifacts,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.map_briefing_packet_refinement import run_packet_critique_and_refinement
from epistemic_case_mapper.map_briefing_packet_repair import run_packet_retention_repair
from epistemic_case_mapper.map_briefing_packet_retention import build_memo_packet_retention_report
from epistemic_case_mapper.map_briefing_reader_packet_repair import (
    build_reader_packet_retention_report,
    run_reader_packet_retention_repair,
)


def _scaffold() -> dict:
    return {
        "question": "Should the city adopt option A for flood protection?",
        "source_display_names": {
            "s1": "Outcome Study",
            "s2": "Counter Study",
            "s3": "Boundary Report",
        },
        "candidate_evidence_cards": {
            "cards": [
                {
                    "candidate_card_id": "ec0001",
                    "source_card_ids": ["sc0001"],
                    "claim_ids": ["c1"],
                    "source_ids": ["s1"],
                    "source_titles": ["Outcome Study"],
                    "claim": "Option A reduced flood losses by 25% in comparable river cities.",
                    "role": "support",
                    "evidence_roles": ["support"],
                    "decision_relevance_score": 10,
                    "inclusion_recommendation": "main_text",
                    "inclusion_reason": "Direct outcome evidence.",
                    "anchor_confidence": "exact",
                    "quantity_values": ["25%"],
                    "section_candidates": ["Evidence Carrying the Conclusion"],
                },
                {
                    "candidate_card_id": "ec0002",
                    "source_card_ids": ["sc0002"],
                    "claim_ids": ["c2"],
                    "source_ids": ["s2"],
                    "source_titles": ["Counter Study"],
                    "claim": "Option A failed when maintenance budgets were cut.",
                    "role": "counterweight",
                    "evidence_roles": ["counterweight"],
                    "decision_relevance_score": 9,
                    "inclusion_recommendation": "main_text",
                    "inclusion_reason": "Important contrary evidence.",
                    "anchor_confidence": "exact",
                    "section_candidates": ["Decision Cruxes"],
                },
                {
                    "candidate_card_id": "ec0003",
                    "source_card_ids": ["sc0003"],
                    "claim_ids": ["c3"],
                    "source_ids": ["s3"],
                    "source_titles": ["Boundary Report"],
                    "claim": "The result only applies where pump capacity exceeds expected peak flow.",
                    "role": "scope",
                    "evidence_roles": ["scope"],
                    "decision_relevance_score": 8,
                    "inclusion_recommendation": "main_text",
                    "inclusion_reason": "Scope boundary.",
                    "anchor_confidence": "exact",
                    "section_candidates": ["Practical Scope and Exceptions"],
                },
            ]
        },
        "source_evidence_cards": {
            "cards": [
                {
                    "source_card_id": "sc0001",
                    "claim_ids": ["c1"],
                    "source_id": "s1",
                    "source_quote_or_excerpt": "Option A reduced flood losses by 25% in comparable river cities.",
                    "quantity_values": ["25%"],
                    "anchor_confidence": "exact",
                },
                {
                    "source_card_id": "sc0002",
                    "claim_ids": ["c2"],
                    "source_id": "s2",
                    "source_quote_or_excerpt": "Option A failed when maintenance budgets were cut.",
                    "anchor_confidence": "exact",
                },
                {
                    "source_card_id": "sc0003",
                    "claim_ids": ["c3"],
                    "source_id": "s3",
                    "source_quote_or_excerpt": "The result only applies where pump capacity exceeds expected peak flow.",
                    "anchor_confidence": "exact",
                },
            ]
        },
        "quantity_ledger": {
            "evidence_cards": [
                {
                    "card_id": "qc0001",
                    "atomic_evidence_card_id": "ec0001",
                    "claim_id": "c1",
                    "claim": "Option A reduced flood losses by 25% in comparable river cities.",
                    "context": "Option A reduced flood losses by 25%.",
                    "key_quantities": ["25%"],
                    "effect_estimates": ["25%"],
                    "card_score": 32,
                    "interpretation_hint": "Direct outcome estimate.",
                }
            ],
            "top_quantitative_anchors": [
                {
                    "quantity_id": "q0001",
                    "claim_id": "c1",
                    "claim": "Option A reduced flood losses by 25% in comparable river cities.",
                    "quantity_text": "25%",
                    "source": "s1",
                }
            ],
        },
        "argument_model": {
            "confidence": "medium",
            "proposed_answer": "Option A is promising but maintenance-dependent.",
            "strongest_support": [
                {
                    "statement": "Option A reduced flood losses by 25%.",
                    "source_ids": ["s1"],
                    "claim_ids": ["c1"],
                    "quantities": ["25%"],
                    "why_it_matters": "Direct outcome evidence.",
                }
            ],
            "strongest_counterarguments": [
                {
                    "statement": "Maintenance cuts can erase the benefit.",
                    "source_ids": ["s2"],
                    "claim_ids": ["c2"],
                    "why_it_matters": "This is a decision crux.",
                }
            ],
            "scope_boundaries": [],
            "cruxes": [],
            "quantitative_anchors": [],
        },
    }


def test_decision_briefing_packet_retains_roles_sources_and_quantities() -> None:
    result = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = result["decision_briefing_packet"]
    sufficiency = result["packet_sufficiency_report"]

    roles = {row["decision_role"] for row in packet["evidence_bundles"]}
    assert {"counterweight", "scope_boundary", "quantitative_anchor"} <= roles
    assert any("25%" in row.get("required_terms", []) for row in packet["must_retain_ledger"])
    assert any(row["source_label"] == "Counter Study" for row in packet["source_trail"])
    assert sufficiency["role_coverage"]["missing_available_roles"] == []
    assert sufficiency["quantity_retention"]["missing_top_quantities"] == []


def test_packet_sufficiency_reports_high_priority_compression_loss() -> None:
    scaffold = _scaffold()
    for index in range(20):
        scaffold["candidate_evidence_cards"]["cards"].append(
            {
                "candidate_card_id": f"extra{index:02d}",
                "claim_ids": [f"cx{index}"],
                "source_ids": [f"sx{index}"],
                "source_titles": [f"Extra Source {index}"],
                "claim": f"Extra high priority support claim {index} with unique value {index}%.",
                "role": "support",
                "evidence_roles": ["support"],
                "decision_relevance_score": 10,
                "inclusion_recommendation": "main_text",
                "anchor_confidence": "exact",
                "quantity_values": [f"{index}%"],
            }
        )

    result = build_decision_briefing_packet_bundle(scaffold, question="Should the city adopt option A for flood protection?")
    sufficiency = result["packet_sufficiency_report"]

    assert sufficiency["high_priority_omitted_evidence"]
    assert "high_priority_omitted_evidence" in sufficiency["issues"]


def test_packet_resolves_quantity_source_labels_and_retains_all_top_quantities() -> None:
    scaffold = _scaffold()
    scaffold["quantity_ledger"]["evidence_cards"] = [
        {
            "card_id": "qc_label_source",
            "claim_id": "c4",
            "claim": "Outcome Study reports a broad quantitative result for option A.",
            "context": "Outcome Study reports 1%, 2%, 3%, 4%, 5%, 6%, 7%, and 8% effects.",
            "key_quantities": ["1%", "2%", "3%", "4%", "5%", "6%", "7%", "8%"],
            "effect_estimates": ["1%", "2%", "3%", "4%", "5%", "6%", "7%", "8%"],
            "source": "Outcome Study",
            "card_score": 40,
        }
    ]

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    packet = result["decision_briefing_packet"]
    sufficiency = result["packet_sufficiency_report"]
    quantity_bundles = [row for row in packet["evidence_bundles"] if row.get("decision_role") == "quantitative_anchor"]

    assert any(row.get("source_ids") == ["s1"] for row in quantity_bundles)
    assert any("8%" in row.get("required_terms", []) for row in packet["must_retain_ledger"])
    assert "8%" not in sufficiency["quantity_retention"]["missing_top_quantities"]


def test_packet_resolves_argument_quantity_anchor_sources_from_claim_ids() -> None:
    scaffold = _scaffold()
    scaffold["argument_model"]["quantitative_anchors"] = [
        {
            "statement": "Option A reduced flood losses by 25% in comparable river cities.",
            "claim_ids": ["c1"],
            "quantity_ids": ["qc0001"],
            "quantities": ["25%"],
            "source_ids": [],
            "why_it_matters": "The estimate is the main quantitative anchor.",
        }
    ]

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    packet = result["decision_briefing_packet"]
    quantity_bundles = [row for row in packet["evidence_bundles"] if row.get("decision_role") == "quantitative_anchor"]

    assert any(row.get("source_ids") == ["s1"] for row in quantity_bundles)
    assert result["packet_sufficiency_report"]["unsupported_or_weakly_anchored_bundles"]["count"] == 0


def test_packet_promotes_source_bottom_lines_as_first_class_evidence() -> None:
    scaffold = _scaffold()
    scaffold["source_bottom_line_cards"] = {
        "schema_id": "source_bottom_line_cards_v1",
        "cards": [
            {
                "source_bottom_line_id": "sbl0001",
                "source_id": "s1",
                "source_label": "Outcome Study",
                "claim_ids": ["c1"],
                "source_bottom_line": (
                    "Option A was not associated with higher downstream flood losses overall, "
                    "though the result may not apply when maintenance funding is cut."
                ),
                "decision_importance_level": "high",
                "decision_function": "answer_bearing",
            }
        ],
    }

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    bundles = result["decision_briefing_packet"]["evidence_bundles"]
    source_summary = [row for row in bundles if row.get("pretrim_kind") == "source_bottom_line"]

    assert source_summary
    assert source_summary[0]["decision_role"] == "strongest_support"
    assert "Source-level bottom line" in source_summary[0]["why_it_matters"]


def test_packet_reports_omitted_source_bottom_lines_after_trimming() -> None:
    scaffold = _scaffold()
    for index in range(12):
        source_id = f"sbl_source_{index}"
        scaffold["source_display_names"][source_id] = f"Source Bottom Line {index}"
    scaffold["source_bottom_line_cards"] = {
        "schema_id": "source_bottom_line_cards_v1",
        "cards": [
            {
                "source_bottom_line_id": f"sbl{index:04d}",
                "source_id": f"sbl_source_{index}",
                "source_label": f"Source Bottom Line {index}",
                "claim_ids": [f"sbl_claim_{index}"],
                "source_bottom_line": f"Option A was not associated with worse outcomes in source {index}.",
                "decision_importance_level": "high",
                "decision_function": "answer_bearing",
            }
            for index in range(12)
        ],
    }

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    coverage = result["decision_briefing_packet"]["coverage_report"]
    sufficiency = result["packet_sufficiency_report"]

    assert coverage["source_bottom_line_candidate_count"] == 12
    assert coverage["omitted_source_bottom_line_ids"]
    assert "source_bottom_lines_omitted_after_trimming" in coverage["warnings"]
    assert sufficiency["source_bottom_line_retention"]["missing_count"] >= 1
    assert "source_bottom_lines_missing" in sufficiency["issues"]


def test_packet_does_not_promote_empty_quantity_rows_to_quantitative_anchors() -> None:
    scaffold = _scaffold()
    scaffold["argument_model"]["quantitative_anchors"] = [
        {
            "statement": "This is only relation-rationale context without a numeric value.",
            "claim_ids": [],
            "quantity_ids": ["qc_empty"],
            "quantities": [],
            "source_ids": [],
        }
    ]
    scaffold["quantity_ledger"]["evidence_cards"].append(
        {
            "card_id": "qc_empty",
            "claim": "This is only relation-rationale context without a numeric value.",
            "key_quantities": [],
            "effect_estimates": [],
            "source": "relation rationale",
            "card_score": 20,
        }
    )

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])

    assert all(
        row.get("claim") != "This is only relation-rationale context without a numeric value."
        for row in result["decision_briefing_packet"]["evidence_bundles"]
    )


def test_packet_does_not_promote_relation_rationale_quantity_rows() -> None:
    scaffold = _scaffold()
    scaffold["quantity_ledger"]["evidence_cards"].append(
        {
            "card_id": "qc_relation_rationale",
            "claim": "Generated relation rationale mentions 7 eggs/week but is not a source document.",
            "context": "Generated relation rationale mentions 7 eggs/week but is not a source document.",
            "key_quantities": ["7 eggs/week"],
            "effect_estimates": [],
            "source": "relation rationale",
            "card_score": 40,
        }
    )

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])

    assert all(
        row.get("claim") != "Generated relation rationale mentions 7 eggs/week but is not a source document."
        for row in result["decision_briefing_packet"]["evidence_bundles"]
    )


def test_scaffold_artifacts_write_packet_reports(tmp_path: Path) -> None:
    scaffold = _scaffold()
    scaffold.update(build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"]))
    scaffold.update(build_quality_synthesis_packet_bundle(scaffold["decision_briefing_packet"]))

    paths = write_scaffold_artifacts(
        artifacts=tmp_path,
        prompt="prompt",
        prioritized_map={"claims": []},
        prioritization_report={},
        erosion_audit={},
        scaffold=scaffold,
    )

    assert paths["decision_briefing_packet"].exists()
    assert paths["decision_briefing_packet_report"].exists()
    assert paths["packet_sufficiency_report"].exists()
    assert paths["packet_assembly_clusters"].exists()
    assert paths["diagnosticity_matrix"].exists()
    assert paths["quantity_binding_report"].exists()
    assert paths["memo_ready_packet"].exists()
    assert paths["memo_ready_packet_synthesis_prompt"].exists()


def test_packet_critique_and_refinement_skips_on_prompt_backend() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")

    result = run_packet_critique_and_refinement(
        built["decision_briefing_packet"],
        built["packet_sufficiency_report"],
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["packet_critique_report"]["status"] == "skipped"
    assert result["packet_critique_adjudication_report"]["status"] == "skipped_prompt_backend"
    assert result["decision_briefing_packet_refinement_report"]["status"] == "skipped"
    assert result["decision_briefing_packet"] == built["decision_briefing_packet"]


def test_packet_refinement_applies_only_known_id_updates(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    known_bundle_id = built["decision_briefing_packet"]["evidence_bundles"][0]["bundle_id"]

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
                  "schema_id": "packet_critique_v1",
                  "packet_sufficiency_judgment": "needs_repair",
                  "recommended_packet_edits": [
                    {"edit_type": "relabel", "target_ids": ["%s"], "recommended_role": "strongest_support", "rationale": "Known bundle."},
                    {"edit_type": "relabel", "target_ids": ["missing_bundle"], "recommended_role": "counterweight", "rationale": "Unknown bundle."}
                  ]
                }
                """
                % known_bundle_id
            )
        return FakeResult(
            """
            {
              "schema_id": "decision_briefing_packet_refinement_v1",
              "packet_ready_for_synthesis": true,
              "bundle_updates": [
                {
                  "bundle_id": "%s",
                  "decision_role": "strongest_support",
                  "weight": "high",
                  "why_it_matters": "This is the primary source-grounded outcome estimate.",
                  "section_use": "Use as the primary load-bearing outcome estimate."
                },
                {
                  "bundle_id": "missing_bundle",
                  "decision_role": "counterweight"
                }
              ],
              "warnings": []
            }
            """
            % known_bundle_id
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_packet_refinement.run_model_backend", fake_backend)

    result = run_packet_critique_and_refinement(
        built["decision_briefing_packet"],
        built["packet_sufficiency_report"],
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["packet_critique_report"]["status"] == "parsed"
    assert result["packet_critique_adjudication_report"]["accepted_count"] == 1
    assert result["packet_critique_adjudication_report"]["rejected_count"] == 1
    assert result["decision_briefing_packet_refinement_report"]["applied_update_count"] == 1
    assert result["decision_briefing_packet_refinement_report"]["rejected_update_count"] == 1
    updated = {
        row["bundle_id"]: row
        for row in result["decision_briefing_packet"]["evidence_bundles"]
    }[known_bundle_id]
    assert updated["section_use"] == "Use as the primary load-bearing outcome estimate."


def test_packet_critique_role_checks_become_relabel_recommendations(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    target = next(row for row in packet["evidence_bundles"] if row.get("decision_role") == "counterweight")
    target["decision_role"] = "strongest_support"
    target["directionality"] = "challenges"
    target["section_use"] = "Use as primary support even though the claim is cautionary."
    target_id = target["bundle_id"]

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
                  "schema_id": "packet_critique_v1",
                  "packet_sufficiency_judgment": "needs_repair",
                  "bundle_role_checks": [
                    {
                      "bundle_id": "%s",
                      "current_role": "strongest_support",
                      "directionality": "challenges",
                      "role_matches_claim_and_direction": false,
                      "recommended_role": "counterweight",
                      "problem": "The claim challenges the answer and should not be primary support."
                    }
                  ],
                  "recommended_packet_edits": [
                    {
                      "edit_type": "relabel",
                      "bundle_id": "%s",
                      "recommended_role": "counterweight",
                      "description": "The bundle-id shorthand should normalize to target_ids."
                    },
                    {
                      "edit_type": "insufficiency_warning",
                      "source_id": "missing_source",
                      "description": "A source-level warning should remain warning-only."
                    }
                  ]
                }
                """
                % (target_id, target_id)
            )
        return FakeResult(
            """
            {
              "schema_id": "decision_briefing_packet_refinement_v1",
              "packet_ready_for_synthesis": true,
              "bundle_updates": [
                {
                  "bundle_id": "%s",
                  "decision_role": "counterweight",
                  "section_use": "Use as contrary evidence that limits the default answer.",
                  "rationale": "Accepted role-check relabel."
                }
              ],
              "warnings": []
            }
            """
            % target_id
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_packet_refinement.run_model_backend", fake_backend)

    result = run_packet_critique_and_refinement(
        packet,
        built["packet_sufficiency_report"],
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["packet_critique_adjudication_report"]["accepted_count"] == 1
    assert result["packet_critique_adjudication_report"]["warning_only_count"] == 1
    accepted = result["packet_critique_adjudication_report"]["accepted_recommendations"]
    assert any(row.get("source") == "bundle_role_check" for row in accepted)
    assert all(row.get("target_ids") == [target_id] for row in accepted)
    assert result["packet_critique_adjudication_report"]["warning_only_recommendations"][0]["edit_type"] == "add_warning"
    updated = {row["bundle_id"]: row for row in result["decision_briefing_packet"]["evidence_bundles"]}[target_id]
    assert updated["decision_role"] == "counterweight"
    assert "primary support" not in updated["section_use"].lower()
    assert "contrary" in updated["section_use"].lower() or "cautionary" in updated["section_use"].lower()


def test_packet_critique_preserves_synthesis_risks_and_packet_quality_issues(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    packet["answer_frame"]["default_answer"] = "{'classification': 'promising', 'current_read': 'truncated..."
    malformed = packet["evidence_bundles"][0]
    malformed["claim"] = "0%"
    malformed["bundle_id"] = "bundle_malformed"
    counterweight = next(row for row in packet["evidence_bundles"] if row.get("decision_role") == "counterweight")
    nonrepairable = next(row for row in packet["evidence_bundles"] if row.get("decision_role") == "scope_boundary")
    nonrepairable["claim"] = "0%"
    nonrepairable["bundle_id"] = "bundle_nonrepairable"
    packet["section_views"].append(
        {
            "section": "Evidence Carrying the Conclusion",
            "section_job": "Identify load-bearing evidence.",
            "primary_bundle_ids": [counterweight["bundle_id"]],
            "contrast_bundle_ids": [],
            "boundary_bundle_ids": [],
            "context_bundle_ids": [],
        }
    )

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
                  "schema_id": "packet_critique_v1",
                  "decision_adequate": true,
                  "packet_sufficiency_judgment": "ready",
                  "misleading_risks": [
                    {
                      "type": "Ambiguous Anchor Interpretation",
                      "description": "A numerical anchor may be interpreted as stronger than it is.",
                      "impact_level": "high",
                      "affected_sections": ["Evidence Carrying the Conclusion"]
                    }
                  ],
                  "challenges": {
                    "answer_frame": {
                      "status": "challenge",
                      "comment": "The answer frame needs cleaner plain-language text."
                    },
                    "section_plan": {
                      "status": "challenge",
                      "comment": "The section plan risks putting contrary evidence in a support slot."
                    }
                  },
                  "insufficiency_warnings": [
                    {
                      "bundle_id": "bundle_malformed",
                      "reason": "Claim '0%%' is insufficient for synthesis."
                    },
                    {
                      "bundle_id": "bundle_nonrepairable",
                      "reason": "Claim '0%%' is insufficient for synthesis."
                    }
                  ],
                  "recommended_packet_edits": [
                    {
                      "target_id": "%s",
                      "edit_type": "relabel",
                      "recommended_role": "counterweight",
                      "description": "Singular target_id should normalize."
                    }
                  ]
                }
                """
                % counterweight["bundle_id"]
            )
        return FakeResult(
            """
            {
              "schema_id": "decision_briefing_packet_refinement_v1",
              "packet_ready_for_synthesis": true,
              "bundle_updates": [],
              "warnings": []
            }
            """
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_packet_refinement.run_model_backend", fake_backend)

    result = run_packet_critique_and_refinement(
        packet,
        built["packet_sufficiency_report"],
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    adjudication = result["packet_critique_adjudication_report"]
    assert adjudication["accepted_recommendations"][0]["target_ids"] == [counterweight["bundle_id"]]
    assert any("Ambiguous Anchor" in row.get("type", "") for row in adjudication["misleading_synthesis_risks"])
    assert any(row.get("source") == "model_challenges" for row in adjudication["misleading_synthesis_risks"])
    assert any(row.get("bundle_id") == "bundle_malformed" for row in adjudication["insufficiency_warnings"])
    assert any(row.get("bundle_id") == "bundle_malformed" for row in adjudication["claim_quality_issues"])
    assert any(row.get("bundle_id") == "bundle_nonrepairable" for row in adjudication["claim_quality_issues"])
    assert any(row.get("bundle_id") == counterweight["bundle_id"] for row in adjudication["section_routing_issues"])
    assert any(row.get("source") == "deterministic_answer_frame_scan" for row in adjudication["answer_frame_issues"])
    repair = result["decision_briefing_packet_refinement_report"]["packet_quality_repair_report"]
    assert repair["claim_repairs"][0]["bundle_id"] == "bundle_malformed"
    assert repair["suppressed_bundle_ids"] == ["bundle_nonrepairable"]
    assert any(row.get("bundle_id") == counterweight["bundle_id"] for row in repair["rerouted_sections"])
    repaired_packet = result["decision_briefing_packet"]
    repaired_bundles = {row["bundle_id"]: row for row in repaired_packet["evidence_bundles"]}
    assert repaired_bundles["bundle_malformed"]["claim_repaired_for_synthesis"] is True
    assert repaired_bundles["bundle_malformed"]["claim"].startswith("Quantitative anchor")
    assert repaired_bundles["bundle_nonrepairable"]["synthesis_suppressed"] is True
    repaired_section = repaired_packet["section_views"][-1]
    assert counterweight["bundle_id"] not in repaired_section["primary_bundle_ids"]
    assert counterweight["bundle_id"] in repaired_section["contrast_bundle_ids"]
    memo_plan = build_packet_memo_plan(repaired_packet)
    evidence_section = memo_plan["section_views"][-1]
    assert all(row.get("bundle_id") != "bundle_nonrepairable" for row in evidence_section["primary_bundles"])


def test_main_memo_obligations_prefer_packet_must_retain_items() -> None:
    scaffold = _scaffold()
    scaffold.update(build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"]))

    obligations = build_main_memo_obligation_plan(scaffold=scaffold)

    packet_obligations = [row for row in obligations if str(row.get("obligation_id", "")).startswith("packet_")]
    assert packet_obligations
    assert packet_obligations[0]["priority"] >= 90
    assert any("25%" in row.get("search_terms", []) for row in packet_obligations)

    evidence_section = section_obligations_for_title("Evidence Carrying the Conclusion", obligations, limit=8)
    assert any("25%" in row.get("search_terms", []) for row in evidence_section)
    practical_section = section_obligations_for_title("Practical Read", obligations, limit=8)
    assert all("25%" not in row.get("search_terms", []) for row in practical_section)


def test_packet_memo_plan_and_draft_include_question_sources_and_required_terms(tmp_path: Path) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]

    plan = build_packet_memo_plan(packet)
    draft = render_packet_first_draft(plan)
    written = write_packet_first_artifacts(artifacts=tmp_path, packet=packet)

    assert "Should the city adopt option A" in draft
    assert "25%" in draft
    assert "Outcome Study" in draft
    assert "Counter Study" in draft
    assert "bundle_" not in draft
    assert "**Must retain:**" not in draft
    assert "Required terms:" not in draft
    reader_packet = plan["reader_facing_packet"]
    assert reader_packet["schema_id"] == "reader_facing_decision_packet_v1"
    assert reader_packet["evidence_cards"]
    assert reader_packet["must_retain_obligations"]
    assert any(card.get("required_in_memo") for card in reader_packet["evidence_cards"])
    assert any("25%" in obligation.get("required_terms", []) for obligation in reader_packet["must_retain_obligations"])
    assert "bundle_id" not in str(reader_packet)
    prompt = build_reader_facing_packet_synthesis_prompt(reader_packet)
    assert "Write like an analyst" in prompt
    assert "must_retain_obligations" in prompt
    assert "required_in_memo" in prompt
    assert written["memo_plan_path"].exists()
    assert written["reader_facing_packet_path"].exists()
    assert written["reader_facing_packet_synthesis_prompt_path"].exists()
    assert written["packet_first_draft_path"].exists()
    assert written["section_context_acceptance_report_path"].exists()
    assert written["reader_packet_verbalization_report_path"].exists()
    assert written["report"]["status"] == "ready"


def test_reader_packet_includes_compact_synthesis_warnings() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    packet["synthesis_warning_inputs"] = {
        "packet_sufficiency_issues": ["counterweights_not_preserved"],
        "packet_quality_gate_issues": ["packet_critique_warning_only_recommendations"],
    }

    reader_packet = build_packet_memo_plan(packet)["reader_facing_packet"]
    prompt = build_reader_facing_packet_synthesis_prompt(reader_packet)

    assert reader_packet["synthesis_warnings"]
    assert any("counterweight" in warning.lower() for warning in reader_packet["synthesis_warnings"])
    assert "packet_critique_warning_only_recommendations" not in prompt
    assert "synthesis_warnings" in prompt


def test_memo_packet_retention_report_flags_missing_required_packet_items() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    complete_memo = """
## Decision Brief

Option A is promising but maintenance-dependent. Option A reduced flood losses by 25% in comparable river cities
according to Outcome Study. Counter Study shows that Option A failed when maintenance budgets were cut.
Maintenance cuts can erase the benefit.
Boundary Report says the result only applies where pump capacity exceeds expected peak flow.
"""
    weak_memo = """
## Decision Brief

Option A is promising.
"""

    complete = build_memo_packet_retention_report(complete_memo, packet)
    weak = build_memo_packet_retention_report(weak_memo, packet)

    assert complete["status"] == "ready"
    assert complete["missing_critical_count"] == 0
    assert weak["status"] == "critical_warnings"
    assert weak["missing_critical_count"] > 0
    assert any(issue["issue_type"] == "missing_must_retain_item" for issue in weak["issues"])


def test_packet_first_comparison_report_accounts_for_calls_and_retention() -> None:
    scaffold = _scaffold()
    scaffold.update(build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"]))
    retention = {
        "must_retain_count": 3,
        "retained_must_retain_count": 3,
        "missing_critical_count": 0,
        "missing_high_count": 0,
        "issues": [],
    }

    report = build_packet_first_comparison_report(
        scaffold=scaffold,
        section_rewrite_report={"packet_first": True, "status": "skipped_packet_first_default"},
        reader_rewrite_report={"status": "full_polish_accepted", "pass_count": 1},
        runtime_budget_report={"model_call_count": 1},
        memo_packet_retention_report=retention,
    )

    assert report["schema_id"] == "packet_first_comparison_report_v1"
    assert report["packet_first"] is True
    assert report["baseline_mode"] == "estimated_section_rewrite_baseline"
    assert report["model_calls"]["estimated_call_delta"] > 0
    assert report["status"] == "packet_first_supported_by_estimated_comparison"


def test_packet_retention_repair_accepts_only_if_retention_improves(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    weak_memo = """
## Decision Brief

Option A is promising.

**Confidence:** medium
"""
    repaired_memo = """
## Decision Brief

Option A is promising but maintenance-dependent. Option A reduced flood losses by 25% in comparable river cities
according to Outcome Study. Counter Study shows that Option A failed when maintenance budgets were cut.
Maintenance cuts can erase the benefit. Boundary Report says the result only applies where pump capacity exceeds expected peak flow.

**Confidence:** medium
"""
    pre_report = build_memo_packet_retention_report(weak_memo, packet)

    class FakeResult:
        text = repaired_memo
        prompt_only = False

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_packet_repair.run_model_backend", lambda *args, **kwargs: FakeResult())

    result = run_packet_retention_repair(
        weak_memo,
        packet,
        pre_report,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "accepted"
    assert result["report"]["final_missing_critical_count"] == 0
    assert "Counter Study" in result["memo"]


def test_reader_packet_retention_report_flags_dropped_numeric_cards() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    plan = build_packet_memo_plan(built["decision_briefing_packet"])
    reader_packet = plan["reader_facing_packet"]
    weak_memo = """
## Decision Brief

Option A is promising but maintenance-dependent.
"""

    report = build_reader_packet_retention_report(weak_memo, reader_packet)

    assert report["status"] == "warning"
    assert report["missing_card_count"] > 0
    assert any("25%" in issue.get("missing_numbers", []) for issue in report["issues"])


def test_reader_packet_retention_repair_accepts_targeted_anchor_reinsertion(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    weak_memo = """
## Decision Brief

Option A is promising but maintenance-dependent.

## Sources

- Outcome Study
"""
    repaired_memo = """
## Decision Brief

Option A is promising but maintenance-dependent.

## What the Evidence Supports

Option A reduced flood losses by 25% in comparable river cities [Outcome Study].

## Sources

- Outcome Study
"""

    class FakeResult:
        text = repaired_memo
        prompt_only = False

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_reader_packet_repair.run_model_backend", lambda *args, **kwargs: FakeResult())

    result = run_reader_packet_retention_repair(
        weak_memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "accepted"
    assert result["report"]["final_missing_number_count"] == 0
    assert "25%" in result["memo"]


def test_reader_packet_retention_repair_uses_deterministic_fallback_after_numeric_regression(monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = built["decision_briefing_packet"]
    packet["evidence_bundles"].append(
        {
            "bundle_id": "bundle_extra_numeric",
            "decision_role": "quantitative_anchor",
            "claim": "Option A also reduced emergency callouts by 40% in comparable river cities.",
            "source_labels": ["Outcome Study"],
            "quantity_values": ["40%"],
            "why_it_matters": "This is a second numerical anchor.",
        }
    )
    initial_memo = """
## Decision Brief

Option A is promising but maintenance-dependent. Option A reduced flood losses by 25% in comparable river cities [Outcome Study].
"""
    regressed_memo = """
## Decision Brief

Option A is promising but maintenance-dependent. Option A also reduced emergency callouts by 40% in comparable river cities [Outcome Study].
"""

    class FakeResult:
        text = regressed_memo
        prompt_only = False

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_reader_packet_repair.run_model_backend", lambda *args, **kwargs: FakeResult())

    result = run_reader_packet_retention_repair(
        initial_memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "accepted"
    assert result["report"]["accepted_via"] == "deterministic_fallback"
    assert result["report"]["deterministic_fallback"]["accepted"] is True
    assert "25%" in result["memo"]
    assert "40%" in result["memo"]
