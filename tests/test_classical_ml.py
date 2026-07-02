from __future__ import annotations

from epistemic_case_mapper.classical_ml import tfidf_near_duplicate_pairs, weighted_pagerank


def test_tfidf_near_duplicate_pairs_catches_paraphrase_like_overlap() -> None:
    pairs = tfidf_near_duplicate_pairs(
        [
            "The trial measured LDL cholesterol biomarkers rather than cardiovascular events.",
            "The trial measured LDL biomarkers instead of cardiovascular event outcomes.",
            "The guideline process weighs broader policy considerations.",
        ],
        ["c001", "c002", "c003"],
        threshold=0.25,
    )

    assert pairs[0][0:2] == ("c001", "c002")
    assert pairs[0][2] > 0.25


def test_weighted_pagerank_prefers_claim_connected_by_stronger_edges() -> None:
    ranks = weighted_pagerank(
        ["c001", "c002", "c003"],
        [
            ("c001", "c002", 3.0),
            ("c002", "c003", 1.0),
        ],
    )

    assert ranks["c002"] > ranks["c001"]
    assert ranks["c002"] > ranks["c003"]

