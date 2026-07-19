from pathlib import Path

from epistemic_case_mapper import (
    case_initializer,
    evidence_bundles,
    map_briefing,
    semantic_pipeline,
    source_intake_filter,
    staged_semantic_pipeline,
    starter_mapper,
)
from epistemic_case_mapper.pipeline.briefing import map_briefing_pipeline
from epistemic_case_mapper.pipeline.documents import (
    case_initializer as documents_case_initializer,
    evidence_bundles as documents_evidence_bundles,
    source_intake_filter as documents_source_intake_filter,
)
from epistemic_case_mapper.pipeline.map import (
    semantic_pipeline as map_semantic_pipeline,
    staged_semantic_pipeline_runner,
    starter_mapper as map_starter_mapper,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "epistemic_case_mapper"


def test_pipeline_directories_match_persisted_stage_handoffs() -> None:
    stage_root = PACKAGE_ROOT / "pipeline"
    actual = {
        path.name
        for path in stage_root.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    assert actual == {"documents", "map", "briefing"}
    assert all((stage_root / stage / "__init__.py").exists() for stage in actual)


def test_stage_implementations_are_not_left_flat_at_package_root() -> None:
    assert not list(PACKAGE_ROOT.glob("map_briefing_*.py"))
    assert [path.name for path in PACKAGE_ROOT.glob("staged_semantic_*.py")] == [
        "staged_semantic_pipeline.py"
    ]


def test_public_facades_delegate_to_their_stage_implementations() -> None:
    assert case_initializer.init_case_package is documents_case_initializer.init_case_package
    assert evidence_bundles.normalize_assertion_bundles is documents_evidence_bundles.normalize_assertion_bundles
    assert source_intake_filter.run_source_intake_filter is documents_source_intake_filter.run_source_intake_filter
    assert semantic_pipeline.build_map_prompt is map_semantic_pipeline.build_map_prompt
    assert starter_mapper.build_starter_case_map is map_starter_mapper.build_starter_case_map
    assert staged_semantic_pipeline.run_staged_map is staged_semantic_pipeline_runner.run_staged_map
    assert map_briefing.run_map_briefing is map_briefing_pipeline.run_map_briefing
