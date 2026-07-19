from __future__ import annotations

import re

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import norm as _norm


def dedupe_linked_citation_clusters(memo: str) -> str:
    link_pattern = re.compile(r"\[[^\]\n]+\]\([^\)\n]+\)")

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        links = link_pattern.findall(content)
        if len(links) == 1 and content.strip() == links[0]:
            return links[0]
        if len(links) < 2:
            return match.group(0)
        deduped = _dedupe_by_norm(links)
        if len(deduped) == 1:
            return deduped[0]
        return "; ".join(deduped)

    return re.sub(r"\[((?:\[[^\]\n]+\]\([^\)\n]+\)(?:\s*(?:;|,)\s*)?)+)\]", replace, memo)


def dedupe_reference_citation_runs(memo: str, citation_displays: list[str]) -> str:
    known = {_norm(display): display for display in citation_displays if str(display or "").strip()}

    def replace(match: re.Match[str]) -> str:
        original = match.group(0)
        tokens = re.findall(r"\[([^\[\]\n]{1,120})\]", original)
        markers = [_norm(token) for token in tokens]
        if len(tokens) < 2 or any(marker not in known for marker in markers):
            return original
        deduped = []
        seen = set()
        for marker in markers:
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(f"[{known[marker]}]")
        separator = "; " if ";" in original else ", "
        return separator.join(deduped) + (" " if original[-1:].isspace() else "")

    return re.sub(r"(?:\[[^\[\]\n]{1,120}\](?:\s*(?:,|;)?\s*)?){2,}", replace, str(memo or ""))


def compact_repeated_sentence_citations(memo: str, citation_displays: list[str]) -> str:
    """Remove identical citation tails on adjacent sentences in the same paragraph.

    This is presentation-only: it does not infer that different evidence shares a source.
    It only handles exact repeated citation clusters already emitted by the model.
    """
    known = {_norm(display) for display in citation_displays if str(display or "").strip()}
    if not known:
        return str(memo or "")
    blocks = re.split(r"(\n\s*\n)", str(memo or ""))
    return "".join(_compact_paragraph_citation_tails(block, known) if not block.startswith("\n") else block for block in blocks)


def _compact_paragraph_citation_tails(paragraph: str, known: set[str]) -> str:
    if "\n" in paragraph and any(line.lstrip().startswith(("#", "* ", "- ", "[", "|")) for line in paragraph.splitlines()):
        return paragraph
    pattern = re.compile(r"(\[[^\[\]\n]{1,120}\](?:\s*(?:,|;)\s*\[[^\[\]\n]{1,120}\])*)")
    parts = pattern.split(paragraph)
    if len(parts) < 5:
        return paragraph
    clusters = [
        cluster
        for index, part in enumerate(parts)
        if index % 2 == 1
        for cluster in [_reference_cluster_key(part, known)]
        if cluster
    ]
    if len(set(clusters)) > 1:
        return paragraph
    output: list[str] = []
    previous_citation_index: int | None = None
    previous_cluster: tuple[str, ...] | None = None
    for index, part in enumerate(parts):
        if index % 2 == 0:
            output.append(part)
            continue
        cluster = _reference_cluster_key(part, known)
        if not cluster:
            output.append(part)
            previous_citation_index = None
            previous_cluster = None
            continue
        previous_text = output[-1] if output else ""
        if (
            previous_citation_index is not None
            and previous_cluster == cluster
            and 0 <= previous_citation_index < len(output)
            and _looks_like_citation_separated_sentence("".join(output[previous_citation_index + 1 :]))
        ):
            if previous_citation_index > 0:
                output[previous_citation_index - 1] = output[previous_citation_index - 1].rstrip()
            output[previous_citation_index] = ""
            previous_citation_index = len(output)
            output.append(part)
        else:
            previous_citation_index = len(output)
            output.append(part)
        previous_cluster = cluster
    return "".join(output)


def _reference_cluster_key(value: str, known: set[str]) -> tuple[str, ...]:
    tokens = re.findall(r"\[([^\[\]\n]{1,120})\]", value)
    markers = tuple(_norm(token) for token in tokens)
    if not markers or any(marker not in known for marker in markers):
        return ()
    return markers


def _looks_like_sentence_tail(value: str) -> bool:
    stripped = str(value or "").rstrip()
    return stripped.endswith((".", "?", "!", ";", ":")) or bool(re.search(r"[.!?]\s*$", stripped))


def _looks_like_citation_separated_sentence(value: str) -> bool:
    text = str(value or "")
    if not re.match(r"\s*[.!?;:]", text):
        return False
    return bool(re.search(r"[A-Za-z0-9]", text))


def _dedupe_by_norm(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped = []
    for value in values:
        marker = _norm(value)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(value)
    return deduped
