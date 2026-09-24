#!/usr/bin/env python3
"""Patch explicit fonts and stable object metadata into DrawingML."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image, ImageFile


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A_NS, "p": P_NS}
EMU_PER_PIXEL = 9525
ImageFile.LOAD_TRUNCATED_IMAGES = True


def ensure_font(parent, tag: str, typeface: str) -> None:
    child = parent.find(f"a:{tag}", NS)
    if child is None:
        child = etree.SubElement(parent, f"{{{A_NS}}}{tag}")
    child.set("typeface", typeface)


def patch_xml(data: bytes, latin: str, east_asian: str, complex_script: str) -> bytes:
    root = etree.fromstring(data)
    changed = False
    for node in root.xpath(
        ".//a:rPr | .//a:defRPr | .//a:endParaRPr", namespaces=NS
    ):
        ensure_font(node, "latin", latin)
        ensure_font(node, "ea", east_asian)
        ensure_font(node, "cs", complex_script)
        changed = True
    for node in root.xpath(".//a:majorFont | .//a:minorFont", namespaces=NS):
        ensure_font(node, "latin", latin)
        ensure_font(node, "ea", east_asian)
        ensure_font(node, "cs", complex_script)
        changed = True
    if not changed:
        return data
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def slide_number(name: str) -> int | None:
    match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name)
    return int(match.group(1)) if match else None


def source_dimensions(scene_dir: Path, element: dict) -> tuple[int, int]:
    source = Path(element["path"])
    if not source.is_absolute():
        source = scene_dir / source
    with Image.open(source) as image:
        return image.size


def crop_to_cover(
    crop: list[float],
    source_size: tuple[int, int],
    frame: list[float],
) -> list[float]:
    left, top, right, bottom = map(float, crop)
    source_width, source_height = source_size
    crop_width = (right - left) * source_width
    crop_height = (bottom - top) * source_height
    target_aspect = float(frame[2]) / float(frame[3])
    crop_aspect = crop_width / crop_height
    if crop_aspect > target_aspect:
        next_width = crop_height * target_aspect / source_width
        center = (left + right) / 2
        left, right = center - next_width / 2, center + next_width / 2
    elif crop_aspect < target_aspect:
        next_height = crop_width / target_aspect / source_height
        center = (top + bottom) / 2
        top, bottom = center - next_height / 2, center + next_height / 2
    return [left, top, right, bottom]


def contain_frame(
    frame: list[float],
    crop: list[float],
    source_size: tuple[int, int],
) -> list[float]:
    x, y, width, height = map(float, frame)
    left, top, right, bottom = map(float, crop)
    source_width, source_height = source_size
    crop_aspect = (
        (right - left) * source_width / ((bottom - top) * source_height)
    )
    frame_aspect = width / height
    if crop_aspect > frame_aspect:
        next_height = width / crop_aspect
        y += (height - next_height) / 2
        height = next_height
    else:
        next_width = height * crop_aspect
        x += (width - next_width) / 2
        width = next_width
    return [x, y, width, height]


def patch_object_metadata(data: bytes, slide: dict, scene_dir: Path) -> bytes:
    root = etree.fromstring(data)
    pictures = root.xpath("./p:cSld/p:spTree/p:pic", namespaces=NS)
    expected = [
        element
        for element in sorted(slide.get("elements", []), key=lambda item: item["z"])
        if element.get("type") in {"local_picture", "background_texture"}
    ]
    for picture, element in zip(pictures, expected, strict=False):
        metadata = picture.find("p:nvPicPr/p:cNvPr", NS)
        if metadata is None:
            continue
        metadata.set("name", str(element["id"]))
        metadata.set(
            "descr",
            str(element.get("complex_reason", "source-specific complex visual")),
        )
        crop = element.get("source_crop")
        if isinstance(crop, list) and len(crop) == 4:
            dimensions = source_dimensions(scene_dir, element)
            if element.get("fit", "cover") == "cover":
                crop = crop_to_cover(crop, dimensions, element["bbox"])
            elif element.get("fit") == "contain":
                xfrm = picture.find("p:spPr/a:xfrm", NS)
                if xfrm is not None:
                    fitted = contain_frame(element["bbox"], crop, dimensions)
                    off = xfrm.find("a:off", NS)
                    ext = xfrm.find("a:ext", NS)
                    if off is not None and ext is not None:
                        off.set("x", str(round(fitted[0] * EMU_PER_PIXEL)))
                        off.set("y", str(round(fitted[1] * EMU_PER_PIXEL)))
                        ext.set("cx", str(round(fitted[2] * EMU_PER_PIXEL)))
                        ext.set("cy", str(round(fitted[3] * EMU_PER_PIXEL)))
            left, top, right, bottom = crop
            src_rect = picture.find("p:blipFill/a:srcRect", NS)
            if src_rect is None:
                blip_fill = picture.find("p:blipFill", NS)
                if blip_fill is not None:
                    src_rect = etree.Element(f"{{{A_NS}}}srcRect")
                    blip_fill.insert(1, src_rect)
            if src_rect is not None:
                src_rect.set("l", str(round(float(left) * 100000)))
                src_rect.set("t", str(round(float(top) * 100000)))
                src_rect.set("r", str(round((1 - float(right)) * 100000)))
                src_rect.set("b", str(round((1 - float(bottom)) * 100000)))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def patch_pptx(
    pptx: Path,
    latin: str,
    east_asian: str,
    complex_script: str,
    scene: dict | None,
    scene_dir: Path | None,
) -> None:
    fd, temp_name = tempfile.mkstemp(suffix=".pptx", dir=pptx.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with zipfile.ZipFile(pptx, "r") as source, zipfile.ZipFile(
            temp_path, "w", zipfile.ZIP_DEFLATED
        ) as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename.startswith("ppt/") and info.filename.endswith(".xml"):
                    try:
                        data = patch_xml(data, latin, east_asian, complex_script)
                        number = slide_number(info.filename)
                        if number and scene and number <= len(scene.get("slides", [])):
                            data = patch_object_metadata(
                                data,
                                scene["slides"][number - 1],
                                scene_dir or Path.cwd(),
                            )
                    except etree.XMLSyntaxError:
                        pass
                target.writestr(info, data)
        os.replace(temp_path, pptx)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--latin", default="Arial")
    parser.add_argument("--east-asian", default="Noto Sans CJK SC")
    parser.add_argument("--complex-script", default="Arial")
    parser.add_argument("--scene", type=Path)
    args = parser.parse_args()
    scene = (
        json.loads(args.scene.resolve().read_text(encoding="utf-8"))
        if args.scene
        else None
    )
    patch_pptx(
        args.pptx.resolve(),
        args.latin,
        args.east_asian,
        args.complex_script,
        scene,
        args.scene.resolve().parent if args.scene else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
