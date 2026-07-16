from __future__ import annotations

import re

import pytest

from epistemic_case_mapper.evidence_anchored_synthesis_experiment import (
    build_evidence_expression_contracts,
    render_evidence_tagged_memo,
    run_evidence_anchored_synthesis_experiment,
)
from epistemic_case_mapper.map_briefing_memo_ready_finalization import run_memo_ready_packet_synthesis
from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
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


def test_evidence_anchored_experiment_runs_with_fake_model() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_from_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        tag = f" {{E:{ids[0]}}}" if ids else ""
        return ModelBackendResult(text=f"## {heading}\n\nThe section expresses its evidence naturally{tag}.\n", backend="fake")

    result = run_evidence_anchored_synthesis_experiment(
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_model=fake_backend,
    )

    assert result["report"]["section_count"] >= 1
    assert result["evidence_trace"]
    assert "{E:" in result["tagged_memo"]
    assert "{E:" not in result["memo"]
    assert result["reconciliation_report"]["known_evidence_id_count"] >= 1
    assert result["report"]["missing_mandatory_count"] >= 0


def test_memo_ready_synthesis_can_use_evidence_anchored_path(monkeypatch: pytest.MonkeyPatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_from_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        tags = " ".join(f"{{E:{evidence_id}}}" for evidence_id in ids[:2])
        return ModelBackendResult(text=f"## {heading}\n\nThe section makes its decision-relevant point with anchored evidence {tags}.\n", backend="fake")

    import epistemic_case_mapper.map_briefing_memo_ready_finalization as finalization

    monkeypatch.setenv("ECM_EVIDENCE_ANCHORED_SYNTHESIS", "1")
    monkeypatch.setattr(finalization, "run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["synthesis_mode"] == "evidence_anchored_section_synthesis"
    assert result["report"]["used_default_path"] is False
    assert result["evidence_expression_contracts"]
    assert result["evidence_trace"]
    assert "{E:" not in result["memo"]
    assert result["report"]["evidence_reconciliation_report"]["used_evidence_id_count"] >= 1


def _heading_from_prompt(prompt: str) -> str:
    match = re.search(r"exactly with: ## (.+)", prompt)
    return match.group(1).strip() if match else "Why This Is the Best Current Read"
