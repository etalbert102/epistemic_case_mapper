# Submission Artifact Summary

Status: `generated`

Purpose: provide quick counts for the FLF submission package. Regenerate with `PYTHONPATH=src python3 scripts/summarize_submission_artifacts.py`.

| Case | Sources | Claims | Relations | Relation types | Cruxes | Erosion losses | Blinded baselines |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| LHC black holes | 5 | 16 | 16 | challenges=4, crux_for=2, depends_on=1, in_tension_with=2, refines=2, similar_to=1, supports=4 | 3 | 6 | 4 |
| Eggs and health | 7 | 19 | 17 | crux_for=2, depends_on=2, in_tension_with=2, refines=8, similar_to=1, supports=2 | 3 | 7 | 4 |
| COVID origins slice | 7 | 18 | 15 | challenges=1, crux_for=2, depends_on=1, in_tension_with=3, refines=4, similar_to=1, supports=3 | 3 | 6 | 0 |

## Full-Case Coverage

| Case | Manifest sources | Full-case clusters | Full-case relations | Full-case files |
| --- | ---: | ---: | ---: | --- |
| LHC black holes | 10 | 9 | 4 | `examples/lhc_black_holes/full_case_index.md`, `examples/lhc_black_holes/full_case_map.md` |
| Eggs and health | 12 | 8 | 5 | `examples/eggs/full_case_index.md`, `examples/eggs/full_case_map.md` |

## Extension Artifacts

| Artifact | Case | File | Status |
| --- | --- | --- | --- |
| Full-case flat baseline | LHC black holes | `examples/lhc_black_holes/full_case_flat_synthesis_baseline.md` | illustrative, non-blinded |
| Full-case flat baseline | Eggs and health | `examples/eggs/full_case_flat_synthesis_baseline.md` | illustrative, non-blinded |
| Draft public-risk worked region | LHC black holes | `examples/lhc_black_holes/worked_region_public_risk_framing_map.md` | draft extension, not canonical counts |
| New-to-map source update demo | LHC black holes | `docs/NEW_SOURCE_UPDATE_DEMO.md` | demo from already acquired source |
| Self-assessment and limitations | Submission | `docs/FLF_SELF_ASSESSMENT_AND_LIMITATIONS.md` | human-review-needed |
| Human audit guide | Submission | `docs/HUMAN_AUDIT_GUIDE.md` | human-review-needed |
| Operational workflow and realism | Submission | `docs/OPERATIONAL_WORKFLOW_AND_REALISM.md` | human-review-needed |

## Totals

- Sources represented in worked regions: `19`
- Curated claims: `53`
- Relations: `48`
- Crux candidates: `9`
- Erosion findings: `19`
- Blinded local-model baselines: `8`
- Investigator task queue items: `10`

## Interpretation

These counts are not quality scores. They help judges verify that the submission includes source grounding, structured relations, cruxes, erosion findings, and multi-model comparators for the worked regions. Full-case coverage remains limited to LHC and eggs; the COVID artifact is a narrow worked region.
