from __future__ import annotations

from typing import Any


def with_section_specific_jobs(rows: list[dict[str, Any]], *, section_id: str) -> list[dict[str, Any]]:
    job = section_evidence_job(section_id)
    if not job:
        return rows
    enriched = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        current = str(row.get("section_specific_job") or "").strip()
        enriched.append({**row, "section_specific_job": current or job})
    return enriched


def section_evidence_job(section_id: str) -> str:
    jobs = {
        "answer_evidence": "Use this evidence to explain why the current read follows; do not use it to restate practical advice or enumerate every caveat.",
        "counterweights": "Use this evidence to narrow, bound, stress-test, or update the current read; explain whether it changes the answer or only calibrates confidence.",
        "practical_implication": "Use this evidence only to translate the answer into advice, exceptions, monitoring, or wording; keep the evidence recap brief.",
        "source_weighting": "Use this source only to explain source hierarchy, directness, credibility, or source-use limits.",
    }
    return jobs.get(section_id, "")
