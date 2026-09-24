# Scene Contract

Use UTF-8 JSON and source-image pixel coordinates. Version `1.1` is the expanded
format. Version `1.2` adds defaults and style references; the build script
expands it to `1.1`.

## Top Level

```json
{
  "version": "1.2",
  "title": "Editable reconstruction",
  "slide_size": {"width": 1672, "height": 941},
  "font_policy": {
    "latin": "Arial",
    "east_asian": "Noto Sans CJK SC",
    "complex_script": "Arial"
  },
  "defaults": {},
  "styles": {},
  "slides": []
}
```

Each slide requires:

- `id`
- `source_image`
- `clean_plate`
- `source_inventory`
- `critical_regions`
- `expected_text`
- `elements`

## Defaults and Styles

Use defaults to avoid repeating fields:

```json
{
  "defaults": {
    "element": {
      "editability": "native"
    },
    "types": {
      "native_text": {
        "layer": "native_text"
      },
      "local_picture": {
        "layer": "visual_asset",
        "editability": "picture",
        "fit": "cover",
        "contains_readable_text": false
      }
    }
  },
  "styles": {
    "body": {
      "font_size": 18,
      "font_face": "Arial",
      "east_asian_font": "Noto Sans CJK SC",
      "color": "#111111",
      "wrap": false,
      "auto_fit": "none",
      "margin": 0
    },
    "display": {
      "font_size": 56,
      "font_face": "Arial",
      "bold": true,
      "color": "#111111",
      "wrap": false,
      "auto_fit": "none",
      "margin": 0
    }
  }
}
```

Reference a style and override only differences:

```json
{
  "id": "title",
  "type": "native_text",
  "style_ref": "display",
  "bbox": [80, 50, 620, 90],
  "z": 20,
  "source_ids": ["s-title"],
  "text": "Editable title",
  "style": {"color": "#E92F72"}
}
```

Defaults may also appear inside a slide and override top-level defaults.
Unknown `style_ref` values are errors.

## Clean Plate

```json
{
  "method": "source_inpaint",
  "reviewed": true,
  "contains_semantic_text": false,
  "contains_detached_visuals": false,
  "min_unmasked_coverage": 0.35
}
```

For dense collages, add one:

```json
{
  "reference_image": "assets/clean-plate-reference.png"
}
```

or:

```json
{
  "mask_image": "assets/baseboard-ignore-mask.png"
}
```

`reference_image` must be the reviewed textless clean plate. It is compared over
the full canvas. In `mask_image`, white pixels are ignored and black pixels are
compared. Do not declare both unless a custom workflow explicitly needs both;
the standard runner prioritizes `reference_image`.

## Inventory

```json
{
  "id": "s-title",
  "kind": "text",
  "layer": "native_text",
  "description": "Main title",
  "bbox": [52, 58, 690, 90],
  "required": true
}
```

Allowed layers:

- `baseboard`
- `structure`
- `visual_asset`
- `native_text`
- `decoration`

Text inventory must use `kind: "text"` and `layer: "native_text"`. Use tight
bounding boxes. Do not group distant decorations into one full-slide box.

## Critical Regions

Declare at least title, main content or hero, and footer/card regions:

```json
{
  "id": "hero-zone",
  "bbox": [620, 0, 660, 570],
  "min_similarity": 0.78,
  "description": "Main hero and boundary"
}
```

## Common Element Fields

Every element requires:

- `id`
- `type`
- `bbox`
- `layer`, directly or through defaults
- `z`
- `source_ids`
- `editability`, directly or through defaults

Supported types:

- `native_text`
- `native_shape`
- `native_line`
- `native_path`
- `native_table`
- `native_chart`
- `local_picture`
- `background_texture`

The compiler orders layers as baseboard, structure, visual asset, native text,
and decoration; then uses `z` within each layer.

## Baseboard Root

Every slide must contain exactly one element with:

```json
{
  "id": "clean-plate",
  "type": "background_texture",
  "role": "baseboard_root",
  "layer": "baseboard",
  "bbox": [0, 0, 1672, 941],
  "z": 0,
  "source_ids": ["s-bg"],
  "editability": "background",
  "path": "assets/clean-plate.png",
  "fit": "cover",
  "contains_readable_text": false,
  "contains_detached_visuals": false,
  "complex_reason": "Reviewed textless clean plate"
}
```

## Pictures

Every local picture requires a bounded box, local path, source id,
`contains_readable_text: false`, and `complex_reason`. A local picture may not
cover 80% or more of the slide. Only the reviewed baseboard may be full-slide.
