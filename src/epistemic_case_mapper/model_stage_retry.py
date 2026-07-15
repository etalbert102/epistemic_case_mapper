from __future__ import annotations

import os


DEFAULT_MODEL_STAGE_ATTEMPTS = 3


def model_stage_attempts() -> int:
    try:
        requested = int(os.environ.get("ECM_MODEL_STAGE_ATTEMPTS", str(DEFAULT_MODEL_STAGE_ATTEMPTS)))
    except ValueError:
        requested = DEFAULT_MODEL_STAGE_ATTEMPTS
    return max(1, min(DEFAULT_MODEL_STAGE_ATTEMPTS, requested))


def model_retry_report(attempt: int, status: str, parse_report: dict, error: str = "") -> dict:
    issues = parse_report.get("issues", []) if isinstance(parse_report, dict) else []
    return {
        "attempt": attempt,
        "status": status,
        "parse_status": parse_report.get("status") if isinstance(parse_report, dict) else None,
        "valid": parse_report.get("valid", False) if isinstance(parse_report, dict) else False,
        "issues": [str(issue) for issue in issues],
        **({"error": error} if error else {}),
    }
