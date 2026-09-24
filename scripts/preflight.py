#!/usr/bin/env python3
"""Probe image inputs, conversion tools, OCR languages, and fonts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageFile


ImageFile.LOAD_TRUNCATED_IMAGES = True


def command_version(command: str, args: list[str]) -> dict:
    path = shutil.which(command)
    result = {"command": command, "path": path, "available": bool(path)}
    if not path:
        return result
    try:
        proc = subprocess.run(
            [path, *args], capture_output=True, text=True, timeout=15, check=False
        )
        text = (proc.stdout or proc.stderr).strip().splitlines()
        result["version"] = text[0] if text else ""
        result["returncode"] = proc.returncode
    except Exception as exc:  # pragma: no cover - defensive probe
        result["error"] = str(exc)
    return result


def tesseract_languages() -> list[str]:
    path = shutil.which("tesseract")
    if not path:
        return []
    proc = subprocess.run(
        [path, "--list-langs"], capture_output=True, text=True, check=False
    )
    lines = [line.strip() for line in proc.stdout.splitlines()]
    return [line for line in lines if line and not line.startswith("List of")]


def resolve_font(family: str) -> dict:
    path = shutil.which("fc-match")
    if not path:
        return {"requested": family, "available": False, "reason": "fc-match missing"}
    proc = subprocess.run(
        [path, "-f", "%{family}|%{file}\n", family],
        capture_output=True,
        text=True,
        check=False,
    )
    first = proc.stdout.splitlines()[0] if proc.stdout.splitlines() else ""
    resolved, _, filename = first.partition("|")
    exact = family.casefold() in {part.strip().casefold() for part in resolved.split(",")}
    return {
        "requested": family,
        "resolved": resolved,
        "file": filename,
        "available": bool(filename),
        "exact": exact,
    }


def inspect_image(path: Path) -> dict:
    item = {"path": str(path.resolve()), "exists": path.exists(), "valid": False}
    if not path.exists():
        item["error"] = "missing"
        return item
    try:
        with Image.open(path) as image:
            image.load()
            item.update(
                {
                    "valid": True,
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                    "format": image.format,
                    "aspect_ratio": round(image.width / image.height, 6),
                }
            )
    except Exception as exc:
        item["error"] = str(exc)
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--latin-font", default="Arial")
    parser.add_argument("--east-asian-font", default="Noto Sans CJK SC")
    parser.add_argument("--fontconfig-file", type=Path)
    args = parser.parse_args()
    if args.fontconfig_file:
        os.environ["FONTCONFIG_FILE"] = str(args.fontconfig_file.resolve())

    images = [inspect_image(path) for path in args.inputs]
    tools = {
        "python": command_version("python3", ["--version"]),
        "node": command_version("node", ["--version"]),
        "tesseract": command_version("tesseract", ["--version"]),
        "soffice": command_version("soffice", ["--version"]),
        "pdftoppm": command_version("pdftoppm", ["-v"]),
    }
    runtime_modules = Path(
        os.environ.get("CODEX_PRIMARY_RUNTIME_NODE_MODULES", "")
    )
    artifact_package = runtime_modules / "@oai" / "artifact-tool" / "package.json"
    tools["artifact_tool"] = {
        "available": artifact_package.exists(),
        "path": str(artifact_package) if artifact_package.exists() else None,
    }
    fonts = {
        "latin": resolve_font(args.latin_font),
        "east_asian": resolve_font(args.east_asian_font),
    }
    errors = []
    warnings = []
    if not all(item["valid"] for item in images):
        errors.append("one_or_more_invalid_images")
    for required in ("python", "node", "artifact_tool"):
        if not tools[required]["available"]:
            errors.append(f"missing_tool:{required}")
    langs = tesseract_languages()
    if not any(lang in langs for lang in ("chi_sim", "chi_tra")):
        warnings.append("chinese_ocr_unavailable_use_visual_transcription_and_review")
    if not fonts["east_asian"].get("exact"):
        errors.append("east_asian_font_not_available_exactly")

    report = {
        "status": "passed" if not errors else "failed",
        "images": images,
        "tools": tools,
        "ocr_languages": langs,
        "fonts": fonts,
        "errors": errors,
        "warnings": warnings,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
