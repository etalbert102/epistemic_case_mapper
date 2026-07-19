from pathlib import Path

from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.pipeline.map.starter_mapper import build_starter_case_map


def test_lhc_case_map_has_required_metadata_and_open_questions() -> None:
    manifest = CaseManifest.model_validate(
        {
            "case_id": "lhc_black_holes",
            "title": "LHC",
            "question": "Why is the LHC risk low?",
            "case_type": "test",
            "open_question_templates": [
                {
                    "question_id": "oq_0001",
                    "text": "Which assumptions make the natural analogue valid?",
                    "why_it_matters": "The top-level conclusion depends on this.",
                    "claim_keywords": ["naturally"],
                    "gap_type": "crux",
                },
                {
                    "question_id": "oq_0002",
                    "text": "Which evidence supports quick evaporation?",
                    "why_it_matters": "This is a major dependency.",
                    "claim_keywords": ["evaporate", "hawking"],
                    "source_id_keywords": ["safety"],
                    "gap_type": "missing source needed",
                },
                {
                    "question_id": "oq_0003",
                    "text": "Which critiques should be added?",
                    "why_it_matters": "The map should preserve public concern and critique.",
                    "claim_keywords": ["concern"],
                    "source_id_keywords": ["concern"],
                    "gap_type": "missing source needed",
                },
            ],
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
