from __future__ import annotations

import json
import sys
from pathlib import Path

from epistemic_case_mapper import cli
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION
from scripts import validate_submission_manifest, validate_submission_references, validate_worked_regions


def test_case_init_creates_runnable_package(monkeypatch, tmp_path: Path) -> None:
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
            "Demo Case",
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

    assert (tmp_path / "package.yaml").exists()
    assert (tmp_path / "data/cases/demo_case/case.yaml").exists()
    assert (tmp_path / "examples/demo_case/worked_map.json").exists()

    monkeypatch.setattr(
        validate_submission_manifest.sys,
        "argv",
        ["validate_submission_manifest.py", "--repo-root", str(tmp_path), "--manifest", "package.yaml"],
    )
    assert validate_submission_manifest.main() == 0
    monkeypatch.setattr(
        validate_worked_regions.sys,
        "argv",
        ["validate_worked_regions.py", "--repo-root", str(tmp_path), "--manifest", "package.yaml"],
    )
    assert validate_worked_regions.main() == 0
    monkeypatch.setattr(
        validate_submission_references.sys,
        "argv",
        ["validate_submission_references.py", "--repo-root", str(tmp_path), "--manifest", "package.yaml"],
    )
    assert validate_submission_references.main() == 0

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "--package",
            "package.yaml",
            "semantic",
            "run",
            "map",
            "--region",
            "demo_case_initial_region",
        ],
    )
    assert cli.main() == 0
    prompt_path = tmp_path / "prompts/demo_case_initial_region/map_prompt.txt"
    assert prompt_path.exists()
    assert MAP_PROMPT_VERSION in prompt_path.read_text(encoding="utf-8")


def test_semantic_run_uses_command_backend_and_validates(monkeypatch, tmp_path: Path) -> None:
    _init_demo_case(monkeypatch, tmp_path)
    fake_model = tmp_path / "fake_model.py"
    fake_model.write_text(
        "import json\n"
        "print('Thinking...')\n"
        "print('```json')\n"
        "print(json.dumps({\n"
        "  'title': 'Generated Demo Map',\n"
        "  'status': 'human-review-needed',\n"
        f"  'prompt_procedure': {MAP_PROMPT_VERSION!r},\n"
        "  'evidence_mode': 'source_grounded',\n"
        "  'sources': ['demo_case_doc_a', 'demo_case_doc_b'],\n"
        "  'claims': [\n"
        "    {'claim_id': 'demo_case_c101', 'claim': 'Alpha supports a generated claim.', 'source_id': 'demo_case_doc_a', 'source_span': 'lines 1-1', 'excerpt': 'Alpha line.', 'entailed_by_excerpt': 'yes', 'role': 'conclusion_support'},\n"
        "    {'claim_id': 'demo_case_c102', 'claim': 'Gamma supplies a crux candidate.', 'sourcecap_id': 'demo_case_doc_b', 'source_span': 'lines 1-1', 'excerpt': 'Gamma line.', 'entailed_by__excerpt': 'yes', 'role': 'crux'}\n"
        "  ],\n"
        "  'relations': [{'relation_id': 'demo_case_r101', 'source_claim': 'demo_case_c102', 'target_claim': 'demo_case_c101', 'relation_type': 'crux_for', 'ration_type': 'The second claim affects how the first should be read.'}],\n"
        "  'crux_candidates': ['demo_case_c102 changes the interpretation of demo_case_c101.'],\n"
        "  'similar_but_not_identical': ['The two claims are related but distinct.'],\n"
        "  'evidence_check': [['Source grounding', 'Survives', 'Exact excerpts are present.']]\n"
        "}))\n"
        "print('```')\n",
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
            "semantic",
            "run",
            "map",
            "--region",
            "demo_case_initial_region",
            "--backend",
            f"command:{sys.executable} {fake_model}",
        ],
    )
    assert cli.main() == 0
    generated = json.loads((tmp_path / "examples/demo_case/worked_map.json").read_text(encoding="utf-8"))
    assert generated["prompt_procedure"] == MAP_PROMPT_VERSION
    assert generated["claims"][1]["source_id"] == "demo_case_doc_b"
    assert generated["claims"][1]["entailed_by_excerpt"] == "yes"
    assert generated["relations"][0]["relation_type"] == "crux_for"
    assert generated["relations"][0]["rationale"].startswith("The second claim")


def test_prompt_backend_returns_prompt_text() -> None:
    result = run_model_backend("source bounded prompt", "prompt")
    assert result.prompt_only is True
    assert result.text == "source bounded prompt"


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
