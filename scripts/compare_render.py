#!/usr/bin/env python3
"""Compare source and render globally, through masks, and by critical region."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFile, ImageFilter, ImageStat


ImageFile.LOAD_TRUNCATED_IMAGES = True


def mean_channel(stat: ImageStat.Stat) -> float:
    return sum(stat.mean) / max(1, len(stat.mean))


def load_json_list(path: Path | None) -> list[dict | list]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON array")
    return payload


def normalized_box(value, size: tuple[int, int]) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"invalid bbox: {value!r}")
    left, top, width, height = (float(item) for item in value)
    right = left + width
    bottom = top + height
    canvas_width, canvas_height = size
    return (
        max(0, min(canvas_width, math.floor(min(left, right)))),
        max(0, min(canvas_height, math.floor(min(top, bottom)))),
        max(0, min(canvas_width, math.ceil(max(left, right)))),
        max(0, min(canvas_height, math.ceil(max(top, bottom)))),
    )


def make_mask(
    size: tuple[int, int],
    *,
    include_bboxes: list[list] | None = None,
    ignore_bboxes: list[list] | None = None,
    ignore_mask: Image.Image | None = None,
) -> Image.Image:
    mask = Image.new("L", size, 0 if include_bboxes else 255)
    draw = ImageDraw.Draw(mask)
    for bbox in include_bboxes or []:
        draw.rectangle(normalized_box(bbox, size), fill=255)
    for bbox in ignore_bboxes or []:
        draw.rectangle(normalized_box(bbox, size), fill=0)
    if ignore_mask is not None:
        prepared = ignore_mask.convert("L").resize(size, Image.Resampling.NEAREST)
        mask = ImageChops.multiply(mask, ImageChops.invert(prepared))
    return mask


def metrics(source: Image.Image, render: Image.Image, mask: Image.Image) -> dict:
    mask_stat = ImageStat.Stat(mask)
    coverage = mask_stat.mean[0] / 255.0
    if coverage <= 0:
        return {
            "coverage": 0.0,
            "pixel_error": 1.0,
            "edge_error": 1.0,
            "histogram_error": 1.0,
            "similarity": 0.0,
            "empty_mask": True,
        }

    difference = ImageChops.difference(source, render)
    pixel_error = mean_channel(ImageStat.Stat(difference, mask)) / 255.0

    source_edges = source.convert("L").filter(ImageFilter.FIND_EDGES)
    render_edges = render.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_error = mean_channel(
        ImageStat.Stat(ImageChops.difference(source_edges, render_edges), mask)
    ) / 255.0

    source_hist = source.histogram(mask)
    render_hist = render.histogram(mask)
    histogram_error = sum(
        abs(a - b) for a, b in zip(source_hist, render_hist)
    ) / max(1, sum(source_hist) + sum(render_hist))

    similarity = max(
        0.0,
        1.0 - (0.60 * pixel_error + 0.25 * edge_error + 0.15 * histogram_error),
    )
    return {
        "coverage": round(coverage, 6),
        "pixel_error": round(pixel_error, 6),
        "edge_error": round(edge_error, 6),
        "histogram_error": round(histogram_error, 6),
        "similarity": round(similarity, 6),
    }


def compare(
    source_path: Path,
    render_path: Path,
    *,
    ignore_bboxes: list[list] | None = None,
    ignore_mask_path: Path | None = None,
    regions: list[dict] | None = None,
    min_similarity: float = 0.55,
    min_region_similarity: float = 0.75,
    min_coverage: float = 0.10,
) -> dict:
    with Image.open(source_path) as source_image, Image.open(render_path) as render_image:
        source = source_image.convert("RGB")
        render = render_image.convert("RGB").resize(source.size, Image.Resampling.LANCZOS)
        ignore_mask = (
            Image.open(ignore_mask_path).copy() if ignore_mask_path is not None else None
        )
        global_mask = make_mask(
            source.size, ignore_bboxes=ignore_bboxes, ignore_mask=ignore_mask
        )
        global_metrics = metrics(source, render, global_mask)

        region_reports = []
        for index, region in enumerate(regions or [], start=1):
            region_id = str(region.get("id") or f"region-{index}")
            bbox = region.get("bbox")
            threshold = float(region.get("min_similarity", min_region_similarity))
            region_mask = make_mask(
                source.size,
                include_bboxes=[bbox],
                ignore_bboxes=ignore_bboxes,
                ignore_mask=ignore_mask,
            )
            region_metrics = metrics(source, render, region_mask)
            region_reports.append(
                {
                    "id": region_id,
                    "bbox": bbox,
                    "description": region.get("description", ""),
                    **region_metrics,
                    "minimum_similarity": threshold,
                    "passed": region_metrics["similarity"] >= threshold,
                }
            )

        coverage_passed = global_metrics["coverage"] >= min_coverage
        global_passed = (
            global_metrics["similarity"] >= min_similarity and coverage_passed
        )
        regions_passed = all(region["passed"] for region in region_reports)
        return {
            "source": str(source_path.resolve()),
            "render": str(render_path.resolve()),
            "source_size": list(source.size),
            "render_size": list(render_image.size),
            **global_metrics,
            "minimum_coverage": min_coverage,
            "coverage_passed": coverage_passed,
            "minimum_similarity": min_similarity,
            "global_passed": global_passed,
            "regions": region_reports,
            "regions_passed": regions_passed,
            "passed": global_passed and regions_passed,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("render", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--min-similarity", type=float, default=0.55)
    parser.add_argument("--min-region-similarity", type=float, default=0.75)
    parser.add_argument("--min-coverage", type=float, default=0.10)
    parser.add_argument("--ignore-bboxes-json", type=Path)
    parser.add_argument(
        "--ignore-mask-image",
        type=Path,
        help="Grayscale/alpha mask where white pixels are ignored",
    )
    parser.add_argument("--regions-json", type=Path)
    args = parser.parse_args()

    ignore_payload = load_json_list(args.ignore_bboxes_json)
    ignore_bboxes = [
        item.get("bbox") if isinstance(item, dict) else item for item in ignore_payload
    ]
    regions = [
        item for item in load_json_list(args.regions_json) if isinstance(item, dict)
    ]
    report = compare(
        args.source,
        args.render,
        ignore_bboxes=ignore_bboxes,
        ignore_mask_path=args.ignore_mask_image,
        regions=regions,
        min_similarity=args.min_similarity,
        min_region_similarity=args.min_region_similarity,
        min_coverage=args.min_coverage,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
