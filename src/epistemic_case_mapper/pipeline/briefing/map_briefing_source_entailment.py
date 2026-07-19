from __future__ import annotations

from typing import Any


def collect_packet_source_evidence_by_source(
    packet: dict[str, Any],
    *,
    per_source_limit: int = 64,
) -> dict[str, list[str]]:
    """Collect source-specific evidence surfaces from nested packet rows."""
    evidence: dict[str, list[str]] = {}

    def add(source_ids: list[str], *values: Any) -> None:
        texts = [" ".join(str(value or "").split()) for value in values]
        for source_id in source_ids:
            bucket = evidence.setdefault(source_id, [])
            for text in texts:
                if text and text not in bucket and len(bucket) < per_source_limit:
                    bucket.append(text)

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        for excerpt in _list_value(value.get("source_excerpts")):
            if not isinstance(excerpt, dict):
                continue
            add(
                _source_ids(excerpt),
                _source_excerpt(excerpt),
            )
        source_ids = _source_ids(value)
        source_excerpt = _source_excerpt(value)
        if len(source_ids) == 1 and source_excerpt:
            add(
                source_ids,
                source_excerpt,
            )
        for nested in value.values():
            visit(nested)

    visit(packet)
    return {source_id: texts for source_id, texts in evidence.items() if texts}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _source_ids(row: dict[str, Any]) -> list[str]:
    values = [*_list_value(row.get("source_ids")), row.get("source_id")]
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _source_excerpt(row: dict[str, Any]) -> str:
    return str(
        row.get("source_excerpt")
        or row.get("quote")
        or row.get("quoted_text")
        or row.get("excerpt")
        or ""
    ).strip()
