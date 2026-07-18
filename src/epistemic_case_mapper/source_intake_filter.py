from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output


SOURCE_INTAKE_FILTER_SCHEMA = "source_intake_filter_report_v1"

URL_RE = re.compile(r"https?://[^\s<>)\]\"']+", re.IGNORECASE)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
PMID_RE = re.compile(r"\bPMID[:\s]+([0-9]{5,9})\b", re.IGNORECASE)
ARXIV_RE = re.compile(r"\barXiv[:\s]+([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)\b", re.IGNORECASE)
AUTHOR_YEAR_RE = re.compile(r"\(([A-Z][A-Za-z'`-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'`-]+)?),?\s+(19|20)\d{2}[a-z]?\)")
BRACKET_CITATION_RE = re.compile(r"\[(?:\d{1,3}(?:\s*[-,;]\s*\d{1,3})*)\]")
REFERENCE_HEADING_RE = re.compile(
    r"(?im)^\s*(references|bibliography|works cited|sources|notes|endnotes|footnotes|literature cited)\s*$"
)
DATE_RE = re.compile(
    r"\b(?:19|20)\d{2}\b|"
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)


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
    check_links: bool = False,
    max_links_per_source: int = 25,
    link_timeout: float = 5.0,
) -> SourceIntakeFilterResult:
    if not question.strip():
        raise ValueError("question is required")
    if not doc_paths:
        raise ValueError("at least one document path is required")
    if backend_timeout is not None and backend_timeout < 1:
        raise ValueError("backend_timeout must be positive")
    if backend_retries < 0:
        raise ValueError("backend_retries must be nonnegative")
    if max_links_per_source < 0:
        raise ValueError("max_links_per_source must be nonnegative")
    if link_timeout <= 0:
        raise ValueError("link_timeout must be positive")
    packets = [
        _document_packet(
            path,
            question=question,
            check_links=check_links,
            max_links=max_links_per_source,
            link_timeout=link_timeout,
        )
        for path in doc_paths
    ]
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
        f"- Live link checks: `{report.get('link_check_mode', 'off')}`",
        "",
        "## Source Decisions",
        "",
        "| Source | Action | Flags | Citation / link signals | Rationale |",
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
                    _md_cell(_traceability_summary(row)),
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
            "",
            "The citation and link checks are deterministic intake warnings. They identify traceability risks such as missing reference sections, sparse citation markers, unresolved persistent identifiers, and broken outbound URLs when live link checking is enabled. They do not decide whether a source is substantively true.",
        ]
    )
    return "\n".join(lines) + "\n"


def _document_packet(
    path: Path,
    *,
    question: str,
    check_links: bool = False,
    max_links: int = 25,
    link_timeout: float = 5.0,
) -> dict[str, Any]:
    expanded = path.expanduser()
    resolved = expanded.resolve() if expanded.exists() else expanded
    text = _read_text_lossy(resolved)
    citation_profile = _citation_profile(text)
    link_profile = _link_profile(text, check_links=check_links, max_links=max_links, timeout=link_timeout)
    metadata_profile = _metadata_profile(path=resolved, text=text, citation_profile=citation_profile)
    flags = _deterministic_flags(
        path=resolved,
        text=text,
        question=question,
        citation_profile=citation_profile,
        link_profile=link_profile,
        metadata_profile=metadata_profile,
    )
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
        "source_type": metadata_profile["source_type"],
        "citation_profile": citation_profile,
        "link_profile": link_profile,
        "metadata_profile": metadata_profile,
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


def _citation_profile(text: str) -> dict[str, Any]:
    words = re.findall(r"\b\w+\b", text)
    word_count = len(words)
    urls = _extract_urls(text)
    dois = _extract_dois(text)
    pmids = PMID_RE.findall(text)
    arxiv_ids = ARXIV_RE.findall(text)
    author_year = AUTHOR_YEAR_RE.findall(text)
    bracket_citations = BRACKET_CITATION_RE.findall(text)
    footnote_markers = re.findall(r"(?m)^\s*(?:\[\d+\]|\d+[.)])\s+\S+", text)
    likely_citations = (
        len(dois)
        + len(pmids)
        + len(arxiv_ids)
        + len(author_year)
        + len(bracket_citations)
        + len(footnote_markers)
        + len(urls)
    )
    malformed_doi_like = [
        match
        for match in re.findall(r"\b10\.\d{4,9}/\S+", text, flags=re.IGNORECASE)
        if _clean_doi(match) not in dois
    ]
    numeric_sentences = _numeric_sentences_without_citation(text)
    return {
        "word_count": word_count,
        "has_reference_section": bool(REFERENCE_HEADING_RE.search(text)),
        "url_count": len(urls),
        "doi_count": len(dois),
        "pmid_count": len(pmids),
        "arxiv_count": len(arxiv_ids),
        "author_year_count": len(author_year),
        "bracket_citation_count": len(bracket_citations),
        "footnote_marker_count": len(footnote_markers),
        "likely_citation_count": likely_citations,
        "citation_density_per_1000_words": round((likely_citations / max(1, word_count)) * 1000, 2),
        "persistent_identifier_count": len(dois) + len(pmids) + len(arxiv_ids),
        "malformed_doi_like_count": len(malformed_doi_like),
        "sample_dois": dois[:8],
        "numeric_sentence_without_citation_count": len(numeric_sentences),
        "numeric_sentence_without_citation_samples": numeric_sentences[:5],
    }


def _link_profile(text: str, *, check_links: bool, max_links: int, timeout: float) -> dict[str, Any]:
    urls = _extract_urls(text)
    unique_urls = _dedupe(urls)
    details: list[dict[str, Any]] = []
    checked_urls = unique_urls[:max_links] if check_links and max_links else []
    for url in checked_urls:
        details.append(_check_url(url, timeout=timeout))
    broken = [row for row in details if row["status_class"] in {"broken", "error"}]
    redirected = [row for row in details if row.get("redirected")]
    return {
        "checked": bool(check_links),
        "url_count": len(unique_urls),
        "checked_count": len(details),
        "unchecked_count": max(0, len(unique_urls) - len(details)),
        "ok_count": sum(1 for row in details if row["status_class"] == "ok"),
        "redirect_count": len(redirected),
        "broken_count": len(broken),
        "broken_ratio": round(len(broken) / max(1, len(details)), 3) if details else 0.0,
        "sample_urls": unique_urls[:10],
        "details": details,
    }


def _metadata_profile(path: Path, text: str, citation_profile: dict[str, Any]) -> dict[str, Any]:
    lowered = text.lower()
    retraction_terms = [
        term
        for term in ("retracted", "retraction", "withdrawn", "expression of concern", "correction notice")
        if term in lowered
    ]
    return {
        "source_type": _infer_source_type(path, text, citation_profile),
        "publication_date_candidates": _date_candidates(text),
        "has_named_author_hint": bool(re.search(r"(?im)^\s*(by|author[s]?)\s*[:\-]\s+\S+", text)),
        "has_publisher_hint": bool(re.search(r"(?im)^\s*(publisher|published by|organization|institution)\s*[:\-]\s+\S+", text)),
        "retraction_terms_detected": retraction_terms[:5],
    }


def _extract_urls(text: str) -> list[str]:
    return [_clean_url(match.group(0)) for match in URL_RE.finditer(text) if _clean_url(match.group(0))]


def _extract_dois(text: str) -> list[str]:
    return _dedupe([_clean_doi(match.group(0)) for match in DOI_RE.finditer(text) if _clean_doi(match.group(0))])


def _clean_url(url: str) -> str:
    cleaned = str(url).strip().rstrip(".,;:!?)]}\"'")
    return cleaned if cleaned.startswith(("http://", "https://")) else ""


def _clean_doi(doi: str) -> str:
    return str(doi).strip().rstrip(".,;:!?)]}\"'").lower()


def _check_url(url: str, *, timeout: float) -> dict[str, Any]:
    for method in ("HEAD", "GET"):
        try:
            req = request.Request(
                url,
                method=method,
                headers={"User-Agent": "epistemic-case-mapper-source-intake/0.1"},
            )
            with request.urlopen(req, timeout=timeout) as response:
                status = int(response.status)
                final_url = response.geturl()
                return {
                    "url": url,
                    "status": status,
                    "status_class": _http_status_class(status),
                    "final_url": final_url,
                    "redirected": final_url != url,
                    "method": method,
                }
        except error.HTTPError as exc:
            if method == "HEAD" and exc.code in {403, 405, 406, 501}:
                continue
            return {
                "url": url,
                "status": int(exc.code),
                "status_class": _http_status_class(int(exc.code)),
                "final_url": url,
                "redirected": False,
                "method": method,
                "error": str(exc.reason),
            }
        except (TimeoutError, OSError, ValueError, error.URLError) as exc:
            if method == "HEAD":
                continue
            return {
                "url": url,
                "status": None,
                "status_class": "error",
                "final_url": url,
                "redirected": False,
                "method": method,
                "error": str(exc),
            }
    return {
        "url": url,
        "status": None,
        "status_class": "error",
        "final_url": url,
        "redirected": False,
        "method": "GET",
        "error": "unresolved",
    }


def _http_status_class(status: int) -> str:
    if 200 <= status < 300:
        return "ok"
    if 300 <= status < 400:
        return "redirect"
    if status in {404, 410} or 400 <= status < 600:
        return "broken"
    return "unknown"


def _numeric_sentences_without_citation(text: str) -> list[str]:
    samples: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip()):
        if not re.search(r"\d", sentence):
            continue
        if DOI_RE.search(sentence) or URL_RE.search(sentence) or BRACKET_CITATION_RE.search(sentence):
            continue
        if AUTHOR_YEAR_RE.search(sentence) or PMID_RE.search(sentence) or ARXIV_RE.search(sentence):
            continue
        samples.append(sentence[:220])
    return samples


def _infer_source_type(path: Path, text: str, citation_profile: dict[str, Any]) -> str:
    suffix = path.suffix.lower()
    lowered = text.lower()
    if citation_profile.get("pmid_count"):
        return "biomedical_scholarly_work"
    if citation_profile.get("arxiv_count") or "arxiv.org" in lowered:
        return "preprint_or_scholarly_work"
    if citation_profile.get("doi_count") and citation_profile.get("has_reference_section"):
        return "scholarly_work"
    if suffix in {".csv", ".tsv", ".json", ".yaml", ".yml"}:
        return "dataset_or_structured_data"
    if "press release" in lowered:
        return "press_release"
    if any(token in lowered for token in ("government", ".gov", "department of", "agency")):
        return "government_or_institutional_report"
    if "http" in lowered or suffix in {".html", ".htm"}:
        return "web_page"
    if citation_profile.get("has_reference_section"):
        return "report_or_review"
    return "document"


def _date_candidates(text: str) -> list[str]:
    return _dedupe([match.group(0) for match in DATE_RE.finditer(text)])[:8]


def _deterministic_flags(
    *,
    path: Path,
    text: str,
    question: str,
    citation_profile: dict[str, Any],
    link_profile: dict[str, Any],
    metadata_profile: dict[str, Any],
) -> list[str]:
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
    if metadata_profile.get("source_type") == "web_page" and not metadata_profile.get("publication_date_candidates"):
        flags.append("web_source_no_detected_date")
    if text.strip() and not citation_profile.get("has_reference_section") and citation_profile.get("likely_citation_count", 0) == 0:
        flags.append("no_detected_citations")
    elif text.strip() and citation_profile.get("citation_density_per_1000_words", 0.0) < 1.0:
        flags.append("very_low_citation_density")
    if citation_profile.get("numeric_sentence_without_citation_count", 0) >= 3:
        flags.append("numbers_without_nearby_citations")
    if citation_profile.get("malformed_doi_like_count", 0):
        flags.append("malformed_doi_like_strings")
    if link_profile.get("url_count", 0) and not link_profile.get("checked"):
        flags.append("outbound_links_not_checked")
    if link_profile.get("broken_count", 0):
        flags.append("broken_outbound_links")
    if link_profile.get("checked_count", 0) >= 3 and link_profile.get("broken_ratio", 0.0) >= 0.25:
        flags.append("high_broken_link_ratio")
    if metadata_profile.get("retraction_terms_detected"):
        flags.append("possible_retraction_or_correction_marker")
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
    strong = {
        "no_question_term_overlap",
        "encoding_replacement_noise",
        "broken_outbound_links",
        "high_broken_link_ratio",
        "possible_retraction_or_correction_marker",
    }
    if strong & set(flags):
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
    cautioned = [row for row in rows if row["final_action"] != "include"]
    issues = [
        *(["all_sources_excluded"] if rows and len(excluded) == len(rows) else []),
        *[f"model_judgment:{issue}" for issue in _string_list(model_report.get("issues"))[:10]],
    ]
    return {
        "schema_id": SOURCE_INTAKE_FILTER_SCHEMA,
        "status": "warning" if cautioned or issues else "ready",
        "question": question,
        "backend": backend,
        "mode": "exclude_flagged" if exclude_flagged else "report_only",
        "link_check_mode": _link_check_mode(packets),
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
        "source_type": packet.get("source_type"),
        "citation_profile": packet.get("citation_profile", {}),
        "link_profile": packet.get("link_profile", {}),
        "metadata_profile": packet.get("metadata_profile", {}),
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


def _link_check_mode(packets: list[dict[str, Any]]) -> str:
    profiles = [packet.get("link_profile", {}) for packet in packets]
    if any(isinstance(profile, dict) and profile.get("checked") for profile in profiles):
        checked = sum(int(profile.get("checked_count", 0)) for profile in profiles if isinstance(profile, dict))
        return f"checked_{checked}_urls"
    if any(isinstance(profile, dict) and profile.get("url_count", 0) for profile in profiles):
        return "extracted_only"
    return "no_urls_detected"


def _traceability_summary(row: dict[str, Any]) -> str:
    citations = row.get("citation_profile", {}) if isinstance(row.get("citation_profile"), dict) else {}
    links = row.get("link_profile", {}) if isinstance(row.get("link_profile"), dict) else {}
    bits = [
        f"type={row.get('source_type', 'unknown')}",
        f"citations={citations.get('likely_citation_count', 0)}",
        f"refs={'yes' if citations.get('has_reference_section') else 'no'}",
        f"ids={citations.get('persistent_identifier_count', 0)}",
        f"urls={links.get('url_count', 0)}",
    ]
    if links.get("checked"):
        bits.append(f"broken={links.get('broken_count', 0)}/{links.get('checked_count', 0)}")
    return ", ".join(bits)


def _compact_citation_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    keys = [
        "has_reference_section",
        "likely_citation_count",
        "citation_density_per_1000_words",
        "persistent_identifier_count",
        "doi_count",
        "url_count",
        "numeric_sentence_without_citation_count",
        "malformed_doi_like_count",
    ]
    return {key: profile.get(key) for key in keys}


def _compact_link_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    keys = ["checked", "url_count", "checked_count", "broken_count", "broken_ratio", "redirect_count", "unchecked_count"]
    return {key: profile.get(key) for key in keys}


def _compact_metadata_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    return {
        "source_type": profile.get("source_type"),
        "publication_date_candidates": profile.get("publication_date_candidates", [])[:3],
        "has_named_author_hint": profile.get("has_named_author_hint"),
        "has_publisher_hint": profile.get("has_publisher_hint"),
        "retraction_terms_detected": profile.get("retraction_terms_detected", []),
    }


def _source_filter_prompt(question: str, packets: list[dict[str, Any]]) -> str:
    compact = [
        {
            "source_path": packet["path"],
            "display_name": packet["display_name"],
            "deterministic_flags": packet["deterministic_flags"],
            "question_term_overlap": packet["question_term_overlap"],
            "char_count": packet["char_count"],
            "source_type": packet.get("source_type"),
            "citation_profile": _compact_citation_profile(packet.get("citation_profile", {})),
            "link_profile": _compact_link_profile(packet.get("link_profile", {})),
            "metadata_profile": _compact_metadata_profile(packet.get("metadata_profile", {})),
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
