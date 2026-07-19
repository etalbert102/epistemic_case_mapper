from __future__ import annotations

import json
import sys
from pathlib import Path

import epistemic_case_mapper.pipeline.map.staged_semantic_whole_doc as whole_doc_adapter
import epistemic_case_mapper.pipeline.map.staged_semantic_whole_doc_pipeline as whole_doc_pipeline
from epistemic_case_mapper.staged_semantic_pipeline import _extract_claims, _load_context
from epistemic_case_mapper.pipeline.map.staged_semantic_progress import PipelineProgress
from epistemic_case_mapper.pipeline.map.staged_semantic_whole_doc import effective_whole_doc_claim_cap, whole_doc_num_predict

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
                                "entailed_by_excerpt": "yes",
                                "question_relevance": "direct",
                                "scope_flags": ["none"],
                                "decision_importance": "high",
                                "why_it_matters": "It directly bears on the decision question.",
                                "natural_bottom_line": "The program appears to reduce the target risk.",
                                "must_preserve_terms": ["20 percent", "target risk"],
                                "claim_context": {
                                    "population": "eligible program participants",
                                    "exposure_or_option": "the program",
                                    "outcome_or_endpoint": "target risk",
                                    "evidence_design": "source-reported result",
                                    "stated_dose_or_threshold": "",
                                    "stated_scope": ["eligible program participants"],
                                    "stated_limitations": ["duration not stated in the excerpt"],
                                    "applicability_limits": ["reported source scope"],
                                },
                            "supporting_quotes": [
                                {
                                    "quote": "The program reduced target risk by 20 percent.",
                                    "line_hint": "lines 1-1",
                                }
                            ],
                            "quantities": [
                                {
                                    "value": "20 percent",
                                    "quantity_role": "effect_estimate",
                                    "measures": "target risk reduction",
                                    "local_interpretation": "This is the main effect estimate.",
                                    "source_quote": "The program reduced target risk by 20 percent.",
                                    "line_hint": "lines 1-1",
                                    "retention_hint": "must_retain",
                                }
                            ],
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
    assert payload["claims"][0]["whole_doc_source_card"]["natural_bottom_line"] == "The program appears to reduce the target risk."
    assert "source_limit" not in payload["claims"][0]["whole_doc_source_card"]
    assert payload["claims"][0]["whole_doc_source_card"]["must_preserve_terms"] == ["20 percent", "target risk"]
    assert payload["claims"][0]["whole_doc_source_card"]["claim_context"] == {
        "population": "eligible program participants",
        "exposure_or_option": "the program",
        "outcome_or_endpoint": "target risk",
        "evidence_design": "source-reported result",
        "stated_dose_or_threshold": "",
        "stated_scope": ["eligible program participants"],
        "stated_limitations": ["duration not stated in the excerpt"],
        "applicability_limits": ["reported source scope"],
    }
    assert payload["claims"][0]["claim_quantities"][0]["quantity_role"] == "effect_estimate"
    assert payload["claims"][0]["claim_quantities"][0]["measures"] == "target risk reduction"
    assert payload["claims"][0]["quantity_values"] == ["20 percent"]
    assert "decision_polarity" not in payload["claims"][0]["whole_doc_source_card"]
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["repair_used"] is False
    assert report["source_card_exact_quote_count"] == 1
    assert report["rich_claim_context_field_counts"]["population"] == 1
    assert report["rich_claim_context_field_counts"]["outcome_or_endpoint"] == 1
    assert report["rich_claim_natural_bottom_line_count"] == 1
    assert report["rich_claim_stated_limitations_count"] == 1
    assert report["rich_claim_must_preserve_terms_count"] == 1
    assert len(calls) == 1
    assert calls[0]["response_schema"] is not None
    claim_schema = calls[0]["response_schema"]["properties"]["canonical_claims"]["items"]
    assert "claim_context" in claim_schema["required"]
    assert "entailed_by_excerpt" in claim_schema["required"]


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


def test_whole_doc_cache_reuse_requires_matching_content_question_backend_and_settings(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    class Result:
        def __init__(self, text: str):
            self.text = text

    def fake_backend(prompt: str, backend: str, **kwargs):
        del kwargs
        calls.append(backend)
        quote = (
            "Changed evidence reduced the target risk."
            if "Changed evidence reduced the target risk." in prompt
            else "Original evidence reduced the target risk."
        )
        return Result(
            json.dumps(
                {
                    "source_id": "demo_source",
                    "source_bottom_line": quote,
                    "canonical_claims": [
                        {
                            "claim": quote,
                            "entailed_by_excerpt": "yes",
                            "question_relevance": "direct",
                            "scope_flags": ["none"],
                            "decision_importance": "high",
                            "why_it_matters": "It directly answers the question.",
                            "supporting_quotes": [{"quote": quote, "line_hint": "lines 1-1"}],
                            "quantities": [],
                            "scope_conditions": [],
                        }
                    ],
                    "excluded_as_not_decision_relevant": [],
                }
            )
        )

    monkeypatch.setattr(whole_doc_adapter, "run_model_backend", fake_backend)
    paths = {
        "canonical_path": tmp_path / "canonical.json",
        "raw_path": tmp_path / "raw.txt",
        "repair_raw_path": tmp_path / "repair_raw.txt",
        "report_path": tmp_path / "report.json",
    }
    base = {
        "source_id": "demo_source",
        "source_title": "Demo Source",
        "source_text": "Original evidence reduced the target risk.",
        "decision_question": "Should the original option be used?",
        "backend": "ollama:model-a",
        "backend_timeout": 5,
        "backend_retries": 0,
        "max_claims": 6,
        **paths,
    }

    first, first_hit, first_error = whole_doc_adapter.whole_doc_claim_payload_for_source(**base, reuse_claim_cache=False)
    same, same_hit, same_error = whole_doc_adapter.whole_doc_claim_payload_for_source(**base, reuse_claim_cache=True)
    changed_question, question_hit, _ = whole_doc_adapter.whole_doc_claim_payload_for_source(
        **{**base, "decision_question": "Should a different option be used?"},
        reuse_claim_cache=True,
    )
    changed_backend, backend_hit, _ = whole_doc_adapter.whole_doc_claim_payload_for_source(
        **{**base, "decision_question": "Should a different option be used?", "backend": "ollama:model-b"},
        reuse_claim_cache=True,
    )
    changed_settings, settings_hit, _ = whole_doc_adapter.whole_doc_claim_payload_for_source(
        **{
            **base,
            "decision_question": "Should a different option be used?",
            "backend": "ollama:model-b",
            "max_claims": 7,
        },
        reuse_claim_cache=True,
    )
    changed_source, source_hit, _ = whole_doc_adapter.whole_doc_claim_payload_for_source(
        **{
            **base,
            "source_text": "Changed evidence reduced the target risk.",
            "decision_question": "Should a different option be used?",
            "backend": "ollama:model-b",
            "max_claims": 7,
        },
        reuse_claim_cache=True,
    )

    assert first_error == same_error == ""
    assert first_hit is False
    assert same_hit is True
    assert question_hit is backend_hit is settings_hit is source_hit is False
    assert first == same
    assert changed_question and changed_backend and changed_settings and changed_source
    assert len(calls) == 5
    assert changed_source["claims"][0]["claim"] == "Changed evidence reduced the target risk."
    assert changed_source["cache_identity"]["source_sha256"] != first["cache_identity"]["source_sha256"]
    assert changed_source["cache_identity"]["settings"]["requested_max_claims"] == 7


def test_source_card_claim_requires_explicit_entailment_and_non_reference_support() -> None:
    valid = {
        "claim": "The intervention was associated with lower mortality.",
        "entailed_by_excerpt": "yes",
        "question_relevance": "direct",
        "scope_flags": ["none"],
        "decision_importance": "high",
        "supporting_quotes": [
            {
                "quote": "The intervention was associated with lower mortality.",
                "line_hint": "lines 1-1",
            }
        ],
        "quantities": [],
    }
    source_text = "The intervention was associated with lower mortality."

    accepted = whole_doc_adapter._normalize_source_card_claim(valid, source_text=source_text)
    uncertain = whole_doc_adapter._normalize_source_card_claim(
        {**valid, "entailed_by_excerpt": "uncertain"},
        source_text=source_text,
    )
    causal_overreach = whole_doc_adapter._normalize_source_card_claim(
        {**valid, "claim": "The intervention caused lower mortality."},
        source_text=source_text,
    )
    reference_quote = "Smith J, et al. Intervention outcomes. Journal 2020;10:1-8. doi:10.1000/demo"
    reference_claim = whole_doc_adapter._normalize_source_card_claim(
        {
            **valid,
            "claim": reference_quote,
            "supporting_quotes": [{"quote": reference_quote, "line_hint": "lines 2-2"}],
        },
        source_text=reference_quote,
    )
    linked_result_quote = (
        "The trial found that the intervention was associated with lower mortality; "
        "the full report is available at https://example.test/trial."
    )
    linked_result_claim = whole_doc_adapter._normalize_source_card_claim(
        {
            **valid,
            "claim": "The trial found that the intervention was associated with lower mortality.",
            "supporting_quotes": [{"quote": linked_result_quote, "line_hint": "lines 3-3"}],
        },
        source_text=linked_result_quote,
    )

    assert accepted is not None
    assert accepted["entailed_by_excerpt"] == "yes"
    assert uncertain is None
    assert causal_overreach is None
    assert reference_claim is None
    assert linked_result_claim is not None


def test_whole_doc_source_card_accepts_fenced_json_with_string_array_key_value_item(monkeypatch, tmp_path: Path) -> None:
    class Result:
        text = """```json
{
  "source_id": "demo_source",
  "source_bottom_line": "The source reports a decision-relevant result.",
  "canonical_claims": [
    {
      "claim": "Alpha lowered target risk by 20 percent.",
      "entailed_by_excerpt": "yes",
      "question_relevance": "direct",
      "scope_flags": [
        "population: adults",
        "outcome_or_endpoint": "target risk"
      ],
      "decision_importance": "high",
      "why_it_matters": "It reports the result most relevant to the decision.",
      "natural_bottom_line": "Alpha lowered target risk.",
      "must_preserve_terms": ["20 percent", "target risk"],
      "claim_context": {
        "population": "adults",
        "exposure_or_option": "Alpha",
        "outcome_or_endpoint": "target risk",
        "evidence_design": "source-reported result",
        "stated_dose_or_threshold": "",
        "stated_scope": ["adults"],
        "stated_limitations": [],
        "applicability_limits": []
      },
      "supporting_quotes": [
        {"quote": "Alpha lowered target risk by 20 percent.", "line_hint": "lines 1-1"}
      ],
      "quantities": [],
      "scope_conditions": []
    }
  ],
  "excluded_as_not_decision_relevant": []
}
```"""

    def fake_backend(*args, **kwargs):
        return Result()

    monkeypatch.setattr(whole_doc_adapter, "run_model_backend", fake_backend)
    payload, cache_hit, error = whole_doc_adapter.whole_doc_claim_payload_for_source(
        source_id="demo_source",
        source_title="Demo Source",
        source_text="Alpha lowered target risk by 20 percent.",
        decision_question="Should Alpha be used?",
        backend="ollama:fake-model",
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
    assert payload["claims"][0]["whole_doc_source_card"]["scope_conditions"] == []
    assert payload["claims"][0]["whole_doc_source_card"]["natural_bottom_line"] == "Alpha lowered target risk."
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["status"] == "ok"


def test_whole_doc_backend_error_writes_source_report(monkeypatch, tmp_path: Path) -> None:
    def fake_backend(*args, **kwargs):
        raise RuntimeError("backend timed out")

    monkeypatch.setattr(whole_doc_adapter, "run_model_backend", fake_backend)
    payload, cache_hit, error = whole_doc_adapter.whole_doc_claim_payload_for_source(
        source_id="demo_source",
        source_title="Demo Source",
        source_text="Alpha line.",
        decision_question="What matters?",
        backend="ollama:fake-model",
        backend_timeout=5,
        backend_retries=0,
        max_claims=8,
        canonical_path=tmp_path / "canonical.json",
        raw_path=tmp_path / "raw.txt",
        repair_raw_path=tmp_path / "repair_raw.txt",
        report_path=tmp_path / "report.json",
        reuse_claim_cache=False,
    )

    assert payload is None
    assert cache_hit is False
    assert error == "backend timed out"
    assert json.loads((tmp_path / "canonical.json").read_text(encoding="utf-8")) == {}
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "backend_error"
    assert report["phase"] == "initial_extraction"
    assert report["source_id"] == "demo_source"


def test_extract_claims_can_use_whole_doc_source_cards(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    manifest, region, case_manifest = _load_context(tmp_path, "submission_manifest.yaml", "demo_region_json")

    def fake_whole_doc_payload_for_source(**kwargs):
        quote = "Alpha line." if kwargs["source_id"] == "demo_source_1" else "Gamma line."
        return (
            {
                "claims": [
                    {
                        "claim": quote,
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
    assert '"parallelism": 2' in progress


def test_claim_extraction_parallelism_uses_stage_override(monkeypatch) -> None:
    monkeypatch.setenv("ECM_MODEL_PARALLELISM", "8")
    monkeypatch.setenv("ECM_OLLAMA_PARALLELISM", "8")
    monkeypatch.delenv("ECM_CLAIM_EXTRACTION_PARALLELISM", raising=False)

    assert whole_doc_pipeline.claim_extraction_parallelism("ollama:fake-model") == 2
    assert whole_doc_pipeline.claim_extraction_parallelism("command:fake") == 8

    monkeypatch.setenv("ECM_CLAIM_EXTRACTION_PARALLELISM", "3")

    assert whole_doc_pipeline.claim_extraction_parallelism("ollama:fake-model") == 3


def test_whole_doc_source_fetch_records_monitorable_backend_call(monkeypatch, tmp_path: Path) -> None:
    chunk = whole_doc_pipeline.WholeDocSourceChunk(
        chunk_id="demo_source_whole_doc",
        source_id="demo_source",
        title="Demo Source",
        start_line=1,
        end_line=1,
        ordinal=1,
        numbered_text="1: Demo source line.",
        plain_text="Demo source line.",
        spans=(),
    )

    def fake_whole_doc_payload_for_source(**kwargs):
        return ({"claims": [], "extractor": "whole-doc"}, False, "")

    monkeypatch.setattr(whole_doc_pipeline, "whole_doc_claim_payload_for_source", fake_whole_doc_payload_for_source)
    progress = PipelineProgress(tmp_path / "pipeline_progress.json", backend_timeout=45)
    progress.start_stage("claim_extraction", total_items=1)

    result = whole_doc_pipeline._fetch_whole_doc_payload(
        (1, chunk),
        selected_question="Should this source be monitored?",
        backend="ollama:fake-model",
        backend_timeout=45,
        backend_retries=0,
        max_claims_per_source=3,
        source_dir=tmp_path,
        reuse_claim_cache=False,
        progress=progress,
        total_sources=1,
    )

    payload = json.loads((tmp_path / "pipeline_progress.json").read_text(encoding="utf-8"))
    assert result["backend_error"] == ""
    assert payload["backend_call_count"] == 1
    assert payload["active_backend_call_count"] == 0
    assert payload["recent_backend_calls"][-1]["item_id"] == "demo_source"
    assert payload["recent_backend_calls"][-1]["stage"] == "claim_extraction"
    assert "stage=claim_extraction" in payload["monitor_summary"]


def test_whole_doc_claim_extraction_retries_backend_errors_serially(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    manifest, region, case_manifest = _load_context(tmp_path, "submission_manifest.yaml", "demo_region_json")
    call_counts: dict[str, int] = {}

    def fake_whole_doc_payload_for_source(**kwargs):
        source_id = kwargs["source_id"]
        call_counts[source_id] = call_counts.get(source_id, 0) + 1
        if source_id == "demo_source_2" and call_counts[source_id] == 1:
            return None, False, "timed out"
        quote = "Alpha line." if source_id == "demo_source_1" else "Gamma line."
        return (
            {
                "claims": [
                    {
                            "claim": quote,
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
        decision_question="Can serial retry recover a required source?",
    )

    assert [claim["source_id"] for claim in claims] == ["demo_source_1", "demo_source_2"]
    assert rejected == []
    assert call_counts == {"demo_source_1": 1, "demo_source_2": 2}
    progress = json.loads((tmp_path / "artifacts" / "claim_extraction_progress.json").read_text(encoding="utf-8"))
    assert progress["backend_call_count"] == 3
    assert progress["serial_retry_attempt_count"] == 1
    assert progress["serial_retry_recovered_count"] == 1
    assert progress["serial_retry_failed_count"] == 0


def test_whole_doc_relevance_validation_warns_without_blocking(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    manifest, region, case_manifest = _load_context(tmp_path, "submission_manifest.yaml", "demo_region_json")
    grounded_claim = "The retrofit increased the risk of equipment discoloration."
    for source in case_manifest.sources:
        assert source.path
        (tmp_path / source.path).write_text(grounded_claim, encoding="utf-8")

    def fake_whole_doc_payload_for_source(**kwargs):
        quote = grounded_claim
        return (
            {
                "claims": [
                    {
                        "claim": grounded_claim,
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
