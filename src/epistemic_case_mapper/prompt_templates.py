from __future__ import annotations

import json
from typing import Any


def render_prompt(*sections: tuple[str, str | list[str] | dict[str, Any]]) -> str:
    rendered: list[str] = []
    for title, body in sections:
        text = _section_text(body)
        if not text.strip():
            continue
        rendered.extend((f"# {title}", "", text.strip(), ""))
    return "\n".join(rendered).strip() + "\n"


def json_schema_block(schema: dict[str, Any]) -> str:
    return "Return only JSON matching this schema:\n" + json.dumps(schema, indent=2, ensure_ascii=False)


def xml_block(tag: str, body: str) -> str:
    return f"<{tag}>\n{body.strip()}\n</{tag}>"


def examples_block(examples: list[dict[str, Any]]) -> str:
    blocks = []
    for index, example in enumerate(examples, start=1):
        blocks.append(xml_block(f"example_{index}", json.dumps(example, indent=2, ensure_ascii=False)))
    return "\n\n".join(blocks)


def _section_text(body: str | list[str] | dict[str, Any]) -> str:
    if isinstance(body, str):
        return body
    if isinstance(body, list):
        return "\n".join(str(item) for item in body)
    return json.dumps(body, indent=2, ensure_ascii=False)
