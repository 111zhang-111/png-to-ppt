#!/usr/bin/env python3
"""Validate the reconstruction scene contract before PPTX compilation."""

from __future__ import annotations

import argparse
import json
import math
import unicodedata
from pathlib import Path

from scene_defaults import load_expanded

ALLOWED_TYPES = {
    "native_text",
    "native_shape",
    "native_line",
    "native_path",
    "native_table",
    "native_chart",
    "local_picture",
    "background_texture",
}
ALLOWED_LAYERS = {
    "baseboard",
    "structure",
    "visual_asset",
    "native_text",
    "decoration",
}
CLEAN_PLATE_METHODS = {"native", "source_inpaint", "source_composite"}
BAD_TEXT_FRAGMENTS = ("�", "Ã", "Â", "â€™", "â€œ", "â€", "锟斤拷")


def issue(bucket: list[dict], code: str, message: str, **context) -> None:
    bucket.append({"code": code, "message": message, **context})


def text_value(element: dict) -> str:
    if "text" in element:
        return str(element.get("text", ""))
    return "".join(str(run.get("text", "")) for run in element.get("runs", []))


def valid_bbox(value) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) and math.isfinite(item) for item in value)
    )


def lint(scene_path: Path) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    try:
        scene = load_expanded(scene_path)
    except Exception as exc:
        return {
            "status": "failed",
            "errors": [{"code": "invalid_or_unexpandable_scene", "message": str(exc)}],
            "warnings": [],
        }

    if scene.get("version") != "1.1":
        issue(
            errors,
            "unsupported_scene_version",
            "clean-plate workflow requires scene version 1.1",
        )

    slide_size = scene.get("slide_size", {})
    width = slide_size.get("width")
    height = slide_size.get("height")
    if not all(isinstance(v, (int, float)) and v > 0 for v in (width, height)):
        issue(errors, "invalid_slide_size", "slide_size width and height must be positive")
        width, height = 1280, 720

    slides = scene.get("slides")
    if not isinstance(slides, list) or not slides:
        issue(errors, "missing_slides", "slides must be a non-empty array")
        slides = []

    all_element_ids: set[str] = set()
    totals = {
        "slides": len(slides),
        "inventory": 0,
        "required_inventory": 0,
        "elements": 0,
        "native_text": 0,
        "native_objects": 0,
        "pictures": 0,
        "baseboard_roots": 0,
        "critical_regions": 0,
    }

    for slide_index, slide in enumerate(slides, start=1):
        sid = slide.get("id") or f"slide-{slide_index}"
        source = Path(slide.get("source_image", ""))
        if source and not source.is_absolute():
            source = scene_path.parent / source
        if not source.exists():
            issue(errors, "missing_source_image", "source image does not exist", slide=sid)

        clean_plate = slide.get("clean_plate")
        if not isinstance(clean_plate, dict):
            issue(errors, "missing_clean_plate", "clean_plate declaration is required", slide=sid)
            clean_plate = {}
        if clean_plate.get("method") not in CLEAN_PLATE_METHODS:
            issue(
                errors,
                "invalid_clean_plate_method",
                "method must be native, source_inpaint, or source_composite",
                slide=sid,
            )
        if clean_plate.get("reviewed") is not True:
            issue(errors, "clean_plate_not_reviewed", "clean plate must be reviewed", slide=sid)
        if clean_plate.get("contains_semantic_text") is not False:
            issue(
                errors,
                "clean_plate_contains_text",
                "clean plate must declare contains_semantic_text=false",
                slide=sid,
            )
        if clean_plate.get("contains_detached_visuals") is not False:
            issue(
                errors,
                "clean_plate_contains_detached_visuals",
                "clean plate must declare contains_detached_visuals=false",
                slide=sid,
            )
        for key in ("reference_image", "mask_image"):
            value = clean_plate.get(key)
            if value and not Path(value).exists():
                issue(
                    errors,
                    f"missing_clean_plate_{key}",
                    str(value),
                    slide=sid,
                )
        min_unmasked_coverage = clean_plate.get("min_unmasked_coverage", 0.35)
        if (
            not isinstance(min_unmasked_coverage, (int, float))
            or not 0.20 <= min_unmasked_coverage <= 1.0
        ):
            issue(
                errors,
                "invalid_clean_plate_min_coverage",
                "min_unmasked_coverage must be between 0.20 and 1.0",
                slide=sid,
            )

        inventory = slide.get("source_inventory", [])
        if not isinstance(inventory, list) or not inventory:
            issue(errors, "missing_inventory", "source_inventory is required", slide=sid)
            inventory = []
        inventory_ids: set[str] = set()
        inventory_by_id: dict[str, dict] = {}
        required_ids: set[str] = set()
        for item in inventory:
            iid = item.get("id")
            if not isinstance(iid, str) or not iid:
                issue(errors, "invalid_inventory_id", "inventory id is required", slide=sid)
                continue
            if iid in inventory_ids:
                issue(errors, "duplicate_inventory_id", iid, slide=sid)
            inventory_ids.add(iid)
            inventory_by_id[iid] = item
            layer = item.get("layer")
            if layer not in ALLOWED_LAYERS:
                issue(
                    errors,
                    "invalid_inventory_layer",
                    str(layer),
                    slide=sid,
                    inventory=iid,
                )
            item_bbox = item.get("bbox")
            if not valid_bbox(item_bbox):
                issue(
                    errors,
                    "invalid_inventory_bbox",
                    "inventory bbox must contain four finite numbers",
                    slide=sid,
                    inventory=iid,
                )
            else:
                left, top, item_width, item_height = item_bbox
                if item_width <= 0 or item_height <= 0:
                    issue(
                        errors,
                        "non_positive_inventory_bbox",
                        "inventory width and height must be positive",
                        slide=sid,
                        inventory=iid,
                    )
                if (
                    left < -1
                    or top < -1
                    or left + item_width > width + 1
                    or top + item_height > height + 1
                ):
                    issue(
                        warnings,
                        "inventory_bbox_outside_canvas",
                        "inventory item exceeds slide canvas",
                        slide=sid,
                        inventory=iid,
                    )
            if item.get("kind") == "text" and layer != "native_text":
                issue(
                    errors,
                    "text_inventory_wrong_layer",
                    "text inventory must use layer native_text",
                    slide=sid,
                    inventory=iid,
                )
            if layer == "native_text" and item.get("kind") != "text":
                issue(
                    errors,
                    "native_text_inventory_wrong_kind",
                    "native_text inventory must use kind text",
                    slide=sid,
                    inventory=iid,
                )
            if item.get("required", True):
                required_ids.add(iid)
        totals["inventory"] += len(inventory_ids)
        totals["required_inventory"] += len(required_ids)

        critical_regions = slide.get("critical_regions", [])
        if not isinstance(critical_regions, list) or not critical_regions:
            issue(
                errors,
                "missing_critical_regions",
                "critical_regions must be a non-empty array",
                slide=sid,
            )
            critical_regions = []
        if len(critical_regions) < 3:
            issue(
                warnings,
                "few_critical_regions",
                "dense slides should declare title, hero/content, and footer/card regions",
                slide=sid,
            )
        critical_ids: set[str] = set()
        for region in critical_regions:
            rid = region.get("id")
            if not isinstance(rid, str) or not rid:
                issue(errors, "invalid_critical_region_id", "region id is required", slide=sid)
                continue
            if rid in critical_ids:
                issue(errors, "duplicate_critical_region_id", rid, slide=sid)
            critical_ids.add(rid)
            if not valid_bbox(region.get("bbox")):
                issue(
                    errors,
                    "invalid_critical_region_bbox",
                    "critical region bbox must contain four finite numbers",
                    slide=sid,
                    region=rid,
                )
            threshold = region.get("min_similarity")
            if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
                issue(
                    errors,
                    "invalid_critical_region_threshold",
                    "min_similarity must be between 0 and 1",
                    slide=sid,
                    region=rid,
                )
        totals["critical_regions"] += len(critical_ids)

        elements = slide.get("elements", [])
        if not isinstance(elements, list) or not elements:
            issue(errors, "missing_elements", "elements is required", slide=sid)
            elements = []
        used_source_ids: set[str] = set()
        native_text = []
        baseboard_roots: list[dict] = []

        for element in elements:
            totals["elements"] += 1
            eid = element.get("id")
            etype = element.get("type")
            if not isinstance(eid, str) or not eid:
                issue(errors, "invalid_element_id", "element id is required", slide=sid)
                continue
            if eid in all_element_ids:
                issue(errors, "duplicate_element_id", eid, slide=sid)
            all_element_ids.add(eid)
            if etype not in ALLOWED_TYPES:
                issue(errors, "unsupported_element_type", str(etype), slide=sid, element=eid)
                continue
            layer = element.get("layer")
            if layer not in ALLOWED_LAYERS:
                issue(
                    errors,
                    "invalid_element_layer",
                    str(layer),
                    slide=sid,
                    element=eid,
                )
            if etype == "native_text" and layer != "native_text":
                issue(
                    errors,
                    "native_text_wrong_layer",
                    "native_text elements must use layer native_text",
                    slide=sid,
                    element=eid,
                )
            if etype == "background_texture" and layer != "baseboard":
                issue(
                    errors,
                    "background_texture_wrong_layer",
                    "background_texture elements must use layer baseboard",
                    slide=sid,
                    element=eid,
                )
            if etype == "local_picture" and layer not in {"visual_asset", "decoration"}:
                issue(
                    errors,
                    "local_picture_wrong_layer",
                    "local_picture elements must use layer visual_asset or decoration",
                    slide=sid,
                    element=eid,
                )
            if not isinstance(element.get("z"), int):
                issue(errors, "invalid_z", "z must be an integer", slide=sid, element=eid)
            bbox = element.get("bbox")
            if not valid_bbox(bbox):
                issue(errors, "invalid_bbox", "bbox must contain four finite numbers", slide=sid, element=eid)
            else:
                left, top, box_width, box_height = bbox
                if etype != "native_line" and (box_width <= 0 or box_height <= 0):
                    issue(errors, "non_positive_bbox", "width and height must be positive", slide=sid, element=eid)
                right = left + box_width
                bottom = top + box_height
                if min(left, right) < -1 or min(top, bottom) < -1 or max(left, right) > width + 1 or max(top, bottom) > height + 1:
                    issue(warnings, "bbox_outside_canvas", "element exceeds slide canvas", slide=sid, element=eid)

            source_ids = element.get("source_ids", [])
            if not isinstance(source_ids, list) or not source_ids:
                issue(errors, "missing_source_ids", "source_ids is required", slide=sid, element=eid)
            else:
                for source_id in source_ids:
                    if source_id not in inventory_ids:
                        issue(errors, "unknown_source_id", str(source_id), slide=sid, element=eid)
                        continue
                    used_source_ids.add(source_id)
                    source_item = inventory_by_id[source_id]
                    source_layer = source_item.get("layer")
                    if source_layer != layer:
                        issue(
                            errors,
                            "source_output_layer_mismatch",
                            f"inventory layer {source_layer!r} maps to element layer {layer!r}",
                            slide=sid,
                            inventory=source_id,
                            element=eid,
                        )
                    if (
                        source_item.get("kind") == "text"
                        or source_layer == "native_text"
                    ) and etype != "native_text":
                        issue(
                            errors,
                            "text_inventory_mapped_to_non_text",
                            "text inventory may map only to native_text",
                            slide=sid,
                            inventory=source_id,
                            element=eid,
                        )

            if etype == "native_text":
                totals["native_text"] += 1
                value = text_value(element)
                native_text.append(value)
                if not value:
                    issue(errors, "empty_native_text", "native text cannot be empty", slide=sid, element=eid)
                if value != unicodedata.normalize("NFC", value):
                    issue(errors, "text_not_nfc", "normalize text to NFC", slide=sid, element=eid)
                for fragment in BAD_TEXT_FRAGMENTS:
                    if fragment in value:
                        issue(errors, "mojibake_or_replacement", fragment, slide=sid, element=eid)
                style = element.get("style", {})
                if style.get("wrap") is not False and "\n" not in value and len(value) <= 40:
                    issue(warnings, "short_text_wrap_enabled", "review one-line text wrapping", slide=sid, element=eid)
                if "outline_color" in style:
                    outline_width = style.get("outline_width", 1)
                    if not isinstance(outline_width, (int, float)) or outline_width <= 0:
                        issue(
                            errors,
                            "invalid_text_outline_width",
                            "outline_width must be positive",
                            slide=sid,
                            element=eid,
                        )
                for run_index, run in enumerate(element.get("runs", []), start=1):
                    if "outline_color" in run:
                        outline_width = run.get("outline_width", 1)
                        if not isinstance(outline_width, (int, float)) or outline_width <= 0:
                            issue(
                                errors,
                                "invalid_run_outline_width",
                                "run outline_width must be positive",
                                slide=sid,
                                element=eid,
                                run=run_index,
                            )
            elif etype in {"local_picture", "background_texture"}:
                totals["pictures"] += 1
                image_path = Path(element.get("path", ""))
                if image_path and not image_path.is_absolute():
                    image_path = scene_path.parent / image_path
                if not image_path.exists():
                    issue(errors, "missing_picture", str(image_path), slide=sid, element=eid)
                if element.get("contains_readable_text") is not False:
                    issue(errors, "picture_text_not_cleared", "picture must declare contains_readable_text=false", slide=sid, element=eid)
                if not element.get("complex_reason"):
                    issue(errors, "missing_complex_reason", "picture requires complex_reason", slide=sid, element=eid)
                if valid_bbox(bbox):
                    area_ratio = abs(bbox[2] * bbox[3]) / (width * height)
                    if etype == "local_picture" and area_ratio >= 0.80:
                        issue(errors, "oversized_local_picture", f"area ratio {area_ratio:.3f}", slide=sid, element=eid)
                if etype == "background_texture":
                    if element.get("contains_detached_visuals") is not False:
                        issue(
                            errors,
                            "background_contains_detached_visuals",
                            "background texture must declare contains_detached_visuals=false",
                            slide=sid,
                            element=eid,
                        )
            else:
                totals["native_objects"] += 1

            if element.get("role") == "baseboard_root":
                baseboard_roots.append(element)
                if layer != "baseboard":
                    issue(
                        errors,
                        "baseboard_root_wrong_layer",
                        "baseboard_root must use layer baseboard",
                        slide=sid,
                        element=eid,
                    )
                if etype not in {"native_shape", "background_texture"}:
                    issue(
                        errors,
                        "baseboard_root_wrong_type",
                        "baseboard_root must be native_shape or background_texture",
                        slide=sid,
                        element=eid,
                    )
                if valid_bbox(bbox):
                    area_ratio = abs(bbox[2] * bbox[3]) / (width * height)
                    if area_ratio < 0.95:
                        issue(
                            errors,
                            "baseboard_root_not_full_slide",
                            f"area ratio {area_ratio:.3f}",
                            slide=sid,
                            element=eid,
                        )
                    left, top, root_width, root_height = bbox
                    if (
                        left > 1
                        or top > 1
                        or left + root_width < width - 1
                        or top + root_height < height - 1
                    ):
                        issue(
                            errors,
                            "baseboard_root_does_not_cover_canvas",
                            "baseboard_root must cover every slide edge",
                            slide=sid,
                            element=eid,
                        )

        if len(baseboard_roots) != 1:
            issue(
                errors,
                "invalid_baseboard_root_count",
                f"expected exactly one baseboard_root, found {len(baseboard_roots)}",
                slide=sid,
            )
        totals["baseboard_roots"] += len(baseboard_roots)

        missing = sorted(required_ids - used_source_ids)
        for iid in missing:
            issue(errors, "unmapped_required_inventory", iid, slide=sid)

        rendered_native_text = "\n".join(native_text)
        compact_native_text = "".join(rendered_native_text.split())
        for expected in slide.get("expected_text", []):
            expected = str(expected)
            if expected != unicodedata.normalize("NFC", expected):
                issue(errors, "expected_text_not_nfc", expected, slide=sid)
            if (
                expected not in rendered_native_text
                and "".join(expected.split()) not in compact_native_text
            ):
                issue(errors, "expected_text_missing_from_native_text", expected, slide=sid)

    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "totals": totals,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = lint(args.scene.resolve())
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
