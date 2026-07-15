from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from epistemic_case_mapper.submission_manifest import BlindedBaseline, WorkedRegion, load_submission_manifest


BASELINE_PROMPT_VERSION = "flat_baseline_prompt_v1_blinded_ollama"
BASELINE_PROMPT = (
    "Using only the listed source excerpts for this worked region, write a concise synthesis "
    "that answers the region question for an informed reader. Preserve important caveats "
    "where they affect the answer, while keeping the output as a direct research memo."
)


@dataclass(frozen=True)
class Span:
    source_id: str
    path: str
    ranges: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class BaselineConfig:
    baseline_id: str
    case_key: str
    region_id: str
    title: str
    question: str
    output_path: str
    required_sources: tuple[str, ...]
    spans: tuple[Span, ...]


def _configs_from_manifest(repo_root: Path, manifest_path: str = "submission_manifest.yaml") -> dict[str, BaselineConfig]:
    manifest = load_submission_manifest(repo_root, manifest_path)
    configs: dict[str, BaselineConfig] = {}
    for region, baseline in manifest.iter_blinded_baselines():
        config = _baseline_config(region, baseline)
        configs[config.baseline_id] = config
    return configs


def _baseline_config(region: WorkedRegion, baseline: BlindedBaseline) -> BaselineConfig:
    return BaselineConfig(
        baseline_id=baseline.baseline_id or region.region_id,
        case_key=region.case_key,
        region_id=region.region_id,
        title=baseline.title,
        question=baseline.question,
        output_path=baseline.output_path,
        required_sources=tuple(baseline.required_sources),
        spans=tuple(
            Span(span.source_id, span.path, tuple(tuple(item) for item in span.ranges))
            for span in baseline.spans
        ),
    )


def build_prompt(repo_root: Path, config: BaselineConfig) -> str:
    source_blocks = [_format_span_block(repo_root, span) for span in config.spans]
    return "\n\n".join(
        (
            "You are writing a blinded flat synthesis baseline.",
            "Create a direct research memo rather than a claim map, relation map, audit, or map critique.",
            f"Baseline ID: {config.baseline_id}",
            f"Region ID: {config.region_id}",
            f"Worked region question: {config.question}",
            f"Prompt version: {BASELINE_PROMPT_VERSION}",
            f"Task: {BASELINE_PROMPT}",
            "Source excerpts:\n\n" + "\n\n".join(source_blocks),
        )
    )


def _format_span_block(repo_root: Path, span: Span) -> str:
    path = repo_root / span.path
    lines = path.read_text(encoding="utf-8").splitlines()
    excerpts = []
    for start, end in span.ranges:
        selected = lines[start - 1 : end]
        numbered = "\n".join(f"{line_number}: {line}" for line_number, line in zip(range(start, end + 1), selected))
        excerpts.append(f"lines {start}-{end}\n{numbered}")
    return f"source_id: {span.source_id}\nsource_path: {span.path}\n" + "\n\n".join(excerpts)
