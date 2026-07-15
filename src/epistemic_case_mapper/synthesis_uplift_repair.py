from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.submission_manifest import WorkedRegion
from epistemic_case_mapper.synthesis_uplift_packet import (
    _audit_slot_for_requirement,
    _deterministic_requirement_coverage,
    _is_meta_loss_text,
    _normalize_for_coverage,
    _packet_scaffold_prompt_block,
    _packet_slots_for_requirements,
)
from epistemic_case_mapper.synthesis_uplift_types import RewriteRequirement


def _requirements_markdown(requirements: tuple[RewriteRequirement, ...]) -> str:
    lines = ["# Validated Rewrite Requirements", "", "Status: `generated`", ""]
    for req in requirements:
        lines.extend(
            [
                f"## {req.requirement_id}: {req.loss_id}",
                "",
                req.instruction,
                "",
                f"- Claims: `{', '.join(req.claim_ids)}`",
                f"- Relations: `{', '.join(req.relation_ids)}`",
                f"- Source refs: `{', '.join(req.source_refs)}`",
                f"- Claim roles: `{', '.join(req.claim_roles)}`",
                f"- Relation types: `{', '.join(req.relation_types)}`",
                "- Claim anchors:",
                *[f"  - {anchor}" for anchor in req.claim_anchors],
                "- Relation anchors:",
                *[f"  - {anchor}" for anchor in req.relation_anchors],
                "- Reader anchors:",
                *[f"  - {anchor}" for anchor in req.reader_anchors],
                "- Directional/boundary phrases:",
                *[f"  - {phrase}" for phrase in req.required_phrases],
                f"- Coverage terms: `{', '.join(req.required_terms)}`",
                "",
            ]
        )
    return "\n".join(lines)
def _repair_synthesis_prompt(
    region: WorkedRegion,
    synthesis: str,
    coverage: dict[str, Any],
    requirements: tuple[RewriteRequirement, ...],
) -> str:
    requirement_lookup = {req.requirement_id: req for req in requirements}
    failed_rows = [
        row
        for row in coverage.get("requirements", [])
        if isinstance(row, dict) and row.get("status") != "clear"
    ]
    failed_blocks = []
    failed_requirements = []
    for row in failed_rows:
        req = requirement_lookup.get(row.get("requirement_id"))
        if req is None:
            continue
        failed_requirements.append(req)
        missing_phrases = [
            phrase
            for phrase in req.required_phrases
            if phrase not in row.get("phrase_hits", [])
        ]
        missing_terms = [
            term
            for term in req.required_terms[:10]
            if term not in row.get("term_hits", [])
        ]
        failed_blocks.append(
            "\n".join(
                (
                    f"- {req.requirement_id} / {req.loss_id}: {req.instruction}",
                    "  Claim anchors: " + (" | ".join(req.claim_anchors) or "none"),
                    "  Relation anchors: " + (" | ".join(req.relation_anchors) or "none"),
                    "  Reader anchors: " + (" | ".join(req.reader_anchors) or "none"),
                    "  Claim roles: " + (", ".join(req.claim_roles) or "none"),
                    "  Relation types: " + (", ".join(req.relation_types) or "none"),
                    "  Missing directional/boundary phrases: " + (" | ".join(missing_phrases) or "none"),
                    "  Missing coverage terms: " + (", ".join(missing_terms) or "none"),
                )
            )
        )
    return "\n\n".join(
        (
            "You are repairing a decision-support packet that failed deterministic map-coverage checks.",
            f"Region: {region.region_id}",
            "Return valid JSON only.",
            "Required JSON shape: "
            "{\"decision_brief\": \"readable repaired bottom-line prose\", "
            "\"confidence\": \"low|medium|high\", "
            "\"decision_implications\": [\"action-relevant implication\"], "
            "\"top_cruxes\": [{\"crux\": \"...\", \"why_it_matters\": \"...\", \"current_read\": \"...\", \"would_change_if\": \"...\"}], "
            "\"evidence_roles\": {\"main_support\": [\"...\"], \"conflicting_evidence\": [\"...\"], \"scope_limits\": [\"...\"], \"method_limits\": [\"...\"]}, "
            "\"stress_caveats\": [\"decision-relevant caveat\"], "
            "\"audit_trail\": [\"map-backed distinction or source-role boundary\"]}",
            "Repair rules:",
            "- Preserve the existing readable decision brief where it is correct, and put checklist residue in audit fields.",
            "- Correct any reversed directional distinction.",
            "- Add missing mapped distinctions below to `audit_trail`, unless they are decision-changing cruxes.",
            "- Put decision-changing missing distinctions in `top_cruxes` with why they matter and what would change the decision.",
            "- Write the actual distinction in words in reader-facing fields.",
            "- Use exact directional/boundary phrases when supplied, unless grammar requires a minimal surrounding phrase.",
            "- Use facts from the mapped claim and relation anchors.",
            "Failed requirements:\n" + ("\n\n".join(failed_blocks) or "none"),
            "Deterministic repair scaffold:\n" + _packet_scaffold_prompt_block(tuple(failed_requirements)),
            "Current synthesis:\n" + synthesis,
        )
    )
def _deterministic_patch_synthesis(
    synthesis: str,
    coverage: dict[str, Any],
    requirements: tuple[RewriteRequirement, ...],
) -> str:
    requirement_lookup = {req.requirement_id: req for req in requirements}
    slot_lookup = {slot.requirement_id: slot for slot in _packet_slots_for_requirements(requirements)}
    patched = synthesis
    for req in requirements:
        for phrase in req.required_phrases:
            patched = _replace_obvious_reversal(patched, phrase)
    coverage = _deterministic_requirement_coverage(patched, requirements)
    additions = []
    for row in coverage.get("requirements", []):
        if not isinstance(row, dict) or row.get("status") == "clear":
            continue
        req = requirement_lookup.get(row.get("requirement_id"))
        if req is None:
            continue
        slot = slot_lookup.get(req.requirement_id) or _audit_slot_for_requirement(req)
        missing_phrases = [
            phrase
            for phrase in req.required_phrases
            if phrase not in row.get("phrase_hits", [])
        ]
        slot_text = slot.text
        safe_missing_phrases = [phrase for phrase in missing_phrases if not _is_meta_loss_text(phrase)]
        if safe_missing_phrases and not any(
            _normalize_for_coverage(phrase) in _normalize_for_coverage(slot_text)
            for phrase in safe_missing_phrases
        ):
            slot_text = safe_missing_phrases[0]
        if slot_text:
            additions.append(f"{req.loss_id}: {slot_text}.")
    if not additions:
        return _ensure_sectioned_packet(patched)
    return _add_mapped_distinctions_section(patched, additions)
def _ensure_sectioned_packet(text: str) -> str:
    if "## Decision Brief" in text and "## Audit Trail" in text:
        return text
    return "\n".join(
        [
            "## Decision Brief",
            "",
            text.strip(),
            "",
            "**Confidence:** Not specified",
            "",
            "## Decision Implications",
            "",
            "- No decision implications returned.",
            "",
            "## What Could Change the Decision",
            "",
            "| Crux | Why it matters | Current read | Would change if |",
            "|---|---|---|---|",
            "| No crux returned | No crux explanation returned. | No current read returned. | No change condition returned. |",
            "",
            "## Evidence Roles",
            "",
            "### Main Support",
            "",
            "- No main support returned.",
            "",
            "### Conflicting Evidence",
            "",
            "- No conflicting evidence returned.",
            "",
            "### Scope Limits",
            "",
            "- No scope limits returned.",
            "",
            "### Method Limits",
            "",
            "- No method limits returned.",
            "",
            "## Decision-Relevant Caveats",
            "",
            "- No stress caveats returned.",
            "",
            "## Audit Trail",
            "",
            "- No additional deterministic mapped-distinction patch required.",
            "",
        ]
    )
def _add_mapped_distinctions_section(text: str, additions: list[str]) -> str:
    unique_additions = [item for index, item in enumerate(additions) if item and item not in additions[:index]]
    if "## Audit Trail" not in text:
        lines = [
            "## Decision Brief",
            "",
            text.strip(),
            "",
            "**Confidence:** Not specified",
            "",
            "## Audit Trail",
            "",
        ]
        lines.extend(f"- {item}" for item in unique_additions)
        return "\n".join(lines)
    lines = text.rstrip().splitlines()
    output = []
    inserted = False
    for line in lines:
        if line.startswith("## Audit Trail") and not inserted:
            output.append(line)
            output.append("")
            output.extend(f"- {item}" for item in unique_additions)
            inserted = True
            continue
        output.append(line)
    if not inserted:
        output.extend(["", "## Audit Trail", "", *[f"- {item}" for item in unique_additions]])
    return "\n".join(output).rstrip() + "\n"
def _replace_obvious_reversal(text: str, required_phrase: str) -> str:
    match = re.search(
        r"(?P<x>[A-Z][A-Za-z0-9\-]+(?: [A-Za-z0-9\-]+){0,4}) may be (?P<property>slower(?: and more trappable)?) than (?P<y>[A-Za-z0-9\-]+(?: [A-Za-z0-9\-]+){0,4})",
        required_phrase,
    )
    if not match:
        return text
    x = match.group("x").strip()
    y = match.group("y").strip()
    prop = match.group("property").strip()
    reversed_phrase = f"{y} may be {prop} than {x}"
    if reversed_phrase in text and required_phrase not in text:
        return text.replace(reversed_phrase, required_phrase)
    return text
