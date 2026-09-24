#!/usr/bin/env python3
"""Expand compact scene defaults and style references deterministically."""

from __future__ import annotations

import copy
import json
from pathlib import Path


def deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def absolute_asset_paths(scene: dict, scene_dir: Path) -> None:
    for slide in scene.get("slides", []):
        source = slide.get("source_image")
        if source and not Path(source).is_absolute():
            slide["source_image"] = str((scene_dir / source).resolve())
        clean_plate = slide.get("clean_plate", {})
        for key in ("reference_image", "mask_image"):
            value = clean_plate.get(key)
            if value and not Path(value).is_absolute():
                clean_plate[key] = str((scene_dir / value).resolve())
        for element in slide.get("elements", []):
            if element.get("type") not in {"local_picture", "background_texture"}:
                continue
            value = element.get("path")
            if value and not Path(value).is_absolute():
                element["path"] = str((scene_dir / value).resolve())


def expand_scene(scene: dict, scene_dir: Path) -> dict:
    expanded = copy.deepcopy(scene)
    defaults = expanded.pop("defaults", {}) or {}
    common_defaults = defaults.get("element", {}) or {}
    type_defaults = defaults.get("types", {}) or {}
    styles = expanded.pop("styles", {}) or {}

    for slide in expanded.get("slides", []):
        slide_defaults = slide.pop("defaults", {}) or {}
        slide_common = deep_merge(common_defaults, slide_defaults.get("element", {}) or {})
        slide_types = deep_merge(type_defaults, slide_defaults.get("types", {}) or {})
        slide_styles = deep_merge(styles, slide.pop("styles", {}) or {})
        output = []
        for raw in slide.get("elements", []):
            element_type = raw.get("type")
            element = deep_merge(slide_common, slide_types.get(element_type, {}) or {})
            element = deep_merge(element, raw)
            style_ref = element.pop("style_ref", None)
            if style_ref:
                if style_ref not in slide_styles:
                    raise ValueError(
                        f"unknown style_ref {style_ref!r} on element {element.get('id')!r}"
                    )
                element["style"] = deep_merge(
                    slide_styles[style_ref], element.get("style", {}) or {}
                )
            output.append(element)
        slide["elements"] = output

    expanded["version"] = "1.1"
    absolute_asset_paths(expanded, scene_dir)
    return expanded


def load_expanded(scene_path: Path) -> dict:
    scene_path = scene_path.resolve()
    raw = json.loads(scene_path.read_text(encoding="utf-8"))
    version = str(raw.get("version", ""))
    if version not in {"1.1", "1.2"}:
        raise ValueError(f"unsupported scene version: {version!r}")
    return expand_scene(raw, scene_path.parent)


def write_expanded(scene_path: Path, output_path: Path) -> Path:
    expanded = load_expanded(scene_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(expanded, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path
