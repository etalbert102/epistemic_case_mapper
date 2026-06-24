from __future__ import annotations

import argparse
from pathlib import Path

from epistemic_case_mapper.io import read_yaml, write_json, write_markdown
from epistemic_case_mapper.schema import CaseManifest, CaseMap
from epistemic_case_mapper.starter_mapper import build_starter_case_map


def render_report(case_map: CaseMap) -> str:
    lines = [
        f"# {case_map.title}",
        "",
        f"Question: {case_map.question}",
        "",
        "## Summary",
        "",
        f"- Sources: {len(case_map.sources)}",
        f"- Candidate claims: {len(case_map.claims)}",
        f"- Seed relations: {len(case_map.relations)}",
        f"- Open questions: {len(case_map.open_questions)}",
        "",
        "## Sources",
        "",
    ]
    for source in case_map.sources:
        lines.append(f"- `{source.source_id}`: {source.title}")
    lines.extend(["", "## Candidate Claims", ""])
    for claim in case_map.claims[:40]:
        lines.append(f"- `{claim.claim_id}` ({claim.claim_type}, {claim.source_id}): {claim.text}")
    if len(case_map.claims) > 40:
        lines.append(f"- ... {len(case_map.claims) - 40} more claims in JSON artifact")
    lines.extend(["", "## Seed Relations", ""])
    for relation in case_map.relations[:30]:
        lines.append(
            f"- `{relation.relation_id}`: `{relation.source_claim_id}` {relation.relation_type} `{relation.target_claim_id}`"
        )
    lines.extend(["", "## Open Questions", ""])
    for question in case_map.open_questions:
        lines.append(f"- `{question.question_id}`: {question.text}")
    lines.extend(["", "## Audit Notes", ""])
    for note in case_map.audit_notes:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a starter epistemic case map.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--case", required=True, help="Path to case.yaml")
    parser.add_argument("--output-root", default="artifacts")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest_path = (repo_root / args.case).resolve()
    manifest = CaseManifest.model_validate(read_yaml(manifest_path))
    case_map = build_starter_case_map(manifest, repo_root=repo_root)

    output_dir = repo_root / args.output_root / manifest.case_id
    write_json(output_dir / "case_map.json", case_map.model_dump(mode="json"))
    write_markdown(output_dir / "report.md", render_report(case_map))
    print(f"Wrote {output_dir / 'case_map.json'}")
    print(f"Wrote {output_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
