from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from artifact_utils import parse_erosion_audit, parse_worked_map
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.submission_manifest import SubmissionCase, load_submission_manifest


OUTPUT_PATH = "ui/data.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static UI data from checked-in FLF artifacts.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--check", action="store_true", help="Check that ui/data.json is current.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    payload = build_payload(repo_root, args.manifest)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    output_path = repo_root / OUTPUT_PATH
    if args.check:
        if not output_path.exists():
            print(f"FAIL: missing_ui_data path={OUTPUT_PATH}")
            return 1
        if output_path.read_text(encoding="utf-8") != rendered:
            print(f"FAIL: stale_ui_data path={OUTPUT_PATH}")
            return 1
        print("UI data is current")
        return 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


def build_payload(repo_root: Path, manifest_path: str = "submission_manifest.yaml") -> dict:
    manifest_config = load_submission_manifest(repo_root, manifest_path)
    cases = []
    for config in manifest_config.iter_ui_cases():
        case_payload = _build_case_payload(repo_root, config)
        cases.append(case_payload)
    return {
        "generatedFrom": "scripts/build_ui_data.py",
        "status": "human-review-needed",
        "package": {
            "packageId": manifest_config.package_id,
            "packageLabel": manifest_config.package_label,
        },
        "hero": manifest_config.ui_hero.model_dump(),
        "summary": {
            "caseCount": len(cases),
            "sourceCount": sum(len(case["sources"]) for case in cases),
            "clusterCount": sum(len(case["clusters"]) for case in cases),
            "claimCount": sum(
                len(region["worked"]["claims"]) for case in cases for region in case["workedRegions"]
            ),
            "relationCount": sum(
                len(region["worked"]["relations"]) for case in cases for region in case["workedRegions"]
            ),
            "taskCount": sum(len(case["tasks"]) for case in cases),
        },
        "cases": cases,
    }


def _build_case_payload(repo_root: Path, config: SubmissionCase) -> dict:
    manifest = CaseManifest.model_validate(read_yaml(repo_root / config.case_path))
    if not config.worked_regions:
        raise ValueError(f"ui_case_missing_worked_region case={config.case_key}")
    worked_region = config.worked_regions[0]
    worked_regions = [_build_worked_region_payload(repo_root, region) for region in config.worked_regions]
    worked_map = worked_regions[0]["worked"]
    audit = worked_regions[0]["erosion"]
    clusters: list[dict[str, str]] = []
    cluster_relations: list[dict[str, str]] = []
    if config.full_case is not None:
        full_map_text = (repo_root / config.full_case.map_path).read_text(encoding="utf-8")
        clusters = _parse_clusters(full_map_text)
        cluster_relations = _parse_full_relations(full_map_text)
    tasks: list[dict[str, str]] = []
    if config.task_queue is not None:
        tasks = _parse_tasks((repo_root / config.task_queue.path).read_text(encoding="utf-8"))
    artifacts = {
        "workedMap": worked_region.map_path,
        "erosionAudit": worked_region.audit_path,
        "workedBaseline": worked_region.baseline_path,
    }
    if worked_region.best_path:
        artifacts["bestRegions"] = worked_region.best_path
    if config.ui.multi_model_audit_path:
        artifacts["multiModelAudit"] = config.ui.multi_model_audit_path
    if config.full_case is not None:
        artifacts["fullIndex"] = config.full_case.index_path
        artifacts["fullMap"] = config.full_case.map_path
        if config.full_case.baseline_path:
            artifacts["fullCaseBaseline"] = config.full_case.baseline_path
    if config.task_queue is not None:
        artifacts["taskQueue"] = config.task_queue.path
    if config.ui.review_packet_path:
        artifacts["reviewPacket"] = config.ui.review_packet_path
    if config.ui.review_checklist_path:
        artifacts["reviewChecklist"] = config.ui.review_checklist_path
    return {
        "caseKey": config.case_key,
        "caseId": config.case_id,
        "label": config.ui.label or config.label,
        "shortLabel": config.ui.short_label or config.label,
        "question": manifest.question,
        "caseType": manifest.case_type,
        "theme": config.ui.theme,
        "reviewStatus": manifest.review_status,
        "sources": [
            {
                "sourceId": source.source_id,
                "title": source.title,
                "sourceType": source.source_type,
                "excerpt": source.excerpt,
                "path": source.path,
            }
            for source in manifest.sources
        ],
        "clusters": clusters,
        "clusterRelations": cluster_relations,
        "worked": {
            "title": worked_map["title"],
            "status": worked_map["status"],
            "claims": worked_map["claims"],
            "relations": worked_map["relations"],
            "cruxes": worked_map["cruxes"],
            "similarClaims": worked_map["similarClaims"],
        },
        "erosion": {
            "losses": audit["losses"],
            "borderline": audit["borderline_or_rejected"],
        },
        "workedRegions": worked_regions,
        "tasks": tasks,
        "spotlights": [spotlight.model_dump() for spotlight in config.ui.spotlights],
        "artifacts": artifacts,
    }


def _build_worked_region_payload(repo_root: Path, worked_region) -> dict:
    worked_map = parse_worked_map(repo_root / worked_region.map_path, worked_region.map_format)
    audit = parse_erosion_audit(repo_root / worked_region.audit_path, worked_region.audit_format)
    artifacts = {
        "definition": worked_region.definition_path,
        "workedMap": worked_region.map_path,
        "erosionAudit": worked_region.audit_path,
        "workedBaseline": worked_region.baseline_path,
    }
    if worked_region.best_path:
        artifacts["bestRegions"] = worked_region.best_path
    return {
        "regionId": worked_region.region_id,
        "caseKey": worked_region.case_key,
        "caseLabel": worked_region.case_label,
        "idPrefix": worked_region.id_prefix,
        "artifacts": artifacts,
        "worked": {
            "title": worked_map["title"],
            "status": worked_map["status"],
            "claims": worked_map["claims"],
            "relations": worked_map["relations"],
            "cruxes": worked_map["crux_candidates"],
            "similarClaims": worked_map["similar_but_not_identical"],
        },
        "erosion": {
            "losses": audit["losses"],
            "borderline_or_rejected": audit["borderline_or_rejected"],
            "borderline": audit["borderline_or_rejected"],
        },
    }


def _parse_clusters(text: str) -> list[dict[str, str]]:
    return [_parse_block(block) for block in _blocks(text, "cluster_id")]


def _parse_full_relations(text: str) -> list[dict[str, str]]:
    return [_parse_block(block) for block in _blocks(text, "relation_id")]


def _parse_tasks(text: str) -> list[dict[str, str]]:
    return [_parse_block(block) for block in _blocks(text, "task_id")]


def _blocks(text: str, id_field: str) -> list[str]:
    pattern = rf"(?ms)^{re.escape(id_field)}:\s*.+?(?=^{re.escape(id_field)}:\s|\n## |\Z)"
    return [match.group(0).strip() for match in re.finditer(pattern, text)]


def _parse_block(block: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []
    for line in block.splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            if current_key:
                result[current_key] = _strip(" ".join(current_value).strip())
            current_key = match.group(1)
            current_value = [match.group(2).strip()]
        elif current_key:
            current_value.append(line.strip())
    if current_key:
        result[current_key] = _strip(" ".join(current_value).strip())
    return result


def _strip(value: str) -> str:
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
