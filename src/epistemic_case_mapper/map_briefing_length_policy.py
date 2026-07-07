from __future__ import annotations

import re
from typing import Any


def executive_length_policy(executive_markdown: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    word_count = _word_count(executive_markdown)
    decision_brief_words = _decision_brief_word_count(executive_markdown)
    budget = _complexity_adjusted_budget(scaffold)
    issues: list[dict[str, str]] = []
    if word_count > budget["executive_word_budget"]:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "executive_brief_too_long_for_complexity",
                "message": (
                    "The executive brief exceeds the complexity-adjusted "
                    f"{budget['executive_word_budget']}-word target."
                ),
            }
        )
    if decision_brief_words > budget["opening_word_budget"]:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "opening_decision_brief_too_long",
                "message": (
                    "The opening Decision Brief exceeds the "
                    f"{budget['opening_word_budget']}-word front-door target."
                ),
            }
        )
    return {
        "schema_id": "executive_length_policy_v1",
        "executive_word_count": word_count,
        "opening_decision_brief_word_count": decision_brief_words,
        "issues": issues,
        **budget,
    }


def executive_length_report_fields(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "executive_word_budget": policy["executive_word_budget"],
        "opening_decision_brief_word_count": policy["opening_decision_brief_word_count"],
        "opening_word_budget": policy["opening_word_budget"],
        "length_complexity": {
            "source_count": policy["source_count"],
            "crux_count": policy["crux_count"],
            "evidence_family_count": policy["evidence_family_count"],
            "counterweight_count": policy["counterweight_count"],
            "missing_slot_count": policy["missing_slot_count"],
        },
    }


def _complexity_adjusted_budget(scaffold: dict[str, Any]) -> dict[str, Any]:
    components = {
        "source_count": _source_count(scaffold),
        "crux_count": _crux_count(scaffold),
        "evidence_family_count": _evidence_family_count(scaffold),
        "counterweight_count": _counterweight_count(scaffold),
        "missing_slot_count": _missing_slot_count(scaffold),
    }
    score = (
        max(0, components["source_count"] - 5) * 55
        + components["crux_count"] * 65
        + max(0, components["evidence_family_count"] - 3) * 45
        + components["counterweight_count"] * 45
        + components["missing_slot_count"] * 35
    )
    executive_budget = min(2600, 1450 + score)
    return {
        **components,
        "executive_word_budget": executive_budget,
        "opening_word_budget": 220,
    }


def _decision_brief_word_count(markdown: str) -> int:
    match = re.search(r"(?ms)^##\s+Decision Brief\s*$([\s\S]*?)(?=^##\s+|\Z)", markdown)
    return _word_count(match.group(1) if match else "")


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _source_count(scaffold: dict[str, Any]) -> int:
    source_names = scaffold.get("source_display_names", {})
    if isinstance(source_names, dict) and source_names:
        return len(source_names)
    anchors = _dict(scaffold.get("canonical_decision_spine")).get("source_anchors", [])
    return len(anchors) if isinstance(anchors, list) else 0


def _crux_count(scaffold: dict[str, Any]) -> int:
    for key in ("decision_synthesis_model", "argument_model"):
        rows = _dict(scaffold.get(key)).get("cruxes", [])
        if isinstance(rows, list) and rows:
            return len(rows)
    return 0


def _evidence_family_count(scaffold: dict[str, Any]) -> int:
    coverage = _dict(scaffold.get("coverage_balance_report"))
    families = coverage.get("evidence_family_counts", {})
    if isinstance(families, dict) and families:
        return len([value for value in families.values() if int(value or 0) > 0])
    argument = _dict(scaffold.get("argument_model"))
    return sum(
        1
        for key in ("strongest_support", "strongest_counterarguments", "quantitative_anchors", "scope_boundaries")
        if isinstance(argument.get(key), list) and argument.get(key)
    )


def _counterweight_count(scaffold: dict[str, Any]) -> int:
    spine = _dict(scaffold.get("canonical_decision_spine"))
    counter = spine.get("strongest_counterevidence", [])
    if isinstance(counter, list) and counter:
        return len(counter)
    argument = _dict(scaffold.get("argument_model")).get("strongest_counterarguments", [])
    return len(argument) if isinstance(argument, list) else 0


def _missing_slot_count(scaffold: dict[str, Any]) -> int:
    spine_missing = _dict(scaffold.get("canonical_decision_spine")).get("missing_decision_slots", [])
    if isinstance(spine_missing, list) and spine_missing:
        return len(spine_missing)
    coverage = _dict(_dict(scaffold.get("decision_memo_slots")).get("coverage"))
    missing = coverage.get("missing_required_slots", [])
    return len(missing) if isinstance(missing, list) else 0


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
