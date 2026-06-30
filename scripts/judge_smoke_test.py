from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from judge_paths import get_judge_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Print and validate the ten-minute FLF judge path.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    judge_paths = get_judge_paths(repo_root, args.manifest)
    failures = [path for path in judge_paths if not (repo_root / path).exists()]
    if failures:
        for path in failures:
            print(f"FAIL: missing_judge_path_file path={path}", file=sys.stderr)
        return 1

    result = subprocess.run(
        [sys.executable, "scripts/validate_submission_references.py", "--manifest", args.manifest],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        return result.returncode

    print("FLF judge path:")
    for index, path in enumerate(judge_paths, start=1):
        print(f"{index}. {path}")
    print("")
    print("Judge smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
