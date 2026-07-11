from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle

from test_decision_briefing_packet import _scaffold


def test_decision_briefing_packet_propagates_source_appraisal_to_derived_bundles() -> None:
    scaffold = _scaffold()
    scaffold["source_appraisal_report"] = {
        "schema_id": "source_appraisal_report_v1",
        "status": "ready",
        "appraisal_by_source_id": {
            "s1": _appraisal("s1", "Outcome Study", ["association_not_causation"]),
            "s2": _appraisal("s2", "Counter Study", ["quality_limit"]),
            "s3": _appraisal("s3", "Boundary Report", ["scope_sensitive"]),
        },
    }

    result = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    bundles = result["decision_briefing_packet"]["evidence_bundles"]

    assert any(row.get("pretrim_kind") == "argument_model.strongest_support" for row in bundles)
    assert all(row.get("source_appraisal", {}).get("status") == "ready" for row in bundles if row.get("source_ids"))
    assert any("association_not_causation" in row.get("source_use_warnings", []) for row in bundles)


def _appraisal(source_id: str, label: str, warnings: list[str]) -> dict:
    return {
        "source_appraisal_id": f"sa_{source_id}",
        "source_id": source_id,
        "source_label": label,
        "status": "ready",
        "source_use_warnings": warnings,
        "allowed_wording": {"preferred_verbs": ["suggests"]},
    }
