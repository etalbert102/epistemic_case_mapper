from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json


def write_claim_progress(
    path: Path,
    progress: dict[str, Any],
    processed_chunks: int,
    current_chunk_id: str,
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> None:
    progress["processed_chunks"] = processed_chunks
    progress["current_chunk_id"] = current_chunk_id
    progress["accepted_claim_count"] = len(accepted)
    progress["rejected_claim_count"] = len(rejected)
    write_json(path, progress)
