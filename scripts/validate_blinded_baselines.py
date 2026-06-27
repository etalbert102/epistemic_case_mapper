from __future__ import annotations

import sys
from pathlib import Path


BASELINE_GROUPS = (
    {
        "glob": "examples/lhc_black_holes/blinded_flat_synthesis_baseline_*.md",
        "required_sources": {
            "lsag_2008_safety_review",
            "spc_2008_lsag_review",
            "giddings_mangano_2008_stable_black_holes",
            "plaga_2008_metastable_black_holes",
            "giddings_mangano_2008_comments_plaga",
        },
    },
    {
        "glob": "examples/eggs/blinded_flat_synthesis_baseline_*.md",
        "required_sources": {
            "dga_2020_2025_pmc_summary",
            "aha_2019_dietary_cholesterol_pubmed",
            "aha_2023_dietary_cholesterol_news",
            "bmj_2020_egg_consumption_cvd",
            "jama_2019_dietary_cholesterol_eggs",
            "li_2020_egg_cholesterol_rct_meta",
            "nnr_2023_eggs_scoping_review",
        },
    },
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    for group in BASELINE_GROUPS:
        paths = sorted(repo_root.glob(str(group["glob"])))
        if not paths:
            failures.append(f"missing_blinded_baseline glob={group['glob']}")
        for path in paths:
            _validate_baseline(path, set(group["required_sources"]), failures)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated blinded baselines")
    return 0


def _validate_baseline(path: Path, required_sources: set[str], failures: list[str]) -> None:
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
    if len(text.split()) < 300:
        failures.append(f"blinded_baseline_too_short path={path} words={len(text.split())}")
    for artifact in ("Thinking", "done thinking", "<think>", "</think>"):
        if artifact in text:
            failures.append(f"blinded_baseline_contains_reasoning_artifact path={path} artifact={artifact}")
    if "\x1b" in text or "\x08" in text:
        failures.append(f"blinded_baseline_contains_terminal_control path={path}")
    forbidden_references = (
        "worked_region_cosmic_ray_map.md",
        "worked_region_observational_vs_rct_map.md",
        "decision_space_erosion_audit.md",
        "BEST_REGIONS.md",
    )
    for forbidden in forbidden_references:
        if forbidden in text:
            failures.append(f"blinded_baseline_references_map_artifact path={path} forbidden={forbidden}")


if __name__ == "__main__":
    raise SystemExit(main())
