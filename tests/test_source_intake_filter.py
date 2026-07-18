from __future__ import annotations

import sys
from urllib import error
from pathlib import Path

from epistemic_case_mapper import cli
from epistemic_case_mapper.source_intake_filter import run_source_intake_filter


def test_source_intake_filter_is_report_only_by_default(tmp_path: Path) -> None:
    relevant = tmp_path / "eggs.txt"
    off_question = tmp_path / "boilers.txt"
    relevant.write_text("Egg prices changed after supply shocks and demand shifts.", encoding="utf-8")
    off_question.write_text("Residential boiler installation notes and warranty terms.", encoding="utf-8")

    result = run_source_intake_filter(
        question="Should shoppers expect egg prices to remain high?",
        doc_paths=[relevant, off_question],
        backend="prompt",
        output_dir=tmp_path / "filter",
    )

    assert result.report["mode"] == "report_only"
    assert result.report["model_judgment_report"]["status"] == "prompt_backend_skipped"
    assert "Decision question" in result.report["model_judgment_report"]["prompt"]
    assert result.markdown_path.exists()
    assert {path.name for path in result.included_docs} == {"eggs.txt", "boilers.txt"}


def test_source_intake_filter_applies_live_model_exclusions_only_when_requested(tmp_path: Path) -> None:
    relevant = tmp_path / "eggs.txt"
    off_question = tmp_path / "boilers.txt"
    model = tmp_path / "filter_model.py"
    relevant.write_text("Egg prices changed after supply shocks and demand shifts.", encoding="utf-8")
    off_question.write_text("Residential boiler installation notes and warranty terms.", encoding="utf-8")
    model.write_text(
        "import json, sys\n"
        "payload = json.loads(sys.stdin.read().split('Source packets:\\n', 1)[1])\n"
        "judgments = []\n"
        "for row in payload:\n"
        "    action = 'exclude' if row['display_name'] == 'boilers.txt' else 'include'\n"
        "    judgments.append({\n"
        "      'source_path': row['source_path'],\n"
        "      'relevance': 'irrelevant' if action == 'exclude' else 'high',\n"
        "      'trust_concern': 'low',\n"
        "      'recommended_action': action,\n"
        "      'rationale': 'fixture decision',\n"
        "      'flags': ['off_question'] if action == 'exclude' else []\n"
        "    })\n"
        "print(json.dumps({'judgments': judgments}))\n",
        encoding="utf-8",
    )

    report_only = run_source_intake_filter(
        question="Should shoppers expect egg prices to remain high?",
        doc_paths=[relevant, off_question],
        backend=f"command:{sys.executable} {model}",
        output_dir=tmp_path / "report_only",
        exclude_flagged=False,
    )
    applied = run_source_intake_filter(
        question="Should shoppers expect egg prices to remain high?",
        doc_paths=[relevant, off_question],
        backend=f"command:{sys.executable} {model}",
        output_dir=tmp_path / "applied",
        exclude_flagged=True,
    )

    assert {path.name for path in report_only.included_docs} == {"eggs.txt", "boilers.txt"}
    assert {path.name for path in applied.included_docs} == {"eggs.txt"}
    assert {path.name for path in applied.excluded_docs} == {"boilers.txt"}


def test_case_filter_sources_cli_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("Egg supply and demand evidence.", encoding="utf-8")

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ecm.py",
            "--repo-root",
            str(tmp_path),
            "case",
            "filter-sources",
            "--question",
            "What explains egg prices?",
            "--docs",
            str(doc),
            "--output-dir",
            "intake",
        ],
    )

    assert cli.main() == 0
    assert (tmp_path / "intake/source_intake_filter.json").exists()
    assert (tmp_path / "intake/SOURCE_INTAKE_FILTER.md").exists()


def test_case_init_can_exclude_unusable_sources_at_intake(monkeypatch, tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    empty = tmp_path / "empty.txt"
    good.write_text("Egg prices changed after supply shocks and demand shifts.", encoding="utf-8")
    empty.write_text("", encoding="utf-8")

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
            "Intake Demo",
            "--title",
            "Intake Demo",
            "--question",
            "What explains egg prices?",
            "--docs",
            str(good),
            str(empty),
            "--filter-sources",
            "--exclude-filtered-sources",
        ],
    )

    assert cli.main() == 0
    case_yaml = (tmp_path / "data/cases/intake_demo/case.yaml").read_text(encoding="utf-8")
    assert "good" in case_yaml
    assert "empty" not in case_yaml


def test_source_intake_filter_records_citation_and_traceability_warnings(tmp_path: Path) -> None:
    uncited = tmp_path / "uncited.txt"
    uncited.write_text(
        "Egg prices rose 47 percent in 2024. Retail demand changed 12 percent. "
        "Supply fell 9 percent. This document gives no source list.",
        encoding="utf-8",
    )

    result = run_source_intake_filter(
        question="What explains egg prices?",
        doc_paths=[uncited],
        backend="prompt",
        output_dir=tmp_path / "filter",
    )

    row = result.report["sources"][0]
    assert result.report["status"] == "warning"
    assert "no_detected_citations" in row["deterministic_flags"]
    assert "numbers_without_nearby_citations" in row["deterministic_flags"]
    assert row["citation_profile"]["likely_citation_count"] == 0
    assert row["citation_profile"]["numeric_sentence_without_citation_count"] >= 3


def test_source_intake_filter_can_check_broken_outbound_links(monkeypatch, tmp_path: Path) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def geturl(self) -> str:
            return "https://example.com/ok"

    def fake_urlopen(req, timeout=None):
        if "missing" in req.full_url:
            raise error.HTTPError(req.full_url, 404, "missing", hdrs=None, fp=None)
        return FakeResponse()

    doc = tmp_path / "links.txt"
    doc.write_text(
        "References\n"
        "[1] Useful page https://example.com/ok\n"
        "[2] Missing page https://example.com/missing\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("epistemic_case_mapper.source_intake_filter.request.urlopen", fake_urlopen)

    result = run_source_intake_filter(
        question="What explains egg prices?",
        doc_paths=[doc],
        backend="prompt",
        output_dir=tmp_path / "filter",
        check_links=True,
    )

    row = result.report["sources"][0]
    assert result.report["link_check_mode"] == "checked_2_urls"
    assert row["link_profile"]["checked_count"] == 2
    assert row["link_profile"]["broken_count"] == 1
    assert "broken_outbound_links" in row["deterministic_flags"]
