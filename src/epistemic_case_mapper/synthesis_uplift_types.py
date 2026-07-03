from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Loss:
    loss_id: str
    loss_type: str
    lost_item: str
    flat_baseline_omission: str
    case_map_preserves: str


@dataclass(frozen=True)
class RewriteRequirement:
    requirement_id: str
    loss_id: str
    loss_type: str
    instruction: str
    claim_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]
    source_refs: tuple[str, ...]
    claim_anchors: tuple[str, ...]
    relation_anchors: tuple[str, ...]
    required_phrases: tuple[str, ...]
    required_terms: tuple[str, ...]
    claim_roles: tuple[str, ...] = ()
    relation_types: tuple[str, ...] = ()
    relation_rationales: tuple[str, ...] = ()
    reader_anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class PacketSlot:
    section: str
    text: str
    requirement_id: str
    loss_id: str
