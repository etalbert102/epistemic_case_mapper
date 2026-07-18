from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output


SOURCE_INTAKE_FILTER_SCHEMA = "source_intake_filter_report_v1"


class ModelSourceJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    relevance: str = "unknown"
    trust_concern: str = "unknown"
    recommended_action: str = "include_with_caution"
    rationale: str = ""
    flags: list[str] = Field(default_factory=list)


class ModelSourceJudgmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    judgments: list[ModelSourceJudgment] = Field(default_factory=list)


@dataclass(frozen=True)
class SourceIntakeFilterResult:
    report: dict[str, Any]
    json_path: Path
    markdown_path: Path
    included_docs: tuple[Path, ...]
    excluded_docs: tuple[Path, ...]


def run_source_intake_filter(
    *,
    question: str,
    doc_paths: list[Path],
    backend: str = "prompt",
    output_dir: str | Path,
    backend_timeout: int | None = 60,
    backend_retries: int = 0,
    exclude_flagged: bool = False,
) -> SourceIntakeFilterResult:
    if not question.strip():
        raise ValueError("question is required")
    if not doc_paths:
        raise ValueError("at least one document path is required")
    if backend_timeout is not None and backend_timeout < 1:
        raise ValueError("backend_timeout must be positive")
    if backend_retries < 0:
        raise ValueError("backend_retries must be nonnegative")
    packets = [_document_packet(path, question=question) for path in doc_paths]
    model_report = _model_judgment_report(
        question=question,
        packets=packets,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    report = _combined_filter_report(
        question=question,
        packets=packets,
        model_report=model_report,
        backend=backend,
        exclude_flagged=exclude_flagged,
    )
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "source_intake_filter.json"
    markdown_path = output_path / "SOURCE_INTAKE_FILTER.md"
    write_json(json_path, report)
    write_markdown(markdown_path, render_source_intake_filter_markdown(report))
    included = tuple(Path(row["path"]) for row in report["sources"] if row["final_action"] != "exclude")
    excluded = tuple(Path(row["path"]) for row in report["sources"] if row["final_action"] == "exclude")
    return SourceIntakeFilterResult(
        report=report,
        json_path=json_path,
        markdown_path=markdown_path,
        included_docs=included,
        excluded_docs=excluded,
    )


def render_source_intake_filter_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Source Intake Filter",
        "",
        f"Status: `{report.get('status', 'unknown')}`",
        "",
        f"Question: {report.get('question', '')}",
        "",
        "This optional first-phase filter combines deterministic document signals with model judgment when a live backend is available. It is an intake screen, not a final source-quality adjudication.",
        "",
        "## Summary",
        "",
        f"- Sources checked: `{report.get('source_count', 0)}`",
        f"- Included: `{report.get('included_count', 0)}`",
        f"- Flagged for exclusion: `{report.get('excluded_count', 0)}`",
        f"- Backend: `{report.get('backend', 'unknown')}`",
        f"- Mode: `{report.get('mode', 'report_only')}`",
        "",
        "## Source Decisions",
        "",
        "| Source | Action | Deterministic flags | Model flags | Rationale |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report.get("sources", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(str(row.get("display_name") or row.get("path") or "")),
                    _md_cell(str(row.get("final_action") or "")),
                    _md_cell(", ".join(_string_list(row.get("deterministic_flags"))) or "-"),
                    _md_cell(", ".join(_string_list(row.get("model_flags"))) or "-"),
                    _md_cell(str(row.get("rationale") or "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Use Guidance",
            "",
            "- `include`: no major intake concern found.",
            "- `include_with_caution`: usable, but check the listed concerns before relying on it.",
            "- `route_to_appendix`: keep available for traceability, but avoid making it load-bearing without review.",
            "- `exclude`: do not feed this source into the main pipeline unless a human overrides the filter.",
        ]
    )
    return "\n".join(lines) + "\n"


def _document_packet(path: Path, *, question: str) -> dict[str, Any]:
    expanded = path.expanduser()
    resolved = expanded.resolve() if expanded.exists() else expanded
    text = _read_text_lossy(resolved)
    flags = _deterministic_flags(path=resolved, text=text, question=question)
    return {
        "path": str(path),
        "resolved_path": str(resolved),
        "display_name": resolved.name,
        "exists": resolved.exists(),
        "is_file": resolved.is_file(),
        "suffix": resolved.suffix.lower(),
        "byte_count": resolved.stat().st_size if resolved.exists() and resolved.is_file() else 0,
        "char_count": len(text),
        "question_term_overlap": _question_overlap(question, text),
        "deterministic_flags": flags,
        "deterministic_action": _deterministic_action(flags),
        "excerpt": _source_excerpt(text),
    }


def _read_text_lossy(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _deterministic_flags(*, path: Path, text: str, question: str) -> list[str]:
    flags: list[str] = []
    if not path.exists():
        flags.append("missing_file")
    elif not path.is_file():
        flags.append("not_a_file")
    if path.suffix.lower() not in {"", ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml"}:
        flags.append("unusual_extension")
    if not text.strip():
        flags.append("empty_or_unreadable")
    elif len(text.strip()) < 120:
        flags.append("very_short_text")
    if text and text.count("\ufffd") / max(1, len(text)) > 0.01:
        flags.append("encoding_replacement_noise")
    if text and _boilerplate_ratio(text) > 0.45:
        flags.append("possible_boilerplate_or_navigation_text")
    overlap = _question_overlap(question, text)
    if text.strip() and overlap == 0:
        flags.append("no_question_term_overlap")
    elif text.strip() and overlap <= 1:
        flags.append("low_question_term_overlap")
    return _dedupe(flags)


def _deterministic_action(flags: list[str]) -> str:
    blocking = {"missing_file", "not_a_file", "empty_or_unreadable"}
    if blocking & set(flags):
        return "exclude"
    if "no_question_term_overlap" in flags or "encoding_replacement_noise" in flags:
        return "route_to_appendix"
    if flags:
        return "include_with_caution"
    return "include"


def _model_judgment_report(
    *,
    question: str,
    packets: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    if backend.strip() == "prompt":
        return {
            "schema_id": "source_intake_model_judgment_report_v1",
            "status": "prompt_backend_skipped",
            "backend": backend,
            "prompt": _source_filter_prompt(question, packets),
            "raw": "",
            "judgments": [],
            "issues": [],
        }
    prompt = _source_filter_prompt(question, packets)
    try:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            response_schema=_source_filter_schema(),
        )
    except RuntimeError as exc:
        return {
            "schema_id": "source_intake_model_judgment_report_v1",
            "status": "backend_error",
            "backend": backend,
            "prompt": prompt,
            "raw": "",
            "judgments": [],
            "issues": [str(exc)],
        }
    payload = _parse_model_json(result.text)
    try:
        parsed = ModelSourceJudgmentOutput.model_validate(payload).model_dump()
    except ValidationError as exc:
        return {
            "schema_id": "source_intake_model_judgment_report_v1",
            "status": "schema_invalid",
            "backend": backend,
            "prompt": prompt,
            "raw": result.text,
            "judgments": [],
            "issues": [str(exc)],
        }
    return {
        "schema_id": "source_intake_model_judgment_report_v1",
        "status": "accepted",
        "backend": backend,
        "prompt": prompt,
        "raw": result.text,
        "judgments": parsed["judgments"],
        "issues": [],
    }


def _combined_filter_report(
    *,
    question: str,
    packets: list[dict[str, Any]],
    model_report: dict[str, Any],
    backend: str,
    exclude_flagged: bool,
) -> dict[str, Any]:
    model_by_path = {
        _path_key(str(row.get("source_path") or "")): row
        for row in model_report.get("judgments", [])
        if isinstance(row, dict)
    }
    rows = []
    for packet in packets:
        model = model_by_path.get(_path_key(str(packet.get("path") or ""))) or model_by_path.get(_path_key(str(packet.get("resolved_path") or ""))) or {}
        rows.append(_combined_source_row(packet, model, exclude_flagged=exclude_flagged))
    excluded = [row for row in rows if row["final_action"] == "exclude"]
    issues = [
        *(["all_sources_excluded"] if rows and len(excluded) == len(rows) else []),
        *[f"model_judgment:{issue}" for issue in _string_list(model_report.get("issues"))[:10]],
    ]
    return {
        "schema_id": SOURCE_INTAKE_FILTER_SCHEMA,
        "status": "warning" if excluded or issues else "ready",
        "question": question,
        "backend": backend,
        "mode": "exclude_flagged" if exclude_flagged else "report_only",
        "source_count": len(rows),
        "included_count": len(rows) - len(excluded),
        "excluded_count": len(excluded),
        "sources": rows,
        "model_judgment_report": {
            key: model_report.get(key)
            for key in ("schema_id", "status", "backend", "prompt", "raw", "issues")
        },
        "issues": issues,
    }


def _combined_source_row(packet: dict[str, Any], model: dict[str, Any], *, exclude_flagged: bool) -> dict[str, Any]:
    deterministic_action = str(packet.get("deterministic_action") or "include_with_caution")
    model_action = _normalize_model_action(str(model.get("recommended_action") or ""))
    recommended = _combined_action(deterministic_action, model_action)
    final = recommended if exclude_flagged or deterministic_action == "exclude" else _report_only_action(recommended)
    return {
        "path": packet.get("path"),
        "resolved_path": packet.get("resolved_path"),
        "display_name": packet.get("display_name"),
        "deterministic_action": deterministic_action,
        "model_action": model_action or "not_run",
        "recommended_action": recommended,
        "final_action": final,
        "deterministic_flags": packet.get("deterministic_flags", []),
        "model_flags": _string_list(model.get("flags")),
        "model_relevance": str(model.get("relevance") or "not_run"),
        "model_trust_concern": str(model.get("trust_concern") or "not_run"),
        "question_term_overlap": packet.get("question_term_overlap"),
        "char_count": packet.get("char_count"),
        "rationale": _combined_rationale(packet, model, recommended, final),
    }


def _combined_action(deterministic_action: str, model_action: str) -> str:
    order = {"include": 0, "include_with_caution": 1, "route_to_appendix": 2, "exclude": 3}
    candidates = [deterministic_action if deterministic_action in order else "include_with_caution"]
    if model_action in order:
        candidates.append(model_action)
    return max(candidates, key=lambda action: order[action])


def _report_only_action(recommended: str) -> str:
    return "route_to_appendix" if recommended == "exclude" else recommended


def _combined_rationale(packet: dict[str, Any], model: dict[str, Any], recommended: str, final: str) -> str:
    parts = []
    flags = _string_list(packet.get("deterministic_flags"))
    if flags:
        parts.append("deterministic flags: " + ", ".join(flags[:5]))
    if model.get("rationale"):
        parts.append(str(model["rationale"]))
    if recommended == "exclude" and final != "exclude":
        parts.append("report-only mode kept the source out of automatic exclusion")
    return "; ".join(parts) or "no intake concern found"


def _source_filter_prompt(question: str, packets: list[dict[str, Any]]) -> str:
    compact = [
        {
            "source_path": packet["path"],
            "display_name": packet["display_name"],
            "deterministic_flags": packet["deterministic_flags"],
            "question_term_overlap": packet["question_term_overlap"],
            "char_count": packet["char_count"],
            "excerpt": packet["excerpt"],
        }
        for packet in packets
    ]
    contract = {
        "judgments": [
            {
                "source_path": "exact source_path from input",
                "relevance": "high | medium | low | irrelevant | unknown",
                "trust_concern": "low | medium | high | unknown",
                "recommended_action": "include | include_with_caution | route_to_appendix | exclude",
                "rationale": "short reason grounded in the provided excerpt and flags",
                "flags": ["off_question", "untrustworthy", "thin_source", "needs_human_review"],
            }
        ]
    }
    return (
        "You are screening source documents before they enter an epistemic mapping pipeline.\n"
        "The goal is to avoid poisoning the full pipeline with sources that are likely off-question, unreadable, duplicative boilerplate, or too untrustworthy to use without review.\n"
        "Use only the source excerpts and deterministic flags below. Mark uncertainty explicitly.\n"
        "Prefer include_with_caution over exclude unless the source is clearly irrelevant or unusable from the supplied evidence.\n"
        "Return strict JSON matching this shape:\n"
        f"{json.dumps(contract, indent=2)}\n\n"
        f"Decision question: {question}\n\n"
        "Source packets:\n"
        f"{json.dumps(compact, indent=2, ensure_ascii=False)}\n"
    )


def _source_filter_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "judgments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_path": {"type": "string"},
                        "relevance": {"type": "string"},
                        "trust_concern": {"type": "string"},
                        "recommended_action": {"type": "string"},
                        "rationale": {"type": "string"},
                        "flags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["source_path", "relevance", "trust_concern", "recommended_action", "rationale", "flags"],
                },
            }
        },
        "required": ["judgments"],
    }


def _parse_model_json(raw: str) -> Any:
    text = canonical_json_output(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _source_excerpt(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= 2200:
        return cleaned
    return cleaned[:1100].rstrip() + "\n...\n" + cleaned[-900:].lstrip()


def _question_overlap(question: str, text: str) -> int:
    return len(_content_terms(question) & _content_terms(text))


def _content_terms(text: str) -> set[str]:
    stop = {
        "about", "after", "also", "because", "between", "could", "from", "have", "into",
        "more", "should", "than", "that", "their", "there", "these", "this", "what",
        "when", "where", "which", "with", "would",
    }
    return {token for token in re.findall(r"[a-z0-9]{4,}", str(text).lower()) if token not in stop}


def _boilerplate_ratio(text: str) -> float:
    lines = [line.strip().lower() for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    boilerplate = sum(1 for line in lines if line in {"home", "menu", "subscribe", "privacy policy", "cookie policy"} or len(line) < 5)
    return boilerplate / len(lines)


def _normalize_model_action(action: str) -> str:
    normalized = re.sub(r"[^a-z_]+", "_", str(action).strip().lower()).strip("_")
    aliases = {
        "include": "include",
        "use": "include",
        "include_with_caution": "include_with_caution",
        "caution": "include_with_caution",
        "route_to_appendix": "route_to_appendix",
        "appendix": "route_to_appendix",
        "exclude": "exclude",
        "remove": "exclude",
    }
    return aliases.get(normalized, "")


def _path_key(path: str) -> str:
    return str(Path(path)).strip().lower()


def _md_cell(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace("|", "\\|").strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
