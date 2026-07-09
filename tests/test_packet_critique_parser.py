from __future__ import annotations

from epistemic_case_mapper.map_briefing_packet_refinement import PacketCritiqueOutput
from epistemic_case_mapper.model_schemas import parse_model_output_report


def test_packet_critique_parser_accepts_common_model_shape_variants() -> None:
    raw = """
    {
      "schema_id": "packet_critique_v1",
      "packet_sufficiency_judgment": "needs_repair",
      "bundle_role_checks": [
        {
          "bundle_id": "bundle_001",
          "role_matches_claim_and_direction": true,
          "recommended_role": null
        }
      ],
      "recommended_packet_edits": [
        {
          "target_id": "bundle_018",
          "edit_type": "relabel",
          "reason": "Administrative website information is not decision evidence."
        }
      ],
      "misleading_synthesis_risks": [
        {
          "risk_type": "off_question_evidence",
          "description": "A bundle answers an adjacent outcome rather than the decision question."
        }
      ],
      "insufficiency_warnings": [
        {
          "type": "source_only_insufficiency",
          "description": "A high-priority counterweight source is omitted."
        }
      ],
      "claim_quality_issues": [
        {
          "bundle_id": "bundle_018",
          "description": "The claim is page chrome, not a substantive evidence claim."
        }
      ],
      "missing_or_weak_cruxes": [
        {
          "description": "The population boundary is present but overcompressed."
        }
      ],
      "section_plan_risks": [
        {
          "description": "The section plan may put contrary evidence in a support slot."
        }
      ]
    }
    """

    report = parse_model_output_report(raw, PacketCritiqueOutput)

    assert report["ok"] is True
    data = report["data"]
    assert data["bundle_role_checks"][0]["recommended_role"] == ""
    assert data["misleading_synthesis_risks"][0]["type"] == "off_question_evidence"
    assert data["insufficiency_warnings"][0]["reason"] == "A high-priority counterweight source is omitted."
    assert data["claim_quality_issues"][0]["issue"] == "The claim is page chrome, not a substantive evidence claim."
    assert data["missing_or_weak_cruxes"] == ["The population boundary is present but overcompressed."]
    assert data["section_plan_risks"] == ["The section plan may put contrary evidence in a support slot."]


def test_packet_critique_parser_coerces_singleton_issue_objects() -> None:
    raw = """
    {
      "schema_id": "packet_critique_v1",
      "packet_sufficiency_judgment": "needs_repair",
      "misleading_synthesis_risks": {
        "risk_type": "off_question_evidence",
        "description": "One primary bundle addresses an adjacent outcome."
      },
      "claim_quality_issues": {
        "bundle_id": "bundle_016",
        "description": "The claim is too broad for the decision question."
      },
      "section_plan_risks": {
        "description": "Why This Read lacks primary answer-bearing evidence."
      },
      "overweighted_bundles": "bundle_016"
    }
    """

    report = parse_model_output_report(raw, PacketCritiqueOutput)

    assert report["ok"] is True
    data = report["data"]
    assert data["misleading_synthesis_risks"][0]["type"] == "off_question_evidence"
    assert data["claim_quality_issues"][0]["bundle_id"] == "bundle_016"
    assert data["section_plan_risks"] == ["Why This Read lacks primary answer-bearing evidence."]
    assert data["overweighted_bundles"] == ["bundle_016"]
