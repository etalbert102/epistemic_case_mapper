from __future__ import annotations

import argparse
from pathlib import Path

from epistemic_case_mapper.io import read_yaml, write_json, write_markdown
from epistemic_case_mapper.schema import CaseManifest, CaseMap
from epistemic_case_mapper.starter_mapper import build_starter_case_map


def _preservation_metadata(case_map: CaseMap) -> dict:
    raw_metadata = case_map.metadata.get("preservation_metadata", {})
    return raw_metadata if isinstance(raw_metadata, dict) else {}


def _metadata_files(case_map: CaseMap) -> list[dict]:
    raw_files = _preservation_metadata(case_map).get("files", [])
    return raw_files if isinstance(raw_files, list) else []


def _metadata_requirements(case_map: CaseMap) -> list[str]:
    raw_requirements = _preservation_metadata(case_map).get("key_requirements", [])
    return raw_requirements if isinstance(raw_requirements, list) else []


def _workflow_telemetry(case_map: CaseMap) -> dict:
    raw_telemetry = case_map.metadata.get("workflow_telemetry", {})
    return raw_telemetry if isinstance(raw_telemetry, dict) else {}


def render_audit(case_map: CaseMap) -> str:
    seed_sources = [source for source in case_map.sources if source.source_type == "seed_notes"]
    source_grounded = case_map.evidence_mode == "source_grounded"
    open_question_count = len(case_map.open_questions)
    relation_rationales = [relation for relation in case_map.relations if relation.rationale]
    metadata_files = _metadata_files(case_map)
    metadata_requirements = _metadata_requirements(case_map)
    workflow_telemetry = _workflow_telemetry(case_map)
    extraction_telemetry = workflow_telemetry.get("extraction", {}) if workflow_telemetry else {}
    ingestion_evidence = (
        "Claims preserve source IDs, normalized spans, text hashes, and source-grounded local paths/excerpts."
        if source_grounded
        else "Claims preserve source IDs, spans, and hashes; seed limitations remain visible."
    )
    judge_usability_evidence = (
        "Report is navigable, but claims and relations remain draft until audited."
        if source_grounded
        else "Report is navigable but still seed-mode unless upgraded to source-grounded evidence."
    )
    score_rows = [
        ("Ingestion", _score_ingestion(case_map), ingestion_evidence),
        ("Structure", _score_structure(case_map), "Relations are candidate links and rationales are explicit."),
        ("Assessment", _score_assessment(case_map), "Open questions surface cruxes and missing sources."),
        ("Compounding", _score_compounding(case_map), "JSON schema, stable IDs, and Markdown outputs support reuse."),
        ("Judge usability", _score_judge_usability(case_map), judge_usability_evidence),
        ("Verification", 1, "Build command generated artifacts; full validator should be run separately."),
        ("Plan discipline", 1, "Goal-plan discipline is documented in docs/plans/lhc_demo_goal_plan.md."),
    ]
    lines = [
        f"# {case_map.title} Audit",
        "",
        f"Case ID: `{case_map.case_id}`",
        f"Evidence mode: `{case_map.evidence_mode}`",
        f"Review status: `{case_map.review_status}`",
        "",
        "## Status",
        "",
    ]
    if seed_sources:
        lines.append(
            "This artifact is seed-derived workflow scaffolding. It must not be treated as a final source-grounded FLF demo."
        )
    elif source_grounded:
        lines.append("This artifact is source-grounded according to the case manifest.")
    else:
        lines.append("Evidence status requires review.")
    lines.extend(
        [
            "",
            "## Completeness Signals",
            "",
            f"- Sources: {len(case_map.sources)}",
            f"- Claims: {len(case_map.claims)}",
            f"- Relations: {len(case_map.relations)}",
            f"- Relations with rationales: {len(relation_rationales)}",
            f"- Open questions: {open_question_count}",
            f"- Seed sources: {len(seed_sources)}",
            f"- Preservation metadata files: {len(metadata_files)}",
            f"- Key preservation requirements: {len(metadata_requirements)}",
            f"- Workflow telemetry stages: {len(workflow_telemetry)}",
            "",
            "## FLF Criteria Score",
            "",
            "| Area | Score | Evidence |",
            "| --- | ---: | --- |",
        ]
    )
    for area, score, evidence in score_rows:
        lines.append(f"| {area} | {score} | {evidence} |")
    lines.extend(
        [
            "",
            "## Missing Evidence",
            "",
        ]
    )
    if seed_sources:
        lines.extend(
            [
                "- Replace seed notes with source-local excerpts from the CERN FAQ or public safety pages.",
                "- Add the LSAG safety report or equivalent formal safety review.",
                "- Add independent review material such as the CERN Scientific Policy Committee assessment.",
                "- Add representative public concern or critique material.",
            ]
        )
    else:
        lines.append("- No seed-mode evidence gap was detected, but source coverage still needs human audit.")
    lines.extend(["", "## Preservation Metadata", ""])
    if metadata_files:
        lines.append("These files are incorporated into the generated case map as decision-context metadata:")
        for item in metadata_files:
            path = item.get("path", "unknown") if isinstance(item, dict) else "unknown"
            title = item.get("title", path) if isinstance(item, dict) else path
            status = "present" if isinstance(item, dict) and item.get("exists") else "missing"
            lines.append(f"- `{path}` ({status}): {title}")
    else:
        lines.append("- No preservation metadata files are registered in the case manifest.")
    if metadata_requirements:
        lines.extend(["", "### Key Preservation Requirements", ""])
        for requirement in metadata_requirements:
            lines.append(f"- {requirement}")
    lines.extend(["", "## Workflow Telemetry", ""])
    if workflow_telemetry:
        lines.extend(
            [
                f"- Extraction candidate sentences: {extraction_telemetry.get('total_candidate_sentences', 'unknown')}",
                f"- Extraction claims created: {extraction_telemetry.get('total_claims_created', 'unknown')}",
                f"- Extraction skipped as too short: {extraction_telemetry.get('total_skipped_short', 'unknown')}",
                f"- Extraction skipped without claim marker: {extraction_telemetry.get('total_skipped_no_marker', 'unknown')}",
            ]
        )
        relation_telemetry = workflow_telemetry.get("relation_mapping", {})
        if isinstance(relation_telemetry, dict):
            lines.append(f"- Relation mapping stage: {relation_telemetry.get('stage', 'unknown')}")
        open_question_telemetry = workflow_telemetry.get("open_question_mapping", {})
        if isinstance(open_question_telemetry, dict):
            lines.append(f"- Open question mapping stage: {open_question_telemetry.get('stage', 'unknown')}")
    else:
        lines.append("- No workflow telemetry is present.")
    lines.extend(["", "## Open Questions", ""])
    for question in case_map.open_questions:
        linked = ", ".join(question.linked_claim_ids or question.linked_source_ids or ["unlinked"])
        lines.append(f"- `{question.question_id}` ({question.gap_type or 'open'}; {linked}): {question.text}")
    lines.append("")
    return "\n".join(lines)


def _score_ingestion(case_map: CaseMap) -> int:
    if not case_map.claims or any(not claim.source_id for claim in case_map.claims):
        return 0
    if any(source.source_type == "seed_notes" for source in case_map.sources):
        return 1
    return 2


def _score_structure(case_map: CaseMap) -> int:
    if not case_map.relations:
        return 0
    if any(not relation.rationale for relation in case_map.relations):
        return 1
    return 2 if case_map.evidence_mode == "source_grounded" else 1


def _score_assessment(case_map: CaseMap) -> int:
    if len(case_map.open_questions) < 3:
        return 0
    if any(not (question.linked_claim_ids or question.linked_source_ids or question.gap_type == "missing source needed") for question in case_map.open_questions):
        return 1
    return 2


def _score_compounding(case_map: CaseMap) -> int:
    if not case_map.claims or not case_map.sources:
        return 0
    return 2


def _score_judge_usability(case_map: CaseMap) -> int:
    if not _metadata_files(case_map):
        return 1
    if _metadata_requirements(case_map):
        return 2
    return 1


def render_report(case_map: CaseMap) -> str:
    metadata_files = _metadata_files(case_map)
    metadata_requirements = _metadata_requirements(case_map)
    workflow_telemetry = _workflow_telemetry(case_map)
    extraction_telemetry = workflow_telemetry.get("extraction", {}) if workflow_telemetry else {}
    lines = [
        f"# {case_map.title}",
        "",
        f"Question: {case_map.question}",
        "",
        f"Evidence mode: `{case_map.evidence_mode}`",
        f"Review status: `{case_map.review_status}`",
        "",
        "## Summary",
        "",
        f"- Sources: {len(case_map.sources)}",
        f"- Candidate claims: {len(case_map.claims)}",
        f"- Seed relations: {len(case_map.relations)}",
        f"- Open questions: {len(case_map.open_questions)}",
        f"- Preservation metadata files: {len(metadata_files)}",
        f"- Workflow telemetry stages: {len(workflow_telemetry)}",
        "",
        "## Sources",
        "",
    ]
    for source in case_map.sources:
        lines.append(f"- `{source.source_id}`: {source.title}")
    lines.extend(["", "## Preservation Metadata", ""])
    if metadata_files:
        for item in metadata_files:
            path = item.get("path", "unknown") if isinstance(item, dict) else "unknown"
            title = item.get("title", path) if isinstance(item, dict) else path
            lines.append(f"- `{path}`: {title}")
    else:
        lines.append("- No preservation metadata files are registered.")
    if metadata_requirements:
        lines.extend(["", "### Key Requirements Carried Into This Artifact", ""])
        for requirement in metadata_requirements:
            lines.append(f"- {requirement}")
    lines.extend(["", "## Workflow Telemetry", ""])
    if workflow_telemetry:
        lines.extend(
            [
                f"- Candidate sentences inspected: {extraction_telemetry.get('total_candidate_sentences', 'unknown')}",
                f"- Candidate claims created: {extraction_telemetry.get('total_claims_created', 'unknown')}",
                f"- Sentences skipped without claim marker: {extraction_telemetry.get('total_skipped_no_marker', 'unknown')}",
            ]
        )
    else:
        lines.append("- No workflow telemetry is present.")
    lines.extend(["", "## Candidate Claims", ""])
    for claim in case_map.claims[:40]:
        lines.append(
            f"- `{claim.claim_id}` ({claim.claim_type}, {claim.source_id}, {claim.source_span}, {claim.provenance_tag}, {claim.review_state}): {claim.text}"
        )
    if len(case_map.claims) > 40:
        lines.append(f"- ... {len(case_map.claims) - 40} more claims in JSON artifact")
    lines.extend(["", "## Seed Relations", ""])
    for relation in case_map.relations[:30]:
        lines.append(
            f"- `{relation.relation_id}`: `{relation.source_claim_id}` {relation.relation_type} `{relation.target_claim_id}`"
            + (f" — {relation.rationale}" if relation.rationale else "")
        )
    lines.extend(["", "## Open Questions", ""])
    for question in case_map.open_questions:
        linked = ", ".join(question.linked_claim_ids or question.linked_source_ids or ["unlinked"])
        lines.append(f"- `{question.question_id}` ({question.gap_type or 'open'}; {linked}): {question.text}")
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
    write_markdown(output_dir / "audit.md", render_audit(case_map))
    print(f"Wrote {output_dir / 'case_map.json'}")
    print(f"Wrote {output_dir / 'report.md'}")
    print(f"Wrote {output_dir / 'audit.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
