from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def source_roles_by_source(source_weighting: list[Any]) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    for row in source_weighting:
        if not isinstance(row, dict):
            continue
        role = _normalized_source_role(row)
        if not role:
            continue
        for source_id in _string_list(row.get("source_ids")):
            roles.setdefault(source_id, set()).add(role)
    return roles


def apply_role_bound_citations_to_section_packet(
    section_packet: dict[str, Any],
    *,
    source_weighting: list[Any],
) -> dict[str, Any]:
    source_roles = source_roles_by_source(source_weighting)
    if not source_roles:
        return {"changed_atom_count": 0, "changed_quantity_count": 0}
    atoms = []
    changed_atom_count = 0
    changed_quantity_count = 0
    for atom in _list(section_packet.get("source_bound_evidence_atoms")):
        if not isinstance(atom, dict):
            continue
        updated = dict(atom)
        selected = role_bound_source_ids(atom, source_roles)
        current = _string_list(atom.get("allowed_citations") or atom.get("source_ids"))
        if selected and selected != current:
            updated["allowed_citations"] = selected
            updated["source_ids"] = selected
            changed_atom_count += 1
        quantity_rows = []
        for quantity in _list(updated.get("quantity_tuples")):
            if not isinstance(quantity, dict):
                quantity_rows.append(quantity)
                continue
            q_selected = role_bound_quantity_source_ids(quantity, atom, source_roles)
            q_current = _string_list(quantity.get("allowed_citations") or quantity.get("source_ids"))
            if q_selected and q_selected != q_current:
                quantity = {**quantity, "allowed_citations": q_selected, "source_ids": q_selected}
                changed_quantity_count += 1
            quantity_rows.append(quantity)
        if quantity_rows:
            updated["quantity_tuples"] = quantity_rows
        atoms.append(updated)
    if changed_atom_count or changed_quantity_count:
        section_packet["source_bound_evidence_atoms"] = atoms
        section_packet["citation_role_binding_report"] = {
            "schema_id": "citation_role_binding_report_v1",
            "changed_atom_count": changed_atom_count,
            "changed_quantity_count": changed_quantity_count,
        }
    return {"changed_atom_count": changed_atom_count, "changed_quantity_count": changed_quantity_count}


def role_bound_source_ids(atom: dict[str, Any], source_roles: dict[str, set[str]]) -> list[str]:
    source_ids = _string_list(atom.get("allowed_citations") or atom.get("source_ids"))
    if len(source_ids) <= 1:
        return source_ids
    desired = desired_roles_for_atom(atom)
    matching = [source_id for source_id in source_ids if source_roles.get(source_id, set()).intersection(desired)]
    if matching:
        return matching[:2]
    quantity_sources = _dedupe(
        [
            source_id
            for quantity in _list(atom.get("quantity_tuples"))
            if isinstance(quantity, dict)
            for source_id in _string_list(quantity.get("source_ids") or quantity.get("allowed_citations"))
        ]
    )
    if quantity_sources and "calibration" in desired:
        return [source_id for source_id in source_ids if source_id in quantity_sources][:2] or source_ids[:1]
    return source_ids[:1] if len(source_ids) > 2 else source_ids


def role_bound_quantity_source_ids(
    quantity: dict[str, Any],
    atom: dict[str, Any],
    source_roles: dict[str, set[str]],
) -> list[str]:
    source_ids = _string_list(quantity.get("allowed_citations") or quantity.get("source_ids")) or _string_list(
        atom.get("allowed_citations") or atom.get("source_ids")
    )
    if len(source_ids) <= 1:
        return source_ids
    matching = [source_id for source_id in source_ids if "calibration" in source_roles.get(source_id, set())]
    if matching:
        return matching[:2]
    return source_ids[:1]


def desired_roles_for_atom(atom: dict[str, Any]) -> set[str]:
    role = str(atom.get("citation_role") or atom.get("reader_evidence_role") or atom.get("role") or "").lower()
    text = " ".join(
        str(atom.get(key) or "")
        for key in (
            "claim",
            "decision_relevance",
            "use_for",
            "section_specific_job",
            "applicability_scope",
        )
    ).lower()
    if role in {"calibration", "calibrates_magnitude", "quantitative_anchor"} or _atom_has_quantities(atom):
        return {"calibration"}
    if role in {"boundary", "bounds_answer", "defines_scope", "scope_or_subgroup_boundary"} or any(
        term in text for term in ("scope", "bound", "boundary", "exception", "subgroup", "applicability")
    ):
        return {"boundary", "counterweight", "calibration"}
    if role in {"counterweight", "limiting_evidence"} or any(
        term in text for term in ("tension", "risk", "harm", "weaken", "would change", "update trigger")
    ):
        return {"counterweight", "boundary", "calibration"}
    if role in {"context", "contextualizes", "interpretive_context"} or any(
        term in text for term in ("context", "background", "guidance", "interpret")
    ):
        return {"context", "direct_support"}
    return {"direct_support"}


def _normalized_source_role(row: dict[str, Any]) -> str:
    main_use = str(row.get("main_use") or "").strip().lower()
    if main_use in {"calibrates_magnitude", "calibration", "sizes_effect"}:
        return "calibration"
    if main_use in {"bounds_answer", "counterweight", "checks_answer"}:
        return "counterweight"
    if main_use in {"defines_scope", "scope_boundary"}:
        return "boundary"
    if main_use in {"contextualizes", "context", "interpretive_context"}:
        return "context"
    if main_use in {"drives_answer", "supports_answer", "primary_support"}:
        return "direct_support"
    text = " ".join(
        str(_dict(row).get(key) or "")
        for key in ("weight_summary", "why_weight_this_way", "reader_facing_limit", "limits")
    ).lower()
    if "calibrat" in text or "magnitude" in text or "quant" in text:
        return "calibration"
    if "bound" in text or "scope" in text or "limit" in text:
        return "boundary"
    if "counter" in text or "tension" in text or "weaken" in text:
        return "counterweight"
    if "context" in text or "guidance" in text or "interpret" in text:
        return "context"
    if "drive" in text or "support" in text or "answer" in text:
        return "direct_support"
    return ""


def _atom_has_quantities(atom: dict[str, Any]) -> bool:
    return any(isinstance(quantity, dict) for quantity in _list(atom.get("quantity_tuples")))
