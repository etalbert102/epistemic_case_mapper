from __future__ import annotations

import json
import sys
from pathlib import Path

import epistemic_case_mapper.pipeline.map.staged_semantic_whole_doc_pipeline as whole_doc_pipeline
from epistemic_case_mapper.pipeline.map.staged_semantic_evidence_routing import build_evidence_unit_routing
from epistemic_case_mapper.staged_semantic_pipeline import _extract_claims, _load_context

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from test_submission_manifest_generalization import _write_transfer_fixture


def test_evidence_unit_routing_projects_model_relevance_labels() -> None:
    units = [
        _unit("u1", "s1", "direct"),
        _unit("u2", "s1", "scope_limit"),
        _unit("u3", "s2", "indirect"),
        _unit("u4", "s3", "background"),
        _unit("u5", "s4", "irrelevant"),
    ]

    routing = build_evidence_unit_routing(units, decision_question="Should the option be adopted?", source_ids=["s1", "s2", "s3", "s4", "s5"])

    rows = routing["evidence_relevance_ledger"]["rows"]
    report = routing["evidence_routing_report"]
    deferred = routing["deferred_evidence_audit"]
    assert [row["routing_decision"] for row in rows] == ["include", "include", "defer", "appendix", "exclude"]
    assert all(row["blocking"] is False for row in rows)
    assert report["routing_counts"] == {"include": 2, "defer": 1, "appendix": 1, "exclude": 1}
    assert report["source_coverage"][-1] == {"source_id": "s5", "coverage_status": "no_evidence_units"}
    assert deferred["deferred_count"] == 1
    assert deferred["appendix_count"] == 1
    assert deferred["excluded_count"] == 1


def test_extraction_writes_evidence_unit_routing_artifacts(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    manifest, region, case_manifest = _load_context(tmp_path, "submission_manifest.yaml", "demo_region_json")

    def fake_whole_doc_payload_for_source(**kwargs):
        source_id = kwargs["source_id"]
        relevance = "direct" if source_id == "demo_source_1" else "irrelevant"
        quote = "Alpha line." if source_id == "demo_source_1" else "Gamma line."
        return (
            {
                "claims": [
                    {
                        "claim": f"{quote} supports a source-card claim.",
                        "source_quote": quote,
                        "span_id": "",
                        "entailed_by_excerpt": "yes",
                        "role": "conclusion_support",
                        "question_relevance": relevance,
                        "relevance_rationale": "Model extraction label.",
                        "scope_flags": ["none"],
                        "decision_importance": "high",
                        "decision_function": "answer_bearing",
                        "default_use": "main_map",
                        "importance_rationale": "It is a canonical source claim.",
                    }
                ],
                "source_evidence_units": {
                    "schema_id": "source_evidence_units_v1",
                    "source_id": source_id,
                    "units": [_unit(f"{source_id}_eu001", source_id, relevance, quote=quote)],
                },
                "source_quantity_tuples": {"schema_id": "source_quantity_tuples_v1", "source_id": source_id, "tuples": []},
                "source_evidence_unit_quality_report": {
                    "schema_id": "source_evidence_unit_quality_report_v1",
                    "status": "ready",
                    "source_id": source_id,
                    "unit_count": 1,
                    "quantity_tuple_count": 0,
                    "quote_count": 1,
                    "exact_quote_count": 1,
                    "warning_counts": {},
                    "issues": [],
                },
                "extractor": "whole-doc",
            },
            False,
            "",
        )

    monkeypatch.setattr(whole_doc_pipeline, "whole_doc_claim_payload_for_source", fake_whole_doc_payload_for_source)

    claims, rejected = _extract_claims(
        repo_root=tmp_path,
        region=region,
        case_manifest=case_manifest,
        backend="ollama:fake-model",
        backend_timeout=5,
        backend_retries=0,
        artifact_dir=tmp_path / "artifacts",
        max_claims_per_source=6,
        reuse_claim_cache=False,
        decision_question="Can routing artifacts preserve excluded evidence?",
    )

    ledger = json.loads((tmp_path / "artifacts" / "evidence_relevance_ledger.json").read_text(encoding="utf-8"))
    report = json.loads((tmp_path / "artifacts" / "evidence_routing_report.json").read_text(encoding="utf-8"))
    deferred = json.loads((tmp_path / "artifacts" / "deferred_evidence_audit.json").read_text(encoding="utf-8"))
    assert len(claims) == 1
    assert ledger["row_count"] == 2
    assert report["routing_counts"] == {"include": 1, "exclude": 1}
    assert deferred["excluded_count"] == 1
    assert deferred["rows"][0]["routing_decision"] == "exclude"


def _unit(unit_id: str, source_id: str, relevance: str, *, quote: str = "Exact source quote.") -> dict[str, object]:
    return {
        "unit_id": unit_id,
        "source_id": source_id,
        "proposition": f"{quote} matters.",
        "question_relevance": relevance,
        "decision_importance": "high",
        "why_it_matters": "Model-provided relevance rationale.",
        "source_quote": quote,
        "source_span": "lines 1-1",
        "quote_lineage": [{"quote": quote, "line_hint": "lines 1-1", "quote_match_status": "exact_or_normalized"}],
        "warnings": [],
    }
