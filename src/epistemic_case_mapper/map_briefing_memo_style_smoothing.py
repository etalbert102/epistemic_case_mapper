from __future__ import annotations


def smooth_stock_memo_phrasing(memo: str) -> str:
    replacements = {
        "This nuanced view": "This reading",
        "The current assessment is driven by": "The current read turns on",
        "The evidence suggests": "The evidence points to",
        "The primary boundary on this assessment": "The main boundary",
        "The current read is further bounded": "The read is also bounded",
        "It is essential to": "The important move is to",
        "To avoid over-applying this answer": "In applying this answer",
    }
    next_memo = memo
    for stock, replacement in replacements.items():
        next_memo = next_memo.replace(stock, replacement)
    return next_memo
