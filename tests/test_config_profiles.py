from __future__ import annotations

import json
import sys
from pathlib import Path

from epistemic_case_mapper import cli
from epistemic_case_mapper.config_profiles import (
    builtin_profiles,
    recommend_config_profile,
)
from epistemic_case_mapper.io import read_yaml


def test_builtin_profiles_include_general_default() -> None:
    profiles = builtin_profiles()

    assert "general_decision_support" in profiles
    assert "empirical_policy_decision" in profiles
    assert "technical_safety_case" in profiles
    assert "other" in profiles["general_decision_support"].claim_role_ids()


def test_model_recommendation_validates_known_profile(tmp_path: Path) -> None:
    doc = tmp_path / "safety.txt"
    doc.write_text("The system has a failure mode and a mitigation with residual risk.", encoding="utf-8")
    fake_model = tmp_path / "fake_config_model.py"
    fake_model.write_text(
        "import json\n"
        "print(json.dumps({\n"
        "  'profile_id': 'technical_safety_case',\n"
        "  'confidence': 'high',\n"
        "  'reasons': ['The packet is about failure modes and mitigations.'],\n"
        "  'suggested_overrides': {'claim_roles': ['monitoring_gap']}\n"
        "}))\n",
        encoding="utf-8",
    )

    run = recommend_config_profile(
        question="Which safety controls matter most?",
        doc_paths=[doc],
        backend=f"command:{sys.executable} {fake_model}",
    )

    assert run.recommendation.profile_id == "technical_safety_case"
    assert run.recommendation.confidence == "high"
    assert run.recommendation.fallback_reason is None
    assert "# Output Schema" in run.prompt
    assert "# Examples" in run.prompt
    assert "<available_profiles>" in run.prompt
    assert "failure mode" in run.prompt


def test_model_recommendation_falls_back_on_unknown_profile(tmp_path: Path) -> None:
    doc = tmp_path / "case.txt"
    doc.write_text("A mixed document packet.", encoding="utf-8")
    fake_model = tmp_path / "fake_bad_config_model.py"
    fake_model.write_text("import json\nprint(json.dumps({'profile_id': 'bespoke_magic'}))\n", encoding="utf-8")

    run = recommend_config_profile(
        question="What should we do?",
        doc_paths=[doc],
        backend=f"command:{sys.executable} {fake_model}",
    )

    assert run.recommendation.profile_id == "general_decision_support"
    assert run.recommendation.fallback_reason == "unknown_profile_id:bespoke_magic"


def test_cli_recommend_config_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    doc = tmp_path / "policy.txt"
    doc.write_text("A randomized trial and guideline discuss external validity.", encoding="utf-8")
    fake_model = tmp_path / "fake_policy_model.py"
    fake_model.write_text(
        "import json\n"
        "print(json.dumps({'profile_id': 'empirical_policy_decision', 'confidence': 'medium', 'reasons': ['Studies and guidelines are present.']}))\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "case",
            "recommend-config",
            "--question",
            "Should the policy be adopted?",
            "--docs",
            str(doc),
            "--backend",
            f"command:{sys.executable} {fake_model}",
        ],
    )

    assert cli.main() == 0
    payload = json.loads(
        (tmp_path / "artifacts/config_recommendations/should_the_policy_be_adopted/config_recommendation.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["recommendation"]["profile_id"] == "empirical_policy_decision"
    assert payload["epistemic_config"]["profile_id"] == "empirical_policy_decision"
    assert (tmp_path / "artifacts/config_recommendations/should_the_policy_be_adopted/CONFIG_RECOMMENDATION.md").exists()


def test_case_init_can_store_recommended_config(monkeypatch, tmp_path: Path) -> None:
    doc = tmp_path / "incident.txt"
    doc.write_text("Incident report: a failure mode persisted after mitigation.", encoding="utf-8")
    fake_model = tmp_path / "fake_safety_model.py"
    fake_model.write_text(
        "import json\n"
        "print(json.dumps({'profile_id': 'technical_safety_case', 'confidence': 'high', 'reasons': ['Incident and mitigation language.']}))\n",
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
            "case",
            "init",
            "--case-id",
            "Safety Case",
            "--title",
            "Safety Case",
            "--question",
            "Which controls should be prioritized?",
            "--docs",
            str(doc),
            "--recommend-config",
            "--config-backend",
            f"command:{sys.executable} {fake_model}",
        ],
    )

    assert cli.main() == 0
    case_manifest = read_yaml(tmp_path / "data/cases/safety_case/case.yaml")
    assert case_manifest["epistemic_config"]["profile_id"] == "technical_safety_case"
    assert case_manifest["epistemic_config"]["confidence"] == "high"

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
            "staged",
            "map",
            "--region",
            "safety_case_initial_region",
            "--backend",
            "prompt",
            "--chunk-lines",
            "2",
            "--max-relation-pairs",
            "1",
            "--no-validate",
        ],
    )
    assert cli.main() == 0
    prompt = (
        tmp_path
        / "artifacts/semantic/safety_case_initial_region/staged/claim_chunks/safety_case_incident_lines_1_1_prompt.txt"
    ).read_text(encoding="utf-8")
    assert "technical_safety_case" in prompt
    assert "failure_mode" in prompt
    summary = json.loads(
        (tmp_path / "artifacts/semantic/safety_case_initial_region/staged/run_summary.json").read_text(encoding="utf-8")
    )
    assert summary["epistemic_config_profile"] == "technical_safety_case"
