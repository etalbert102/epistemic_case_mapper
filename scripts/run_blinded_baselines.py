from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from epistemic_case_mapper.blinded_baselines import (
    BASELINE_PROMPT,
    BASELINE_PROMPT_VERSION,
    BaselineConfig,
    _configs_from_manifest,
    build_prompt,
)


def _legacy_configs_from_manifest(repo_root: Path, manifest_path: str = "submission_manifest.yaml") -> dict[str, BaselineConfig]:
    configs = _configs_from_manifest(repo_root, manifest_path)
    legacy = dict(configs)
    by_case: dict[str, list[BaselineConfig]] = {}
    for config in configs.values():
        by_case.setdefault(config.case_key, []).append(config)
    for case_key, case_configs in by_case.items():
        if len(case_configs) == 1:
            legacy[case_key] = case_configs[0]
    return legacy


CONFIGS = _legacy_configs_from_manifest(Path(__file__).resolve().parents[1])


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate blinded flat-synthesis baselines with Ollama.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--case", help="Run all baseline configs for one case key.")
    parser.add_argument("--region", help="Run one baseline config by region ID or baseline ID.")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument(
        "--output-label",
        help="Filename label for outputs. Defaults to a stable label derived from --model.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompts and write no output; useful for checking isolation.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    configs = _configs_from_manifest(repo_root, args.manifest)
    if args.case and args.region:
        parser.error("use --case or --region, not both")
    output_label = args.output_label or _model_label(args.model)
    selected = _select_configs(configs, args.case, args.region, parser)
    for config in selected:
        _validate_config_spans(repo_root, config)
        prompt = build_prompt(repo_root, config)
        if args.dry_run:
            print(f"\n--- {config.region_id} prompt ---\n{prompt}")
            continue
        output = _clean_model_output(_run_ollama(args.model, prompt))
        output_path = _output_path(config, output_label)
        _write_baseline(repo_root, config, args.model, output_path, output)
        print(f"Wrote {output_path}")
    return 0


def _select_configs(
    configs: dict[str, BaselineConfig],
    case_key: str | None,
    region_or_baseline_id: str | None,
    parser: argparse.ArgumentParser,
) -> tuple[BaselineConfig, ...]:
    if region_or_baseline_id is not None:
        matches = [
            config
            for baseline_id, config in configs.items()
            if baseline_id == region_or_baseline_id or config.region_id == region_or_baseline_id
        ]
        if not matches:
            choices = sorted({*configs.keys(), *(config.region_id for config in configs.values())})
            parser.error(f"unknown region/baseline {region_or_baseline_id!r}; choose one of {', '.join(choices)}")
        return tuple(matches)
    if case_key is not None:
        matches = [config for config in configs.values() if config.case_key == case_key]
        if not matches:
            parser.error(
                f"unknown case {case_key!r}; choose one of {', '.join(sorted({config.case_key for config in configs.values()}))}"
            )
        return tuple(matches)
    return tuple(configs.values())


def _validate_config_spans(repo_root: Path, config: BaselineConfig) -> None:
    span_sources = {span.source_id for span in config.spans}
    missing_sources = set(config.required_sources) - span_sources
    if missing_sources:
        raise SystemExit(
            "baseline_missing_source_span "
            + f"case={config.case_key} sources={','.join(sorted(missing_sources))}"
        )
    for span in config.spans:
        path = repo_root / span.path
        if not path.exists():
            raise SystemExit(f"baseline_span_missing_file case={config.case_key} path={span.path}")
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        for start, end in span.ranges:
            if start < 1 or end < start or end > line_count:
                raise SystemExit(
                    f"baseline_span_out_of_range case={config.case_key} "
                    f"source={span.source_id} range={start}-{end} line_count={line_count}"
                )


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
    output = re.sub(r"(?is)<think>.*?</think>\s*", "", output).strip()
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


def _model_label(model: str) -> str:
    if model == "gemma4:e4b":
        return "gemma4"
    return re.sub(r"[^A-Za-z0-9]+", "_", model).strip("_").lower()


def _output_path(config: BaselineConfig, output_label: str) -> str:
    return config.output_path.replace("_gemma4.md", f"_{output_label}.md")


def _write_baseline(repo_root: Path, config: BaselineConfig, model: str, output_path_text: str, output: str) -> None:
    output_path = repo_root / output_path_text
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
