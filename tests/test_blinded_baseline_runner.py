from pathlib import Path

from scripts.run_blinded_baselines import CONFIGS, _clean_model_output, build_prompt


def test_blinded_baseline_prompt_omits_map_artifacts() -> None:
    prompt = build_prompt(repo_root=Path.cwd(), config=CONFIGS["lhc"])

    assert "worked_region_cosmic_ray_map.md" not in prompt
    assert "decision_space_erosion_audit.md" not in prompt
    assert "BEST_REGIONS.md" not in prompt
    assert "Common Flat-Synthesis Losses" not in prompt
    assert "Do not create a claim map" in prompt


def test_clean_model_output_removes_thinking_block_and_control_chars() -> None:
    raw = "Thinking...\nabc\bX\n...done thinking.\n\nFinal synthesis\x1b[0m"

    assert _clean_model_output(raw) == "Final synthesis"


def test_clean_model_output_renders_cursor_left_delete_sequence() -> None:
    raw = "The star has bi\x1b[2D\x1b[Kbillions of years"

    assert _clean_model_output(raw) == "The star has billions of years"
