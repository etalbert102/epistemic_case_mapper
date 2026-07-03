from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.llm_stress_eval import run_llm_stress_eval
from epistemic_case_mapper.submission_manifest import load_submission_manifest


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _run_decision_packet(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    output_dir: str | None,
    skip_stress_run: bool,
    backend_timeout: int,
    backend_retries: int,
) -> int:
    if backend_timeout < 1:
        print("decision_packet_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("decision_packet_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1

    helpers = _decision_packet_helpers()

    manifest = load_submission_manifest(repo_root, package)
    try:
        region = manifest.region_for_id(region_id)
    except KeyError:
        print(f"decision_packet_failed unknown_region={region_id}", file=sys.stderr)
        return 1

    selected_backend = backend or manifest.default_model_backend
    artifacts = Path(output_dir) if output_dir else Path("artifacts") / "decision_packets" / region_id
    if not artifacts.is_absolute():
        artifacts = repo_root / artifacts
    artifacts.mkdir(parents=True, exist_ok=True)

    stress_dir = artifacts / "stress"
    stress_json = stress_dir / "llm_stress_eval.json"
    try:
        if not skip_stress_run or not stress_json.exists():
            run_llm_stress_eval(
                repo_root=repo_root,
                manifest_path=package,
                region_id=region_id,
                backend=selected_backend,
                output_dir=stress_dir,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
            )
        stress_report = json.loads(stress_json.read_text(encoding="utf-8"))
        losses = helpers["_parse_losses"](repo_root / region.audit_path)
        baseline = helpers["_read"](repo_root / region.baseline_path)
        map_payload = helpers["_read_map_payload"](repo_root, region)
        map_text = json.dumps(map_payload, indent=2)
        requirements = helpers["_compile_rewrite_requirements"](losses, map_payload, stress_report)

        write_json(artifacts / "rewrite_requirements.json", {"requirements": [helpers["_requirement_dict"](req) for req in requirements]})
        write_markdown(artifacts / "REWRITE_REQUIREMENTS.md", helpers["_requirements_markdown"](requirements))

        prompt = helpers["_synthesis_prompt"](region, baseline, map_text, losses, requirements=requirements, stress_report=stress_report)
        write_markdown(artifacts / "decision_packet_prompt.txt", prompt)
        packet = helpers["_run_synthesis_backend"](
            prompt,
            selected_backend,
            backend_timeout,
            backend_retries,
            map_payload,
            requirements,
        )
        initial_coverage = helpers["_deterministic_requirement_coverage"](packet, requirements)
        repair_ran = False
        deterministic_patch_ran = False
        if helpers["_needs_repair"](initial_coverage):
            repair_ran = True
            write_markdown(artifacts / "decision_packet_initial.md", packet)
            repair_prompt = helpers["_repair_synthesis_prompt"](region, packet, initial_coverage, requirements)
            write_markdown(artifacts / "decision_packet_repair_prompt.txt", repair_prompt)
            packet = helpers["_run_synthesis_backend"](
                repair_prompt,
                selected_backend,
                backend_timeout,
                backend_retries,
                map_payload,
                requirements,
            )
            repaired_coverage = helpers["_deterministic_requirement_coverage"](packet, requirements)
            if helpers["_needs_repair"](repaired_coverage):
                deterministic_patch_ran = True
                write_markdown(artifacts / "decision_packet_repaired_before_patch.md", packet)
                packet = helpers["_deterministic_patch_synthesis"](packet, repaired_coverage, requirements)
        packet = helpers["_clean_reader_packet_metadata"](packet)
        coverage = helpers["_deterministic_requirement_coverage"](packet, requirements)
    except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"decision_packet_failed region={region_id} error={exc}", file=sys.stderr)
        return 1

    packet_path = artifacts / "DECISION_PACKET.md"
    coverage_path = artifacts / "deterministic_requirement_coverage.json"
    summary_path = artifacts / "decision_packet.json"
    write_markdown(packet_path, packet)
    write_json(coverage_path, coverage)
    write_json(
        summary_path,
        _decision_packet_summary(
            repo_root=repo_root,
            region_id=region_id,
            selected_backend=selected_backend,
            artifacts=artifacts,
            packet_path=packet_path,
            coverage_path=coverage_path,
            stress_json=stress_json,
            requirements=requirements,
            coverage=coverage,
            repair_ran=repair_ran,
            deterministic_patch_ran=deterministic_patch_ran,
        ),
    )
    print(
        "Decision packet wrote "
        f"{_display_path(repo_root, packet_path)} "
        f"backend={selected_backend} "
        f"coverage={coverage['clear_count']}/{len(requirements)} clear "
        f"repair_ran={str(repair_ran).lower()} patch_ran={str(deterministic_patch_ran).lower()}"
    )
    print(f"Coverage: {_display_path(repo_root, coverage_path)}")
    print(f"Summary: {_display_path(repo_root, summary_path)}")
    return 0
def _decision_packet_helpers() -> dict[str, Any]:
    from run_synthesis_uplift_eval import (  # noqa: PLC0415
        _clean_reader_packet_metadata,
        _compile_rewrite_requirements,
        _deterministic_patch_synthesis,
        _deterministic_requirement_coverage,
        _needs_repair,
        _parse_losses,
        _read,
        _read_map_payload,
        _repair_synthesis_prompt,
        _requirement_dict,
        _requirements_markdown,
        _run_synthesis_backend,
        _synthesis_prompt,
    )

    return locals()
def _decision_packet_summary(
    *,
    repo_root: Path,
    region_id: str,
    selected_backend: str,
    artifacts: Path,
    packet_path: Path,
    coverage_path: Path,
    stress_json: Path,
    requirements: list[Any],
    coverage: dict[str, Any],
    repair_ran: bool,
    deterministic_patch_ran: bool,
) -> dict[str, Any]:
    return {
        "schema_id": "decision_packet_v1",
        "region_id": region_id,
        "backend": selected_backend,
        "paths": {
            "decision_packet": _display_path(repo_root, packet_path),
            "deterministic_requirement_coverage": _display_path(repo_root, coverage_path),
            "rewrite_requirements": _display_path(repo_root, artifacts / "rewrite_requirements.json"),
            "stress_report": _display_path(repo_root, stress_json),
        },
        "requirement_count": len(requirements),
        "deterministic_coverage": {
            "clear": coverage["clear_count"],
            "partial": coverage["partial_count"],
            "missing": coverage["missing_count"],
        },
        "repair_ran": repair_ran,
        "deterministic_patch_ran": deterministic_patch_ran,
    }

