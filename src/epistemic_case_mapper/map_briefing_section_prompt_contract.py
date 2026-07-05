from __future__ import annotations

from typing import Any


def model_facing_section_contract(contract: dict[str, Any]) -> dict[str, Any]:
    model_contract = dict(contract)
    model_contract["owned_elsewhere_evidence"] = [
        _model_facing_owned_elsewhere_row(row)
        for row in contract.get("owned_elsewhere_evidence", [])
        if isinstance(row, dict)
    ]
    return model_contract


def _model_facing_owned_elsewhere_row(row: dict[str, Any]) -> dict[str, Any]:
    policy = row.get("reference_policy", {}) if isinstance(row.get("reference_policy"), dict) else {}
    owner = str(policy.get("owner_section", "")).strip()
    style = str(policy.get("reference_style", "")).strip() or "short_reference"
    return {
        "slot": row.get("slot"),
        "owner_section": owner,
        "reference_style": style,
        "allowed": bool(policy.get("allowed", style != "do_not_repeat")),
        "reference_instruction": _reference_instruction(owner, style),
    }


def _reference_instruction(owner: str, style: str) -> str:
    if style == "do_not_repeat":
        return f"Do not mention this evidence here; leave it to {owner}." if owner else "Do not mention this evidence here."
    return (
        f"Use only a brief cross-reference to {owner}; do not include source-level details."
        if owner
        else "Use only a brief cross-reference; do not include source-level details."
    )
