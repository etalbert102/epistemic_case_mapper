from __future__ import annotations

import re


def smooth_stock_memo_phrasing(memo: str) -> str:
    replacements = {
        "This nuanced view": "This reading",
        "The current assessment is driven by": "The current read turns on",
        "The evidence suggests": "The evidence points to",
        "The primary boundary on this assessment": "The main boundary",
        "The current read is further bounded": "The read is also bounded",
        "It is essential to": "The important move is to",
        "To avoid over-applying this answer": "In applying this answer",
        "provide the foundational basis for a neutral stance": "carry the main answer",
        "provides the foundational basis for a neutral stance": "carries the main answer",
        "provide the necessary nuance to ensure": "help ensure",
        "provides the necessary nuance to ensure": "helps ensure",
        "primary empirical basis for a neutral stance": "primary empirical support for that conclusion",
        "provide the foundational basis": "carry the main answer",
        "provides the foundational basis": "carries the main answer",
        "serve to narrow the scope": "mainly narrow the scope",
        "serves to narrow the scope": "mainly narrows the scope",
        "provide the necessary nuance": "keep the recommendation calibrated",
        "provides the necessary nuance": "keeps the recommendation calibrated",
        "To ensure practical application without overclaiming": "In practice",
        "current neutral stance": "current neutral conclusion",
        "The neutral stance": "The neutral conclusion",
        "this neutral stance": "this neutral conclusion",
        "a neutral stance": "a neutral conclusion",
        "the neutral stance": "the neutral conclusion",
        "This neutral stance": "This neutral conclusion",
        "boundaries of \"safe\" limits": "working intake boundaries",
        "boundaries of safe limits": "working intake boundaries",
        "dose-dependent boundary for safety": "dose-dependent boundary for risk",
        "the \"safe\" threshold": "the working boundary",
        "the safe threshold": "the working boundary",
        "\"safe\" threshold": "working boundary",
        "safe threshold": "working boundary",
    }
    next_memo = memo
    for stock, replacement in replacements.items():
        next_memo = next_memo.replace(stock, replacement)
    for pattern, replacement in _OVERCLAIM_REPLACEMENTS:
        next_memo = re.sub(pattern, replacement, next_memo)
    return next_memo


_OVERCLAIM_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        r"\b[Dd]oes not increase ([^.\n;]{0,120}?\brisk\b)",
        r"is not associated with increased \1",
    ),
    (
        r"\b[Dd]id not increase ([^.\n;]{0,120}?\brisk\b)",
        r"was not associated with increased \1",
    ),
)
