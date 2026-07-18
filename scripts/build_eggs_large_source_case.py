#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import ssl
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib import error, parse, request
from xml.etree import ElementTree

from epistemic_case_mapper.io import write_yaml


DEFAULT_CASE_ID = "eggs_large_source_stress"
DEFAULT_TITLE = "Eggs and Health: Large Source Stress Case"
DEFAULT_QUESTION = (
    "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, "
    "or beneficial in dietary advice, especially with respect to cardiovascular risk?"
)
DEFAULT_TARGET_WORDS = 260_000
DEFAULT_RETMAX_PER_QUERY = 35
DEFAULT_MAX_ACCEPTED_PER_QUERY = 12
DEFAULT_MIN_WORDS = 1_000
NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ALLOW_INSECURE_TLS = False

DEFAULT_TOPIC_QUERIES = [
    '"egg consumption" AND cardiovascular',
    '"egg intake" AND cardiovascular',
    '"egg consumption" AND cholesterol',
    '"egg consumption" AND mortality',
    '"egg consumption" AND diabetes',
    '"dietary cholesterol" AND egg AND cardiovascular',
    '"dietary cholesterol" AND nutrition AND cardiovascular',
    '"egg" AND "diet quality" AND adults',
    '"egg" AND choline AND nutrition',
    '"egg" AND lutein AND nutrition',
    '"egg allergy" AND diet',
]


@dataclass(frozen=True)
class ArticleRecord:
    pmc_uid: str
    source_id: str
    title: str
    url: str
    authors: str | None
    publication_date: str | None
    source_type: str
    abstract: str
    text: str
    word_count: int
    acquisition_query: str
    raw_xml: str = ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _element_text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return _collapse_whitespace(" ".join(element.itertext()))


def _first_text(root: ElementTree.Element, names: Iterable[str]) -> str:
    wanted = set(names)
    for element in root.iter():
        if _local_name(element.tag) in wanted:
            text = _element_text(element)
            if text:
                return text
    return ""


def _article_meta(root: ElementTree.Element) -> ElementTree.Element | None:
    for element in root.iter():
        if _local_name(element.tag) == "article-meta":
            return element
    return None


def _article_body(root: ElementTree.Element) -> ElementTree.Element | None:
    for element in root.iter():
        if _local_name(element.tag) == "body":
            return element
    return None


def _pmc_uid(root: ElementTree.Element, fallback_uid: str) -> str:
    for element in root.iter():
        if _local_name(element.tag) != "article-id":
            continue
        if element.attrib.get("pub-id-type") == "pmc":
            text = _element_text(element)
            if text:
                return re.sub(r"^PMC", "", text, flags=re.IGNORECASE)
    return fallback_uid


def _publication_date(meta: ElementTree.Element | None) -> str | None:
    if meta is None:
        return None
    for pub_date in meta.iter():
        if _local_name(pub_date.tag) != "pub-date":
            continue
        parts: dict[str, str] = {}
        for child in pub_date:
            local = _local_name(child.tag)
            if local in {"year", "month", "day"}:
                text = _element_text(child)
                if text:
                    parts[local] = text.zfill(2) if local in {"month", "day"} else text
        if "year" in parts:
            date_parts = [parts["year"]]
            if "month" in parts:
                date_parts.append(parts["month"])
            if "day" in parts:
                date_parts.append(parts["day"])
            return "-".join(date_parts)
    return None


def _authors(meta: ElementTree.Element | None, limit: int = 4) -> str | None:
    if meta is None:
        return None
    names: list[str] = []
    for contrib in meta.iter():
        if _local_name(contrib.tag) != "contrib" or contrib.attrib.get("contrib-type") != "author":
            continue
        surname = ""
        given = ""
        collab = ""
        for child in contrib.iter():
            local = _local_name(child.tag)
            if local == "surname":
                surname = _element_text(child)
            elif local == "given-names":
                given = _element_text(child)
            elif local == "collab":
                collab = _element_text(child)
        if collab:
            names.append(collab)
        elif surname:
            initials = "".join(part[0] for part in given.split() if part)
            names.append(f"{surname} {initials}".strip())
    if not names:
        return None
    if len(names) > limit:
        return ", ".join(names[:limit]) + " et al."
    return ", ".join(names)


def _source_type(root: ElementTree.Element, title: str) -> str:
    pub_types = []
    for element in root.iter():
        if _local_name(element.tag) == "article-categories":
            pub_types.extend(
                _element_text(child).lower()
                for child in element.iter()
                if _local_name(child.tag) in {"subject", "article-type"}
            )
    label = " ".join(pub_types + [title.lower()])
    if "systematic review" in label or "meta-analysis" in label:
        return "peer_reviewed_review"
    if "randomized" in label or "trial" in label:
        return "peer_reviewed_trial"
    if "cohort" in label:
        return "peer_reviewed_cohort_study"
    if "review" in label:
        return "peer_reviewed_review"
    return "peer_reviewed_article"


def _body_blocks(body: ElementTree.Element | None) -> list[str]:
    if body is None:
        return []
    blocks: list[str] = []
    for element in body.iter():
        local = _local_name(element.tag)
        if local == "title":
            text = _element_text(element)
            if text:
                blocks.append(f"\n## {text}\n")
        elif local == "p":
            text = _element_text(element)
            if text:
                blocks.append(text)
        elif local == "caption":
            text = _element_text(element)
            if text:
                blocks.append(f"Table or figure caption: {text}")
    return blocks


def extract_article_record(xml_text: str, fallback_uid: str, acquisition_query: str) -> ArticleRecord:
    root = ElementTree.fromstring(xml_text)
    meta = _article_meta(root)
    uid = _pmc_uid(root, fallback_uid=fallback_uid)
    title = _first_text(root, ["article-title"]) or f"PMC{uid}"
    abstract = _first_text(root, ["abstract"])
    body = _article_body(root)
    blocks = [f"# {title}"]
    if abstract:
        blocks.append("## Abstract")
        blocks.append(abstract)
    blocks.extend(_body_blocks(body))
    text = "\n\n".join(block for block in blocks if block).strip() + "\n"
    word_count = len(re.findall(r"\b\w+\b", text))
    return ArticleRecord(
        pmc_uid=uid,
        source_id=f"pmc{uid}",
        title=title,
        url=f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{uid}/",
        authors=_authors(meta),
        publication_date=_publication_date(meta),
        source_type=_source_type(root, title),
        abstract=abstract,
        text=text,
        word_count=word_count,
        acquisition_query=acquisition_query,
        raw_xml=xml_text,
    )


def _ncbi_url(endpoint: str, params: dict[str, str | int]) -> str:
    email = os.environ.get("NCBI_EMAIL", "anonymous@example.com")
    api_key = os.environ.get("NCBI_API_KEY")
    merged: dict[str, str | int] = {"tool": "epistemic_case_mapper", "email": email, **params}
    if api_key:
        merged["api_key"] = api_key
    return f"{NCBI_BASE_URL}/{endpoint}?{parse.urlencode(merged)}"


def _fetch_url(url: str, timeout_seconds: int = 45) -> str:
    req = request.Request(url, headers={"User-Agent": "epistemic-case-mapper/large-eggs-source-builder"})
    context = ssl._create_unverified_context() if ALLOW_INSECURE_TLS else None
    with request.urlopen(req, timeout=timeout_seconds, context=context) as response:
        return response.read().decode("utf-8", errors="replace")


def search_pmc(query: str, retmax: int) -> list[str]:
    url = _ncbi_url(
        "esearch.fcgi",
        {
            "db": "pmc",
            "term": query,
            "retmax": retmax,
            "retmode": "json",
            "sort": "relevance",
        },
    )
    payload = json.loads(_fetch_url(url))
    return list(payload.get("esearchresult", {}).get("idlist", []))


def fetch_pmc_xml(uid: str) -> str:
    url = _ncbi_url("efetch.fcgi", {"db": "pmc", "id": uid, "retmode": "xml"})
    return _fetch_url(url)


def _source_manifest_entry(record: ArticleRecord, text_path: Path, retrieval_date: str) -> dict[str, object]:
    excerpt = record.abstract or record.text
    return {
        "source_id": record.source_id,
        "title": record.title,
        "url": record.url,
        "author": record.authors,
        "publication_date": record.publication_date,
        "retrieval_date": retrieval_date,
        "source_type": record.source_type,
        "path": text_path.as_posix(),
        "excerpt": _collapse_whitespace(excerpt)[:360],
        "provenance_level": "peer_reviewed",
        "evidence_role": "broad_acquired_source",
        "limitations": [
            "Acquired by a broad PMC query for stress testing; source relevance is not manually curated.",
            "May be tangential to the specific healthy-adult egg guidance question.",
        ],
        "notes": f"PMC full-text XML acquired from query: {record.acquisition_query}",
    }


def _inventory_markdown(records: list[ArticleRecord], skipped: list[dict[str, str]], total_words: int) -> str:
    rows = [
        "# Eggs Large Source Stress Case Inventory",
        "",
        "This corpus was acquired from PMC full-text records using broad egg, dietary cholesterol, and nutrition queries. It intentionally includes some tangentially relevant material so the pipeline can be tested against a noisy real source set.",
        "",
        f"- Source count: {len(records)}",
        f"- Total extracted words: {total_words:,}",
        f"- Estimated tokens: {int(total_words * 1.33):,}",
        "",
        "| Source ID | Words | Type | Title | Query |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for record in records:
        title = record.title.replace("|", "\\|")
        query = record.acquisition_query.replace("|", "\\|")
        rows.append(f"| {record.source_id} | {record.word_count:,} | {record.source_type} | [{title}]({record.url}) | `{query}` |")
    if skipped:
        rows.extend(["", "## Skipped Records", "", "| UID | Reason |", "| --- | --- |"])
        for item in skipped:
            rows.append(f"| {item['uid']} | {item['reason'].replace('|', '/')} |")
    return "\n".join(rows) + "\n"


def _corpus_report(records: list[ArticleRecord], skipped: list[dict[str, str]], total_words: int, target_words: int) -> str:
    queries = sorted({record.acquisition_query for record in records})
    lines = [
        "# Eggs Large Source Stress Case Report",
        "",
        "Status: `generated-source-corpus`",
        "",
        "Purpose: create a legitimate large egg-related source set that a single raw-context synthesis pass should struggle to absorb, while preserving source provenance for staged processing.",
        "",
        f"- Source count: {len(records)}",
        f"- Extracted words: {total_words:,}",
        f"- Estimated tokens: {int(total_words * 1.33):,}",
        f"- Target words: {target_words:,}",
        f"- Retrieval date: {date.today().isoformat()}",
        f"- Skipped records: {len(skipped)}",
        "",
        "## Acquisition Queries",
        "",
    ]
    lines.extend(f"- `{query}`" for query in queries)
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The corpus is deliberately broader than the curated eggs case. It should be used to test intake filtering, staged claim extraction, prioritization, and memo synthesis under realistic source overload. Because relevance is not manually curated, downstream artifacts should distinguish high-value decision evidence from tangential nutrition, allergy, or mechanism material.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_case_payload(case_id: str, records: list[ArticleRecord], root: Path, retrieval_date: str) -> dict[str, object]:
    sources: list[dict[str, object]] = []
    for record in records:
        text_path = root / "data" / "cases" / case_id / "sources" / "text" / f"{record.source_id}.txt"
        sources.append(_source_manifest_entry(record, text_path.relative_to(root), retrieval_date))
    return {
        "case_id": case_id,
        "title": DEFAULT_TITLE,
        "question": DEFAULT_QUESTION,
        "case_type": "large noisy source stress case",
        "evidence_mode": "source_grounded",
        "review_status": "draft",
        "status": "in_progress",
        "notes": [
            "Generated from live PMC source acquisition; not a manually curated evidence base.",
            "Includes directly and tangentially egg-, dietary-cholesterol-, and nutrition-related sources.",
            "Designed to exceed a 256k context-window-scale source corpus so staged processing can be demonstrated.",
        ],
        "sources": sources,
    }


def acquire_records(
    queries: list[str],
    retmax_per_query: int,
    max_accepted_per_query: int,
    target_words: int,
    min_words: int,
    sleep_seconds: float,
) -> tuple[list[ArticleRecord], list[dict[str, str]]]:
    seen: set[str] = set()
    records: list[ArticleRecord] = []
    skipped: list[dict[str, str]] = []
    total_words = 0
    for query in queries:
        print(f"[acquire] search query={query!r}", flush=True)
        try:
            ids = search_pmc(query, retmax_per_query)
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            print(f"[acquire] search failed query={query!r} reason={exc}", flush=True)
            skipped.append({"uid": f"query:{query}", "reason": f"search failed: {exc}"})
            continue
        time.sleep(sleep_seconds)
        accepted_for_query = 0
        for uid in ids:
            if uid in seen:
                continue
            seen.add(uid)
            if total_words >= target_words:
                break
            if accepted_for_query >= max_accepted_per_query:
                break
            print(f"[acquire] fetch PMC{uid}", flush=True)
            try:
                xml_text = fetch_pmc_xml(uid)
                record = extract_article_record(xml_text, fallback_uid=uid, acquisition_query=query)
            except (OSError, error.URLError, ElementTree.ParseError) as exc:
                print(f"[acquire] skipped PMC{uid} reason={exc}", flush=True)
                skipped.append({"uid": uid, "reason": f"fetch/parse failed: {exc}"})
                time.sleep(sleep_seconds)
                continue
            if record.word_count < min_words:
                print(f"[acquire] skipped PMC{uid} words={record.word_count:,} below min={min_words:,}", flush=True)
                skipped.append({"uid": uid, "reason": f"too short after extraction: {record.word_count} words"})
                time.sleep(sleep_seconds)
                continue
            records.append(record)
            accepted_for_query += 1
            total_words += record.word_count
            print(f"[acquire] accepted {record.source_id} words={record.word_count:,} total={total_words:,}", flush=True)
            time.sleep(sleep_seconds)
        if total_words >= target_words:
            break
    return records, skipped


def write_case(root: Path, case_id: str, records: list[ArticleRecord], skipped: list[dict[str, str]], target_words: int, force: bool) -> Path:
    case_dir = root / "data" / "cases" / case_id
    raw_dir = case_dir / "sources" / "raw"
    text_dir = case_dir / "sources" / "text"
    if case_dir.exists() and not force:
        raise SystemExit(f"{case_dir} already exists. Pass --force to replace generated files.")
    if case_dir.exists() and force:
        shutil.rmtree(case_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    retrieval_date = date.today().isoformat()
    total_words = sum(record.word_count for record in records)
    for record in records:
        raw_path = raw_dir / f"{record.source_id}.xml"
        text_path = text_dir / f"{record.source_id}.txt"
        raw_path.write_text(record.raw_xml, encoding="utf-8")
        text_path.write_text(record.text, encoding="utf-8")
    write_yaml(case_dir / "case.yaml", build_case_payload(case_id, records, root, retrieval_date))
    (case_dir / "sources" / "SOURCE_INVENTORY.md").write_text(
        _inventory_markdown(records, skipped, total_words),
        encoding="utf-8",
    )
    (case_dir / "CORPUS_REPORT.md").write_text(
        _corpus_report(records, skipped, total_words, target_words),
        encoding="utf-8",
    )
    return case_dir / "case.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire a large real PMC egg-related source corpus.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--case-id", default=DEFAULT_CASE_ID)
    parser.add_argument("--target-words", type=int, default=DEFAULT_TARGET_WORDS)
    parser.add_argument("--retmax-per-query", type=int, default=DEFAULT_RETMAX_PER_QUERY)
    parser.add_argument(
        "--max-accepted-per-query",
        type=int,
        default=DEFAULT_MAX_ACCEPTED_PER_QUERY,
        help="Maximum accepted full-text records per query before moving to the next topic.",
    )
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    parser.add_argument("--sleep-seconds", type=float, default=0.34)
    parser.add_argument("--query", action="append", dest="queries", help="Override/add a PMC query. Can be repeated.")
    parser.add_argument("--dry-run", action="store_true", help="Acquire and report without writing files.")
    parser.add_argument("--force", action="store_true", help="Overwrite generated case files.")
    parser.add_argument(
        "--insecure-tls",
        action="store_true",
        help="Disable TLS certificate verification for local environments with an intercepting/self-signed certificate.",
    )
    args = parser.parse_args()

    global ALLOW_INSECURE_TLS
    ALLOW_INSECURE_TLS = args.insecure_tls
    root = Path(args.repo_root).resolve()
    queries = args.queries or DEFAULT_TOPIC_QUERIES
    records, skipped = acquire_records(
        queries=queries,
        retmax_per_query=args.retmax_per_query,
        max_accepted_per_query=args.max_accepted_per_query,
        target_words=args.target_words,
        min_words=args.min_words,
        sleep_seconds=args.sleep_seconds,
    )
    total_words = sum(record.word_count for record in records)
    print(
        f"[summary] accepted={len(records)} skipped={len(skipped)} words={total_words:,} estimated_tokens={int(total_words * 1.33):,}",
        flush=True,
    )
    if args.dry_run:
        return 0
    case_path = write_case(root, args.case_id, records, skipped, args.target_words, args.force)
    print(f"[write] {case_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
