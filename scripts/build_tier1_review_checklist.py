from __future__ import annotations

import argparse
import csv
from pathlib import Path

from artifact_utils import RegionFiles, parse_erosion_audit, parse_worked_map, region_files_from_manifest
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.submission_manifest import ReviewPriority, SubmissionManifest, load_submission_manifest


OUTPUT_PATH = "docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv"
ALLOWED_DECISIONS = "accept|revise|reject|needs_discussion"


FIELDNAMES = [
    "case",
    "worked_region_id",
    "tier",
    "item_type",
    "item_id",
    "source_id",
    "source_or_file",
    "item_text",
    "source_excerpt_or_support",
    "map_context",
    "review_question",
    "falsification_prompt",
    "allowed_decisions",
    "reviewer_decision",
    "confidence",
    "required_revision",
    "reviewer_notes",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a self-contained Tier 1 human review checklist.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--check", action="store_true", help="Check that the checked-in checklist is current.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    rendered = render_csv(repo_root, args.manifest)
    output_path = repo_root / OUTPUT_PATH
    if args.check:
        if not output_path.exists():
            print(f"FAIL: missing_tier1_review_checklist path={OUTPUT_PATH}")
            return 1
        if output_path.read_text(encoding="utf-8") != rendered:
            print(f"FAIL: stale_tier1_review_checklist path={OUTPUT_PATH}")
            return 1
        print("Tier 1 human review checklist is current")
        return 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


def render_csv(repo_root: Path, manifest_path: str = "submission_manifest.yaml") -> str:
    manifest = load_submission_manifest(repo_root, manifest_path)
    region_files = {region.region_id: files for region, files in zip(manifest.iter_worked_regions(), region_files_from_manifest(manifest))}
    rows: list[dict[str, str]] = []
    for worked_region in manifest.iter_worked_regions():
        priority = worked_region.review
        if priority is None:
            continue
        case = manifest.case_for_key(worked_region.case_key)
        case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
        source_paths = {source.source_id: source.path or "" for source in case_manifest.sources}
        region = region_files[worked_region.region_id]
        worked_map = parse_worked_map(repo_root / region.map_path, region.map_format)
        audit = parse_erosion_audit(repo_root / region.audit_path, region.audit_format)
        claims = {claim["claim_id"]: claim for claim in worked_map["claims"]}
        relations = {relation["relation_id"]: relation for relation in worked_map["relations"]}
        losses = {loss["loss_id"]: loss for loss in audit["losses"]}

        for claim_id in priority.claim_ids:
            claim = _required_item("claim", worked_region.region_id, claim_id, claims)
            rows.append(_claim_row(region, priority.worked_region_id, claim, source_paths))
        for relation_id in priority.relation_ids:
            relation = _required_item("relation", worked_region.region_id, relation_id, relations)
            rows.append(_relation_row(region, priority.worked_region_id, relation, claims))
        for loss_id in priority.loss_ids:
            loss = _required_item("loss", worked_region.region_id, loss_id, losses)
            rows.append(_loss_row(region, priority.worked_region_id, loss))
        rows.append(_overall_row(region, priority.worked_region_id))

    from io import StringIO

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _required_item(
    item_type: str, region_id: str, item_id: str, items: dict[str, dict[str, str]]
) -> dict[str, str]:
    if item_id not in items:
        raise KeyError(f"missing_review_priority_item type={item_type} region={region_id} id={item_id}")
    return items[item_id]


def _claim_row(
    region: RegionFiles,
    worked_region_id: str,
    claim: dict[str, str],
    source_paths: dict[str, str],
) -> dict[str, str]:
    claim_id = claim["claim_id"]
    source_id = claim.get("source_id", "")
    source_path = source_paths.get(source_id, "")
    source_span = claim.get("source_span", "")
    source_or_file = source_path if source_path else region.map_path
    if source_span:
        source_or_file = f"{source_or_file} {source_span}"
    return _base_row(
        region=region,
        worked_region_id=worked_region_id,
        item_type="claim",
        item_id=claim_id,
        source_id=source_id,
        source_or_file=source_or_file,
        item_text=claim.get("claim", ""),
        source_excerpt_or_support=claim.get("excerpt", ""),
        map_context=f"role={claim.get('role', '')}; source_file={source_path}; span={source_span}; entailed_by_excerpt={claim.get('entailed_by_excerpt', '')}",
        review_question="Does the excerpt/source support this exact claim without making it too strong?",
        falsification_prompt="Mark revise or reject if the claim adds causal force, certainty, scope, or consensus not present in the source.",
    )


def _relation_row(
    region: RegionFiles, worked_region_id: str, relation: dict[str, str], claims: dict[str, dict[str, str]]
) -> dict[str, str]:
    source_claim_id = relation.get("source_claim", "")
    target_claim_id = relation.get("target_claim", "")
    source_claim = claims.get(source_claim_id, {})
    target_claim = claims.get(target_claim_id, {})
    item_text = (
        f"{source_claim_id} --{relation.get('relation_type', '')}--> {target_claim_id}: "
        f"{relation.get('rationale', '')}"
    )
    context = (
        f"source_claim={source_claim.get('claim', '')} | "
        f"target_claim={target_claim.get('claim', '')}"
    )
    return _base_row(
        region=region,
        worked_region_id=worked_region_id,
        item_type="relation",
        item_id=relation["relation_id"],
        source_id="",
        source_or_file=region.map_path,
        item_text=item_text,
        source_excerpt_or_support=(
            f"{source_claim_id} excerpt: {source_claim.get('excerpt', '')} | "
            f"{target_claim_id} excerpt: {target_claim.get('excerpt', '')}"
        ),
        map_context=context,
        review_question="Is this relation type and rationale fair, or should the edge be weakened, retagged, or removed?",
        falsification_prompt="Mark revise or reject if the edge would make a reviewer infer stronger support, challenge, dependency, or crux status than the sources justify.",
    )


def _loss_row(region: RegionFiles, worked_region_id: str, loss: dict[str, str]) -> dict[str, str]:
    return _base_row(
        region=region,
        worked_region_id=worked_region_id,
        item_type="loss",
        item_id=loss["loss_id"],
        source_id="",
        source_or_file=region.audit_path,
        item_text=loss.get("lost_item", ""),
        source_excerpt_or_support=loss.get("source_support", ""),
        map_context=(
            f"case_map_preserves={loss.get('case_map_preserves', '')}; "
            f"flat_baseline_omission={loss.get('flat_baseline_omission', '')}; "
            f"adversarial_check={loss.get('adversarial_check', '')}"
        ),
        review_question="Is this a fair decision-space erosion finding when compared with the baseline?",
        falsification_prompt="Mark revise or reject if the flat synthesis preserved the distinction well enough, or if the distinction is not decision-relevant.",
    )


def _overall_row(region: RegionFiles, worked_region_id: str) -> dict[str, str]:
    return _base_row(
        region=region,
        worked_region_id=worked_region_id,
        item_type="overall",
        item_id=f"{region.case_key}_overall",
        source_id="",
        source_or_file="docs/review/REVIEWER_START_HERE.md",
        item_text="Overall judgment for this worked region.",
        source_excerpt_or_support="Use the completed Tier 1 claim, relation, and loss rows.",
        map_context="Scores: source_fidelity, relation_correctness, crux_usefulness, flat_synthesis_fairness, reasoning_utility.",
        review_question="Is this worked region showable with stated limits, or does it require revision first?",
        falsification_prompt="Mark needs_discussion or revise if any accepted claim depends on unresolved source-fidelity or relation-correctness problems.",
    )


def _base_row(
    *,
    region: RegionFiles,
    worked_region_id: str,
    item_type: str,
    item_id: str,
    source_id: str,
    source_or_file: str,
    item_text: str,
    source_excerpt_or_support: str,
    map_context: str,
    review_question: str,
    falsification_prompt: str,
) -> dict[str, str]:
    return {
        "case": region.case_label,
        "worked_region_id": worked_region_id,
        "tier": "1",
        "item_type": item_type,
        "item_id": item_id,
        "source_id": source_id,
        "source_or_file": source_or_file,
        "item_text": item_text,
        "source_excerpt_or_support": source_excerpt_or_support,
        "map_context": map_context,
        "review_question": review_question,
        "falsification_prompt": falsification_prompt,
        "allowed_decisions": ALLOWED_DECISIONS,
        "reviewer_decision": "pending",
        "confidence": "",
        "required_revision": "",
        "reviewer_notes": "",
    }


if __name__ == "__main__":
    raise SystemExit(main())
