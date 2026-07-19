from __future__ import annotations

import re


def smooth_stock_memo_phrasing(memo: str) -> str:
    replacements = {
        "This nuanced view": "This reading",
        "The current assessment is driven by": "The current read turns on",
        "The evidence suggests": "The evidence points to",
        "The evidence hierarchy is anchored by": "Put most weight on",
        "which establish a neutral stance": "which support a neutral read",
        "which establish a neutral conclusion": "which support a neutral read",
        "further bound this recommendation": "set additional limits",
        "set additional limits by identifying dose-response limits and specific high-risk subgroups": "set boundaries around dose-response and specific high-risk subgroups",
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
        "The primary recommendation is driven by evidence suggesting that": "The core evidence says",
        "These sources carry the main answer": "That is the core of the answer",
        "While these driver sources establish the baseline, other evidence calibrates the specific limits of this recommendation": "The limits come from a second layer of evidence",
        "These sources do not overturn the neutral stance for moderate intake but instead establish": "These sources do not change the answer for moderate intake; they set",
        "These sources do not overturn the neutral conclusion for moderate intake but instead establish": "These sources do not change the answer for moderate intake; they set",
        "specific evidence bounds the recommendation": "specific evidence narrows the recommendation",
        "The recommendation is further bounded by": "The main exceptions are",
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
        "This neutral conclusion is maintained because": "That read holds because",
        "While a neutral conclusion applies to moderate intake, evidence suggests a dose-dependent boundary for risk": "For moderate intake, the read is neutral; risk becomes more relevant as intake rises",
        "While a neutral conclusion applies to moderate intake, evidence suggests": "For moderate intake, the read is neutral; the boundary is dose-dependent",
        "While a neutral conclusion applies to moderate intake": "The neutral read applies to moderate intake",
        "That read holds because the evidence suggests that while": "That read holds because",
        "may correlate with elevated lipid ratios, moderate intake": "may correlate with elevated lipid ratios, but moderate intake",
        "Large prospective cohort studies support this neutral conclusion": "Large prospective cohort studies support that read",
        "The current neutral conclusion for healthy adults is constrained by": "For healthy adults, the neutral read still depends on",
        "the current neutral conclusion for healthy adults is constrained by": "for healthy adults, the neutral read still depends on",
        "For healthy adults, the neutral read still depends on the fact that": "For healthy adults, the important caveat is that",
        "However, this recommendation is not universal and requires specific exceptions": "This advice has important exceptions",
        "This advice does not apply equally to everyone for high-risk populations": "This advice has important exceptions for high-risk populations",
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
    for stock, replacement in _FINAL_STYLE_REPAIRS:
        next_memo = next_memo.replace(stock, replacement)
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


_FINAL_STYLE_REPAIRS: tuple[tuple[str, str], ...] = (
    (
        "For moderate intake, the read is neutral; the boundary is dose-dependent a dose-dependent boundary for risk",
        "For moderate intake, the read is neutral; risk becomes more relevant as intake rises",
    ),
)
