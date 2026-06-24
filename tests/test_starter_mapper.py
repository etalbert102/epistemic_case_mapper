from pathlib import Path

from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.starter_mapper import build_starter_case_map


def test_starter_mapper_extracts_claims_and_relations() -> None:
    manifest = CaseManifest.model_validate(
        {
            "case_id": "demo",
            "title": "Demo",
            "question": "What matters?",
            "case_type": "test",
            "sources": [
                {
                    "source_id": "a",
                    "title": "A",
                    "text": "The risk depends on evidence about mechanism and uncertainty.",
                },
                {
                    "source_id": "b",
                    "title": "B",
                    "text": "The evidence suggests mechanism details change the risk assessment.",
                },
            ],
        }
    )

    case_map = build_starter_case_map(manifest, repo_root=Path("."))

    assert case_map.case_id == "demo"
    assert len(case_map.claims) == 2
    assert case_map.relations
    assert case_map.open_questions
