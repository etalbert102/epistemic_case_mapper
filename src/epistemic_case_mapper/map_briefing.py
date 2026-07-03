from __future__ import annotations

from importlib import import_module

_SHARD_NAMES = [
    'epistemic_case_mapper.map_briefing_impl_1',
    'epistemic_case_mapper.map_briefing_impl_2',
    'epistemic_case_mapper.map_briefing_impl_3',
    'epistemic_case_mapper.map_briefing_impl_4',
    'epistemic_case_mapper.map_briefing_impl_5',
    'epistemic_case_mapper.map_briefing_impl_6',
    'epistemic_case_mapper.map_briefing_impl_7',
    'epistemic_case_mapper.map_briefing_impl_8',
    'epistemic_case_mapper.map_briefing_impl_9',
]

_SHARDS = [import_module(name) for name in _SHARD_NAMES]
_NAMESPACE = {}
for _module in _SHARDS:
    for _name, _value in _module.__dict__.items():
        if not _name.startswith("__"):
            _NAMESPACE[_name] = _value

for _module in _SHARDS:
    _module.__dict__.update(_NAMESPACE)

globals().update(_NAMESPACE)
__all__ = sorted(name for name in _NAMESPACE if not name.startswith("_"))

