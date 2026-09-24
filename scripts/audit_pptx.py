#!/usr/bin/env python3
"""Audit PPTX OOXML for editability, text coverage, and package integrity."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

from lxml import etree

from scene_defaults import load_expanded

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}
BAD_TEXT_FRAGMENTS = ("�", "Ã", "Â", "â€™", "â€œ", "â€", "锟斤拷")


def slide_sort_key(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def load_xml(archive: zipfile.ZipFile, name: str):
    return etree.fromstring(archive.read(name))


def inspect_picture_frames(root, slide_width: int, slide_height: int) -> list[dict]:
    frames = []
    for picture in root.xpath(".//p:pic", namespaces=NS):
        metadata = picture.find(".//p:cNvPr", NS)
        xfrm = picture.find(".//p:spPr/a:xfrm", NS)
        if xfrm is None:
            continue
        off = xfrm.find("a:off", NS)
        ext = xfrm.find("a:ext", NS)
        if off is None or ext is None:
            continue
        x, y = int(off.get("x", 0)), int(off.get("y", 0))
        cx, cy = int(ext.get("cx", 0)), int(ext.get("cy", 0))
        ratio = (cx * cy) / (slide_width * slide_height) if slide_width and slide_height else 0
        frames.append(
            {
                "name": metadata.get("name", "") if metadata is not None else "",
                "x": x,
                "y": y,
                "cx": cx,
                "cy": cy,
                "area_ratio": ratio,
            }
        )
    return frames


def inspect_object_frames(root, slide_width: int, slide_height: int) -> list[dict]:
    frames = []
    sp_tree = root.find(".//p:spTree", NS)
    if sp_tree is None:
        return frames
    for child in sp_tree:
        if etree.QName(child).localname not in {"sp", "pic", "graphicFrame", "grpSp"}:
            continue
        metadata = child.find(".//p:cNvPr", NS)
        xfrm = child.find(".//a:xfrm", NS)
        if xfrm is None:
            continue
        off = xfrm.find("a:off", NS)
        ext = xfrm.find("a:ext", NS)
        if off is None or ext is None:
            continue
        x, y = int(off.get("x", 0)), int(off.get("y", 0))
        cx, cy = int(ext.get("cx", 0)), int(ext.get("cy", 0))
        frames.append(
            {
                "name": metadata.get("name", "") if metadata is not None else "",
                "x": x,
                "y": y,
                "cx": cx,
                "cy": cy,
                "inside": x >= 0
                and y >= 0
                and x + cx <= slide_width
                and y + cy <= slide_height,
            }
        )
    return frames


def audit(pptx: Path, scene_path: Path) -> dict:
    scene = load_expanded(scene_path)
    errors: list[dict] = []
    warnings: list[dict] = []
    counts = {
        "slides": 0,
        "native_text_shapes": 0,
        "native_shapes": 0,
        "native_tables": 0,
        "native_charts": 0,
        "pictures": 0,
        "full_slide_pictures": 0,
        "full_slide_backgrounds": 0,
        "prohibited_full_slide_pictures": 0,
        "media_files": 0,
        "objects_outside_slide": 0,
    }
    all_text: list[str] = []
    all_names: set[str] = set()
    font_nodes = 0
    east_asian_nodes = 0

    try:
        archive = zipfile.ZipFile(pptx, "r")
    except Exception as exc:
        return {
            "status": "failed",
            "errors": [{"code": "invalid_pptx_zip", "message": str(exc)}],
            "warnings": [],
            "counts": counts,
        }

    with archive:
        names = archive.namelist()
        required = {"[Content_Types].xml", "ppt/presentation.xml"}
        missing_required = sorted(required - set(names))
        for name in missing_required:
            errors.append({"code": "missing_package_part", "message": name})

        presentation = load_xml(archive, "ppt/presentation.xml")
        sld_size = presentation.find("p:sldSz", NS)
        slide_width = int(sld_size.get("cx", 0)) if sld_size is not None else 0
        slide_height = int(sld_size.get("cy", 0)) if sld_size is not None else 0

        slide_names = sorted(
            [
                name
                for name in names
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ],
            key=slide_sort_key,
        )
        counts["slides"] = len(slide_names)

        scene_slides = scene.get("slides", [])
        for slide_index, slide_name in enumerate(slide_names):
            root = load_xml(archive, slide_name)
            counts["native_text_shapes"] += len(
                root.xpath(".//p:sp[p:txBody]", namespaces=NS)
            )
            counts["native_shapes"] += len(root.xpath(".//p:sp", namespaces=NS))
            counts["native_tables"] += len(root.xpath(".//a:tbl", namespaces=NS))
            counts["native_charts"] += len(root.xpath(".//c:chart", namespaces=NS))
            counts["pictures"] += len(root.xpath(".//p:pic", namespaces=NS))
            for text_node in root.xpath(".//a:t", namespaces=NS):
                all_text.append(text_node.text or "")
            for node in root.xpath(".//*[local-name()='cNvPr']"):
                for field in ("name", "descr", "title"):
                    if node.get(field):
                        all_names.add(node.get(field))
            font_nodes += len(
                root.xpath(
                    ".//a:rPr | .//a:defRPr | .//a:endParaRPr", namespaces=NS
                )
            )
            east_asian_nodes += len(
                root.xpath(
                    ".//a:rPr/a:ea | .//a:defRPr/a:ea | .//a:endParaRPr/a:ea",
                    namespaces=NS,
                )
            )
            frames = inspect_picture_frames(root, slide_width, slide_height)
            allowed_background_ids = {
                str(element.get("id"))
                for element in (
                    scene_slides[slide_index].get("elements", [])
                    if slide_index < len(scene_slides)
                    else []
                )
                if element.get("type") == "background_texture"
                and element.get("role") == "baseboard_root"
                and element.get("contains_readable_text") is False
                and element.get("contains_detached_visuals") is False
            }
            for frame in frames:
                if frame["area_ratio"] < 0.90:
                    continue
                counts["full_slide_pictures"] += 1
                if frame["name"] in allowed_background_ids:
                    counts["full_slide_backgrounds"] += 1
                else:
                    counts["prohibited_full_slide_pictures"] += 1
            for frame in inspect_object_frames(root, slide_width, slide_height):
                if not frame["inside"]:
                    counts["objects_outside_slide"] += 1
                    errors.append(
                        {
                            "code": "object_outside_slide",
                            "message": f'{slide_name}: {frame["name"] or "unnamed"}',
                            "frame": frame,
                        }
                    )

        media_names = [name for name in names if name.startswith("ppt/media/")]
        counts["media_files"] = len(media_names)
        for name in media_names:
            if archive.getinfo(name).file_size == 0:
                errors.append({"code": "zero_byte_media", "message": name})

    if counts["slides"] != len(scene.get("slides", [])):
        errors.append(
            {
                "code": "slide_count_mismatch",
                "message": f'{counts["slides"]} != {len(scene.get("slides", []))}',
            }
        )

    joined_text = "\n".join(all_text)
    compact_text = "".join("".join(all_text).split())
    for fragment in BAD_TEXT_FRAGMENTS:
        if fragment in joined_text:
            errors.append({"code": "mojibake_or_replacement", "message": fragment})

    expected_total = 0
    expected_found = 0
    missing_expected = []
    expected_object_ids = []
    for slide in scene.get("slides", []):
        for expected in slide.get("expected_text", []):
            expected_total += 1
            if (
                str(expected) in joined_text
                or "".join(str(expected).split()) in compact_text
            ):
                expected_found += 1
            else:
                missing_expected.append(str(expected))
        for element in slide.get("elements", []):
            if element.get("type") not in {"native_table", "native_chart"}:
                expected_object_ids.append(element.get("id"))

    for expected in missing_expected:
        errors.append({"code": "expected_text_missing_from_pptx", "message": expected})

    missing_objects = []
    for object_id in expected_object_ids:
        if not object_id:
            continue
        if not any(object_id in value for value in all_names):
            missing_objects.append(object_id)
    for object_id in missing_objects:
        errors.append({"code": "scene_object_missing_from_pptx", "message": object_id})

    if counts["prohibited_full_slide_pictures"]:
        errors.append(
            {
                "code": "full_slide_picture_detected",
                "message": str(counts["prohibited_full_slide_pictures"]),
            }
        )
    if font_nodes and east_asian_nodes < font_nodes:
        errors.append(
            {
                "code": "east_asian_font_not_explicit_everywhere",
                "message": f"{east_asian_nodes}/{font_nodes}",
            }
        )

    report = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "counts": counts,
        "expected_text": {
            "total": expected_total,
            "found": expected_found,
            "coverage": expected_found / expected_total if expected_total else 1.0,
            "missing": missing_expected,
        },
        "scene_objects": {
            "expected": len(expected_object_ids),
            "found": len(expected_object_ids) - len(missing_objects),
            "missing": missing_objects,
        },
        "fonts": {
            "text_property_nodes": font_nodes,
            "explicit_east_asian_nodes": east_asian_nodes,
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = audit(args.pptx.resolve(), args.scene.resolve())
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
