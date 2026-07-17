from __future__ import annotations

import re

import pytest

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_finalization import run_memo_ready_packet_synthesis
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.map_briefing_section_evidence_anchoring import (
    build_evidence_expression_contracts,
    build_evidence_reconciliation_report,
    render_evidence_tagged_memo,
)
from epistemic_case_mapper.model_backends import ModelBackendResult

from test_decision_briefing_packet import _scaffold


def test_evidence_expression_contracts_derive_required_slots() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "must_use": True,
                "obligation_level": "must_include",
                "reader_claim": "Option A reduces losses.",
                "role": "strongest_support",
                "quantities": [{"value": "25%", "interpretation": "loss reduction"}],
                "caveat": "Comparable cities only",
                "source_ids": ["s1"],
            }
        ],
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "evidence_item_ids": ["e1"],
                    "source_ids": ["s1"],
                    "statement": "Use Option A support.",
                }
            ],
            "evidence_language_contracts": [
                {
                    "item_id": "e1",
                    "avoid_language": ["proves"],
                    "must_qualify_with": ["observational"],
                    "source_ids": ["s1"],
                }
            ],
        },
    }

    contracts = build_evidence_expression_contracts(packet)

    assert contracts[0]["evidence_id"] == "e1"
    assert contracts[0]["required"] is True
    assert contracts[0]["source_ids"] == ["s1"]
    assert contracts[0]["required_quantity_atoms"][0]["value"] == "25%"
    assert contracts[0]["population_scope"] == "Comparable cities only"
    assert contracts[0]["must_not_imply"] == ["proves"]


def test_evidence_expression_contracts_include_numeric_must_preserve_terms() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "Comparator evidence bounds the answer.",
                "role": "strongest_counterweight",
                "source_ids": ["s1"],
                "quantities": [{"value": "1.15", "interpretation": "hazard ratio"}],
                "must_preserve_terms": [
                    "hazard ratio 1.15 with 95% confidence interval 1.05 to 1.27",
                    "secondary estimate 8.14",
                    "observational evidence",
                ],
            }
        ],
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "canonical_decision_writer_packet": {},
    }

    contracts = build_evidence_expression_contracts(packet)

    quantities = contracts[0]["required_quantity_atoms"]
    assert any("1.15" in row["value"] and "1.05 to 1.27" in row["value"] for row in quantities)
    assert not any("8.14" in row["value"] for row in quantities)
    assert contracts[0]["must_preserve_terms"][0].startswith("hazard ratio 1.15")


def test_evidence_reconciliation_warns_when_required_quantity_missing_near_tag() -> None:
    contracts = [
        {
            "evidence_id": "e1",
            "required": True,
            "required_quantity_atoms": [{"value": "25%", "interpretation": "loss reduction"}],
        }
    ]

    report = build_evidence_reconciliation_report(
        "## Why\n\nThe study supports the answer {E:e1}.",
        "## Why\n\nThe study supports the answer [s1].",
        contracts,
    )

    assert report["status"] == "warning"
    assert report["quantity_warning_count"] == 1
    assert report["quantity_warnings"][0]["missing_quantity_near_tag"] == "25%"


def test_evidence_reconciliation_accepts_quantity_on_one_repeated_tag_expression() -> None:
    contracts = [
        {
            "evidence_id": "e1",
            "required": True,
            "required_quantity_atoms": [{"value": "1.15", "interpretation": "hazard ratio"}],
        }
    ]

    report = build_evidence_reconciliation_report(
        (
            "## Why\n\n"
            "Comparator evidence reports a hazard ratio of 1.15 {E:e1}. "
            "The same evidence also bounds the recommendation {E:e1}."
        ),
        "rendered",
        contracts,
    )

    assert report["status"] == "ready"
    assert report["quantity_warning_count"] == 0


def test_evidence_expression_contracts_do_not_hard_require_soft_quantity_obligations() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "The biomarker evidence bounds the answer.",
                "role": "strongest_counterweight",
                "source_ids": ["s1"],
                "lineage": {"covered_evidence_item_ids": ["claim:one"]},
                "quantities": [{"value": "0.14", "interpretation": "primary ratio"}],
            }
        ],
        "source_trail": [{"source_id": "s1", "source_label": "Study One"}],
        "quantity_obligation_plan": {
            "rows": [
                {
                    "source_evidence_item_id": "claim:one",
                    "value": "8.14",
                    "memo_use": "yes",
                    "must_retain": False,
                    "retention_phrase": "secondary concentration endpoint",
                }
            ]
        },
        "canonical_decision_writer_packet": {},
    }

    contracts = build_evidence_expression_contracts(packet)
    quantities = contracts[0]["required_quantity_atoms"]

    assert any(row["value"] == "0.14" for row in quantities)
    assert not any(row["value"] == "8.14" for row in quantities)


def test_evidence_expression_contracts_resolve_source_ids_from_labels() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "A biomarker worsens.",
                "role": "strongest_counterweight",
                "source_labels": ["Biomarker Trial"],
            }
        ],
        "source_trail": [{"source_id": "s_bio", "source_label": "Biomarker Trial"}],
        "canonical_decision_writer_packet": {},
    }

    contracts = build_evidence_expression_contracts(packet)

    assert contracts[0]["source_ids"] == ["s_bio"]
    assert contracts[0]["required"] is True


def test_render_evidence_tags_to_source_citations_and_trace() -> None:
    rendered = render_evidence_tagged_memo(
        "## Why\n\nOption A reduced losses {E:e1}. Option B is bounded {e1, e2}. Source-level context {s2}.\n",
        [
            {"evidence_id": "e1", "source_ids": ["s1"], "claim": "Option A reduces losses."},
            {"evidence_id": "e2", "source_ids": ["s2"], "claim": "Option B is bounded."},
        ],
    )

    assert "{E:e1}" not in rendered["memo"]
    assert "{e1, e2}" not in rendered["memo"]
    assert "{s2}" not in rendered["memo"]
    assert "[s1]" in rendered["memo"]
    assert "[s1, s2]" in rendered["memo"]
    assert "[s2]" in rendered["memo"]
    assert rendered["trace"][0]["evidence_id"] == "e1"
    assert rendered["trace"][0]["source_ids"] == ["s1"]


def test_render_evidence_tags_normalizes_zero_padded_evidence_ids() -> None:
    rendered = render_evidence_tagged_memo(
        "## Why\n\nThe boundary matters {E:decision_writer_item_11}.\n",
        [{"evidence_id": "decision_writer_item_011", "source_ids": ["s1"], "claim": "Boundary claim."}],
    )

    assert "{E:" not in rendered["memo"]
    assert "[s1]" in rendered["memo"]
    assert rendered["trace"][0]["evidence_id"] == "decision_writer_item_011"


def test_memo_ready_synthesis_uses_unified_evidence_tag_path(monkeypatch: pytest.MonkeyPatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    prompts: list[str] = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        prompts.append(prompt)
        heading = _heading_from_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        if ids:
            tags = " ".join(f"{{E:{evidence_id}}}" for evidence_id in ids)
            body = f"The section makes its decision-relevant point with a 25% anchored effect {tags}."
        else:
            body = "Weight Outcome Study most while using Counter Study and Boundary Report to bound the answer [s1, s2, s3]."
        return ModelBackendResult(text=f"## {heading}\n\n{body}\n", backend="fake")

    import epistemic_case_mapper.map_briefing_memo_ready_finalization as finalization

    monkeypatch.setattr(finalization, "run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["synthesis_mode"] == "unified_section_synthesis"
    assert result["report"]["used_default_path"] is False
    assert result["evidence_expression_contracts"]
    assert result["evidence_trace"]
    assert result["evidence_tag_section_reports"]
    assert any("### Evidence expression contracts" in prompt for prompt in prompts)
    assert any("### Source weighting notes" in prompt for prompt in prompts)
    assert "{E:" not in result["memo"]
    assert result["report"]["evidence_reconciliation_report"]["used_evidence_id_count"] >= 1


def _heading_from_prompt(prompt: str) -> str:
    match = re.search(r"exactly(?: with)?: ## (.+)", prompt)
    if not match:
        match = re.search(r"Output starts exactly with: ## (.+)", prompt)
    return match.group(1).strip() if match else "Why This Is the Best Current Read"
