from pathlib import Path

from scripts.validate_eggs_large_source_stress import validate_packet


def test_checked_in_eggs_large_source_stress_packet_is_valid() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert validate_packet(repo_root) == []
