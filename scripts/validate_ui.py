from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_UI_FILES = (
    "ui/index.html",
    "ui/styles.css",
    "ui/app.js",
    "ui/data.json",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the static FLF prototype UI.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    failures: list[str] = []
    for relative_path in REQUIRED_UI_FILES:
        path = repo_root / relative_path
        if not path.exists():
            failures.append(f"missing_ui_file path={relative_path}")
        elif path.stat().st_size < 500:
            failures.append(f"ui_file_too_small path={relative_path} bytes={path.stat().st_size}")

    if (repo_root / "ui/data.json").exists():
        _validate_data(repo_root, failures)
    _validate_static_assets(repo_root, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated static UI")
    return 0


def _validate_data(repo_root: Path, failures: list[str]) -> None:
    data = json.loads((repo_root / "ui/data.json").read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if len(cases) != 2:
        failures.append(f"ui_data_case_count count={len(cases)}")
    summary = data.get("summary", {})
    for key in ("sourceCount", "clusterCount", "claimCount", "relationCount", "taskCount"):
        if int(summary.get(key, 0)) <= 0:
            failures.append(f"ui_data_empty_summary key={key}")
    for case in cases:
        case_key = case.get("caseKey", "unknown")
        if len(case.get("sources", [])) < 5:
            failures.append(f"ui_case_too_few_sources case={case_key}")
        if len(case.get("clusters", [])) < 5:
            failures.append(f"ui_case_too_few_clusters case={case_key}")
        if len(case.get("worked", {}).get("claims", [])) < 10:
            failures.append(f"ui_case_too_few_claims case={case_key}")
        if len(case.get("tasks", [])) < 5:
            failures.append(f"ui_case_too_few_tasks case={case_key}")
        for artifact_path in case.get("artifacts", {}).values():
            if not (repo_root / artifact_path).exists():
                failures.append(f"ui_missing_artifact case={case_key} path={artifact_path}")


def _validate_static_assets(repo_root: Path, failures: list[str]) -> None:
    index = (repo_root / "ui/index.html").read_text(encoding="utf-8") if (repo_root / "ui/index.html").exists() else ""
    styles = (repo_root / "ui/styles.css").read_text(encoding="utf-8") if (repo_root / "ui/styles.css").exists() else ""
    script = (repo_root / "ui/app.js").read_text(encoding="utf-8") if (repo_root / "ui/app.js").exists() else ""
    for marker in ("caseTabs", "clusterGrid", "lossList", "taskList", "bestRegionsLink", "fullBaselineLink"):
        if marker not in index:
            failures.append(f"ui_index_missing_marker marker={marker}")
    for marker in ("renderCase", "renderClusters", "renderClaims", "renderTasks"):
        if marker not in script:
            failures.append(f"ui_script_missing_function marker={marker}")
    for marker in ("--ink", "--paper", "--accent", ".dashboard", ".case-card"):
        if marker not in styles:
            failures.append(f"ui_css_missing_marker marker={marker}")


if __name__ == "__main__":
    raise SystemExit(main())
