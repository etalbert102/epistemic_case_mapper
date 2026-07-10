from __future__ import annotations

import json
from typing import Any


def build_memo_ready_packet_synthesis_prompt(memo_ready_packet: dict[str, Any]) -> str:
    return (
        "You are a senior decision analyst. Write a coherent decision memo from the memo-ready evidence packet.\n"
        "Use the packet as the complete evidence record, but write for a human decision-maker rather than exposing packet structure.\n"
        "The packet may include memo_obligations, a decision_synthesis_contract, analyst_decision_logic, analyst_argument_plan, and memo_warning_packet. Treat these as guidance for what matters, not as a rigid outline. Exercise analyst judgment about order, emphasis, merging, and compression.\n"
        "Write the best decision-ready answer the evidence supports. It is better to integrate a warning, caveat, or mandatory item by explaining its decision relevance than to restate it mechanically.\n"
        "Use memo_obligations as the writer-facing contract: satisfy required obligations in natural prose; use optional obligations only when they improve the decision read.\n"
        "Do not merely summarize or list evidence. Produce a decision read: answer, reason, counterweight, scope, uncertainty, and practical implication.\n\n"
        "Rules:\n"
        "- Answer the decision question directly in the first paragraph.\n"
        "- Preserve load-bearing quantities, source attributions, strongest support, strongest counterweights, and scope boundaries.\n"
        "- You may merge, reorder, compress, or omit low-value detail when doing so improves the memo and does not change the evidence-backed answer.\n"
        "- Use source labels where they help the reader audit a claim; do not cite every sentence mechanically.\n"
        "- When quantity_tuples are present, use those tuple labels instead of pairing estimates and intervals yourself.\n"
        "- If a quantity is marked ambiguous or unpaired, describe it without inventing an estimate/interval pair.\n"
        "- Explain what the key quantities mean for the decision; do not dump bare numbers.\n"
        "- Explain why the strongest support does or does not outweigh the strongest counterweight.\n"
        "- Name the conditions, subgroups, contexts, or assumptions that change the answer.\n"
        "- Include decision cruxes only when they sharpen the decision; translate uncertainty into a practical implication.\n"
        "- Do not mention packet schemas, item IDs, validation, telemetry, obligations, warnings, or internal pipeline machinery.\n"
        "- Avoid meta-commentary about what the memo needs to do; just make the point naturally.\n"
        "- Use natural Markdown and choose headings that fit the decision question.\n\n"
        "Suggested memo shape when it fits the case:\n"
        "## Decision Brief\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change the Answer\n"
        "## Decision-Relevant Evidence\n"
        "## Sources\n\n"
        "Memo-ready packet:\n"
        f"{json.dumps(memo_ready_packet, indent=2, ensure_ascii=False)}\n"
    )
