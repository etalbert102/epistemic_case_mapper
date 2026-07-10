from __future__ import annotations

from epistemic_case_mapper.config_profiles import config_profile_from_manifest_payload
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.submission_manifest import SubmissionManifest


def relation_type_semantics(manifest: SubmissionManifest, case_manifest: CaseManifest) -> str:
    profile = config_profile_from_manifest_payload(case_manifest.epistemic_config)
    permitted = manifest.relation_ontology.permitted_types()
    profile_rows = {
        relation.relation_type: relation
        for relation in profile.relation_types
        if relation.relation_type in permitted
    }
    lines: list[str] = []
    for relation_type in sorted(permitted):
        row = profile_rows.get(relation_type)
        if row is not None:
            markers = ", ".join(row.sharpness_markers) if row.sharpness_markers else "none recorded"
            lines.append(
                f"- {relation_type}: {row.description} Use when: {row.use_when} Sharpness markers: {markers}."
            )
            continue
        definition = manifest.relation_ontology.custom_definitions.get(relation_type, "No custom definition supplied.")
        lines.append(f"- {relation_type}: {definition}")
    return "\n".join(lines)
