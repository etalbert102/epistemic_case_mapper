from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_markdown_quality import repair_markdown_structure
from epistemic_case_mapper.map_briefing_source_identity import common_source_prefix, preferred_source_display
from epistemic_case_mapper.map_briefing_text_cleanup import replace_internal_reader_phrases


def ensure_reader_memo_metadata(markdown: str, scaffold: dict[str, Any]) -> str:
    memo = repair_markdown_structure(markdown).strip()
    question = str(scaffold.get("question", "")).strip()
    if question:
        memo = remove_standalone_question_restatement(memo, question)
        memo = ensure_decision_question_line(memo, question)
    source_lines = cited_source_list_lines(memo, scaffold) or source_list_lines(scaffold)
    if source_lines:
        memo = _replace_sources_section(memo, source_lines)
    if question:
        memo = normalize_reader_memo_metadata_layout(memo, question)
    memo = replace_internal_reader_phrases(memo)
    memo = improve_reader_memo_readability(memo)
    if source_lines:
        memo = link_source_mentions(memo, scaffold)
    return _clean_memo_text(memo)


def decision_question_lines(scaffold: dict[str, Any]) -> list[str]:
    question = str(scaffold.get("question", "")).strip()
    if not question:
        return []
    return [f"**Decision question:** {question}", ""]


def ensure_decision_question_line(markdown: str, question: str) -> str:
    exact_line = f"**Decision question:** {question}"
    memo = _remove_decision_question_metadata_lines(str(markdown), exact_line=exact_line)
    if exact_line in memo:
        return memo
    metadata = exact_line + "\n\n"
    decision_heading = re.compile(r"^(## Decision Brief\s*\n+)", flags=re.MULTILINE)
    if decision_heading.search(memo):
        return decision_heading.sub(lambda match: match.group(1) + metadata, memo, count=1)
    first_heading = re.compile(r"^(#{1,3}\s+[^\n]+\n+)")
    if first_heading.search(memo):
        return first_heading.sub(lambda match: match.group(1) + metadata, memo, count=1)
    return metadata + memo.lstrip()


def _remove_decision_question_metadata_lines(markdown: str, *, exact_line: str) -> str:
    lines = []
    for line in str(markdown).splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("**decision question:**") and exact_line not in stripped:
            continue
        lines.append(line)
    return "\n".join(lines)


def normalize_reader_memo_metadata_layout(markdown: str, question: str) -> str:
    """Keep protected reader metadata out of the opening answer paragraph."""

    memo = str(markdown)
    if question:
        pattern = re.compile(rf"(\*\*Decision question:\*\*\s*{re.escape(question)})(?:[ \t]+|\n(?!\n))", flags=re.DOTALL)
        memo = pattern.sub(lambda match: match.group(1).strip() + "\n\n", memo, count=1)
    memo = re.sub(r"(?m)([^\n])\s+(\*\*Confidence:\*\*)", r"\1\n\n\2", memo)
    return memo


def remove_standalone_question_restatement(markdown: str, question: str) -> str:
    normalized_question = _normalized_question_text(question)
    if not normalized_question:
        return markdown
    paragraphs = re.split(r"(\n\s*\n)", markdown.strip())
    kept: list[str] = []
    for index in range(0, len(paragraphs), 2):
        paragraph = paragraphs[index]
        separator = paragraphs[index + 1] if index + 1 < len(paragraphs) else ""
        if _normalized_question_text(paragraph) == normalized_question:
            continue
        kept.append(paragraph)
        if separator:
            kept.append(separator)
    return "".join(kept).strip()


def source_list_lines(scaffold: dict[str, Any]) -> list[str]:
    rows = [
        _source_list_row(entry)
        for entry in sorted(_source_entries(scaffold), key=lambda entry: entry["display"].lower())
    ]
    return ["", "## Sources", "", *rows] if rows else []


def cited_source_list_lines(markdown: str, scaffold: dict[str, Any]) -> list[str]:
    body = _body_without_sources(markdown)
    rows = [_source_list_row(entry) for entry in _cited_source_entries(body, scaffold)]
    return ["", "## Sources", "", *rows] if rows else []


def link_source_mentions(markdown: str, scaffold: dict[str, Any]) -> str:
    """Link known source labels outside the final Sources section.

    The model already receives readable source labels. This pass adds URLs only
    when the case metadata supplied them, avoiding model-invented citations.
    """
    source_lookup = scaffold.get("source_display_names", {})
    source_urls = scaffold.get("source_urls", {})
    source_citations = scaffold.get("source_citation_labels", {})
    if not isinstance(source_lookup, dict) or not isinstance(source_urls, dict):
        return markdown
    if not isinstance(source_citations, dict):
        source_citations = {}
    label_targets = {
        str(display).strip(): (
            str(source_urls.get(source_id, "")).strip(),
            str(source_citations.get(source_id, "")).strip() or str(display).strip(),
        )
        for source_id, display in source_lookup.items()
        if str(display).strip() and _is_linkable_url(str(source_urls.get(source_id, "")).strip())
    }
    if not label_targets:
        return markdown
    sources_match = re.search(r"\n## Sources\n", markdown)
    body = markdown[: sources_match.start()] if sources_match else markdown
    tail = markdown[sources_match.start() :] if sources_match else ""
    body = _link_parenthetical_source_labels(body, label_targets)
    for label, (url, citation_label) in sorted(label_targets.items(), key=lambda item: len(item[0]), reverse=True):
        body = _link_unlinked_label(body, label, url, citation_label)
    return body + tail


def improve_reader_memo_readability(markdown: str) -> str:
    cleaned = _smooth_generic_answer_frame(markdown)
    return _drop_repeated_prefixed_evidence_clauses(cleaned)


def _replace_sources_section(markdown: str, source_lines: list[str]) -> str:
    source_block = "\n".join(source_lines).strip()
    pattern = re.compile(r"\n## Sources\n.*\Z", flags=re.DOTALL)
    if pattern.search(markdown):
        return pattern.sub("\n" + source_block, markdown.rstrip())
    return markdown.rstrip() + "\n" + source_block


def _source_entries(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    source_lookup = scaffold.get("source_display_names", {})
    if not isinstance(source_lookup, dict) or not source_lookup:
        return []
    source_urls = scaffold.get("source_urls", {})
    if not isinstance(source_urls, dict):
        source_urls = {}
    source_citations = scaffold.get("source_citation_labels", {})
    if not isinstance(source_citations, dict):
        source_citations = {}
    common_prefix = common_source_prefix([str(value) for value in source_lookup.values()])
    entries = []
    for source_id, display in source_lookup.items():
        original_display = str(display).strip() or str(source_id).strip()
        label = preferred_source_display(
            {
                "source_id": str(source_id).strip(),
                "source_label": original_display,
                "citation_label": str(source_citations.get(source_id, "")).strip(),
            },
            common_prefix=common_prefix,
        )
        if not label:
            continue
        entries.append(
            {
                "source_id": str(source_id).strip(),
                "display": label,
                "url": str(source_urls.get(source_id, "")).strip(),
                "citation_label": str(source_citations.get(source_id, "")).strip(),
                "aliases": [original_display],
            }
        )
    return entries


def _cited_source_entries(body: str, scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    cited = []
    for entry in _source_entries(scaffold):
        position = _source_mention_position(body, entry)
        if position >= 0:
            cited.append((position, entry))
    return [entry for _, entry in sorted(cited, key=lambda row: row[0])]


def _source_mention_position(body: str, entry: dict[str, Any]) -> int:
    positions = [
        _source_label_position(body, label)
        for label in (entry.get("display", ""), entry.get("citation_label", ""), *entry.get("aliases", []))
        if label
    ]
    positions = [position for position in positions if position >= 0]
    return min(positions) if positions else -1


def _source_label_position(body: str, label: str) -> int:
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(label)}(?![A-Za-z0-9])", flags=re.IGNORECASE)
    match = pattern.search(body)
    if match:
        return match.start()
    normalized_body = _normalize_source_label(body)
    normalized_label = _normalize_source_label(label)
    if len(normalized_label) >= 12 and normalized_label in normalized_body:
        return normalized_body.find(normalized_label)
    return -1


def _source_list_row(entry: dict[str, str]) -> str:
    label = entry["display"]
    url = entry["url"]
    return f"- [{label}]({url})" if _is_linkable_url(url) else f"- {label}"


def _body_without_sources(markdown: str) -> str:
    return re.split(r"\n## Sources\n", str(markdown), maxsplit=1)[0]


def _smooth_generic_answer_frame(markdown: str) -> str:
    pattern = re.compile(
        r"The current map supports a (?P<classification>[^.]+?) answer frame\. "
        r"The main support is: Evidence supports (?P<support>[^.]+?)\. "
        r"The strongest counterposition is: Counterevidence supports caution because (?P<caution>[^.]+?)\.",
        flags=re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        classification = match.group("classification").strip()
        caution = match.group("caution").strip()
        return f"The current map supports a {classification} read. The main counterweight is that {caution}."

    return pattern.sub(replace, markdown)


def _drop_repeated_prefixed_evidence_clauses(markdown: str) -> str:
    lines: list[str] = []
    in_sources = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped == "## Sources":
            in_sources = True
        if (
            in_sources
            or not stripped
            or stripped.startswith("#")
            or stripped.startswith("|")
            or stripped.startswith("- ")
            or "**Decision question:**" in stripped
            or _contains_markdown_link(stripped)
        ):
            lines.append(line)
            continue
        lines.append(_drop_repeated_prefixed_clauses_in_line(line))
    return "\n".join(lines)


def _contains_markdown_link(text: str) -> bool:
    return bool(re.search(r"\[[^\]\n]+\]\([^)]+\)", str(text or "")))


def _drop_repeated_prefixed_clauses_in_line(line: str) -> str:
    seen: set[str] = set()
    sentences = re.findall(r".*?(?:[.!?](?=\s+[A-Z0-9(]|\s*$)|$)", line)
    kept_sentences: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        pieces = [piece.strip() for piece in re.split(r";\s+and\s+", sentence)]
        kept_pieces: list[str] = []
        for piece in pieces:
            canonical = _canonical_prefixed_evidence_clause(piece)
            if canonical and canonical in seen:
                continue
            if canonical:
                seen.add(canonical)
            kept_pieces.append(piece)
        if kept_pieces:
            rebuilt = "; and ".join(kept_pieces).rstrip()
            if sentence.endswith(".") and not rebuilt.endswith((".", "!", "?")):
                rebuilt += "."
            kept_sentences.append(rebuilt)
    return " ".join(kept_sentences) if kept_sentences else line


def _canonical_prefixed_evidence_clause(text: str) -> str:
    cleaned = re.sub(r"^\s*[A-Z][A-Za-z0-9 /_-]{2,45}:\s*", "", text.strip())
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\([^()]{4,180}\)", "", cleaned)
    terms = [
        term
        for term in re.findall(r"[a-z0-9]+", cleaned.lower())
        if term not in {"the", "and", "that", "with", "from", "this", "these", "those"}
    ]
    return " ".join(terms[:18]) if len(terms) >= 6 else ""


def _clean_memo_text(text: str) -> str:
    text = text.replace("\\n", "\n")
    lines = [line.rstrip() for line in text.strip().splitlines()]
    collapsed: list[str] = []
    blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and blank:
            continue
        collapsed.append(line)
        blank = is_blank
    return "\n".join(collapsed).strip() + "\n"


def _link_unlinked_label(text: str, label: str, url: str, citation_label: str) -> str:
    pattern = re.compile(rf"(?<!\[)\b{re.escape(label)}\b(?!\]\()")

    def replace(match: re.Match[str]) -> str:
        if _inside_markdown_link(text, match.start()):
            return match.group(0)
        return f"[{citation_label}]({url})"

    return pattern.sub(replace, text)


def _link_parenthetical_source_labels(text: str, label_targets: dict[str, tuple[str, str]]) -> str:
    normalized_targets = {_normalize_source_label(label): target for label, target in label_targets.items()}

    def replace(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        if "](" in label:
            return match.group(0)
        target = normalized_targets.get(_normalize_source_label(label))
        if not target:
            return match.group(0)
        url, citation_label = target
        return f"([{citation_label}]({url}))"

    return re.sub(r"\(([^()\n]{4,260})\)", replace, text)


def _inside_markdown_link(text: str, position: int) -> bool:
    line_start = text.rfind("\n", 0, position) + 1
    prefix = text[line_start:position]
    open_brackets = prefix.count("[") - prefix.count("]")
    if open_brackets > 0:
        return True
    last_link_open = prefix.rfind("](")
    if last_link_open == -1:
        return False
    last_close = prefix.rfind(")")
    return last_close < last_link_open


def _is_linkable_url(url: str) -> bool:
    return bool(re.fullmatch(r"https?://\S+", url.strip()))


def _normalize_source_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _normalized_question_text(text: str) -> str:
    cleaned = re.sub(r"^\*\*Decision question:\*\*\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned.rstrip("?!.")
