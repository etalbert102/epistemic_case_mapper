from __future__ import annotations

import json
from typing import Any

from epistemic_case_mapper.map_briefing_section_prompt_contract import (
    model_facing_section_contract,
    model_facing_section_markdown,
)
from epistemic_case_mapper.map_briefing_section_quality_prompt import section_quality_guidance


def section_rewrite_prompt(section: dict[str, str], contract: dict[str, Any], *, previous_title: str, next_title: str) -> str:
    model_contract = model_facing_section_contract(contract)
    model_section = model_facing_section_markdown(section["markdown"], contract)
    quality_guidance = section_quality_guidance(model_contract)
    return (
        "You are an analyst producing decision-ready analysis for one section of a source-grounded decision memo.\n"
        "Your job is to help a thoughtful reader decide what follows from the evidence, not to mechanically restate the packet.\n"
        "Rewrite only the supplied section. You may reorganize and synthesize within this section, but do not add facts.\n"
        "Use only the allowed information in model_section_packet and validation_obligations. If a fact is not present there or in the supplied deterministic draft, leave it out.\n"
        "Use model_section_packet as the primary structure: section_thesis, primary_evidence, contrast_evidence, boundary_evidence, contextual_evidence, local_tensions, canonical_cruxes, and must_include_quantities define the section's job.\n"
        "Treat primary_evidence as the load-bearing working set; use contrast_evidence to surface counterweights or cruxes; use boundary_evidence to define where the answer does and does not travel; use contextual_evidence only when it clarifies this section's distinct analytic move.\n"
        "When evidence appears in multiple sections, use section_use_projections and the role-aware evidence groups to decide what distinct value this section adds. Do not repeat a source summary unless it performs this section's assigned section_use.\n"
        "When model_section_packet includes must_include_quantities, use one relevant estimate in evidence-bearing sections instead of only qualitative phrasing.\n"
        "Apply evidence-weight discipline: say which evidence is doing the most work, which evidence weakens or bounds it, and which inputs are indirect, weak, role-inferred, appendix-only, or otherwise lower weight.\n"
        "Do not turn low-weight or indirect evidence into broad practical advice. Use calibrated verbs such as suggests, bounds, weakens, or is consistent with when the packet marks evidence as weak or indirect.\n"
        "In evidence-bearing sections, prefer a compact analytic progression over a list: load-bearing support, counterweight, scope or method limit, then the implication for this section.\n"
        "Preserve every required local evidence anchor, gap, confidence line, crux item, and main-memo obligation in the section contract.\n"
        "For each validation_obligations.required_main_memo_obligations item, include one listed search term exactly when search_terms are provided; otherwise use a faithful source-grounded paraphrase of its statement.\n"
        "Use owned_evidence only as the compatibility view of the role-aware working set; do not let it override the more specific primary, contrast, boundary, contextual, and do_not_use evidence groups.\n"
        "Do not invent or abbreviate citation labels. Avoid parenthetical source labels unless the exact label already appears in the deterministic draft or section contract.\n"
        "Return only the rewritten section as regular Markdown. Start with exactly the same ## heading and do not include any other top-level ## section.\n"
        "Do not wrap the answer in JSON or a code fence; the validator will check evidence coverage after generation.\n\n"
        f"Previous section heading: {previous_title or 'none'}\n"
        f"Next section heading: {next_title or 'none'}\n\n"
        "Evidence-quality guidance for this section:\n"
        f"{quality_guidance}\n\n"
        "Section contract:\n"
        f"{json.dumps(model_contract, indent=2, ensure_ascii=False)}\n\n"
        "The section below is the deterministic draft to improve using the section synthesis packet.\n"
        "Section to rewrite:\n"
        f"{model_section.strip()}\n"
    )
