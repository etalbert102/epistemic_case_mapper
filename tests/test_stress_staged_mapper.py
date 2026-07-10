from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import stress_staged_mapper


def test_stress_staged_mapper_writes_reports(monkeypatch, tmp_path: Path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    doc_a = source_dir / "doc_a.txt"
    doc_b = source_dir / "doc_b.txt"
    doc_a.write_text("Alpha evidence favors one interpretation.\n", encoding="utf-8")
    doc_b.write_text("Beta evidence challenges that interpretation.\n", encoding="utf-8")
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        "case_id: stress_fixture\n"
        "title: Stress Fixture\n"
        "question: What should the fixture show?\n"
        "case_type: stress fixture\n"
        "evidence_mode: source_grounded\n"
        "review_status: draft\n"
        "sources:\n"
        "  - source_id: doc_a\n"
        "    title: Doc A\n"
        "    source_type: note\n"
        "    path: sources/doc_a.txt\n"
        "  - source_id: doc_b\n"
        "    title: Doc B\n"
        "    source_type: note\n"
        "    path: sources/doc_b.txt\n",
        encoding="utf-8",
    )
    fake_model = tmp_path / "fake_model.py"
    fake_model.write_text(
        "import json, re, sys\n"
        "prompt = sys.stdin.read()\n"
        "if 'staged_claim_extraction_prompt_v1_json' in prompt:\n"
        "    span_id = re.search(r'span_id: ([^\\n]+)', prompt).group(1)\n"
        "    payload = {'claims': [{'claim': 'Selected source-grounded fixture claim.', 'span_id': span_id, 'entailed_by_excerpt': 'yes', 'role': 'crux'}]}\n"
        "elif 'staged_relation_prompt_v2_contract_json' in prompt:\n"
        "    pair_id = re.search(r'Pair ID: ([^\\n]+)', prompt).group(1)\n"
        "    ids = re.findall(r'claim_id: ([^\\n]+)', prompt)\n"
        "    payload = {'pair_id': pair_id, 'source_claim': ids[0], 'target_claim': ids[1], 'relation_type': 'crux_for', 'rationale': 'The fixture claims should be read together.', 'crux_candidates': ['fixture crux'], 'similar_but_not_identical': []}\n"
        "else:\n"
        "    payload = {}\n"
        "print(json.dumps(payload))\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "stress_out"

    monkeypatch.setattr(
        stress_staged_mapper.sys,
        "argv",
        [
            "stress_staged_mapper.py",
            "--repo-root",
            str(tmp_path),
            "--cases",
            "case.yaml",
            "--backends",
            f"command:{sys.executable} {fake_model}",
            "--timeouts",
            "5",
            "--retries",
            "0",
            "--relation-pairs",
            "1",
            "--claim-extractor",
            "native",
            "--output-dir",
            str(output_dir),
            "--fail-on-failure",
        ],
    )

    assert stress_staged_mapper.main() == 0
    rows = [json.loads(line) for line in (output_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["status"] == "validated"
    assert rows[0]["claim_count"] == 2
    assert rows[0]["relation_count"] == 1
    progress = json.loads((Path(rows[0]["artifact_dir"]) / "pipeline_progress.json").read_text(encoding="utf-8"))
    assert progress["status"] == "completed"
    assert progress["active_backend_call"] == {}
    assert progress["backend_timeout_seconds"] == 5
    assert progress["stages"]["claim_extraction"]["status"] == "completed"
    assert progress["stages"]["relation_extraction"]["accepted_relation_count"] == 1
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["validated_count"] == 1
