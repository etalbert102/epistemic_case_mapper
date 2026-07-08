from __future__ import annotations

import json

from epistemic_case_mapper.model_outputs import canonical_json_output


def test_canonical_json_output_accepts_fenced_json() -> None:
    canonical = canonical_json_output('```json\n{"edits":[{"target":"a","replacement":"b"}]}\n```')

    assert json.loads(canonical) == {"edits": [{"target": "a", "replacement": "b"}]}


def test_canonical_json_output_escapes_raw_newlines_inside_strings() -> None:
    raw = '```json\n{"edits":[{"target":"a","replacement":"first line\n* second line"}]}\n```'

    canonical = canonical_json_output(raw)

    assert json.loads(canonical)["edits"][0]["replacement"] == "first line\n* second line"
