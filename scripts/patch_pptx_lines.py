#!/usr/bin/env python3
"""Set semantic strokes to 1 pt and attach arrowheads to the same line shape."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
ARROW_TYPES = {"triangle", "stealth", "diamond", "oval", "arrow"}


def arrow_type(value: object) -> str | None:
    if value is None or value is False or str(value).lower() == "none":
        return None
    return str(value) if str(value) in ARROW_TYPES else "triangle"


def add_line_end(stroke: etree._Element, tag: str, kind: str | None) -> None:
    qn = f"{{{NS['a']}}}{tag}"
    for existing in list(stroke):
        if existing.tag == qn:
            stroke.remove(existing)
    if kind is None:
        return
    node = etree.Element(qn, type=kind, w="sm", len="sm")
    extension = stroke.find("a:extLst", NS)
    if extension is None:
        stroke.append(node)
    else:
        stroke.insert(stroke.index(extension), node)


def patch_slide(
    root: etree._Element, elements: list[dict], slide_number: int, stage: str
) -> tuple[int, int]:
    shapes: dict[str, etree._Element] = {}
    for shape in root.xpath(".//p:sp | .//p:cxnSp", namespaces=NS):
        metadata = shape.find("p:nvSpPr/p:cNvPr", NS)
        if metadata is None:
            metadata = shape.find("p:nvCxnSpPr/p:cNvPr", NS)
        if metadata is not None:
            name = metadata.get("name")
            if name in shapes:
                raise ValueError(f"slide {slide_number}: duplicate shape name {name}")
            shapes[name] = shape

    line_count = arrow_count = 0
    for element in elements:
        if stage == "baseboard" and element.get("layer") != "baseboard":
            continue
        if stage == "semantic" and element.get("layer") == "decoration":
            continue
        semantic_line = element.get("type") == "native_line"
        stroke_path = element.get("type") == "native_path" and element.get("fill", "none") == "none"
        if not (semantic_line or stroke_path):
            continue
        element_id = str(element["id"])
        shape = shapes.get(element_id)
        if shape is None:
            raise ValueError(f"slide {slide_number}: missing line shape {element_id}")
        stroke = shape.find("p:spPr/a:ln", NS)
        if stroke is None:
            raise ValueError(f"slide {slide_number}: missing stroke on {element_id}")
        width_pt = float((element.get("line") or {}).get("width_pt", 1))
        if width_pt <= 0:
            raise ValueError(f"slide {slide_number}: invalid line.width_pt on {element_id}")
        stroke.set("w", str(round(width_pt * 12700)))  # DrawingML EMU: 12700 per point.
        line_count += 1
        if semantic_line:
            # Scene bbox [x, y, dx, dy] defines the final endpoint at x+dx, y+dy.
            # The compiler's line preset applies flips for negative deltas.
            start = arrow_type(element.get("tail"))
            end = arrow_type(element.get("head"))
            add_line_end(stroke, "headEnd", start)
            add_line_end(stroke, "tailEnd", end)
            arrow_count += int(start is not None) + int(end is not None)
            if f"{element_id}-head" in shapes:
                raise ValueError(f"slide {slide_number}: detached arrowhead on {element_id}")
    return line_count, arrow_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--stage", choices=("baseboard", "semantic", "final"), default="final")
    args = parser.parse_args()
    pptx = args.pptx.resolve()
    scene = json.loads(args.scene.read_text(encoding="utf-8"))
    slides = scene.get("slides", [])
    patched: dict[str, bytes] = {}
    total_lines = total_arrows = 0

    handle, temp_name = tempfile.mkstemp(suffix=".pptx", dir=pptx.parent)
    os.close(handle)
    temporary = Path(temp_name)
    try:
        with zipfile.ZipFile(pptx, "r") as original:
            for index, slide in enumerate(slides, start=1):
                part = f"ppt/slides/slide{index}.xml"
                root = etree.fromstring(original.read(part))
                lines, arrows = patch_slide(root, slide.get("elements", []), index, args.stage)
                total_lines += lines
                total_arrows += arrows
                patched[part] = etree.tostring(
                    root, encoding="UTF-8", xml_declaration=True, standalone=True
                )
            with zipfile.ZipFile(temporary, "w") as output:
                for info in original.infolist():
                    data = patched[info.filename] if info.filename in patched else original.read(info.filename)
                    output.writestr(info, data)
        os.replace(temporary, pptx)
    finally:
        temporary.unlink(missing_ok=True)

    print(json.dumps({"semantic_lines": total_lines, "attached_arrow_ends": total_arrows}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
