from pathlib import Path

from scripts.run_blinded_baselines import CONFIGS, _clean_model_output, _model_label, _output_path, build_prompt


def test_blinded_baseline_prompt_omits_map_artifacts() -> None:
    prompt = build_prompt(repo_root=Path.cwd(), config=CONFIGS["lhc"])

    assert "worked_region_cosmic_ray_map.md" not in prompt
    assert "decision_space_erosion_audit.md" not in prompt
    assert "BEST_REGIONS.md" not in prompt
    assert "Common Flat-Synthesis Losses" not in prompt
    assert "Create a direct research memo rather than a claim map" in prompt


def test_clean_model_output_removes_thinking_block_and_control_chars() -> None:
    raw = "Thinking...\nabc\bX\n...done thinking.\n\nFinal synthesis\x1b[0m"

    assert _clean_model_output(raw) == "Final synthesis"


def test_clean_model_output_renders_cursor_left_delete_sequence() -> None:
    raw = "The star has bi\x1b[2D\x1b[Kbillions of years"

    assert _clean_model_output(raw) == "The star has billions of years"


def test_clean_model_output_removes_think_tags() -> None:
    raw = "<think>private chain of thought</think>\nVisible answer"

    assert _clean_model_output(raw) == "Visible answer"


def test_model_label_and_output_path_are_stable() -> None:
    assert _model_label("gemma4:e4b") == "gemma4"
    assert _model_label("gemma4:26b") == "gemma4_26b"
    assert _model_label("qwen3:8b") == "qwen3_8b"
    assert _output_path(CONFIGS["eggs"], "qwen3_8b").endswith("blinded_flat_synthesis_baseline_qwen3_8b.md")
