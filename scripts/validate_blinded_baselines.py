from __future__ import annotations

import argparse
import sys
from pathlib import Path

from epistemic_case_mapper.submission_manifest import load_submission_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate checked-in blinded flat-synthesis baselines.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    failures: list[str] = []
    for region, baseline in manifest.iter_blinded_baselines():
        output_dir = (repo_root / baseline.output_path).parent
        paths = sorted(output_dir.glob("blinded_flat_synthesis_baseline_*.md"))
        if not paths:
            failures.append(f"missing_blinded_baseline case={region.case_key} dir={output_dir.relative_to(repo_root)}")
        forbidden_references = {Path(region.map_path).name, Path(region.audit_path).name}
        if region.best_path:
            forbidden_references.add(Path(region.best_path).name)
        for path in paths:
            _validate_baseline(path, set(baseline.required_sources), baseline.min_words, forbidden_references, failures)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated blinded baselines")
    return 0


def _validate_baseline(
    path: Path,
    required_sources: set[str],
    min_words: int,
    forbidden_references: set[str],
    failures: list[str],
) -> None:
    if not path.exists():
        failures.append(f"missing_blinded_baseline path={path}")
        return
    text = path.read_text(encoding="utf-8")
    required_markers = (
        "flat_baseline_prompt_v1_blinded_ollama",
        "Model: `",
        "baseline_writer_had_access_to_curated_map: `no`",
        "Blinding protocol:",
        "## Baseline Output",
    )
    for marker in required_markers:
        if marker not in text:
            failures.append(f"blinded_baseline_missing_marker path={path} marker={marker}")
    for source_id in required_sources:
        if source_id not in text:
            failures.append(f"blinded_baseline_missing_source path={path} source={source_id}")
    if len(text.split()) < min_words:
        failures.append(f"blinded_baseline_too_short path={path} words={len(text.split())}")
    for artifact in ("Thinking", "done thinking", "<think>", "</think>"):
        if artifact in text:
            failures.append(f"blinded_baseline_contains_reasoning_artifact path={path} artifact={artifact}")
    if "\x1b" in text or "\x08" in text:
        failures.append(f"blinded_baseline_contains_terminal_control path={path}")
    for forbidden in forbidden_references:
        if forbidden in text:
            failures.append(f"blinded_baseline_references_map_artifact path={path} forbidden={forbidden}")


if __name__ == "__main__":
    raise SystemExit(main())
