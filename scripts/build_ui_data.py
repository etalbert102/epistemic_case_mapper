from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from artifact_utils import parse_erosion_audit, parse_worked_map
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest


OUTPUT_PATH = "ui/data.json"

CASES = (
    {
        "case_key": "lhc",
        "case_id": "lhc_black_holes",
        "label": "LHC Black Hole Risk",
        "short_label": "LHC",
        "case_path": "data/cases/lhc_black_holes/case.yaml",
        "full_index_path": "examples/lhc_black_holes/full_case_index.md",
        "full_map_path": "examples/lhc_black_holes/full_case_map.md",
        "worked_map_path": "examples/lhc_black_holes/worked_region_cosmic_ray_map.md",
        "audit_path": "examples/lhc_black_holes/decision_space_erosion_audit.md",
        "best_path": "examples/lhc_black_holes/BEST_REGIONS.md",
        "full_baseline_path": "examples/lhc_black_holes/full_case_flat_synthesis_baseline.md",
        "worked_baseline_path": "examples/lhc_black_holes/flat_synthesis_baseline.md",
        "task_path": "examples/lhc_black_holes/investigator_task_queue.md",
        "review_packet_path": "docs/review/LHC_HUMAN_AUDIT_PACKET.md",
        "review_checklist_path": "docs/review/LHC_HUMAN_AUDIT_CHECKLIST.csv",
        "theme": "risk",
    },
    {
        "case_key": "eggs",
        "case_id": "eggs",
        "label": "Eggs And Health",
        "short_label": "Eggs",
        "case_path": "data/cases/eggs/case.yaml",
        "full_index_path": "examples/eggs/full_case_index.md",
        "full_map_path": "examples/eggs/full_case_map.md",
        "worked_map_path": "examples/eggs/worked_region_observational_vs_rct_map.md",
        "audit_path": "examples/eggs/decision_space_erosion_audit.md",
        "best_path": "examples/eggs/BEST_REGIONS.md",
        "full_baseline_path": "examples/eggs/full_case_flat_synthesis_baseline.md",
        "worked_baseline_path": "examples/eggs/flat_synthesis_baseline.md",
        "task_path": "examples/eggs/investigator_task_queue.md",
        "review_packet_path": "docs/review/EGGS_HUMAN_AUDIT_PACKET.md",
        "review_checklist_path": "docs/review/EGGS_HUMAN_AUDIT_CHECKLIST.csv",
        "theme": "evidence",
    },
)

SPOTLIGHTS = {
    "lhc": (
        {
            "distinction": "Low-velocity LHC products may be trappable even if cosmic-ray products are not.",
            "flat": "Flat synthesis tends to mention velocity without preserving the dependency on trapping and Earth cosmic-ray limits.",
            "map": "The worked map preserves `lhc_c004`, `lhc_c012`, `lhc_r003`, `lhc_r004`, and `lhc_r016`.",
            "status": "Recurring loss across model families.",
        },
        {
            "distinction": "Critique and response are multi-threaded.",
            "flat": "A synthesis can treat the Plaga/GM exchange as a broad dispute.",
            "map": "The map separates Plaga scenario claims, white-dwarf stopping critique, power-output response, and accretion response.",
            "status": "Strong review target.",
        },
    ),
    "eggs": (
        {
            "distinction": "Outcome evidence and lipid-marker evidence answer different questions.",
            "flat": "Flat synthesis can collapse randomized lipid findings into general health outcome language.",
            "map": "The worked map preserves endpoint boundaries through `eggs_c015`, `eggs_c016`, `eggs_r005`, and `eggs_r006`.",
            "status": "Partly preserved by stronger blinded baselines.",
        },
        {
            "distinction": "`Up to one egg/day` has different meanings across sources.",
            "flat": "Similar wording is easy to merge across AHA, BMJ, and NNR.",
            "map": "The map separates public guidance, cohort conclusion, and scoping-review synthesis.",
            "status": "Recurring scope-distinction loss.",
        },
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static UI data from checked-in FLF artifacts.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="Check that ui/data.json is current.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    payload = build_payload(repo_root)
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


def build_payload(repo_root: Path) -> dict:
    cases = []
    for config in CASES:
        manifest = CaseManifest.model_validate(read_yaml(repo_root / str(config["case_path"])))
        worked_map = parse_worked_map(repo_root / str(config["worked_map_path"]))
        audit = parse_erosion_audit(repo_root / str(config["audit_path"]))
        full_map_text = (repo_root / str(config["full_map_path"])).read_text(encoding="utf-8")
        case_payload = {
            "caseKey": config["case_key"],
            "caseId": config["case_id"],
            "label": config["label"],
            "shortLabel": config["short_label"],
            "question": manifest.question,
            "caseType": manifest.case_type,
            "theme": config["theme"],
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
            "clusters": _parse_clusters(full_map_text),
            "clusterRelations": _parse_full_relations(full_map_text),
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
                "borderline": audit["borderline_or_rejected"],
            },
            "tasks": _parse_tasks((repo_root / str(config["task_path"])).read_text(encoding="utf-8")),
            "spotlights": list(SPOTLIGHTS[config["case_key"]]),
            "artifacts": {
                "fullIndex": config["full_index_path"],
                "fullMap": config["full_map_path"],
                "workedMap": config["worked_map_path"],
                "erosionAudit": config["audit_path"],
                "bestRegions": config["best_path"],
                "fullCaseBaseline": config["full_baseline_path"],
                "workedBaseline": config["worked_baseline_path"],
                "multiModelAudit": "docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md",
                "taskQueue": config["task_path"],
                "reviewPacket": config["review_packet_path"],
                "reviewChecklist": config["review_checklist_path"],
            },
        }
        cases.append(case_payload)
    return {
        "generatedFrom": "scripts/build_ui_data.py",
        "status": "human-review-needed",
        "summary": {
            "caseCount": len(cases),
            "sourceCount": sum(len(case["sources"]) for case in cases),
            "clusterCount": sum(len(case["clusters"]) for case in cases),
            "claimCount": sum(len(case["worked"]["claims"]) for case in cases),
            "relationCount": sum(len(case["worked"]["relations"]) for case in cases),
            "taskCount": sum(len(case["tasks"]) for case in cases),
        },
        "cases": cases,
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
