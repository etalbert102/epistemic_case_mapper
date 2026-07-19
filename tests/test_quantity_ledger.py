from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing import briefing_scaffold, compose_final_reader_memo_package
from epistemic_case_mapper.pipeline.briefing.map_briefing_artifacts import write_final_review_packet, write_scaffold_artifacts
from epistemic_case_mapper.pipeline.briefing.map_briefing_quantities import build_quantity_ledger, quantity_ledger_markdown, top_quantity_anchors


def test_quantity_ledger_extracts_effect_sizes_intervals_and_thresholds() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "A meta-analysis found RR = 0.98 (95% CI 0.93-1.03) for one serving per day.",
                "excerpt": "The analysis included 1,720,108 participants and 139,195 events over 17.5 years.",
                "source_id": "source_a",
                "role": "crux",
            }
        ],
        "relations": [],
    }

    ledger = build_quantity_ledger(candidate_map, {"source_a": "Source A"}, question="Should the intervention affect risk?")

    quantity_text = " ".join(row["quantity_text"] for row in ledger["quantities"])
    types = {row["quantity_type"] for row in ledger["quantities"]}
    assert "RR = 0.98" in quantity_text
    assert "95% CI 0.93-1.03" in quantity_text
    assert "1,720,108 participants" in quantity_text
    assert "effect_size" in types
    assert "confidence_interval" in types
    assert "sample_size" in types
    assert ledger["top_quantitative_anchors"]
    assert ledger["evidence_cards"]
    assert ledger["evidence_cards"][0]["key_quantities"]


def test_quantity_ledger_markdown_renders_auditable_table() -> None:
    ledger = {
        "quantities": [
            {
                "quantity_text": "RR 1.04",
                "quantity_type": "effect_size",
                "source": "Source A",
                "context_window": "Risk was RR 1.04 in the cohort.",
            }
        ],
        "evidence_cards": [
            {
                "evidence_use": "outcome estimate",
                "key_quantities": ["RR 1.04", "95% CI 1.00-1.08"],
                "source": "Source A",
                "interpretation_hint": "RR 1.04 with 95% CI 1.00-1.08; interval includes the usual null value, so treat as uncertain.",
            }
        ],
    }

    markdown = "\n".join(quantity_ledger_markdown(ledger))

    assert "## Quantitative Evidence Ledger" in markdown
    assert "### Quantitative Evidence Cards" in markdown
    assert "### Raw Extracted Quantities" in markdown
    assert "RR 1.04" in markdown
    assert "effect size" in markdown


def test_quantity_cards_pair_effect_interval_and_scale() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The pooled estimate was RR 0.98 with 95% CI 0.93 to 1.03 for one serving per day.",
                "excerpt": "Before the estimate, unrelated text ends. The analysis included 1,720,108 participants and 139,195 events. The pooled estimate was RR 0.98 with 95% CI 0.93 to 1.03 for one serving per day.",
                "source_id": "source_a",
                "role": "crux",
            }
        ],
        "relations": [],
    }

    ledger = build_quantity_ledger(candidate_map, {"source_a": "Source A"}, question="Should it affect risk?")
    card = ledger["evidence_cards"][0]

    assert card["evidence_use"] in {"outcome estimate", "study scale or follow-up context"}
    assert "RR 0.98" in card["key_quantities"]
    assert "95% CI 0.93 to 1.03" in card["key_quantities"]
    assert "interval includes the usual null value" in card["interpretation_hint"]
    assert not any(str(row["context_window"]).startswith("efore") for row in ledger["quantities"])


def test_quantity_cards_use_claim_local_tuple_over_unrelated_excerpt_quantities() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The pooled relative risk of CVD for the highest vs lowest intake was 1.19 (95% CI 1.02-1.38).",
                "excerpt": (
                    "The pooled RRs of the risk of CVD, CVD for separated diabetes patients, and diabetes "
                    "for the highest vs lowest intake were 1.19 (95% CI 1.02-1.38), "
                    "1.83 (95% CI 1.42-2.37), 1.68 (95% CI 1.41-2.00), respectively. "
                    "Subgroup analyses showed higher risk in other countries than the USA "
                    "(RR 2.00, 95% CI 1.14 to 3.51 vs 1.13, 95% CI 0.98 to 1.30)."
                ),
                "source_id": "source_a",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }

    ledger = build_quantity_ledger(candidate_map, {"source_a": "Source A"}, question="Should intake affect CVD risk?")
    card = ledger["evidence_cards"][0]

    assert "1.19" in card["key_quantities"]
    assert "95% CI 1.02-1.38" in card["key_quantities"]
    assert "RR 2.00" not in card["key_quantities"]
    assert "95% CI 1.42-2.37" not in card["key_quantities"]
    assert any(row["estimate"] == "1.19" and row["interval"] == "95% CI 1.02-1.38" for row in card["quantity_tuples"])
    top_anchor_text = " ".join(str(row["quantity_text"]) for row in ledger["top_quantitative_anchors"])
    assert "95% CI 1.42-2.37" not in top_anchor_text


def test_top_quantity_anchors_preserve_rank_with_claim_diversity() -> None:
    rows = [
        {
            "quantity_text": "RR 0.98",
            "quantity_type": "effect_size",
            "source": "Source A",
            "claim_id": "a",
            "relevance_score": 22,
        },
        {
            "quantity_text": "RR 1.04",
            "quantity_type": "effect_size",
            "source": "Source B",
            "claim_id": "b",
            "relevance_score": 22,
        },
        {
            "quantity_text": "RR 1.08",
            "quantity_type": "effect_size",
            "source": "Source B",
            "claim_id": "b",
            "relevance_score": 22,
        },
        {
            "quantity_text": "RR 1.05",
            "quantity_type": "effect_size",
            "source": "Source B",
            "claim_id": "b",
            "relevance_score": 22,
        },
    ]

    anchors = top_quantity_anchors(rows, limit=3)

    assert [row["quantity_text"] for row in anchors] == ["RR 0.98", "RR 1.04", "RR 1.08"]


def test_briefing_scaffold_exposes_quantitative_anchors_in_appendix() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The intervention was associated with lower risk (RR 0.82, 95% CI 0.70-0.96).",
                "excerpt": "The cohort included 12,400 participants over 4 years.",
                "source_id": "source_a",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }

    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 85, "issues": []},
        {"source_a": "Source A"},
        {"items": []},
        question="Should the intervention be used to reduce risk?",
    )
    package = compose_final_reader_memo_package("## Decision Brief\n\nA decision.", scaffold)

    assert scaffold["quantity_ledger"]["quantity_count"] >= 3
    assert scaffold["quantity_ledger"]["quantitative_card_count"] >= 1
    assert scaffold["quantitative_evidence_cards"]
    assert scaffold["quantitative_anchors"]
    assert "## Quantitative Evidence Ledger" in package["appendix"]
    assert "### Quantitative Evidence Cards" in package["appendix"]
    assert "RR 0.82" in package["appendix"]


def test_scaffold_artifacts_write_argument_model(tmp_path) -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The intervention was associated with lower risk (RR 0.82, 95% CI 0.70-0.96).",
                "excerpt": "The cohort included 12,400 participants over 4 years.",
                "source_id": "source_a",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 85, "issues": []},
        {"source_a": "Source A"},
        {"items": []},
        question="Should the intervention be used to reduce risk?",
    )

    paths = write_scaffold_artifacts(
        artifacts=tmp_path,
        prompt="prompt",
        prioritized_map=candidate_map,
        prioritization_report={"changed": False},
        erosion_audit={"items": []},
        scaffold=scaffold,
    )

    argument_model = json.loads(paths["argument_model"].read_text(encoding="utf-8"))
    assert argument_model["schema_id"] == "argument_model_v1"
    assert argument_model["decision_question"] == "Should the intervention be used to reduce risk?"
    assert argument_model["strongest_support"]


def test_final_review_packet_summarizes_structured_artifacts(tmp_path) -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The intervention was associated with lower risk (RR 0.82, 95% CI 0.70-0.96).",
                "source_id": "source_a",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 85, "issues": []},
        {"source_a": "Source A"},
        {"items": []},
        question="Should the intervention be used to reduce risk?",
    )
    scaffold_paths = write_scaffold_artifacts(
        artifacts=tmp_path,
        prompt="prompt",
        prioritized_map=candidate_map,
        prioritization_report={"changed": False},
        erosion_audit={"items": []},
        scaffold=scaffold,
    )
    briefing = tmp_path / "BRIEFING.md"
    appendix = tmp_path / "EVIDENCE_APPENDIX.md"
    summary = tmp_path / "briefing_summary.json"
    section_packets = tmp_path / "section_synthesis_packets.json"
    gap = tmp_path / "telemetry" / "gap_diagnosis.json"
    for path in (briefing, appendix, summary, section_packets, gap):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    packet_path = tmp_path / "FINAL_REVIEW_PACKET.md"
    write_final_review_packet(
        packet_path,
        repo_root=tmp_path,
        question="Should the intervention be used to reduce risk?",
        backend="prompt",
        summary_path=summary,
        briefing_path=briefing,
        evidence_appendix_path=appendix,
        scaffold_paths=scaffold_paths,
        telemetry_paths={"gap_diagnosis": gap},
        final_outputs={
            "briefing_validation": {"status": "passes_contract", "score": 100},
            "polish_report": {"status": "polished", "score": 95},
            "rewrite_result": {"report": {"status": "skipped_prompt_backend"}},
            "summary_paths": {"section_synthesis_packets": section_packets},
        },
        quality_report={"status": "usable_with_review", "score": 85, "issues": []},
        candidate_map=candidate_map,
        prioritized_map=candidate_map,
        scaffold=scaffold,
    )

    text = packet_path.read_text(encoding="utf-8")
    assert "# Final Review Packet" in text
    assert "Argument model" in text
    assert "Quantitative anchors" in text
    assert "`BRIEFING.md`" in text
