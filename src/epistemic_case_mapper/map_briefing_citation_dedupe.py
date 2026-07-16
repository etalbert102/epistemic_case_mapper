from __future__ import annotations

import re

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import norm as _norm


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
