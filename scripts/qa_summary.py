#!/usr/bin/env python3
"""Emit a compact QA summary and optional failed-region crops."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def crop_region(image_path: Path, bbox: list, output_path: Path) -> None:
    with Image.open(image_path) as image:
        left, top, width, height = [float(value) for value in bbox]
        sx = image.width / 1672.0
        sy = image.height / 941.0
        # The caller normally replaces these scales with source-size-based values.
        box = (
            round(left * sx),
            round(top * sy),
            round((left + width) * sx),
            round((top + height) * sy),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.crop(box).save(output_path)


def summarize(report: dict) -> dict:
    audit = report.get("pptx_audit", {})
    counts = audit.get("counts", {})
    failed_regions = []
    comparisons = report.get("comparisons", [])
    for slide_index, comparison in enumerate(comparisons, start=1):
        for region in comparison.get("regions", []):
            if not region.get("passed", False):
                failed_regions.append(
                    {
                        "slide": slide_index,
                        "id": region.get("id"),
                        "bbox": region.get("bbox"),
                        "similarity": region.get("similarity"),
                        "minimum": region.get("minimum_similarity"),
                    }
                )
    baseboard = []
    for slide_index, comparison in enumerate(
        report.get("baseboard_stage", {}).get("comparisons", []), start=1
    ):
        baseboard.append(
            {
                "slide": slide_index,
                "passed": bool(comparison.get("passed")),
                "coverage": comparison.get("coverage"),
                "minimum_coverage": comparison.get("minimum_coverage"),
                "similarity": comparison.get("similarity"),
                "minimum_similarity": comparison.get("minimum_similarity"),
                "reference_mode": comparison.get("reference_mode", "source_masked"),
            }
        )
    global_similarity = [
        item.get("similarity") for item in comparisons if "similarity" in item
    ]
    return {
        "status": report.get("status", "failed"),
        "failed_checks": [
            key
            for key, passed in report.get("hard_checks", {}).items()
            if not passed
        ],
        "slides": counts.get("slides", len(comparisons)),
        "native_text_shapes": counts.get("native_text_shapes"),
        "native_shapes": counts.get("native_shapes"),
        "native_charts": counts.get("native_charts"),
        "native_tables": counts.get("native_tables"),
        "pictures": counts.get("pictures"),
        "prohibited_full_slide_pictures": counts.get(
            "prohibited_full_slide_pictures"
        ),
        "objects_outside_slide": counts.get("objects_outside_slide"),
        "expected_text_coverage": audit.get("expected_text", {}).get("coverage"),
        "global_similarity": global_similarity,
        "failed_regions": failed_regions,
        "baseboard": baseboard,
    }


def write_failed_crops(report: dict, crop_dir: Path) -> list[str]:
    outputs: list[str] = []
    for slide_index, comparison in enumerate(report.get("comparisons", []), start=1):
        source_path = Path(comparison.get("source", ""))
        render_path = Path(comparison.get("render", ""))
        if not source_path.exists() or not render_path.exists():
            continue
        source_size = comparison.get("source_size") or [1672, 941]
        with Image.open(source_path) as source, Image.open(render_path) as render:
            sx_source = source.width / float(source_size[0])
            sy_source = source.height / float(source_size[1])
            sx_render = render.width / float(source_size[0])
            sy_render = render.height / float(source_size[1])
            for region in comparison.get("regions", []):
                if region.get("passed", False) or not region.get("bbox"):
                    continue
                left, top, width, height = [float(v) for v in region["bbox"]]
                rid = str(region.get("id") or "region").replace("/", "-")
                source_box = (
                    round(left * sx_source),
                    round(top * sy_source),
                    round((left + width) * sx_source),
                    round((top + height) * sy_source),
                )
                render_box = (
                    round(left * sx_render),
                    round(top * sy_render),
                    round((left + width) * sx_render),
                    round((top + height) * sy_render),
                )
                crop_dir.mkdir(parents=True, exist_ok=True)
                source_out = crop_dir / f"slide-{slide_index:02d}-{rid}-source.png"
                render_out = crop_dir / f"slide-{slide_index:02d}-{rid}-render.png"
                source.crop(source_box).save(source_out)
                render.crop(render_box).save(render_out)
                outputs.extend([str(source_out), str(render_out)])
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--crop-dir", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    summary = summarize(report)
    if args.crop_dir:
        summary["failed_region_crops"] = write_failed_crops(report, args.crop_dir)
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if summary["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
