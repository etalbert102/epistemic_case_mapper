from __future__ import annotations

import hashlib
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
    extraction_telemetry = {
        "stage": "deterministic_starter_extraction",
        "source_count": len(manifest.sources),
        "sources": [],
        "total_candidate_sentences": 0,
        "total_claims_created": 0,
        "total_skipped_short": 0,
        "total_skipped_no_marker": 0,
    }
    for source in manifest.sources:
        text = _source_text(source, repo_root)
        source_claims, source_telemetry = _claims_from_source(source, text, start_index=len(claims) + 1)
        claims.extend(source_claims)
        extraction_telemetry["sources"].append(source_telemetry)
        extraction_telemetry["total_candidate_sentences"] += source_telemetry["candidate_sentences"]
        extraction_telemetry["total_claims_created"] += source_telemetry["claims_created"]
        extraction_telemetry["total_skipped_short"] += source_telemetry["skipped_short"]
        extraction_telemetry["total_skipped_no_marker"] += source_telemetry["skipped_no_marker"]

    relations = _starter_relations(claims)
    open_questions = _starter_open_questions(manifest, claims)
    preservation_metadata = _preservation_metadata(manifest, repo_root)
    workflow_telemetry = {
        "extraction": extraction_telemetry,
        "relation_mapping": {
            "stage": "shared_tag_seed_relations",
            "relation_limit": 25,
            "relations_created": len(relations),
            "relation_types": sorted({relation.relation_type for relation in relations}),
        },
        "open_question_mapping": {
            "stage": "case_specific_seed_open_questions",
            "open_questions_created": len(open_questions),
            "linked_question_count": sum(
                1 for question in open_questions if question.linked_claim_ids or question.linked_source_ids
            ),
        },
    }
    return CaseMap(
        case_id=manifest.case_id,
        title=manifest.title,
        question=manifest.question,
        evidence_mode=manifest.evidence_mode,
        review_status=manifest.review_status,
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
            "preservation_metadata": preservation_metadata,
            "workflow_telemetry": workflow_telemetry,
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


def _preservation_metadata(manifest: CaseManifest, repo_root: Path) -> dict[str, object]:
    files = []
    key_requirements = []
    for relative_path in manifest.metadata_files:
        path = (repo_root / relative_path).resolve()
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        requirements = _extract_key_requirements(text)
        key_requirements.extend(requirements)
        files.append(
            {
                "path": relative_path,
                "title": _first_heading(text) or path.name,
                "exists": path.exists(),
                "headings": _headings(text),
                "key_requirements": requirements,
            }
        )
    return {
        "files": files,
        "key_requirements": key_requirements,
    }


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return None


def _headings(text: str) -> list[str]:
    return [line.lstrip("#").strip() for line in text.splitlines() if line.startswith("#")]


def _extract_key_requirements(text: str) -> list[str]:
    lines = text.splitlines()
    requirements: list[str] = []
    in_requirements = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_requirements = "preservation requirements" in stripped.lower()
            continue
        if in_requirements and stripped.startswith("- "):
            requirements.append(stripped.removeprefix("- ").strip())
    return requirements


def _claims_from_source(source: Source, text: str, *, start_index: int) -> tuple[list[Claim], dict[str, object]]:
    claims: list[Claim] = []
    normalized_text = _normalized_text(text)
    source_text_hash = _stable_hash(normalized_text)
    sentence_spans = _sentence_spans(normalized_text)
    telemetry = {
        "source_id": source.source_id,
        "source_text_hash": source_text_hash,
        "candidate_sentences": len(sentence_spans),
        "claims_created": 0,
        "skipped_short": 0,
        "skipped_no_marker": 0,
    }
    for sentence, start, end in sentence_spans:
        lowered = sentence.lower()
        if len(sentence.split()) < 8:
            telemetry["skipped_short"] += 1
            continue
        if not any(marker in lowered for marker in CLAIM_MARKERS):
            telemetry["skipped_no_marker"] += 1
            continue
        claim_id = f"claim_{start_index + len(claims):04d}"
        claims.append(
            Claim(
                claim_id=claim_id,
                text=sentence,
                source_id=source.source_id,
                source_span=f"normalized_chars:{start}-{end}",
                source_start=start,
                source_end=end,
                source_text_hash=source_text_hash,
                excerpt_hash=_stable_hash(sentence),
                extraction_method="deterministic_marker_sentence_v1",
                provenance_tag="local_source_text" if source.path or source.text else "local_seed_note",
                review_state="source_supported",
                entailed_by_excerpt="yes",
                claim_type=_classify_claim(sentence),
                confidence="low",
                tags=_tags(sentence),
            )
        )
    telemetry["claims_created"] = len(claims)
    return claims, telemetry


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def _sentence_spans(text: str) -> list[tuple[str, int, int]]:
    spans = []
    for match in re.finditer(r"[^.!?]+(?:[.!?]+|$)", text):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw) - len(raw.rstrip())
        sentence = raw.strip()
        if not sentence:
            continue
        start = match.start() + leading
        end = match.end() - trailing
        spans.append((sentence, start, end))
    return spans


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


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
                    rationale="Tentative seed relation from shared tags: " + ", ".join(sorted(shared_tags)),
                )
            )
            if len(relations) >= 25:
                return relations
    return relations


def _starter_open_questions(manifest: CaseManifest, claims: list[Claim]) -> list[OpenQuestion]:
    if manifest.case_id == "lhc_black_holes":
        return [
            OpenQuestion(
                question_id="oq_0001",
                text="Which assumptions make the natural cosmic-ray analogue valid or invalid for LHC conditions?",
                why_it_matters="The safety case depends on whether naturally occurring collisions cover the relevant collider-specific conditions.",
                linked_claim_ids=[claim.claim_id for claim in claims if "cosmic-ray" in claim.text.lower() or "naturally" in claim.text.lower()][:5],
                linked_source_ids=[source.source_id for source in manifest.sources],
                gap_type="crux",
            ),
            OpenQuestion(
                question_id="oq_0002",
                text="Which source-grounded evidence directly supports the claim that hypothetical microscopic black holes would evaporate quickly?",
                why_it_matters="The Hawking-radiation premise is a major dependency and should not be treated as settled by seed notes alone.",
                linked_claim_ids=[claim.claim_id for claim in claims if "evaporate" in claim.text.lower() or "hawking" in claim.text.lower()][:5],
                linked_source_ids=[source.source_id for source in manifest.sources if "safety" in source.source_id],
                gap_type="missing source needed",
            ),
            OpenQuestion(
                question_id="oq_0003",
                text="Which independent reviews, critiques, or public-risk arguments should be added before treating this as source-grounded?",
                why_it_matters="A useful FLF artifact should preserve why the concern seemed live to critics as well as why the final safety conclusion was reassuring.",
                linked_claim_ids=[claim.claim_id for claim in claims if "concern" in claim.text.lower() or "critic" in claim.text.lower() or "transparent" in claim.text.lower()][:5],
                linked_source_ids=[source.source_id for source in manifest.sources if "concern" in source.source_id],
                gap_type="missing source needed",
            ),
        ]
    if manifest.case_id == "eggs":
        return [
            OpenQuestion(
                question_id="oq_0001",
                text="Which findings depend on substitution context: what foods eggs replace or accompany?",
                why_it_matters="Egg guidance can change if eggs replace refined carbohydrates, processed meat, fish, legumes, or other protein sources.",
                linked_claim_ids=[claim.claim_id for claim in claims if "diet" in claim.text.lower() or "pattern" in claim.text.lower() or "replace" in claim.text.lower()][:5],
                linked_source_ids=[source.source_id for source in manifest.sources if "aha" in source.source_id or "nnr" in source.source_id],
                gap_type="crux",
            ),
            OpenQuestion(
                question_id="oq_0002",
                text="How should observational cardiovascular findings be weighted against randomized lipid-marker findings?",
                why_it_matters="The eggs case turns on whether clinical outcomes, residual confounding, or biomarker changes should carry more weight.",
                linked_claim_ids=[claim.claim_id for claim in claims if "cardiovascular" in claim.text.lower() or "ldl" in claim.text.lower() or "cholesterol" in claim.text.lower()][:5],
                linked_source_ids=[source.source_id for source in manifest.sources if "jama" in source.source_id or "bmj" in source.source_id or "li_2020" in source.source_id],
                gap_type="crux",
            ),
            OpenQuestion(
                question_id="oq_0003",
                text="Which populations need separate guidance, especially people with diabetes, high LDL cholesterol, or different baseline dietary patterns?",
                why_it_matters="A single global egg recommendation may erase heterogeneity across baseline risk, cholesterol response, and dietary context.",
                linked_claim_ids=[claim.claim_id for claim in claims if "diabetes" in claim.text.lower() or "population" in claim.text.lower() or "subgroup" in claim.text.lower()][:5],
                linked_source_ids=[source.source_id for source in manifest.sources],
                gap_type="population heterogeneity",
            ),
        ]
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
