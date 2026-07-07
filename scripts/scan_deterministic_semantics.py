from __future__ import annotations

import argparse
from pathlib import Path

from epistemic_case_mapper.deterministic_semantic_audit import (
    render_semantic_audit_markdown,
    scan_deterministic_semantic_decisions,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan deterministic code for semantic-decision hotspots.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--output", help="Optional Markdown output path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    findings = scan_deterministic_semantic_decisions([repo_root / "src" / "epistemic_case_mapper"])
    markdown = render_semantic_audit_markdown(findings, repo_root=repo_root)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
