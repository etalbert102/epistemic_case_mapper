from __future__ import annotations

import json
import sys
from pathlib import Path

import epistemic_case_mapper.staged_semantic_whole_doc as whole_doc_adapter
import epistemic_case_mapper.staged_semantic_whole_doc_pipeline as whole_doc_pipeline
from epistemic_case_mapper.staged_semantic_pipeline import _extract_claims, _load_context
from epistemic_case_mapper.staged_semantic_whole_doc import effective_whole_doc_claim_cap, whole_doc_num_predict

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from test_submission_manifest_generalization import _write_transfer_fixture


def test_whole_doc_source_card_repairs_common_schema_variant(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    class Result:
        def __init__(self, text: str):
            self.text = text

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None, num_predict=None):
        calls.append({"prompt": prompt, "response_schema": response_schema})
        if response_schema is None:
            return Result(
                json.dumps(
                    {
                        "source_id": "demo_source",
                        "claims": [
                            {
                                "claim": "The program reduced target risk by 20 percent.",
                                "supporting_quotes": ["The program reduced target risk by 20 percent."],
                                "line_hint": "lines 1-1",
                                "decision_importance": "high",
                            }
                        ],
                    }
                )
            )
        return Result(
            json.dumps(
                {
                    "source_id": "demo_source",
                    "source_bottom_line": "The source supports the intervention.",
                    "canonical_claims": [
                            {
                                "claim": "The program reduced target risk by 20 percent.",
                                "question_relevance": "direct",
                                "scope_flags": ["none"],
                                "decision_importance": "high",
                                "why_it_matters": "It directly bears on the decision question.",
                            "supporting_quotes": [
                                {
                                    "quote": "The program reduced target risk by 20 percent.",
                                    "line_hint": "lines 1-1",
                                }
                            ],
                            "quantities": ["20 percent"],
                            "scope_conditions": [],
                        }
                    ],
                    "excluded_as_not_decision_relevant": [],
                }
            )
        )

    monkeypatch.setattr(whole_doc_adapter, "run_model_backend", fake_backend)

    payload, cache_hit, error = whole_doc_adapter.whole_doc_claim_payload_for_source(
        source_id="demo_source",
        source_title="Demo Source",
        source_text="The program reduced target risk by 20 percent.",
        decision_question="Should the program be adopted?",
        backend="ollama:fake",
        backend_timeout=5,
        backend_retries=0,
        max_claims=6,
        canonical_path=tmp_path / "canonical.json",
        raw_path=tmp_path / "raw.txt",
        repair_raw_path=tmp_path / "repair_raw.txt",
        report_path=tmp_path / "report.json",
        reuse_claim_cache=False,
    )

    assert error == ""
    assert cache_hit is False
    assert payload is not None
    assert payload["claims"][0]["claim"] == "The program reduced target risk by 20 percent."
    assert payload["claims"][0]["source_quote"] == "The program reduced target risk by 20 percent."
    assert payload["claims"][0]["role"] == "source_claim"
    assert payload["claims"][0]["question_relevance"] == "direct"
    assert payload["claims"][0]["whole_doc_source_card"]["quantities"] == ["20 percent"]
    assert "decision_polarity" not in payload["claims"][0]["whole_doc_source_card"]
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["repair_used"] is False
    assert report["source_card_exact_quote_count"] == 1
    assert len(calls) == 1
    assert calls[0]["response_schema"] is not None


def test_whole_doc_claim_cap_and_output_budget_scale_for_long_documents(monkeypatch) -> None:
    monkeypatch.delenv("ECM_WHOLE_DOC_MAX_CLAIMS_CAP", raising=False)
    monkeypatch.delenv("ECM_WHOLE_DOC_OLLAMA_NUM_PREDICT", raising=False)
    monkeypatch.delenv("ECM_WHOLE_DOC_OLLAMA_NUM_PREDICT_MAX", raising=False)
    monkeypatch.delenv("ECM_OLLAMA_NUM_PREDICT", raising=False)

    assert effective_whole_doc_claim_cap("short source", 8) == 8
    assert effective_whole_doc_claim_cap("x" * 60_000, 8) == 14
    assert whole_doc_num_predict("short source", 8) == 8192
    assert whole_doc_num_predict("x" * 60_000, 14) == 13_312

    monkeypatch.setenv("ECM_WHOLE_DOC_MAX_CLAIMS_CAP", "10")
    assert effective_whole_doc_claim_cap("x" * 60_000, 8) == 10

    monkeypatch.setenv("ECM_WHOLE_DOC_OLLAMA_NUM_PREDICT", "9000")
    assert whole_doc_num_predict("x" * 60_000, 14) == 9000


def test_extract_claims_can_use_whole_doc_source_cards(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    manifest, region, case_manifest = _load_context(tmp_path, "submission_manifest.yaml", "demo_region_json")

    def fake_whole_doc_payload_for_source(**kwargs):
        quote = "Alpha line." if kwargs["source_id"] == "demo_source_1" else "Gamma line."
        return (
            {
                "claims": [
                    {
                        "claim": f"{quote} supports a decision-relevant source-card claim.",
                        "source_quote": quote,
                        "span_id": "",
                        "entailed_by_excerpt": "yes",
                        "role": "conclusion_support",
                        "question_relevance": "direct",
                        "relevance_rationale": "It is included in the source-card output.",
                        "scope_flags": ["none"],
                        "decision_importance": "high",
                        "decision_function": "answer_bearing",
                        "default_use": "main_map",
                        "importance_rationale": "It is a canonical source claim.",
                    }
                ],
                "extractor": "whole-doc",
            },
            False,
            "",
        )

    monkeypatch.setattr(whole_doc_pipeline, "whole_doc_claim_payload_for_source", fake_whole_doc_payload_for_source)
    monkeypatch.setenv("ECM_MODEL_PARALLELISM", "4")

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
        decision_question="Can the demo source-card extraction work?",
    )

    assert [claim["source_id"] for claim in claims] == ["demo_source_1", "demo_source_2"]
    assert all(claim["extraction_method"] == "whole_doc_source_card" for claim in claims)
    assert rejected == []
    progress = (tmp_path / "artifacts" / "claim_extraction_progress.json").read_text(encoding="utf-8")
    assert '"stage": "whole_doc_claim_extraction"' in progress
    assert '"claim_extraction_method": "whole_doc_source_card"' in progress
    assert '"parallelism": 4' in progress


def test_whole_doc_relevance_validation_warns_without_blocking(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    manifest, region, case_manifest = _load_context(tmp_path, "submission_manifest.yaml", "demo_region_json")

    def fake_whole_doc_payload_for_source(**kwargs):
        quote = "Alpha line." if kwargs["source_id"] == "demo_source_1" else "Gamma line."
        return (
            {
                "claims": [
                    {
                        "claim": "The retrofit increased the risk of equipment discoloration.",
                        "source_quote": quote,
                        "span_id": "",
                        "entailed_by_excerpt": "yes",
                        "role": "conclusion_support",
                        "question_relevance": "direct",
                        "relevance_rationale": "The model judged this source-card claim relevant.",
                        "scope_flags": ["none"],
                        "decision_importance": "high",
                        "decision_function": "answer_bearing",
                        "default_use": "main_map",
                        "importance_rationale": "It is a canonical source claim.",
                    }
                ],
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
        decision_question="Should the retrofit reduce hospital admissions?",
    )

    assert len(claims) == 2
    assert rejected == []
    assert claims[0]["deterministic_relevance_validation"] == {
        "status": "warning",
        "reason": "question_outcome_mismatch",
        "blocking": False,
        "method": "deterministic_question_fit_check_v1",
    }
    assert claims[0]["label_audit"]["synthesis_bucket"] == "supporting"
    assert claims[0]["label_audit"]["routing_default_use"] == "supporting_map"
    progress = json.loads((tmp_path / "artifacts" / "claim_extraction_progress.json").read_text(encoding="utf-8"))
    assert progress["relevance_validation_warning_counts"] == {"question_outcome_mismatch": 2}
    assert progress["label_audit_bucket_counts"] == {"supporting": 2}
