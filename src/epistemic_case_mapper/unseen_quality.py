from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from epistemic_case_mapper.schema import CaseManifest


BASE_DIR = Path("docs/unseen_case_tests")
REQUIRED_FILES = (
    "TEST_PROTOCOL.md",
    "QUALITY_REVIEW.md",
    "BASELINE_COMPARISON.md",
    "SCORECARD.md",
)

PROTOCOL_HEADINGS = (
    "Case",
    "Why This Is Unseen",
    "Source Inclusion Rules",
    "Baseline Isolation",
    "Budget",
    "Success Criteria",
    "Failure Criteria",
)

QUALITY_DIMENSIONS = (
    "Source fidelity",
    "Load-bearing visibility",
    "Crux quality",
    "Relation usefulness",
    "Erosion audit quality",
    "Human reviewability",
    "Generalizability",
    "Incremental extensibility",
    "UI usefulness",
    "Baseline improvement",
)

BASELINE_COMPARISON_HEADINGS = (
    "Flat Baseline Summary",
    "Map Preserved",
    "Flat Baseline Did Better",
    "Cruxes Clarified",
    "Claims Made More Inspectable",
    "Investigator View Change",
    "Complexity Worth It",
)

ACCEPTANCE_CRITERIA = (
    "package_prepare",
    "package_validate",
    "ui_renders",
    "review_checklist_source_spans",
    "no_parser_artifacts",
    "non_obvious_crux",
    "real_flat_synthesis_loss",
    "human_reviewer_can_inspect",
    "better_than_flat_baseline",
)
WEAK_PROVENANCE_LEVELS = {"secondary_summary", "local_note", "synthetic_note"}
RISK_STATUSES = {"risk", "fail"}


@dataclass(frozen=True)
class UnseenCaseInfo:
    case_slug: str
    title: str
    question: str


@dataclass(frozen=True)
class QualitySignal:
    signal_type: str
    severity: str
    label: str
    evidence: str


def init_quality_test(
    repo_root: Path,
    case_slug: str,
    title: str,
    question: str,
    *,
    force: bool = False,
) -> list[Path]:
    info = UnseenCaseInfo(case_slug=_normalize_slug(case_slug), title=title.strip(), question=question.strip())
    if not info.title:
        raise ValueError("title_required")
    if not info.question:
        raise ValueError("question_required")

    case_dir = quality_case_dir(repo_root, info.case_slug)
    case_dir.mkdir(parents=True, exist_ok=True)
    templates = {
        "TEST_PROTOCOL.md": _protocol_template(info),
        "QUALITY_REVIEW.md": _quality_review_template(info),
        "BASELINE_COMPARISON.md": _baseline_comparison_template(info),
        "SCORECARD.md": _scorecard_template(info),
    }
    written: list[Path] = []
    for filename, content in templates.items():
        path = case_dir / filename
        if path.exists() and not force:
            continue
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def validate_quality_test(repo_root: Path, case_slug: str) -> list[str]:
    slug = _normalize_slug(case_slug)
    case_dir = quality_case_dir(repo_root, slug)
    failures: list[str] = []
    if not case_dir.exists():
        return [f"unseen_quality_dir_missing case={slug} path={_display_path(repo_root, case_dir)}"]

    for filename in REQUIRED_FILES:
        path = case_dir / filename
        if not path.exists():
            failures.append(f"unseen_quality_file_missing case={slug} path={_display_path(repo_root, path)}")
            continue
        text = path.read_text(encoding="utf-8")
        _validate_no_placeholders(slug, path, text, repo_root, failures)
        _validate_complete_status(slug, path, text, repo_root, failures)

    _validate_headings(slug, case_dir / "TEST_PROTOCOL.md", PROTOCOL_HEADINGS, repo_root, failures)
    _validate_quality_scores(slug, case_dir / "QUALITY_REVIEW.md", repo_root, failures)
    _validate_headings(slug, case_dir / "BASELINE_COMPARISON.md", BASELINE_COMPARISON_HEADINGS, repo_root, failures)
    _validate_scorecard(slug, case_dir / "SCORECARD.md", repo_root, failures)
    return failures


def quality_summary(repo_root: Path, case_slug: str) -> dict:
    slug = _normalize_slug(case_slug)
    case_dir = quality_case_dir(repo_root, slug)
    scorecard_path = case_dir / "SCORECARD.md"
    review_path = case_dir / "QUALITY_REVIEW.md"
    summary = {
        "exists": case_dir.exists(),
        "caseSlug": slug,
        "paths": {
            "protocol": (case_dir / "TEST_PROTOCOL.md").relative_to(repo_root).as_posix()
            if (case_dir / "TEST_PROTOCOL.md").exists()
            else None,
            "qualityReview": review_path.relative_to(repo_root).as_posix() if review_path.exists() else None,
            "baselineComparison": (case_dir / "BASELINE_COMPARISON.md").relative_to(repo_root).as_posix()
            if (case_dir / "BASELINE_COMPARISON.md").exists()
            else None,
            "scorecard": scorecard_path.relative_to(repo_root).as_posix() if scorecard_path.exists() else None,
            "riskTasks": (case_dir / "GENERATED_RISK_TASKS.md").relative_to(repo_root).as_posix()
            if (case_dir / "GENERATED_RISK_TASKS.md").exists()
            else None,
        },
        "overallResult": None,
        "riskCriteria": [],
        "lowScores": [],
    }
    if scorecard_path.exists():
        scorecard = scorecard_path.read_text(encoding="utf-8")
        match = re.search(r"^Overall result:\s*`?([^`\n]+)`?\s*$", scorecard, re.MULTILINE | re.IGNORECASE)
        if match:
            summary["overallResult"] = match.group(1).strip().lower()
        summary["riskCriteria"] = _risk_criteria(scorecard)
    if review_path.exists():
        summary["lowScores"] = _low_quality_scores(review_path.read_text(encoding="utf-8"))
    return summary


def source_quality_signals(case_manifest: CaseManifest) -> list[QualitySignal]:
    signals: list[QualitySignal] = []
    for source in case_manifest.sources:
        if source.needs_upgrade:
            signals.append(
                QualitySignal(
                    signal_type="source_upgrade",
                    severity="risk",
                    label=source.source_id,
                    evidence="Source is marked needs_upgrade=true.",
                )
            )
        if source.provenance_level in WEAK_PROVENANCE_LEVELS:
            signals.append(
                QualitySignal(
                    signal_type="source_provenance",
                    severity="risk",
                    label=source.source_id,
                    evidence=f"provenance_level={source.provenance_level}",
                )
            )
        for limitation in source.limitations:
            signals.append(
                QualitySignal(
                    signal_type="source_limitation",
                    severity="note",
                    label=source.source_id,
                    evidence=limitation,
                )
            )
    return signals


def quality_signals(repo_root: Path, case_slug: str, case_manifest: CaseManifest) -> list[QualitySignal]:
    signals = source_quality_signals(case_manifest)
    summary = quality_summary(repo_root, case_slug)
    for criterion in summary["riskCriteria"]:
        signals.append(
            QualitySignal(
                signal_type="scorecard_criterion",
                severity=criterion["status"],
                label=criterion["criterion"],
                evidence=criterion["evidence"],
            )
        )
    for score in summary["lowScores"]:
        signals.append(
            QualitySignal(
                signal_type="quality_score",
                severity="risk",
                label=score["dimension"],
                evidence=f"score={score['score']}; {score['evidence']}",
            )
        )
    overall = summary["overallResult"]
    if overall in {"fail", "inconclusive"}:
        signals.append(
            QualitySignal(
                signal_type="overall_quality_result",
                severity="risk" if overall == "inconclusive" else "fail",
                label="overall_result",
                evidence=overall,
            )
        )
    return signals


def write_quality_risk_tasks(repo_root: Path, case_slug: str, case_manifest: CaseManifest) -> Path:
    slug = _normalize_slug(case_slug)
    case_dir = quality_case_dir(repo_root, slug)
    case_dir.mkdir(parents=True, exist_ok=True)
    output_path = case_dir / "GENERATED_RISK_TASKS.md"
    signals = quality_signals(repo_root, slug, case_manifest)
    lines = [
        f"# {case_manifest.title} Generated Risk Tasks",
        "",
        "Status: `generated`",
        "",
        "These tasks are generated from source provenance metadata and unseen-case quality review risk/fail rows.",
        "",
    ]
    if not signals:
        lines.extend(["No quality risk tasks generated.", ""])
    for index, signal in enumerate(signals, start=1):
        task_id = f"quality_task_{index:03d}"
        lines.extend(
            [
                f"task_id: {task_id}",
                f"task_type: {signal.signal_type}",
                f"priority: {_priority_for_signal(signal)}",
                f"target: {signal.label}",
                f"risk_status: {signal.severity}",
                f"task: {_task_text(signal)}",
                f"evidence: {signal.evidence}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _risk_criteria(scorecard: str) -> list[dict[str, str]]:
    criteria: list[dict[str, str]] = []
    for line in scorecard.splitlines():
        if not line.startswith("|"):
            continue
        cells = _split_table_row(line)
        if len(cells) < 3:
            continue
        criterion, status, evidence = cells[0], cells[1].lower(), cells[2]
        if status in RISK_STATUSES:
            criteria.append({"criterion": criterion, "status": status, "evidence": evidence})
    return criteria


def _low_quality_scores(review: str) -> list[dict[str, str]]:
    scores: list[dict[str, str]] = []
    for dimension in QUALITY_DIMENSIONS:
        row = _table_row_for_label(review, dimension)
        if row is None:
            continue
        cells = _split_table_row(row)
        if len(cells) < 3 or not re.fullmatch(r"[1-5]", cells[1]):
            continue
        score = int(cells[1])
        if score <= 2:
            scores.append({"dimension": dimension, "score": str(score), "evidence": cells[2]})
    return scores


def _priority_for_signal(signal: QualitySignal) -> str:
    if signal.severity == "fail":
        return "high"
    if signal.signal_type in {"source_upgrade", "source_provenance", "overall_quality_result"}:
        return "high"
    return "medium"


def _task_text(signal: QualitySignal) -> str:
    if signal.signal_type in {"source_upgrade", "source_provenance"}:
        return f"Upgrade or justify source provenance for {signal.label} before treating it as load-bearing."
    if signal.signal_type == "source_limitation":
        return f"Bound the limitation for {signal.label} in the map, checklist, or source inventory."
    if signal.signal_type == "scorecard_criterion":
        return f"Resolve the unseen-case scorecard {signal.severity} criterion {signal.label}."
    if signal.signal_type == "quality_score":
        return f"Improve the low quality dimension {signal.label} or record why the limitation is acceptable."
    if signal.signal_type == "overall_quality_result":
        return "Resolve the non-passing overall unseen-case quality result before presenting the package as showable."
    return f"Review quality signal {signal.label}."


def quality_case_dir(repo_root: Path, case_slug: str) -> Path:
    return repo_root / BASE_DIR / _normalize_slug(case_slug)


def _validate_no_placeholders(
    slug: str,
    path: Path,
    text: str,
    repo_root: Path,
    failures: list[str],
) -> None:
    if re.search(r"\bTODO\b|<[^>\n]+>", text):
        failures.append(f"unseen_quality_placeholder case={slug} path={_display_path(repo_root, path)}")


def _validate_complete_status(
    slug: str,
    path: Path,
    text: str,
    repo_root: Path,
    failures: list[str],
) -> None:
    if not re.search(r"^Status:\s*`complete`\s*$", text, re.MULTILINE):
        failures.append(f"unseen_quality_status_not_complete case={slug} path={_display_path(repo_root, path)}")


def _validate_headings(
    slug: str,
    path: Path,
    required_headings: tuple[str, ...],
    repo_root: Path,
    failures: list[str],
) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for heading in required_headings:
        pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
        if not pattern.search(text):
            failures.append(
                f"unseen_quality_heading_missing case={slug} path={_display_path(repo_root, path)} heading={heading!r}"
            )


def _validate_quality_scores(slug: str, path: Path, repo_root: Path, failures: list[str]) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for dimension in QUALITY_DIMENSIONS:
        row = _table_row_for_label(text, dimension)
        if row is None:
            failures.append(
                f"unseen_quality_dimension_missing case={slug} path={_display_path(repo_root, path)} dimension={dimension!r}"
            )
            continue
        cells = _split_table_row(row)
        score = cells[1] if len(cells) > 1 else ""
        if not re.fullmatch(r"[1-5]", score):
            failures.append(
                f"unseen_quality_score_invalid case={slug} path={_display_path(repo_root, path)} dimension={dimension!r}"
            )


def _validate_scorecard(slug: str, path: Path, repo_root: Path, failures: list[str]) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for criterion in ACCEPTANCE_CRITERIA:
        row = _table_row_for_label(text, criterion)
        if row is None:
            failures.append(
                f"unseen_quality_acceptance_missing case={slug} path={_display_path(repo_root, path)} criterion={criterion}"
            )
            continue
        cells = _split_table_row(row)
        status = cells[1].lower() if len(cells) > 1 else ""
        if status not in {"pass", "fail", "risk", "n/a"}:
            failures.append(
                f"unseen_quality_acceptance_status_invalid case={slug} path={_display_path(repo_root, path)} criterion={criterion}"
            )
        elif status == "fail":
            failures.append(
                f"unseen_quality_acceptance_failed case={slug} path={_display_path(repo_root, path)} criterion={criterion}"
            )
    overall_match = re.search(r"^Overall result:\s*`?(pass|fail|inconclusive)`?\s*$", text, re.MULTILINE | re.IGNORECASE)
    if overall_match is None:
        failures.append(f"unseen_quality_overall_result_missing case={slug} path={_display_path(repo_root, path)}")
    elif overall_match.group(1).lower() in {"fail", "inconclusive"}:
        failures.append(
            f"unseen_quality_overall_result_not_pass case={slug} path={_display_path(repo_root, path)} "
            f"result={overall_match.group(1).lower()}"
        )


def _table_row_for_label(text: str, label: str) -> str | None:
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = _split_table_row(line)
        if cells and cells[0].lower() == label.lower():
            return line
    return None


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _normalize_slug(case_slug: str) -> str:
    slug = case_slug.strip().lower().replace(" ", "_")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_\-]*", slug):
        raise ValueError(f"invalid_case_slug value={case_slug!r}")
    return slug


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _protocol_template(info: UnseenCaseInfo) -> str:
    return f"""# {info.title} Unseen Case Test Protocol

Status: `draft`

## Case

- Case slug: `{info.case_slug}`
- Title: {info.title}
- Question: {info.question}

## Why This Is Unseen

TODO: Explain why this case differs from prior packages by domain, source shape, stakeholder structure, and uncertainty profile.

## Source Inclusion Rules

TODO: Record the source packet rules before building the map, including inclusion/exclusion criteria and perspective balance.

## Baseline Isolation

TODO: Describe how the flat baseline will be generated before inspecting the map artifacts.

## Budget

TODO: Record time, model, compute, and human-review budget limits.

## Success Criteria

TODO: State concrete success criteria for source fidelity, crux visibility, reviewability, and baseline improvement.

## Failure Criteria

TODO: State concrete failure criteria, including parser artifacts, overclaiming, hidden uncertainty, and inability to beat the flat baseline.
"""


def _quality_review_template(info: UnseenCaseInfo) -> str:
    rows = "\n".join(f"| {dimension} | TODO | TODO |" for dimension in QUALITY_DIMENSIONS)
    return f"""# {info.title} Quality Review

Status: `draft`

Scores use 1-5, where 1 is poor, 3 is usable with visible limitations, and 5 is strong.

| Dimension | Score | Evidence |
| --- | --- | --- |
{rows}

## Human Judge Simulation

TODO: Record the reviewer's answers, time to answer, artifacts used, and points of confusion.

## Adversarial Findings

TODO: List quality failures as correctness bug, presentation bug, methodology weakness, missing source, or generalizability failure.

## Revision Decisions

TODO: Record which failures must be fixed before the package is showable and which are bounded limitations.
"""


def _baseline_comparison_template(info: UnseenCaseInfo) -> str:
    return f"""# {info.title} Baseline Comparison

Status: `draft`

## Flat Baseline Summary

TODO: Summarize what the isolated flat baseline concluded before seeing the map artifacts.

## Map Preserved

TODO: Identify what the map preserved that the flat baseline blurred or omitted.

## Flat Baseline Did Better

TODO: Identify anything the flat baseline communicated more clearly than the map.

## Cruxes Clarified

TODO: List cruxes that became clearer because of the map structure.

## Claims Made More Inspectable

TODO: List source-grounded claims that became easier to inspect, challenge, or revise.

## Investigator View Change

TODO: State whether the map changed the investigator's view and why.

## Complexity Worth It

TODO: Decide whether the added structure was worth the extra complexity for a human judge.
"""


def _scorecard_template(info: UnseenCaseInfo) -> str:
    rows = "\n".join(f"| {criterion} | TODO | TODO |" for criterion in ACCEPTANCE_CRITERIA)
    return f"""# {info.title} Unseen Case Scorecard

Status: `draft`

Overall result: `TODO`

| Criterion | Status | Evidence |
| --- | --- | --- |
{rows}

## Final Assessment

TODO: Give the concise judgment: pass, fail, or inconclusive, and name the highest-value prototype improvement discovered by this run.
"""
