from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegionFiles:
    case_key: str
    case_label: str
    map_path: str
    audit_path: str
    baseline_path: str
    best_path: str
    output_json_path: str


REGION_FILES = (
    RegionFiles(
        case_key="lhc",
        case_label="LHC black holes",
        map_path="examples/lhc_black_holes/worked_region_cosmic_ray_map.md",
        audit_path="examples/lhc_black_holes/decision_space_erosion_audit.md",
        baseline_path="examples/lhc_black_holes/flat_synthesis_baseline.md",
        best_path="examples/lhc_black_holes/BEST_REGIONS.md",
        output_json_path="examples/lhc_black_holes/worked_region_cosmic_ray_map.json",
    ),
    RegionFiles(
        case_key="eggs",
        case_label="Eggs and health",
        map_path="examples/eggs/worked_region_observational_vs_rct_map.md",
        audit_path="examples/eggs/decision_space_erosion_audit.md",
        baseline_path="examples/eggs/flat_synthesis_baseline.md",
        best_path="examples/eggs/BEST_REGIONS.md",
        output_json_path="examples/eggs/worked_region_observational_vs_rct_map.json",
    ),
)


def parse_worked_map(path: Path) -> dict:
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
    }


def parse_erosion_audit(path: Path) -> dict:
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


def collect_ids(repo_root: Path) -> dict[str, set[str]]:
    ids: dict[str, set[str]] = {"claim": set(), "relation": set(), "loss": set()}
    for region in REGION_FILES:
        worked_map = parse_worked_map(repo_root / region.map_path)
        audit = parse_erosion_audit(repo_root / region.audit_path)
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


def _strip_marker(value: str) -> str:
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value
