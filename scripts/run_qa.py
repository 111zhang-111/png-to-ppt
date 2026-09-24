#!/usr/bin/env python3
"""Run clean-plate, structural, rendering, regional, and overflow QA."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from build_deck import initialize_artifact_workspace, node_executable
from qa_summary import summarize, write_failed_crops
from scene_defaults import load_expanded


def run_json(command: list[str], report_path: Path, env: dict[str, str]) -> dict:
    proc = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    if report_path.exists():
        return json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "status": "failed",
        "errors": [
            {
                "code": "subprocess_failed",
                "message": (proc.stdout + "\n" + proc.stderr).strip(),
            }
        ],
    }


def render_deck(
    *,
    pptx: Path,
    render_dir: Path,
    workspace: Path,
    skill_dir: Path,
    env: dict[str, str],
) -> dict:
    if render_dir.exists():
        shutil.rmtree(render_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    initialize_artifact_workspace(workspace, env)
    render_tool = workspace / "render_pptx.mjs"
    shutil.copy2(skill_dir / "render_pptx.mjs", render_tool)
    proc = subprocess.run(
        [
            node_executable(env),
            str(render_tool),
            str(pptx),
            str(render_dir),
            "1.30625",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "directory": str(render_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--qa-dir", required=True, type=Path)
    parser.add_argument(
        "--mode",
        choices=("economy", "standard", "strict"),
        default="economy",
    )
    parser.add_argument("--min-similarity", type=float)
    parser.add_argument("--min-region-similarity", type=float)
    parser.add_argument("--min-baseboard-similarity", type=float)
    parser.add_argument("--fontconfig-file", type=Path)
    parser.add_argument("--crop-failures", action="store_true")
    parser.add_argument("--verbose-report", action="store_true")
    args = parser.parse_args()

    mode_defaults = {
        "economy": {
            "similarity": 0.48,
            "region_similarity": 0.68,
            "baseboard_similarity": 0.78,
        },
        "standard": {
            "similarity": 0.55,
            "region_similarity": 0.75,
            "baseboard_similarity": 0.82,
        },
        "strict": {
            "similarity": 0.65,
            "region_similarity": 0.78,
            "baseboard_similarity": 0.85,
        },
    }[args.mode]
    min_similarity = args.min_similarity or mode_defaults["similarity"]
    min_region_similarity = (
        args.min_region_similarity or mode_defaults["region_similarity"]
    )
    min_baseboard_similarity = (
        args.min_baseboard_similarity or mode_defaults["baseboard_similarity"]
    )

    scene_path = args.scene.resolve()
    pptx = args.pptx.resolve()
    qa_dir = args.qa_dir.resolve()
    qa_dir.mkdir(parents=True, exist_ok=True)
    skill_dir = Path(__file__).resolve().parent
    env = os.environ.copy()
    if args.fontconfig_file:
        env["FONTCONFIG_FILE"] = str(args.fontconfig_file.resolve())

    scene_lint_path = qa_dir / "scene-lint.json"
    scene_lint = run_json(
        [
            sys.executable,
            str(skill_dir / "scene_lint.py"),
            str(scene_path),
            "--report",
            str(scene_lint_path),
        ],
        scene_lint_path,
        env,
    )

    audit_path = qa_dir / "editability-report.json"
    audit = run_json(
        [
            sys.executable,
            str(skill_dir / "audit_pptx.py"),
            str(pptx),
            "--scene",
            str(scene_path),
            "--report",
            str(audit_path),
        ],
        audit_path,
        env,
    )

    scene = load_expanded(scene_path)
    slide_count = len(scene.get("slides", []))

    final_render = render_deck(
        pptx=pptx,
        render_dir=qa_dir / "renders",
        workspace=qa_dir / "render-workspace",
        skill_dir=skill_dir,
        env=env,
    )

    baseboard_required = args.mode != "economy"
    baseboard_build_returncode = 0
    baseboard_build_stdout = ""
    baseboard_build_stderr = ""
    if baseboard_required:
        baseboard_pptx = qa_dir / "baseboard-stage.pptx"
        baseboard_build = subprocess.run(
            [
                sys.executable,
                str(skill_dir / "build_deck.py"),
                "--scene",
                str(scene_path),
                "--output",
                str(baseboard_pptx),
                "--run-dir",
                str(qa_dir / "baseboard-build"),
                "--stage",
                "baseboard",
                *(
                    ["--fontconfig-file", str(args.fontconfig_file.resolve())]
                    if args.fontconfig_file
                    else []
                ),
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        baseboard_build_returncode = baseboard_build.returncode
        baseboard_build_stdout = baseboard_build.stdout.strip()
        baseboard_build_stderr = baseboard_build.stderr.strip()
        if baseboard_build.returncode == 0 and baseboard_pptx.exists():
            baseboard_render = render_deck(
                pptx=baseboard_pptx,
                render_dir=qa_dir / "baseboard-renders",
                workspace=qa_dir / "baseboard-render-workspace",
                skill_dir=skill_dir,
                env=env,
            )
        else:
            baseboard_render = {
                "returncode": baseboard_build.returncode or 2,
                "stdout": baseboard_build_stdout,
                "stderr": baseboard_build_stderr,
                "directory": str(qa_dir / "baseboard-renders"),
            }
    else:
        baseboard_render = {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "directory": str(qa_dir / "baseboard-renders"),
            "skipped": True,
        }

    comparisons = []
    baseboard_comparisons = []
    final_passed = True
    baseboard_passed = True
    for index, slide in enumerate(scene.get("slides", []), start=1):
        source = Path(slide["source_image"])
        if not source.is_absolute():
            source = scene_path.parent / source

        regions_path = qa_dir / f"slide-{index:02d}-critical-regions.json"
        critical_regions = (
            [] if args.mode == "economy" else slide.get("critical_regions", [])
        )
        regions_path.write_text(
            json.dumps(critical_regions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        final_report_path = qa_dir / f"slide-{index:02d}-comparison.json"
        final_comparison = run_json(
            [
                sys.executable,
                str(skill_dir / "compare_render.py"),
                str(source),
                str(qa_dir / "renders" / f"slide-{index}.png"),
                "--report",
                str(final_report_path),
                "--min-similarity",
                str(min_similarity),
                "--min-region-similarity",
                str(min_region_similarity),
                "--regions-json",
                str(regions_path),
            ],
            final_report_path,
            env,
        )
        comparisons.append(final_comparison)
        final_passed &= bool(final_comparison.get("passed"))

        if not baseboard_required:
            continue

        clean_plate = slide.get("clean_plate", {})
        reference_image = clean_plate.get("reference_image")
        mask_image = clean_plate.get("mask_image")
        baseboard_report_path = qa_dir / f"slide-{index:02d}-baseboard-comparison.json"
        min_baseboard_coverage = clean_plate.get("min_unmasked_coverage", 0.35)
        if reference_image:
            reference = Path(reference_image)
            command = [
                sys.executable,
                str(skill_dir / "compare_render.py"),
                str(reference),
                str(qa_dir / "baseboard-renders" / f"slide-{index}.png"),
                "--report",
                str(baseboard_report_path),
                "--min-similarity",
                str(min_baseboard_similarity),
                "--min-coverage",
                "0.99",
            ]
            reference_mode = "clean_plate_reference"
        else:
            ignored = [
                item.get("bbox")
                for item in slide.get("source_inventory", [])
                if item.get("layer") != "baseboard" and item.get("bbox")
            ]
            ignore_path = qa_dir / f"slide-{index:02d}-baseboard-ignore.json"
            ignore_path.write_text(
                json.dumps(ignored, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(skill_dir / "compare_render.py"),
                str(source),
                str(qa_dir / "baseboard-renders" / f"slide-{index}.png"),
                "--report",
                str(baseboard_report_path),
                "--min-similarity",
                str(min_baseboard_similarity),
                "--min-coverage",
                str(min_baseboard_coverage),
            ]
            if mask_image:
                command.extend(["--ignore-mask-image", str(Path(mask_image))])
                reference_mode = "source_alpha_mask"
            else:
                command.extend(["--ignore-bboxes-json", str(ignore_path)])
                reference_mode = "source_bbox_mask"
        baseboard_comparison = run_json(
            command,
            baseboard_report_path,
            env,
        )
        baseboard_comparison["reference_mode"] = reference_mode
        baseboard_comparisons.append(baseboard_comparison)
        baseboard_passed &= bool(baseboard_comparison.get("passed"))

    final_render_ok = (
        final_render["returncode"] == 0
        and len(list((qa_dir / "renders").glob("slide-*.png"))) == slide_count
    )
    baseboard_render_ok = True
    if baseboard_required:
        baseboard_render_ok = (
            baseboard_render["returncode"] == 0
            and len(list((qa_dir / "baseboard-renders").glob("slide-*.png")))
            == slide_count
        )
    hard_checks = {
        "scene_lint": scene_lint.get("status") == "passed",
        "pptx_audit": audit.get("status") == "passed",
        "render": final_render_ok,
        "baseboard_render": baseboard_render_ok,
        "baseboard_similarity": baseboard_passed,
        "overflow": audit.get("counts", {}).get("objects_outside_slide", 1) == 0,
        "visual_similarity_and_regions": final_passed,
    }
    report = {
        "status": "passed" if all(hard_checks.values()) else "failed",
        "mode": args.mode,
        "hard_checks": hard_checks,
        "scene_lint": scene_lint,
        "pptx_audit": audit,
        "render": final_render,
        "baseboard_stage": {
            "required": baseboard_required,
            "skipped": not baseboard_required,
            "build_returncode": baseboard_build_returncode,
            "build_stdout": baseboard_build_stdout,
            "build_stderr": baseboard_build_stderr,
            "render": baseboard_render,
            "comparisons": baseboard_comparisons,
        },
        "overflow": {
            "returncode": (
                0 if audit.get("counts", {}).get("objects_outside_slide", 1) == 0 else 2
            ),
            "objects_outside_slide": audit.get("counts", {}).get(
                "objects_outside_slide", 0
            ),
        },
        "comparisons": comparisons,
    }
    qa_report = qa_dir / "qa-report.json"
    qa_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = summarize(report)
    if args.crop_failures:
        summary["failed_region_crops"] = write_failed_crops(
            report, qa_dir / "failed-regions"
        )
    (qa_dir / "qa-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            report if args.verbose_report else summary,
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
