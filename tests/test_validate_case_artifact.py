from pathlib import Path

from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.starter_mapper import build_starter_case_map


def test_lhc_case_map_has_required_metadata_and_open_questions() -> None:
    manifest = CaseManifest.model_validate(
        {
            "case_id": "lhc_black_holes",
            "title": "LHC",
            "question": "Why is the LHC risk low?",
            "case_type": "test",
            "sources": [
                {
                    "source_id": "cern_faq_seed",
                    "title": "Seed",
                    "source_type": "seed_notes",
                    "text": "The public safety argument suggests low risk because cosmic rays occur naturally.",
                },
                {
                    "source_id": "safety_review_seed",
                    "title": "Safety",
                    "source_type": "seed_notes",
                    "text": "Safety reviews argue that microscopic black holes would evaporate quickly under Hawking radiation assumptions.",
                },
                {
                    "source_id": "public_concern_seed",
                    "title": "Concern",
                    "source_type": "seed_notes",
                    "text": "Public concern focused on the risk that unprecedented experimental conditions could create hazards.",
                },
            ],
        }
    )

    case_map = build_starter_case_map(manifest, repo_root=Path("."))

    assert case_map.evidence_mode == "seed"
    assert case_map.review_status == "draft"
    assert len(case_map.open_questions) == 3
    assert all(question.linked_claim_ids or question.linked_source_ids or question.gap_type for question in case_map.open_questions)
