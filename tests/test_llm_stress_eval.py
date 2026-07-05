from __future__ import annotations

import json
import sys
from pathlib import Path

from epistemic_case_mapper import cli


def test_llm_stress_eval_prompt_backend_writes_reviewable_artifacts(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "package.yaml",
            "eval",
            "llm-stress",
            "--region",
            "demo_case_initial_region",
            "--backend",
            "prompt",
        ],
    )
    assert cli.main() == 0

    report_path = tmp_path / "artifacts/llm_stress_eval/demo_case_initial_region/llm_stress_eval.json"
    markdown_path = tmp_path / "artifacts/llm_stress_eval/demo_case_initial_region/LLM_STRESS_EVAL.md"
    prompt_path = tmp_path / "artifacts/llm_stress_eval/demo_case_initial_region/prompts/insight_delta.txt"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert markdown_path.exists()
    assert prompt_path.exists()
    assert report["summary"]["prompt_only"] is True
    assert report["summary"]["prompt_count"] == 4
    assert report["summary"]["model_run_count"] == 4
    assert report["built_in_metamorphic_checks"][0]["test_type"] == "source_order_shuffle"
    prompt_text = prompt_path.read_text(encoding="utf-8")
    assert "# Output Schema" in prompt_text
    assert "# Examples" in prompt_text
    assert "<packet>" in prompt_text
    assert "Known claim IDs: demo_case_c001, demo_case_c002" in prompt_text


def test_llm_stress_eval_validates_model_references(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
    fake_model = tmp_path / "fake_eval_model.py"
    fake_model.write_text(
        "import json, sys\n"
        "prompt = sys.stdin.read()\n"
        "if 'Prompt ID: insight_delta' in prompt:\n"
        "    payload = {'insight_deltas': [{\n"
        "        'delta_type': 'caveat',\n"
        "        'decision_consequence': 'The map points to the imported document rather than treating the baseline as analysis.',\n"
        "        'map_claim_ids': ['demo_case_c001'],\n"
        "        'relation_ids': [],\n"
        "        'source_ids': ['demo_case_doc_a'],\n"
        "        'baseline_excerpt': 'This starter baseline records the imported source packet',\n"
        "        'risk_if_wrong': 'Could overstate a starter map.'\n"
        "    }]}\n"
        "elif 'Prompt ID: adversarial_critique' in prompt:\n"
        "    payload = {'critic_findings': [{\n"
        "        'finding_type': 'unsupported_confidence',\n"
        "        'severity': 'high',\n"
        "        'threatened_claim_ids': ['missing_claim'],\n"
        "        'relation_ids': [],\n"
        "        'source_ids': ['demo_case_doc_b'],\n"
        "        'reason': 'Intentional bad ID should be caught.',\n"
        "        'repair_prompt': 'Re-check source-linked IDs.'\n"
        "    }]}\n"
        "elif 'Prompt ID: relation_usefulness' in prompt:\n"
        "    payload = {'relation_assessments': []}\n"
        "else:\n"
        "    payload = {'metamorphic_tests': [{\n"
        "        'test_type': 'source_removal',\n"
        "        'mutation': 'Remove one imported document.',\n"
        "        'expected_invariant': 'Affected claims should weaken.',\n"
        "        'linked_claim_ids': ['demo_case_c001'],\n"
        "        'source_ids': ['demo_case_doc_a'],\n"
        "        'failure_signal': 'Confidence remains unchanged.'\n"
        "    }]}\n"
        "print(json.dumps(payload))\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "package.yaml",
            "eval",
            "llm-stress",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
        ],
    )
    assert cli.main() == 0

    report_path = tmp_path / "artifacts/llm_stress_eval/demo_case_initial_region/llm_stress_eval.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["summary"]["prompt_only"] is False
    assert report["summary"]["parsed_output_count"] == 4
    assert report["summary"]["reference_issue_count"] == 1
    assert report["summary"]["status"] == "risk"
    assert report["reference_issues"][0]["reason"] == "unknown_claim_id missing_claim"
    assert any(finding["finding_type"] == "candidate_insight_delta" for finding in report["findings"])
    assert any(finding["finding_type"] == "model_proposed_metamorphic_test" for finding in report["findings"])


def _init_demo_case(monkeypatch, tmp_path: Path) -> None:
    doc_a = tmp_path / "doc_a.txt"
    doc_b = tmp_path / "doc_b.txt"
    doc_a.write_text("Alpha line.\nBeta line.\n", encoding="utf-8")
    doc_b.write_text("Gamma line.\nDelta line.\n", encoding="utf-8")
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "package.yaml",
            "case",
            "init",
            "--case-id",
            "demo_case",
            "--title",
            "Demo Case",
            "--question",
            "Can this package be initialized from arbitrary docs?",
            "--docs",
            str(doc_a),
            str(doc_b),
        ],
    )
    assert cli.main() == 0
