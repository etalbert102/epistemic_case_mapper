from __future__ import annotations

import json
import sys
from pathlib import Path

import epistemic_case_mapper.pipeline.map.staged_semantic_whole_doc_pipeline as whole_doc_pipeline
from epistemic_case_mapper.pipeline.map.staged_semantic_evidence_units import (
    build_quantity_tuple_binding_report,
    build_quantity_tuple_mutation_eval,
    build_source_evidence_units,
)
from epistemic_case_mapper.staged_semantic_pipeline import _extract_claims, _load_context

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from test_submission_manifest_generalization import _write_transfer_fixture


def test_source_evidence_units_preserve_exact_quote_and_quantity_tuple() -> None:
    source_text = "Adults receiving the program had 20 percent lower hospital admissions over 12 months."
    source_card = {
        "source_id": "demo_source",
        "canonical_claims": [
            {
                "claim": "Adults receiving the program had 20 percent lower hospital admissions over 12 months.",
                "question_relevance": "direct",
                "decision_importance": "critical",
                "why_it_matters": "It directly estimates the target endpoint.",
                "supporting_quotes": [
                    {
                        "quote": "Adults receiving the program had 20 percent lower hospital admissions over 12 months.",
                        "line_hint": "lines 1-1",
                    }
                ],
                "quantities": [
                    {
                        "value": "20 percent",
                        "quantity_role": "effect_estimate",
                        "measures": "hospital admission reduction",
                        "local_interpretation": "Main outcome effect estimate.",
                        "source_quote": "Adults receiving the program had 20 percent lower hospital admissions over 12 months.",
                        "line_hint": "lines 1-1",
                        "retention_hint": "must_retain",
                    },
                    "12 months",
                ],
                "scope_conditions": ["adult participants"],
                "natural_bottom_line": "The program lowered hospital admissions in adults.",
                "must_preserve_terms": ["20 percent", "12 months"],
                "claim_context": {
                    "population": "adult participants",
                    "exposure_or_option": "program receipt",
                    "outcome_or_endpoint": "hospital admissions",
                    "evidence_design": "source-described outcome evidence",
                    "stated_limitations": "single source-local population",
                },
            }
        ],
    }

    bundle = build_source_evidence_units(source_card, source_id="demo_source", source_text=source_text)

    units = bundle["source_evidence_units"]["units"]
    tuples = bundle["source_quantity_tuples"]["tuples"]
    report = bundle["source_evidence_unit_quality_report"]
    assert units[0]["unit_id"] == "demo_source_eu001"
    assert units[0]["source_quote"] == source_text
    assert units[0]["source_span"] == "lines 1-1"
    assert units[0]["warnings"] == []
    assert units[0]["quantities"][0]["quantity_type"] == "percentage"
    assert units[0]["quantities"][0]["quantity_role"] == "effect_estimate"
    assert units[0]["quantities"][0]["measures"] == "hospital admission reduction"
    assert units[0]["quantities"][1]["quantity_type"] == "duration"
    assert units[0]["population"] == "adult participants"
    assert units[0]["exposure_or_intervention"] == "program receipt"
    assert units[0]["endpoint"] == "hospital admissions"
    assert units[0]["evidence_type"] == "source-described outcome evidence"
    assert units[0]["natural_bottom_line"] == "The program lowered hospital admissions in adults."
    assert units[0]["must_preserve_terms"] == ["20 percent", "12 months"]
    assert units[0]["claim_context"]["stated_limitations"] == "single source-local population"
    assert tuples[0]["unit_id"] == "demo_source_eu001"
    assert tuples[0]["schema_id"] == "source_result_quantity_tuple_v1"
    assert tuples[0]["result_tuple_id"] == "demo_source_eu001_q001"
    assert tuples[0]["claim_id"] == "demo_source_eu001"
    assert tuples[0]["value"] == "20 percent"
    assert tuples[0]["estimate"] == "20 percent"
    assert tuples[0]["estimate_type"] == "percentage"
    assert tuples[0]["quantity_role"] == "effect_estimate"
    assert tuples[0]["measures"] == "hospital admission reduction"
    assert tuples[0]["endpoint"] == "hospital admissions"
    assert tuples[0]["population"] == "adult participants"
    assert tuples[0]["exposure_or_intervention"] == "program receipt"
    assert tuples[0]["design"] == "source-described outcome evidence"
    assert report["unit_count"] == 1
    assert report["quantity_tuple_count"] == 2


def test_result_quantity_tuple_reports_detect_identity_and_binding_mutations() -> None:
    source_text = (
        "Adults receiving the program had 20 percent lower hospital admissions over 12 months. "
        "Older adults receiving the program had RR 0.86 (95% CI 0.74 to 0.99) for admissions."
    )
    source_card = {
        "canonical_claims": [
            {
                "claim": "Adults receiving the program had 20 percent lower hospital admissions over 12 months.",
                "supporting_quotes": [
                    {
                        "quote": "Adults receiving the program had 20 percent lower hospital admissions over 12 months.",
                        "line_hint": "line 1",
                    }
                ],
                "quantities": ["20 percent", "12 months"],
                "claim_context": {"population": "adults", "outcome_or_endpoint": "hospital admissions"},
            },
            {
                "claim": "Older adults receiving the program had RR 0.86 (95% CI 0.74 to 0.99) for admissions.",
                "supporting_quotes": [
                    {
                        "quote": "Older adults receiving the program had RR 0.86 (95% CI 0.74 to 0.99) for admissions.",
                        "line_hint": "line 2",
                    }
                ],
                "quantities": ["RR 0.86", "95% CI 0.74 to 0.99"],
                "claim_context": {"population": "older adults", "outcome_or_endpoint": "hospital admissions"},
            },
        ]
    }
    bundle = build_source_evidence_units(source_card, source_id="demo_source", source_text=source_text)
    tuples = bundle["source_quantity_tuples"]["tuples"]

    binding = build_quantity_tuple_binding_report(tuples)
    mutation = build_quantity_tuple_mutation_eval(tuples)

    assert binding["status"] == "ready"
    assert binding["result_tuple_id_count"] == len(tuples)
    assert mutation["status"] == "ready"
    assert mutation["detected_mutation_count"] == mutation["mutation_count"]
    interval = next(row for row in tuples if row["estimate_type"] == "interval")
    assert interval["interval_low"] == "0.74"
    assert interval["interval_high"] == "0.99"


def test_source_evidence_units_warn_when_exact_quote_does_not_support_claim() -> None:
    source_text = "The program was implemented in 2019."
    source_card = {
        "source_id": "demo_source",
        "canonical_claims": [
            {
                "claim": "The program reduced hospital admissions by 20 percent.",
                "supporting_quotes": [{"quote": "The program was implemented in 2019.", "line_hint": "line 1"}],
                "quantities": ["20 percent", "2019"],
                "scope_conditions": [],
            }
        ],
    }

    bundle = build_source_evidence_units(source_card, source_id="demo_source", source_text=source_text)

    unit = bundle["source_evidence_units"]["units"][0]
    report = bundle["source_evidence_unit_quality_report"]
    assert unit["quote_lineage"][0]["quote_match_status"] == "exact_or_normalized"
    assert "weak_quote_claim_overlap" in unit["warnings"]
    assert report["warning_counts"] == {"weak_quote_claim_overlap": 1}


def test_source_evidence_units_do_not_keyword_backfill_semantic_context() -> None:
    source_text = "The randomized trial reduced risk compared with usual care."
    source_card = {
        "source_id": "demo_source",
        "canonical_claims": [
            {
                "claim": "The randomized trial reduced risk compared with usual care.",
                "supporting_quotes": [{"quote": source_text, "line_hint": "line 1"}],
                "quantities": [],
            }
        ],
    }

    unit = build_source_evidence_units(source_card, source_id="demo_source", source_text=source_text)["source_evidence_units"]["units"][0]

    assert unit["evidence_type"] == "unspecified"
    assert unit["endpoint"] == ""
    assert unit["comparator"] == ""
    assert unit["method"] == ""


def test_whole_doc_extraction_writes_aggregate_evidence_unit_artifacts(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    manifest, region, case_manifest = _load_context(tmp_path, "submission_manifest.yaml", "demo_region_json")

    def fake_whole_doc_payload_for_source(**kwargs):
        quote = "Alpha line." if kwargs["source_id"] == "demo_source_1" else "Gamma line."
        unit_id = f"{kwargs['source_id']}_eu001"
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
                "source_evidence_units": {
                    "schema_id": "source_evidence_units_v1",
                    "source_id": kwargs["source_id"],
                    "units": [
                        {
                            "schema_id": "source_evidence_unit_v1",
                            "unit_id": unit_id,
                            "source_id": kwargs["source_id"],
                            "proposition": f"{quote} supports a decision-relevant source-card claim.",
                            "source_quote": quote,
                            "source_span": "lines 1-1",
                            "quote_lineage": [{"quote": quote, "line_hint": "lines 1-1", "quote_match_status": "exact_or_normalized"}],
                            "quantities": [],
                            "warnings": [],
                        }
                    ],
                },
                "source_quantity_tuples": {
                    "schema_id": "source_quantity_tuples_v1",
                    "source_id": kwargs["source_id"],
                    "tuples": [],
                },
                "source_evidence_unit_quality_report": {
                    "schema_id": "source_evidence_unit_quality_report_v1",
                    "status": "ready",
                    "source_id": kwargs["source_id"],
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
        decision_question="Can aggregate evidence-unit artifacts be written?",
    )

    aggregate = json.loads((tmp_path / "artifacts" / "source_evidence_units.json").read_text(encoding="utf-8"))
    quality = json.loads((tmp_path / "artifacts" / "source_evidence_unit_quality_report.json").read_text(encoding="utf-8"))
    quantities = json.loads((tmp_path / "artifacts" / "source_quantity_tuples.json").read_text(encoding="utf-8"))
    binding = json.loads((tmp_path / "artifacts" / "quantity_tuple_binding_report.json").read_text(encoding="utf-8"))
    mutation = json.loads((tmp_path / "artifacts" / "quantity_tuple_mutation_eval.json").read_text(encoding="utf-8"))
    assert len(claims) == 2
    assert rejected == []
    assert aggregate["unit_count"] == 2
    assert [unit["source_id"] for unit in aggregate["units"]] == ["demo_source_1", "demo_source_2"]
    assert quality["status"] == "ready"
    assert quality["exact_quote_count"] == 2
    assert quantities["tuple_count"] == 0
    assert quantities["canonical_record_type"] == "source_result_quantity_tuple_v1"
    assert binding["tuple_count"] == 0
    assert mutation["mutation_count"] == 0
