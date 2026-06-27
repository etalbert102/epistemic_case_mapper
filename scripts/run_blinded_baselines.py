from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


BASELINE_PROMPT_VERSION = "flat_baseline_prompt_v1_blinded_ollama"
BASELINE_PROMPT = (
    "Using only the listed source excerpts for this worked region, write a concise synthesis "
    "that answers the region question for an informed reader. Preserve important caveats "
    "where they affect the answer, but do not create a structured claim map."
)


@dataclass(frozen=True)
class Span:
    source_id: str
    path: str
    ranges: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class BaselineConfig:
    case_key: str
    region_id: str
    title: str
    question: str
    output_path: str
    required_sources: tuple[str, ...]
    spans: tuple[Span, ...]


CONFIGS = {
    "lhc": BaselineConfig(
        case_key="lhc",
        region_id="lhc_cosmic_ray_argument",
        title="LHC Blinded Flat Synthesis Baseline",
        question=(
            "Does the cosmic-ray safety argument, including compact-star variants and critiques, "
            "rule out decision-relevant LHC microscopic-black-hole risk?"
        ),
        output_path="examples/lhc_black_holes/blinded_flat_synthesis_baseline_gemma4.md",
        required_sources=(
            "lsag_2008_safety_review",
            "spc_2008_lsag_review",
            "giddings_mangano_2008_stable_black_holes",
            "plaga_2008_metastable_black_holes",
            "giddings_mangano_2008_comments_plaga",
        ),
        spans=(
            Span(
                "lsag_2008_safety_review",
                "data/cases/lhc_black_holes/sources/text/lsag_2008_safety_review.txt",
                ((119, 138), (175, 183), (193, 207), (292, 350)),
            ),
            Span(
                "spc_2008_lsag_review",
                "data/cases/lhc_black_holes/sources/text/spc_2008_lsag_review.txt",
                ((43, 72), (101, 140), (167, 178)),
            ),
            Span(
                "giddings_mangano_2008_stable_black_holes",
                "data/cases/lhc_black_holes/sources/text/giddings_mangano_2008_stable_black_holes.txt",
                ((2402, 2411), (2415, 2460), (2465, 2508), (3600, 3641), (3710, 3716)),
            ),
            Span(
                "plaga_2008_metastable_black_holes",
                "data/cases/lhc_black_holes/sources/text/plaga_2008_metastable_black_holes.txt",
                ((18, 31), (94, 107), (421, 430), (439, 498), (563, 606)),
            ),
            Span(
                "giddings_mangano_2008_comments_plaga",
                "data/cases/lhc_black_holes/sources/text/giddings_mangano_2008_comments_plaga.txt",
                ((39, 46), (61, 105)),
            ),
        ),
    ),
    "eggs": BaselineConfig(
        case_key="eggs",
        region_id="eggs_observational_vs_rct",
        title="Eggs Blinded Flat Synthesis Baseline",
        question=(
            "How should a synthesis preserve the relationship between observational CVD outcome "
            "evidence, randomized lipid-marker evidence, guideline framing, and population/context "
            "caveats for egg consumption?"
        ),
        output_path="examples/eggs/blinded_flat_synthesis_baseline_gemma4.md",
        required_sources=(
            "dga_2020_2025_pmc_summary",
            "aha_2019_dietary_cholesterol_pubmed",
            "aha_2023_dietary_cholesterol_news",
            "bmj_2020_egg_consumption_cvd",
            "jama_2019_dietary_cholesterol_eggs",
            "li_2020_egg_cholesterol_rct_meta",
            "nnr_2023_eggs_scoping_review",
        ),
        spans=(
            Span(
                "dga_2020_2025_pmc_summary",
                "data/cases/eggs/sources/text/dga_2020_2025_pmc_summary.txt",
                ((31, 37), (45, 60), (73, 86)),
            ),
            Span(
                "aha_2019_dietary_cholesterol_pubmed",
                "data/cases/eggs/sources/text/aha_2019_dietary_cholesterol_pubmed.txt",
                ((122, 124),),
            ),
            Span(
                "aha_2023_dietary_cholesterol_news",
                "data/cases/eggs/sources/text/aha_2023_dietary_cholesterol_news.txt",
                ((39, 71),),
            ),
            Span(
                "bmj_2020_egg_consumption_cvd",
                "data/cases/eggs/sources/text/bmj_2020_egg_consumption_cvd_pmc.txt",
                ((40, 43), (238, 241), (524, 544)),
            ),
            Span(
                "jama_2019_dietary_cholesterol_eggs",
                "data/cases/eggs/sources/text/jama_2019_dietary_cholesterol_eggs_pmc.txt",
                ((33, 52), (70, 73), (367, 383), (471, 484)),
            ),
            Span(
                "li_2020_egg_cholesterol_rct_meta",
                "data/cases/eggs/sources/text/li_2020_egg_cholesterol_rct_meta_pmc.txt",
                ((30, 36), (188, 201), (207, 207), (279, 293)),
            ),
            Span(
                "nnr_2023_eggs_scoping_review",
                "data/cases/eggs/sources/text/nnr_2023_eggs_scoping_review_pmc.txt",
                ((30, 52), (600, 617)),
            ),
        ),
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate blinded flat-synthesis baselines with Ollama.")
    parser.add_argument("--case", choices=["all", *CONFIGS.keys()], default="all")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompts and write no output; useful for checking isolation.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    selected = CONFIGS.values() if args.case == "all" else (CONFIGS[args.case],)
    for config in selected:
        prompt = build_prompt(repo_root, config)
        if args.dry_run:
            print(f"\n--- {config.region_id} prompt ---\n{prompt}")
            continue
        output = _clean_model_output(_run_ollama(args.model, prompt))
        _write_baseline(repo_root, config, args.model, output)
        print(f"Wrote {config.output_path}")
    return 0


def build_prompt(repo_root: Path, config: BaselineConfig) -> str:
    source_blocks = []
    for span in config.spans:
        source_blocks.append(_format_span_block(repo_root, span))
    return "\n\n".join(
        (
            "You are writing a blinded flat synthesis baseline.",
            "Do not create a claim map, relation map, audit, or critique of a map.",
            f"Worked region question: {config.question}",
            f"Prompt version: {BASELINE_PROMPT_VERSION}",
            f"Task: {BASELINE_PROMPT}",
            "Source excerpts:\n\n" + "\n\n".join(source_blocks),
        )
    )


def _format_span_block(repo_root: Path, span: Span) -> str:
    path = repo_root / span.path
    lines = path.read_text(encoding="utf-8").splitlines()
    excerpts = []
    for start, end in span.ranges:
        selected = lines[start - 1 : end]
        numbered = "\n".join(f"{line_number}: {line}" for line_number, line in zip(range(start, end + 1), selected))
        excerpts.append(f"lines {start}-{end}\n{numbered}")
    return f"source_id: {span.source_id}\nsource_path: {span.path}\n" + "\n\n".join(excerpts)


def _run_ollama(model: str, prompt: str) -> str:
    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def _clean_model_output(output: str) -> str:
    output = _render_terminal_rewrites(output)
    output = re.sub(r"(?is)^\s*Thinking\.\.\..*?\.\.\.done thinking\.\s*", "", output).strip()
    return output


def _render_terminal_rewrites(text: str) -> str:
    rendered: list[str] = []
    cursor = 0
    index = 0
    while index < len(text):
        if text.startswith("\x1b[", index):
            match = re.match(r"\x1b\[([0-9;?]*)([A-Za-z])", text[index:])
            if match:
                params, command = match.groups()
                if command == "D":
                    amount = int(params or "1")
                    cursor = max(0, cursor - amount)
                elif command == "K":
                    line_end = _next_line_end(rendered, cursor)
                    del rendered[cursor:line_end]
                index += match.end()
                continue
        char = text[index]
        if char == "\b":
            cursor = max(0, cursor - 1)
        elif char == "\r":
            cursor = _line_start(rendered, cursor)
        else:
            if cursor < len(rendered):
                rendered[cursor] = char
            else:
                rendered.append(char)
            cursor += 1
        index += 1
    return "".join(rendered)


def _line_start(rendered: list[str], cursor: int) -> int:
    for index in range(cursor - 1, -1, -1):
        if rendered[index] == "\n":
            return index + 1
    return 0


def _next_line_end(rendered: list[str], cursor: int) -> int:
    for index in range(cursor, len(rendered)):
        if rendered[index] == "\n":
            return index
    return len(rendered)


def _write_baseline(repo_root: Path, config: BaselineConfig, model: str, output: str) -> None:
    output_path = repo_root / config.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    source_list = "\n".join(f"- `{source_id}`" for source_id in config.required_sources)
    span_list = "\n".join(
        f"- `{span.source_id}`: "
        + ", ".join(f"lines {start}-{end}" for start, end in span.ranges)
        for span in config.spans
    )
    text = f"""# {config.title}

Status: `human-review-needed`
Prompt/procedure: `{BASELINE_PROMPT_VERSION}`
Model: `{model}`
Generated_at_utc: `{now}`
Blinding protocol: prompt built by `scripts/run_blinded_baselines.py` from raw source text line spans only; the prompt does not load curated maps, erosion audits, best-region indexes, judge walkthroughs, or source excerpt packet loss/crux guidance.

## Source Subset

{source_list}

## Source Spans Used

{span_list}

## Prompt

```text
{BASELINE_PROMPT}
```

## Baseline Protocol Notes

- baseline_writer_had_access_to_curated_map: `no`
- baseline_protocol_limitation: The local model was prompted only with selected source spans, not full documents. This improves blinding from the curated map but means the baseline is a span-limited synthesis, not a full-corpus synthesis.

## Baseline Output

{output}
"""
    output_path.write_text(textwrap.dedent(text), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
