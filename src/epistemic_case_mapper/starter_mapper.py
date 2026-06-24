from __future__ import annotations

import re
from pathlib import Path

from epistemic_case_mapper.schema import CaseManifest, CaseMap, Claim, OpenQuestion, Relation, Source


CLAIM_MARKERS = (
    "because",
    "therefore",
    "suggests",
    "argues",
    "evidence",
    "risk",
    "uncertain",
    "depends",
    "however",
    "but",
    "although",
)


def build_starter_case_map(manifest: CaseManifest, *, repo_root: Path) -> CaseMap:
    claims: list[Claim] = []
    for source in manifest.sources:
        text = _source_text(source, repo_root)
        claims.extend(_claims_from_source(source, text, start_index=len(claims) + 1))

    relations = _starter_relations(claims)
    open_questions = _starter_open_questions(manifest, claims)
    return CaseMap(
        case_id=manifest.case_id,
        title=manifest.title,
        question=manifest.question,
        sources=manifest.sources,
        claims=claims,
        relations=relations,
        open_questions=open_questions,
        audit_notes=[
            "Starter map is deterministic and intentionally conservative.",
            "Claims are heuristic candidates; human/AI workflow should classify, merge, and audit them.",
            "Relations are seed links only and should not be treated as settled assessment.",
        ],
        metadata={
            "builder": "starter_mapper_v0",
            "source_count": len(manifest.sources),
            "claim_count": len(claims),
            "relation_count": len(relations),
        },
    )


def _source_text(source: Source, repo_root: Path) -> str:
    if source.text:
        return source.text
    if source.path:
        path = (repo_root / source.path).resolve()
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return source.notes or ""


def _claims_from_source(source: Source, text: str, *, start_index: int) -> list[Claim]:
    claims: list[Claim] = []
    sentences = _sentences(text)
    for sentence in sentences:
        lowered = sentence.lower()
        if len(sentence.split()) < 8:
            continue
        if not any(marker in lowered for marker in CLAIM_MARKERS):
            continue
        claim_id = f"claim_{start_index + len(claims):04d}"
        claims.append(
            Claim(
                claim_id=claim_id,
                text=sentence,
                source_id=source.source_id,
                source_span="heuristic_sentence",
                claim_type=_classify_claim(sentence),
                confidence="low",
                tags=_tags(sentence),
            )
        )
    return claims


def _sentences(text: str) -> list[str]:
    compact = " ".join(text.split())
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", compact) if part.strip()]


def _classify_claim(sentence: str) -> str:
    lowered = sentence.lower()
    if "risk" in lowered or "hazard" in lowered:
        return "risk_claim"
    if "evidence" in lowered or "data" in lowered or "study" in lowered:
        return "evidence_claim"
    if "because" in lowered or "therefore" in lowered or "depends" in lowered:
        return "inference_claim"
    if "however" in lowered or "but" in lowered or "although" in lowered:
        return "counterpoint_or_caveat"
    return "substantive_claim"


def _tags(sentence: str) -> list[str]:
    lowered = sentence.lower()
    tags = []
    for marker in ("risk", "evidence", "uncertainty", "mechanism", "method", "population", "crux"):
        if marker in lowered:
            tags.append(marker)
    return tags


def _starter_relations(claims: list[Claim]) -> list[Relation]:
    relations: list[Relation] = []
    for index, left in enumerate(claims):
        for right in claims[index + 1 :]:
            if left.source_id == right.source_id:
                continue
            shared_tags = set(left.tags) & set(right.tags)
            if not shared_tags:
                continue
            relations.append(
                Relation(
                    relation_id=f"rel_{len(relations) + 1:04d}",
                    source_claim_id=left.claim_id,
                    target_claim_id=right.claim_id,
                    relation_type="similar_to",
                    rationale="Seed relation from shared tags: " + ", ".join(sorted(shared_tags)),
                )
            )
            if len(relations) >= 25:
                return relations
    return relations


def _starter_open_questions(manifest: CaseManifest, claims: list[Claim]) -> list[OpenQuestion]:
    return [
        OpenQuestion(
            question_id="oq_0001",
            text="Which claims are cruxes for the top-level question?",
            why_it_matters="Crux identification determines what further investigation would most change the case map.",
            linked_claim_ids=[claim.claim_id for claim in claims[:5]],
        ),
        OpenQuestion(
            question_id="oq_0002",
            text="What important source types or perspectives are missing from the current manifest?",
            why_it_matters="The map should surface missing evidence rather than perform false closure.",
        ),
    ]
