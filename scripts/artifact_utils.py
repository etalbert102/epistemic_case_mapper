from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path

from epistemic_case_mapper.submission_manifest import SubmissionManifest, load_submission_manifest


@dataclass(frozen=True)
class RegionFiles:
    case_key: str
    case_label: str
    region_id: str
    map_path: str
    map_format: str
    audit_path: str
    audit_format: str
    baseline_path: str
    best_path: str | None
    output_json_path: str


def region_files_from_manifest(manifest: SubmissionManifest) -> tuple[RegionFiles, ...]:
    return tuple(
        RegionFiles(
            case_key=region.case_key,
            case_label=region.case_label,
            region_id=region.region_id,
            map_path=region.map_path,
            map_format=region.map_format,
            audit_path=region.audit_path,
            audit_format=region.audit_format,
            baseline_path=region.baseline_path,
            best_path=region.best_path,
            output_json_path=region.output_json_path,
        )
        for region in manifest.iter_worked_regions()
    )


def load_region_files(repo_root: Path, manifest_path: str | Path = "submission_manifest.yaml") -> tuple[RegionFiles, ...]:
    return region_files_from_manifest(load_submission_manifest(repo_root, manifest_path))


REGION_FILES = load_region_files(Path(__file__).resolve().parents[1])


def parse_worked_map(path: Path, artifact_format: str = "markdown_kv_v1") -> dict:
    if artifact_format == "json_case_map_v1":
        return _parse_json_worked_map(path)
    if artifact_format != "markdown_kv_v1":
        raise ValueError(f"unknown_worked_map_format format={artifact_format}")
    text = path.read_text(encoding="utf-8")
    return {
        "title": _first_heading(text),
        "status": _field(text, "Status"),
        "prompt_procedure": _field(text, "Prompt/procedure"),
        "evidence_mode": _field(text, "Evidence mode"),
        "sources": _section_bullets(text, "Source Subset"),
        "claims": [_parse_key_value_block(block) for block in _blocks(text, "claim_id")],
        "relations": [_parse_key_value_block(block) for block in _blocks(text, "relation_id")],
        "crux_candidates": _section_bullets(text, "Crux Candidates"),
        "similar_but_not_identical": _section_bullets(text, "Similar But Not Identical"),
        "evidence_check": _evidence_check_rows(text),
    }


def parse_erosion_audit(path: Path, artifact_format: str = "markdown_kv_v1") -> dict:
    if artifact_format == "json_case_map_v1":
        return _parse_json_erosion_audit(path)
    if artifact_format != "markdown_kv_v1":
        raise ValueError(f"unknown_audit_format format={artifact_format}")
    text = path.read_text(encoding="utf-8")
    return {
        "title": _first_heading(text),
        "status": _field(text, "Status"),
        "prompt_procedure": _field(text, "Prompt/procedure"),
        "baseline_comparator": _field(text, "Baseline comparator"),
        "map_comparator": _field(text, "Map comparator"),
        "losses": [_parse_key_value_block(block) for block in _blocks(text, "loss_id")],
        "borderline_or_rejected": _section_bullets(text, "Borderline Or Rejected Losses"),
    }


def collect_ids(
    repo_root: Path,
    manifest: SubmissionManifest | None = None,
) -> dict[str, set[str]]:
    ids: dict[str, set[str]] = {"claim": set(), "relation": set(), "loss": set()}
    region_files = region_files_from_manifest(manifest) if manifest is not None else REGION_FILES
    for region in region_files:
        worked_map = parse_worked_map(repo_root / region.map_path, region.map_format)
        audit = parse_erosion_audit(repo_root / region.audit_path, region.audit_format)
        ids["claim"].update(str(claim.get("claim_id", "")) for claim in worked_map["claims"])
        ids["relation"].update(str(relation.get("relation_id", "")) for relation in worked_map["relations"])
        ids["loss"].update(str(loss.get("loss_id", "")) for loss in audit["losses"])
    return {key: {item for item in values if item} for key, values in ids.items()}


def _first_heading(text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _field(text: str, field_name: str) -> str:
    match = re.search(rf"^{re.escape(field_name)}:\s*(.+)$", text, flags=re.MULTILINE)
    return _strip_marker(match.group(1).strip()) if match else ""


def _blocks(text: str, id_field: str) -> list[str]:
    pattern = rf"(?ms)^{re.escape(id_field)}:\s*.+?(?=^{re.escape(id_field)}:\s|\n## |\Z)"
    return [match.group(0).strip() for match in re.finditer(pattern, text)]


def _parse_key_value_block(block: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []
    for line in block.splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            if current_key is not None:
                result[current_key] = _strip_marker(" ".join(current_value).strip())
            current_key = match.group(1)
            current_value = [match.group(2).strip()]
        elif current_key is not None:
            current_value.append(line.strip())
    if current_key is not None:
        result[current_key] = _strip_marker(" ".join(current_value).strip())
    return result


def _section_bullets(text: str, heading: str) -> list[str]:
    match = re.search(rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.+?)(?=^##\s|\Z)", text)
    if not match:
        return []
    items = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(_strip_marker(line[2:].strip()))
    return items


def _evidence_check_rows(text: str) -> list[list[str]]:
    rows = []
    in_evidence_check = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_evidence_check = line == "## Evidence Check"
            continue
        if not in_evidence_check or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] not in {"Probe", "---"} and not set(cells[0]) <= {"-", ":"}:
            rows.append(cells)
    return rows


def _parse_json_worked_map(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    worked = data.get("worked_map", data)
    return {
        "title": worked.get("title", ""),
        "status": worked.get("status", ""),
        "prompt_procedure": worked.get("prompt_procedure", ""),
        "evidence_mode": worked.get("evidence_mode", ""),
        "sources": list(worked.get("sources", [])),
        "claims": list(worked.get("claims", [])),
        "relations": list(worked.get("relations", [])),
        "crux_candidates": list(worked.get("crux_candidates", worked.get("cruxes", []))),
        "similar_but_not_identical": list(
            worked.get("similar_but_not_identical", worked.get("similar_claims", []))
        ),
        "evidence_check": list(worked.get("evidence_check", [])),
    }


def _parse_json_erosion_audit(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    audit = data.get("erosion_audit", data)
    return {
        "title": audit.get("title", ""),
        "status": audit.get("status", ""),
        "prompt_procedure": audit.get("prompt_procedure", ""),
        "baseline_comparator": audit.get("baseline_comparator", ""),
        "map_comparator": audit.get("map_comparator", ""),
        "losses": list(audit.get("losses", [])),
        "borderline_or_rejected": list(audit.get("borderline_or_rejected", [])),
    }


def _strip_marker(value: str) -> str:
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value
