from __future__ import annotations

from typing import Any

from epistemic_case_mapper.synthesis_uplift_types import Loss


def _normalize_loss_judgment(loss_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if "loss_judgments" in payload and isinstance(payload["loss_judgments"], list) and payload["loss_judgments"]:
        payload = payload["loss_judgments"][0] if isinstance(payload["loss_judgments"][0], dict) else {}
    row = {
        "loss_id": payload.get("loss_id") if isinstance(payload.get("loss_id"), str) else loss_id,
        "winner": payload.get("winner") if payload.get("winner") in {"A", "B", "tie", "neither"} else "invalid",
        "a_coverage": payload.get("a_coverage") if payload.get("a_coverage") in {"none", "partial", "clear"} else "invalid",
        "b_coverage": payload.get("b_coverage") if payload.get("b_coverage") in {"none", "partial", "clear"} else "invalid",
        "reason": payload.get("reason") if isinstance(payload.get("reason"), str) else "",
    }
    row["consistency_error"] = _judgment_consistency_error(row)
    return row
def _judgment_consistency_error(row: dict[str, Any]) -> str | None:
    winner = row["winner"]
    a_rank = _coverage_rank(row["a_coverage"])
    b_rank = _coverage_rank(row["b_coverage"])
    if winner == "invalid" or a_rank < 0 or b_rank < 0:
        return "invalid_enum"
    if winner == "A" and a_rank <= b_rank:
        return "winner_A_not_better_than_B"
    if winner == "B" and b_rank <= a_rank:
        return "winner_B_not_better_than_A"
    if winner == "tie" and a_rank != b_rank:
        return "tie_with_unequal_coverage"
    if winner == "neither" and (a_rank > 0 or b_rank > 0):
        return "neither_with_positive_coverage"
    return None
def _coverage_rank(value: str) -> int:
    return {"none": 0, "partial": 1, "clear": 2}.get(value, -1)
def _overall_from_loss_judgments(judgments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in judgments if not row.get("parse_error") and not row.get("consistency_error")]
    winners = [row.get("winner") for row in valid]
    counts = {winner: winners.count(winner) for winner in ("A", "B", "tie", "neither")}
    if counts["B"] > counts["A"]:
        winner = "B"
    elif counts["A"] > counts["B"]:
        winner = "A"
    elif valid:
        winner = "tie"
    else:
        winner = "neither"
    return {"winner": winner, "counts": counts, "valid_judgments": len(valid), "total_judgments": len(judgments)}
def _region_summary(losses: list[Loss], judgment: dict[str, Any]) -> dict[str, Any]:
    known_loss_ids = {loss.loss_id for loss in losses}
    rows = judgment.get("loss_judgments", [])
    if not isinstance(rows, list):
        rows = []
    valid_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("loss_id") in known_loss_ids
        and not row.get("parse_error")
        and not row.get("consistency_error")
    ]
    winners = [row.get("winner") for row in valid_rows]
    invalid_rows = [row for row in rows if isinstance(row, dict) and row not in valid_rows]
    return {
        "stress_wins": winners.count("B"),
        "map_only_wins": winners.count("A"),
        "ties": winners.count("tie"),
        "neither": winners.count("neither"),
        "valid_judgments": len(valid_rows),
        "invalid_judgments": max(0, len(losses) - len(valid_rows)),
        "invalid_reasons": _invalid_reasons(invalid_rows),
        "overall_winner": (judgment.get("overall") or {}).get("winner") if isinstance(judgment.get("overall"), dict) else None,
    }
def _invalid_reasons(rows: list[dict[str, Any]]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for row in rows:
        reason = row.get("parse_error") or row.get("consistency_error") or "missing_or_unknown_loss_id"
        reasons[reason] = reasons.get(reason, 0) + 1
    return reasons
def _aggregate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "region_count": len(rows),
        "loss_count": sum(row["loss_count"] for row in rows),
        "stress_wins": sum(row["summary"]["stress_wins"] for row in rows),
        "map_only_wins": sum(row["summary"]["map_only_wins"] for row in rows),
        "ties": sum(row["summary"]["ties"] for row in rows),
        "neither": sum(row["summary"]["neither"] for row in rows),
        "invalid_judgments": sum(row["summary"]["invalid_judgments"] for row in rows),
    }
def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Synthesis Uplift Eval",
        "",
        f"Schema: `{report['schema_id']}`",
        f"Backend: `{report['backend']}`",
        f"Judge backend: `{report['judge_backend']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Regions", ""])
    for row in report["regions"]:
        lines.append(f"### {row['region_id']}")
        lines.append("")
        for key, value in row["summary"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append(f"- stress report: `{row['paths']['stress_report']}`")
        lines.append(f"- rewrite requirements: `{row['paths']['rewrite_requirements']}`")
        lines.append(f"- deterministic coverage: `{row['paths']['deterministic_requirement_coverage']}`")
        lines.append(f"- map-only synthesis: `{row['paths']['map_only_synthesis']}`")
        lines.append(f"- stress-assisted synthesis: `{row['paths']['stress_assisted_synthesis']}`")
        lines.append(f"- judgment: `{row['paths']['judgment']}`")
        lines.append("")
    return "\n".join(lines)

