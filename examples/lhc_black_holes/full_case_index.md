# LHC Black Hole Risk Full-Case Index

Status: `broad-source-scaffold`

Purpose: provide a full-case navigation layer over all currently acquired LHC sources. The worked region `lhc_cosmic_ray_argument` remains the deeper curated anchor.

## Case Question

Why did investigators conclude that LHC operation would not create a catastrophic black hole risk?

## Source Coverage

| Source ID | Role In Full Case | Current Use |
| --- | --- | --- |
| `lsag_2008_safety_review` | formal safety assessment | central safety argument, natural exposure, exotic-risk categories |
| `spc_2008_lsag_review` | independent review | review endorsement, scope caveats, decision readiness |
| `giddings_mangano_2008_stable_black_holes` | technical safety analysis | stable black-hole assumptions, astrophysical constraints |
| `cern_lhc_current_page` | public explanation | current public-facing settled view |
| `cern_tiny_black_holes_page` | public explanation | extra dimensions, tiny black holes, rapid decay framing |
| `cms_2011_black_hole_search` | public experimental update | later search summary and no-signal communication |
| `cms_2010_black_hole_search_paper` | technical experimental result | model-specific empirical search evidence |
| `plaga_2008_metastable_black_holes` | technical critique | residual-risk challenge and operational caution |
| `giddings_mangano_2008_comments_plaga` | technical response | rebuttal to critique and assumption consistency |
| `johnson_2009_black_hole_case` | legal/public-risk framing | governance, injunction, and catastrophic-risk decision context |

## Full-Case Cluster Index

| Cluster ID | Topic | Primary Sources | Review Priority |
| --- | --- | --- | --- |
| `lhc_full_cluster_001` | Institutional safety conclusion | `lsag_2008_safety_review`, `spc_2008_lsag_review` | high |
| `lhc_full_cluster_002` | Natural cosmic-ray exposure | `lsag_2008_safety_review`, `giddings_mangano_2008_stable_black_holes`, `spc_2008_lsag_review` | worked-region anchor |
| `lhc_full_cluster_003` | Hawking radiation and independent decay | `lsag_2008_safety_review`, `spc_2008_lsag_review`, `cern_tiny_black_holes_page` | high |
| `lhc_full_cluster_004` | Stable black-hole worst-case assumptions | `giddings_mangano_2008_stable_black_holes`, `spc_2008_lsag_review` | high |
| `lhc_full_cluster_005` | Compact-star bounds | `giddings_mangano_2008_stable_black_holes`, `spc_2008_lsag_review` | worked-region anchor |
| `lhc_full_cluster_006` | Critique and technical response | `plaga_2008_metastable_black_holes`, `giddings_mangano_2008_comments_plaga` | worked-region anchor |
| `lhc_full_cluster_007` | Later empirical searches | `cms_2010_black_hole_search_paper`, `cms_2011_black_hole_search` | medium |
| `lhc_full_cluster_008` | Public communication | `cern_lhc_current_page`, `cern_tiny_black_holes_page`, `cms_2011_black_hole_search` | medium |
| `lhc_full_cluster_009` | Legal and governance framing | `johnson_2009_black_hole_case` | medium |

## Best Current Anchor

- Deep worked map: `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
- Full broad map: `examples/lhc_black_holes/full_case_map.md`
- Erosion audit anchor: `examples/lhc_black_holes/decision_space_erosion_audit.md`

## Immediate Human Review Path

1. Confirm each source appears in the correct cluster.
2. Review the worked-region anchor before reviewing broader clusters.
3. Check whether CMS search evidence is kept separate from safety-proof evidence.
4. Check whether Johnson's legal framing is kept separate from physics evidence.
5. Add any missing sources or critique threads before treating this as full-case reviewed.
