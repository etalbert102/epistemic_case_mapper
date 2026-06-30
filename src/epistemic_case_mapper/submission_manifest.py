from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from epistemic_case_mapper.io import read_yaml


DEFAULT_MANIFEST_PATH = "submission_manifest.yaml"


class ValidationThresholds(BaseModel):
    min_claims: int = 12
    max_claims: int = 25
    min_relation_types: int = 3
    min_crux_mentions: int = 2
    min_evidence_rows: int = 4
    min_losses: int = 5
    min_surviving_checks: int = 5
    min_baseline_words: int = 250


class ReviewPriority(BaseModel):
    worked_region_id: str
    claim_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    loss_ids: list[str] = Field(default_factory=list)
    selection_strategy: str = "explicit"


class SourceSpan(BaseModel):
    source_id: str
    path: str
    ranges: list[tuple[int, int]]


class BlindedBaseline(BaseModel):
    title: str
    question: str
    output_path: str
    required_sources: list[str] = Field(default_factory=list)
    spans: list[SourceSpan] = Field(default_factory=list)
    min_words: int = 300


class WorkedRegion(BaseModel):
    case_key: str
    case_label: str
    region_id: str
    id_prefix: str
    definition_path: str
    map_path: str
    audit_path: str
    baseline_path: str
    best_path: str
    output_json_path: str
    required_sources: list[str] = Field(default_factory=list)
    thresholds: ValidationThresholds = Field(default_factory=ValidationThresholds)
    review: ReviewPriority | None = None
    blinded_baseline: BlindedBaseline | None = None


class FullCaseScaffold(BaseModel):
    index_path: str
    map_path: str
    worked_anchor: str
    min_clusters: int = 5
    min_relations: int = 4
    baseline_path: str | None = None


class TaskQueue(BaseModel):
    path: str
    prefix: str
    min_tasks: int = 5


class UiSpotlight(BaseModel):
    distinction: str
    flat: str
    map: str
    status: str


class UiConfig(BaseModel):
    include: bool = False
    label: str | None = None
    short_label: str | None = None
    theme: str = "default"
    review_packet_path: str | None = None
    review_checklist_path: str | None = None
    spotlights: list[UiSpotlight] = Field(default_factory=list)


class SubmissionCase(BaseModel):
    case_key: str
    case_id: str
    label: str
    case_path: str
    examples_path: str | None = None
    build_starter: bool = False
    full_case: FullCaseScaffold | None = None
    task_queue: TaskQueue | None = None
    ui: UiConfig = Field(default_factory=UiConfig)
    worked_regions: list[WorkedRegion] = Field(default_factory=list)


class ExtensionArtifact(BaseModel):
    artifact: str
    case: str
    path: str
    status: str


class UpdateDemo(BaseModel):
    demo_id: str
    case_key: str
    path: str
    claim_id_prefix: str
    relation_id_prefix: str


class SubmissionManifest(BaseModel):
    schema_version: int = 1
    judge_paths: list[str] = Field(default_factory=list)
    required_docs: list[str] = Field(default_factory=list)
    reference_scan_paths: list[str] = Field(default_factory=list)
    extension_artifacts: list[ExtensionArtifact] = Field(default_factory=list)
    update_demos: list[UpdateDemo] = Field(default_factory=list)
    cases: list[SubmissionCase] = Field(default_factory=list)

    def iter_worked_regions(self) -> list[WorkedRegion]:
        regions: list[WorkedRegion] = []
        for case in self.cases:
            regions.extend(case.worked_regions)
        return regions

    def iter_full_cases(self) -> list[tuple[SubmissionCase, FullCaseScaffold]]:
        return [(case, case.full_case) for case in self.cases if case.full_case is not None]

    def iter_task_queues(self) -> list[tuple[SubmissionCase, TaskQueue]]:
        return [(case, case.task_queue) for case in self.cases if case.task_queue is not None]

    def iter_ui_cases(self) -> list[SubmissionCase]:
        return [case for case in self.cases if case.ui.include]

    def iter_starter_cases(self) -> list[SubmissionCase]:
        return [case for case in self.cases if case.build_starter and case.examples_path]

    def iter_blinded_baselines(self) -> list[tuple[WorkedRegion, BlindedBaseline]]:
        baselines: list[tuple[WorkedRegion, BlindedBaseline]] = []
        for region in self.iter_worked_regions():
            if region.blinded_baseline is not None:
                baselines.append((region, region.blinded_baseline))
        return baselines

    def case_for_key(self, case_key: str) -> SubmissionCase:
        for case in self.cases:
            if case.case_key == case_key:
                return case
        raise KeyError(case_key)

    def region_for_id(self, region_id: str) -> WorkedRegion:
        for region in self.iter_worked_regions():
            if region.region_id == region_id:
                return region
        raise KeyError(region_id)

    def known_id_prefixes(self) -> set[str]:
        return {region.id_prefix for region in self.iter_worked_regions()}


def load_submission_manifest(repo_root: Path, manifest_path: str | Path = DEFAULT_MANIFEST_PATH) -> SubmissionManifest:
    path = Path(manifest_path)
    if not path.is_absolute():
        path = repo_root / path
    return SubmissionManifest.model_validate(read_yaml(path))
