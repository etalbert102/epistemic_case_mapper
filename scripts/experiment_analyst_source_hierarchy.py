from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import dedupe, dict_value, list_value, short_text, string_list
from epistemic_case_mapper.map_briefing_source_identity import source_id_alias_map
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output


LANE_LABELS = {
    "primary_answer_drivers": "Start with",
    "quantitative_calibrators": "Use to size the effect or comparison",
    "counterweight_sources": "Use as the main check",
    "scope_boundary_sources": "Use to bound the recommendation",
    "contextual_sources": "Use for context and translation",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Experiment with adding global source hierarchy to the analyst decision model output.")
    parser.add_argument("--artifact-dir", required=True, help="Directory containing analyst_decision_model.json and related artifacts.")
    parser.add_argument("--backend", default="prompt", help="Model backend, for example prompt or ollama:gemma4:12b-mlx.")
    parser.add_argument("--backend-timeout", type=int, default=180)
    parser.add_argument("--backend-retries", type=int, default=0)
    parser.add_argument("--out", help="Output directory. Defaults to ARTIFACT_DIR/source_hierarchy_experiment.")
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir)
    out = Path(args.out) if args.out else artifact_dir / "source_hierarchy_experiment"
    out.mkdir(parents=True, exist_ok=True)

    context = build_context(artifact_dir)
    prompt = build_prompt(context)
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    result = run_model_backend(
        prompt,
        args.backend,
        timeout_seconds=args.backend_timeout,
        max_retries=args.backend_retries,
        json_mode=True,
        num_predict=4096,
    )
    raw = result.text
    payload = parse_payload(raw)
    validated = validate_hierarchy(payload, context)
    section = render_section(validated)
    current = extract_source_weighting_section((artifact_dir / "BRIEFING.md").read_text(encoding="utf-8") if (artifact_dir / "BRIEFING.md").exists() else "")
    comparison = render_comparison(current, section, validated)

    (out / "raw.txt").write_text(raw, encoding="utf-8")
    (out / "source_hierarchy.json").write_text(json.dumps(validated, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "source_hierarchy_section.md").write_text(section + "\n", encoding="utf-8")
    (out / "comparison.md").write_text(comparison + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "status": validated["report"]["status"], "warnings": validated["report"]["warnings"]}, indent=2))
    return 0


def build_context(artifact_dir: Path) -> dict[str, Any]:
    analyst = json.loads((artifact_dir / "analyst_decision_model.json").read_text(encoding="utf-8"))
    ledger = json.loads((artifact_dir / "analyst_evidence_ledger.json").read_text(encoding="utf-8"))
    memo_packet = json.loads((artifact_dir / "memo_ready_packet.json").read_text(encoding="utf-8"))
    canonical = dict_value(memo_packet.get("canonical_decision_writer_packet"))
    source_trail = list_value(memo_packet.get("source_trail"))
    aliases = source_id_alias_map(source_trail)
    ledger_by_id = {str(row.get("evidence_item_id") or ""): row for row in list_value(ledger.get("rows")) if isinstance(row, dict)}
    groups = [compact_group(group, ledger_by_id, aliases) for group in list_value(analyst.get("evidence_groups")) if isinstance(group, dict)]
    source_roles = build_source_role_summary(groups, source_trail)
    return {
        "schema_id": "analyst_source_hierarchy_experiment_context_v1",
        "decision_question": analyst.get("decision_question") or memo_packet.get("decision_question"),
        "direct_answer": analyst.get("direct_answer"),
        "decision_logic": dict_value(analyst.get("decision_logic")),
        "source_trail": compact_source_trail(source_trail),
        "analyst_evidence_groups": groups,
        "existing_source_weight_judgments": list_value(canonical.get("source_weight_judgments")),
        "source_role_summary": source_roles,
        "allowed_source_ids": [str(row.get("source_id") or "") for row in source_trail if isinstance(row, dict)],
    }


def compact_group(group: dict[str, Any], ledger_by_id: dict[str, dict[str, Any]], aliases: dict[str, str]) -> dict[str, Any]:
    evidence_ids = string_list(group.get("covered_evidence_item_ids"))
    source_ids: list[str] = []
    source_limits: list[str] = []
    for evidence_id in evidence_ids:
        row = ledger_by_id.get(evidence_id, {})
        source_ids.extend(aliases.get(source_id, source_id) for source_id in string_list(row.get("source_ids")))
        appraisal = dict_value(row.get("source_appraisal"))
        source_limits.extend(string_list(appraisal.get("source_use_warnings")))
    return {
        "group_id": group.get("group_id"),
        "memo_role": group.get("memo_role"),
        "importance_rank": group.get("importance_rank"),
        "answer_relation": group.get("answer_relation"),
        "target_answer_option": group.get("target_answer_option"),
        "proposition": short_text(str(group.get("proposition") or ""), 360),
        "answer_impact": short_text(str(group.get("answer_impact") or ""), 220),
        "evidence_strength": short_text(str(group.get("evidence_strength") or ""), 160),
        "uncertainty_type": group.get("uncertainty_type"),
        "covered_evidence_item_ids": evidence_ids,
        "source_ids": dedupe(source_ids),
        "source_limits": dedupe(source_limits)[:4],
    }


def compact_source_trail(source_trail: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for row in source_trail:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "source_id": row.get("source_id"),
                "display_label": row.get("display_label") or row.get("source_label"),
                "used_for": string_list(row.get("used_for")),
            }
        )
    return rows


def build_source_role_summary(groups: list[dict[str, Any]], source_trail: list[Any]) -> list[dict[str, Any]]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels = {str(row.get("source_id") or ""): str(row.get("display_label") or row.get("source_label") or "") for row in source_trail if isinstance(row, dict)}
    for group in groups:
        for source_id in string_list(group.get("source_ids")):
            by_source[source_id].append(group)
    rows = []
    for source_id, source_groups in sorted(by_source.items()):
        roles = Counter(str(group.get("memo_role") or "") for group in source_groups)
        rows.append(
            {
                "source_id": source_id,
                "display_label": labels.get(source_id, source_id),
                "group_count": len(source_groups),
                "memo_role_counts": dict(roles),
                "top_group_ids": [str(group.get("group_id") or "") for group in sorted(source_groups, key=lambda row: int(row.get("importance_rank") or 100))[:5]],
            }
        )
    return rows


def build_prompt(context: dict[str, Any]) -> str:
    schema = {
        "schema_id": "analyst_source_hierarchy_experiment_v1",
        "hierarchy_thesis": "one concise paragraph explaining how to read source weight comparatively",
        "lanes": {
            lane: [
                {
                    "source_ids": ["source IDs from allowed_source_ids"],
                    "evidence_group_ids": ["analyst evidence group IDs supporting this lane"],
                    "reader_use_sentence": "reader-facing sentence explaining how this lane should be used",
                    "why_this_role": "comparative rationale",
                    "limits": ["important source-use limits"],
                }
            ]
            for lane in LANE_LABELS
        },
        "source_accounting": [{"source_id": "source ID", "primary_lane": "one lane key", "rationale": "why"}],
        "warnings": ["optional concerns about weak hierarchy or source limitations"],
    }
    packet = {
        "task": (
            "Extend the analyst decision model with a global comparative source hierarchy. "
            "Do not judge each source in isolation. Decide which sources carry the answer, which calibrate magnitude, "
            "which bound or challenge the answer, which define scope, and which mainly contextualize."
        ),
        "rules": [
            "Return strict JSON matching the schema.",
            "Use only allowed_source_ids.",
            "Account for every allowed source in source_accounting.",
            "Tie each lane to analyst evidence group IDs.",
            "Use compact reader-facing prose suitable for a decision memo.",
        ],
        "required_schema": schema,
        "context": context,
    }
    return json.dumps(packet, indent=2, ensure_ascii=False)


def parse_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(canonical_json_output(raw))
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def validate_hierarchy(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    allowed_sources = set(string_list(context.get("allowed_source_ids")))
    allowed_groups = {str(group.get("group_id") or "") for group in list_value(context.get("analyst_evidence_groups"))}
    normalized = {
        "schema_id": "analyst_source_hierarchy_experiment_v1",
        "hierarchy_thesis": short_text(str(payload.get("hierarchy_thesis") or ""), 900),
        "lanes": {},
        "source_accounting": [],
        "warnings": string_list(payload.get("warnings")),
    }
    invalid_sources: list[str] = []
    invalid_groups: list[str] = []
    accounted_sources: list[str] = []
    for lane in LANE_LABELS:
        rows = []
        for row in list_value(dict_value(payload.get("lanes")).get(lane)):
            if not isinstance(row, dict):
                continue
            source_ids = [source_id for source_id in string_list(row.get("source_ids")) if source_id in allowed_sources]
            invalid_sources.extend(source_id for source_id in string_list(row.get("source_ids")) if source_id not in allowed_sources)
            group_ids = [group_id for group_id in string_list(row.get("evidence_group_ids")) if group_id in allowed_groups]
            invalid_groups.extend(group_id for group_id in string_list(row.get("evidence_group_ids")) if group_id not in allowed_groups)
            if not source_ids:
                continue
            accounted_sources.extend(source_ids)
            rows.append(
                {
                    "source_ids": dedupe(source_ids),
                    "evidence_group_ids": dedupe(group_ids),
                    "reader_use_sentence": short_text(str(row.get("reader_use_sentence") or ""), 500),
                    "why_this_role": short_text(str(row.get("why_this_role") or ""), 500),
                    "limits": [short_text(limit, 220) for limit in string_list(row.get("limits"))[:4]],
                }
            )
        normalized["lanes"][lane] = rows
    for row in list_value(payload.get("source_accounting")):
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").strip()
        if source_id not in allowed_sources:
            invalid_sources.append(source_id)
            continue
        normalized["source_accounting"].append(
            {
                "source_id": source_id,
                "primary_lane": str(row.get("primary_lane") or "").strip(),
                "rationale": short_text(str(row.get("rationale") or ""), 360),
            }
        )
    missing_sources = sorted(allowed_sources - set(accounted_sources) - {row["source_id"] for row in normalized["source_accounting"]})
    primary_count = len(dedupe(source_id for row in normalized["lanes"]["primary_answer_drivers"] for source_id in row["source_ids"]))
    report_warnings = [
        *(["missing_source_accounting"] if missing_sources else []),
        *(["invalid_source_ids_removed"] if invalid_sources else []),
        *(["invalid_group_ids_removed"] if invalid_groups else []),
        *(["flattened_primary_driver_lane"] if primary_count > 3 else []),
        *(["missing_hierarchy_thesis"] if not normalized["hierarchy_thesis"] else []),
    ]
    normalized["report"] = {
        "schema_id": "analyst_source_hierarchy_experiment_report_v1",
        "status": "ready" if not report_warnings else "warning",
        "warnings": report_warnings,
        "missing_sources": missing_sources,
        "invalid_sources_removed": sorted(set(source_id for source_id in invalid_sources if source_id)),
        "invalid_groups_removed": sorted(set(group_id for group_id in invalid_groups if group_id)),
        "primary_driver_source_count": primary_count,
    }
    return normalized


def render_section(hierarchy: dict[str, Any]) -> str:
    lines = ["## How to Weight the Evidence", ""]
    thesis = str(hierarchy.get("hierarchy_thesis") or "").strip()
    lines.append(thesis or "Use the sources in layers: start with answer-driving evidence, then use other sources to size, bound, contextualize, or challenge the answer.")
    for lane, label in LANE_LABELS.items():
        rows = list_value(dict_value(hierarchy.get("lanes")).get(lane))
        if not rows:
            continue
        clauses = []
        for row in rows:
            sources = cite_list(string_list(row.get("source_ids")))
            sentence = str(row.get("reader_use_sentence") or row.get("why_this_role") or "").strip().rstrip(".")
            if sources and sentence:
                clauses.append(f"{sources} {sentence[:1].lower() + sentence[1:]}")
        if clauses:
            lines.extend(["", f"**{label}:** " + " ".join(clauses)])
    return "\n".join(lines).strip()


def cite_list(source_ids: list[str]) -> str:
    return ", ".join(f"[{source_id}]" for source_id in dedupe(source_ids) if source_id)


def extract_source_weighting_section(memo: str) -> str:
    marker = "## How to Weight the Evidence"
    start = memo.find(marker)
    if start < 0:
        return ""
    next_heading = memo.find("\n## ", start + len(marker))
    return memo[start:].strip() if next_heading < 0 else memo[start:next_heading].strip()


def render_comparison(current: str, experimental: str, hierarchy: dict[str, Any]) -> str:
    report = dict_value(hierarchy.get("report"))
    return "\n\n".join(
        [
            "# Analyst Source Hierarchy Experiment",
            "## Report\n\n```json\n" + json.dumps(report, indent=2, ensure_ascii=False) + "\n```",
            "## Current Section\n\n" + (current or "_No current section found._"),
            "## Experimental Section\n\n" + experimental,
        ]
    ).strip()


if __name__ == "__main__":
    raise SystemExit(main())
