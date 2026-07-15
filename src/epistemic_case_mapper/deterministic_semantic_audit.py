from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SemanticAuditFinding:
    path: str
    line: int
    category: str
    severity: str
    text: str
    recommendation: str


PATTERNS: tuple[tuple[str, str, str, str, re.Pattern[str]], ...] = (
    (
        "hard_missing_from_count",
        "high",
        "Assert semantic absence only after reconciling labels, counts, relations, spine fields, and source-backed candidates.",
        "count-driven missing evidence or slot assertion",
        re.compile(r"(role_counts\.get|_missing_major_dimensions|missing_expected_|missing_source_categories|source set is missing)", re.I),
    ),
    (
        "keyword_semantic_classification",
        "medium",
        "Keep keyword classifiers advisory unless another structured signal corroborates them.",
        "keyword-based support/counterweight/scope classification",
        re.compile(r"(_support_terms|_counterevidence_terms|_stance_score|_role_for_claim|_candidate_role|_looks_like_)", re.I),
    ),
    (
        "semantic_rejection_gate",
        "medium",
        "Route semantic rejection to review or model adjudication unless the failure is schema, ID, or source-anchor invalidity.",
        "deterministic rejection of semantic relation/claim quality",
        re.compile(r"(semantic_rejection|relation_semantic_rejection|_append_semantic_relation_rejection|return \"no_relation\")", re.I),
    ),
    (
        "profile_vocabulary_semantics",
        "medium",
        "Use vocabulary/profile matches as routing hints, not final evidence sufficiency or memo claims.",
        "profile vocabulary controls semantic slot assignment",
        re.compile(r"(profile_vocabulary|evidence_family_markers|decision_concept|expected_decision_slots|expected_evidence_families)", re.I),
    ),
)


def scan_deterministic_semantic_decisions(paths: Iterable[Path]) -> list[SemanticAuditFinding]:
    findings: list[SemanticAuditFinding] = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in files:
            if "__pycache__" in path.parts:
                continue
            if path.name == "deterministic_semantic_audit.py":
                continue
            lines = _safe_lines(path)
            for lineno, line in enumerate(lines, start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if _skip_non_actionable_line(path, stripped, lines=lines, index=lineno - 1):
                    continue
                for category, severity, recommendation, description, pattern in PATTERNS:
                    if pattern.search(stripped):
                        findings.append(
                            SemanticAuditFinding(
                                path=str(path),
                                line=lineno,
                                category=category,
                                severity=severity,
                                text=stripped,
                                recommendation=f"{description}: {recommendation}",
                            )
                        )
                        break
    return findings


def _skip_non_actionable_line(path: Path, stripped: str, *, lines: list[str], index: int) -> bool:
    """Skip references that do not make a runtime semantic decision."""

    if path.name in {
        "config_profiles.py",
        "config_profile_vocabularies.py",
        "map_briefing.py",
    }:
        return True
    if stripped.startswith(("from ", "import ", "def ", "class ")):
        return True
    if stripped.startswith('"') or stripped.startswith("'"):
        return True
    if re.match(r"\w+\s*:\s*.*(?:Field|list\[|dict\[|Literal\[)", stripped):
        return True
    if re.match(
        r"[\"'](?:schema_id|method|question_profile|present_decision_slots|present_evidence_families|"
        r"missing_expected_decision_slots|missing_expected_evidence_families|missing_source_categories|"
        r"source_sufficiency_missing_categories|decision_concepts|expected_decision_slots|expected_evidence_families)[\"']\s*:",
        stripped,
    ):
        return True
    if re.match(r"missing_source_categories\s*=", stripped):
        return True
    if re.match(r"missing_expected_(?:slots|families)\s*=\s*missing_expected_", stripped):
        return True
    if stripped.startswith("__all__") or (
        stripped.endswith(",")
        and (
            re.fullmatch(r"[\"'][_A-Za-z0-9]+[\"'],?", stripped)
            or re.fullmatch(r"[_A-Za-z][_A-Za-z0-9]*,?", stripped)
        )
    ):
        return True
    if (
        ("missing_expected_" in stripped or "missing_source_categories" in stripped)
        and any(
            "reader_facing_unresolved" in lookahead or "current map does not cleanly establish" in lookahead
            for lookahead in _lookahead(lines, index, window=8)
        )
    ):
        return True
    return False


def _lookahead(lines: list[str], index: int, *, window: int) -> list[str]:
    return lines[index + 1 : index + 1 + window]


def render_semantic_audit_markdown(findings: list[SemanticAuditFinding], *, repo_root: Path | None = None) -> str:
    repo_root = repo_root or Path.cwd()
    by_category: dict[str, list[SemanticAuditFinding]] = {}
    for finding in findings:
        by_category.setdefault(finding.category, []).append(finding)
    lines = [
        "# Deterministic Semantic Decision Audit",
        "",
        "This audit flags deterministic code paths that appear to make semantic judgments from labels, keywords, or counts.",
        "Findings are review prompts, not automatic failures.",
        "",
        f"Total findings: `{len(findings)}`",
        "",
    ]
    for category in sorted(by_category):
        rows = by_category[category]
        lines.extend([f"## {category}", "", f"Findings: `{len(rows)}`", ""])
        for finding in rows[:25]:
            rel = _relative_path(Path(finding.path), repo_root)
            lines.append(f"- `{rel}:{finding.line}` `{finding.severity}` {finding.text}")
        if len(rows) > 25:
            lines.append(f"- ... {len(rows) - 25} more")
        lines.append("")
        lines.append(f"Recommended handling: {rows[0].recommendation}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _safe_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return path.read_text(errors="ignore").splitlines()


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)
