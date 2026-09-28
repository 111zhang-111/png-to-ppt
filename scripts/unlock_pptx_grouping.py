#!/usr/bin/env python3
"""Remove PowerPoint grouping locks after the last PPTX export."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
LOCK_TAGS = {"spLocks", "picLocks", "cxnSpLocks", "graphicFrameLocks", "grpSpLocks"}


def unlock(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(suffix=".pptx", dir=output.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    removed = changed_parts = 0
    try:
        with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(temporary, "w") as repaired:
            for info in original.infolist():
                data = original.read(info.filename)
                if info.filename.startswith("ppt/") and info.filename.endswith(".xml"):
                    root = etree.fromstring(data)
                    part_removed = 0
                    for node in root.iter():
                        if not isinstance(node.tag, str):
                            continue
                        tag = etree.QName(node)
                        if tag.namespace == DRAWING_NS and tag.localname in LOCK_TAGS and "noGrp" in node.attrib:
                            del node.attrib["noGrp"]
                            part_removed += 1
                    if part_removed:
                        data = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
                        removed += part_removed
                        changed_parts += 1
                repaired.writestr(info, data)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"output": str(output), "grouping_locks_removed": removed, "changed_xml_parts": changed_parts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--output", type=Path, help="Write a repaired copy; otherwise update in place")
    args = parser.parse_args()
    print(json.dumps(unlock(args.pptx, args.output or args.pptx), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
