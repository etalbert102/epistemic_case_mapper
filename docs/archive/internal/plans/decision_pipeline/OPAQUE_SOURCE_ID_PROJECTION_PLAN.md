# Plan: Opaque Source IDs For Memo-Ready Synthesis

## Objective
Use deterministic opaque source IDs as the citation keys in memo-ready packets so model synthesis and source-binding validation can rely on exact, citation-safe identifiers. Preserve descriptive source identity as metadata for debugging and final reader-facing source labels.

## Current Gap
Memo drafts currently cite descriptive source IDs and final presentation replaces them with labels such as `Zhong et al. 2019`. Final validation can then split citations at `et al.` and incorrectly report missing source binding. Descriptive IDs are useful upstream, but they are not ideal as model-facing citation tokens.

## Design
- Apply the change at the active memo-ready packet boundary.
- Generate stable opaque IDs from the original source identity, e.g. `SRC_F4K2P9QX`.
- Replace `source_id` and `source_ids` fields in the memo-ready packet with those opaque IDs.
- Preserve the original descriptive value in `source_slug` and `original_source_id`.
- Preserve source labels, display labels, URLs, and citation labels for final presentation.
- Teach source alias utilities to treat `source_slug` and `original_source_id` as aliases for the new source ID.
- Rebuild canonical source-weight quality reports after projection.

## Non-Goals
- Do not rewrite upstream maps, ledgers, or source extraction artifacts.
- Do not remove human-readable source metadata.
- Do not rely on random keys; keys must be deterministic across runs for the same original source identity.

## Validation
- Unit test projection idempotence, stable key shape, and preservation of old IDs as aliases.
- Unit test that final presentation maps opaque citations to readable labels.
- Run source-weighting and presentation tests.
- Run the full test suite.

## Generalizability Checks
- The key generator must not depend on case-specific vocabularies.
- Packets with missing source IDs must still get stable IDs from source labels.
- Re-running projection must not change keys or duplicate metadata.
