from pathlib import Path

from scripts.validate_live_model_examples import _is_safe_relative_path, validate_packet


def test_checked_in_live_model_pair_is_valid() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert validate_packet(repo_root, "submission_manifest.yaml") == []


def test_live_model_artifact_paths_must_be_normalized_and_relative() -> None:
    assert _is_safe_relative_path("eggs_success/generated_map.json")
    assert not _is_safe_relative_path("../generated_map.json")
    assert not _is_safe_relative_path("/tmp/generated_map.json")

