from __future__ import annotations

import json

from epistemic_case_mapper.io import write_json
from epistemic_case_mapper.map_briefing_model_context import build_model_context_audit


def test_model_context_audit_separates_record_only_and_model_context(tmp_path) -> None:
    packet_path = tmp_path / "section_synthesis_packets.json"
    write_json(
        packet_path,
        {
            "packets": [
                {
                    "title": "Why This Read",
                    "packet": {"debug_only": "x" * 1000},
                    "model_packet": {
                        "schema_id": "model_section_packet_v1",
                        "section_thesis": "Explain the decision logic.",
                        "prohibited_repetition": [{"slot": "Boundary", "owner_section": "Scope"}],
                    },
                }
            ]
        },
    )

    audit = build_model_context_audit(
        backend="prompt",
        legacy_prompt="legacy prompt",
        global_plan_prompt="global plan prompt",
        section_packets_path=packet_path,
        reader_rewrite_prompt="",
    )

    stages = {stage["stage"]: stage for stage in audit["stages"]}
    section = stages["section_rewrite"]["sections"][0]

    assert stages["whole_briefing_legacy_prompt"]["status"] == "record_only_legacy_prompt"
    assert stages["global_memo_plan"]["sent_to_model"] is False
    assert section["model_to_debug_char_ratio"] < 1
    assert "negative_anchor_terms_visible" not in section["pollution_flags"]


def test_model_context_audit_flags_visible_negative_anchor_terms(tmp_path) -> None:
    packet_path = tmp_path / "section_synthesis_packets.json"
    write_json(
        packet_path,
        {
            "packets": [
                {
                    "title": "Practical Read",
                    "packet": {},
                    "model_packet": {"prohibited_repetition": [{"anchor_terms_to_avoid_repeating": ["42"]}]},
                }
            ]
        },
    )

    audit = build_model_context_audit(
        backend="fake",
        legacy_prompt="",
        global_plan_prompt="",
        section_packets_path=packet_path,
        reader_rewrite_prompt=json.dumps({"edits": []}),
    )

    section = audit["stages"][2]["sections"][0]
    assert "negative_anchor_terms_visible" in section["pollution_flags"]
    assert audit["stages"][3]["sent_to_model"] is True
