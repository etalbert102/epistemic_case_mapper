# LHC Source-Grounded Acquisition Plan

## Purpose

This plan defines the minimum source-acquisition work needed to upgrade `lhc_black_holes` from seed mode to source-grounded mode.

Current status: executed on 2026-06-26. Raw documents and extracted text were added under `data/cases/lhc_black_holes/sources/`, and the case manifest was updated to source-grounded mode.

Web use policy for this plan: allowed only when the user explicitly asks to execute this acquisition plan. When executed, record retrieval date for every web-acquired source and store source-local excerpts or local files so claims can be audited without repeating search.

## Minimum Source Set

The first source-grounded LHC demo should include at least these source classes:

1. Formal safety assessment.
2. Independent review or endorsement of the safety assessment.
3. Public-facing CERN explanation or FAQ.
4. Later empirical result or detector-search update.
5. Representative critique, concern, or legal/public-risk framing.

## Candidate Sources

### LSAG Safety Report

- Candidate source ID: `lsag_2008_safety_review`
- Title: `Review of the Safety of LHC Collisions`
- URL: `https://cds.cern.ch/record/1111112`
- Source type: `formal_safety_review`
- Candidate use: primary source for the formal safety argument, including cosmic-ray comparison, microscopic black hole discussion, Hawking-radiation premise, and astronomical-body stability arguments.
- Notes from lookup: CERN Document Server lists the report as `CERN-PH-TH-2008-136`, published in 2008, with DOI `10.1088/0954-3899/35/11/115004`.
- Retrieval date to record when ingested: required.

### CERN Scientific Policy Committee Review

- Candidate source ID: `spc_2008_lsag_review`
- Title: `SPC Report on LSAG Documents`
- URL: `https://indico.cern.ch/event/35065/contributions/1757729/attachments/693082/951703/SPC_on_LSAG_report.pdf`
- Source type: `independent_review`
- Candidate use: independent review layer; useful for distinguishing the LSAG argument from external endorsement and for identifying caveats about future colliders or assumptions.
- Notes from lookup: the report describes an SPC panel review of LSAG documents and summarizes endorsement of the LSAG conclusions.
- Retrieval date to record when ingested: required.

### CERN Public Black Hole Explanation

- Candidate source IDs: `cern_lhc_current_page`, `cern_tiny_black_holes_page`
- Titles: `Large Hadron Collider`; `Extra dimensions, gravitons, and tiny black holes`
- URLs: `https://home.cern/science/accelerators/large-hadron-collider/`; `https://home.cern/science/physics/extra-dimensions-gravitons-and-tiny-black-holes/`
- Source type: `public_explanation_current`
- Candidate use: public-facing explanation of the black-hole concern; useful for report readability and for comparing technical vs public framing.
- Notes from lookup: current CERN public pages expose the relevant public-facing black-hole claims more cleanly than the archived Angels & Demons FAQ.
- Retrieval date to record when ingested: required.

### CMS Microscopic Black Hole Search

- Candidate source ID: `cms_2011_black_hole_search`
- Title: `Search for microscopic black hole signatures at the Large Hadron Collider`
- URL: `https://cms.cern/news/search-microscopic-black-hole-signatures-large-hadron-collider`
- Source type: `experimental_result_public_summary`
- Candidate use: later empirical update showing how microscopic black-hole hypotheses were searched for in LHC data.
- Notes from lookup: CMS reports no experimental evidence for microscopic black holes in the described search and gives excluded mass ranges for tested models.
- Retrieval date to record when ingested: required.

### Public Concern Or Legal-Risk Framing

- Candidate source IDs: `plaga_2008_metastable_black_holes`, `johnson_2009_black_hole_case`
- Titles: `On the potential catastrophic risk from metastable quantum-black holes produced at particle colliders`; `The Black Hole Case: The Injunction Against the End of the World`
- URLs: `https://arxiv.org/abs/0808.1415`; `https://arxiv.org/abs/0912.5480`
- Source types: `technical_critique`; `legal_public_risk_framing`
- Candidate use: preserves why the case seemed live to critics and avoids presenting the final safety conclusion as if there were never a public decision problem.
- Retrieval date to record when ingested: required.

### Technical Response To Critique

- Candidate source ID: `giddings_mangano_2008_comments_plaga`
- Title: `Comments on claimed risk from metastable black holes`
- URL: `https://arxiv.org/abs/0808.4087`
- Source type: `technical_response`
- Candidate use: captures the direct response to Plaga's metastable-black-hole risk argument.
- Retrieval date to record when ingested: required.

## Acquisition Steps

1. Retrieve each source using web access.
2. Record URL, retrieval date, title, author or institution, publication date when available, source type, and relevance.
3. Store source-local excerpts in `data/cases/lhc_black_holes/case.yaml` or local files under `data/cases/lhc_black_holes/sources/`.
4. Replace seed sources with source-grounded sources or retain seed sources only under a clearly labeled background section.
5. Rebuild the case map.
6. Validate source-grounded mode.
7. Update `examples/lhc_black_holes/` snapshots.
8. Mark review status no stronger than `agent-reviewed` until human review occurs.

## Minimum Source-Grounded Done Criteria

- At least four source-grounded sources are present.
- Every web-acquired source has retrieval date.
- Every source-grounded claim has source ID and source-local span or excerpt marker.
- Seed sources are removed or clearly excluded from final scoring.
- Audit distinguishes direct source claims from inferred relations.
- The validator passes in source-grounded mode.
