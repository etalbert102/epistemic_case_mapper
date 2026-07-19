from __future__ import annotations

from epistemic_case_mapper.pipeline.map.staged_semantic_relation_claim_cards import relation_routing_context_lines


def test_relation_routing_context_includes_whole_doc_source_local_fields() -> None:
    lines = relation_routing_context_lines(
        {
            "decision_function": "answer_bearing",
            "whole_doc_source_card": {
                "natural_bottom_line": "The measured endpoint moved in the source population.",
                "must_preserve_terms": ["source population", "measured endpoint"],
                "claim_context": {
                    "population": "source population",
                    "exposure_or_option": "tested option",
                    "outcome_or_endpoint": "measured endpoint",
                    "evidence_design": "source-described design",
                    "applicability_limits": "not a broader population claim",
                },
            },
        }
    )

    assert lines
    rendered = "\n".join(lines)
    assert "source_local_context" in rendered
    assert "source population" in rendered
    assert "measured endpoint" in rendered
    assert "natural_bottom_line" in rendered
    assert "must_preserve_terms" in rendered
