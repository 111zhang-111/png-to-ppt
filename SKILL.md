---
name: image-to-editable-pptx
description: Reconstruct PNG, JPG, screenshot, rendered slide, PDF page, or image-only PPTX inputs as high-fidelity editable PowerPoint decks while controlling context and token use. Use when readable text, charts, tables, cards, lines, arrows, badges, and simple diagrams must become native editable PPT objects; keep only photos, textures, characters, and complex artwork as bounded movable pictures.
---

# Image to Editable PPTX

Reconstruct source images through a compact scene contract, deterministic
Artifact Tool compilation, and script-first QA. Default to economy mode and
preserve visual fidelity without feeding raw OCR, full inspection logs, or
complete QA traces back into context.

## Required Companion

Read and follow the built-in `Presentations` skill. Use
`@oai/artifact-tool`; never use `python-pptx`.

Read these references:

- Read [element-routing.md](references/element-routing.md) when deciding which
  elements remain pictures or become native objects.
- Read [qa-contract.md](references/qa-contract.md) before running `standard` or
  `strict` QA, or when an `economy` structural check fails.
- Read [layer-decomposition.md](references/layer-decomposition.md) when building
  the inventory or clean plate.
- Read [font-policy.md](references/font-policy.md) for Chinese, Japanese, Korean,
  mixed-language, or decorative-font slides.
- Read [scene-schema.md](references/scene-schema.md) only when authoring or
  changing `scene.json`.

## Token Budget Rules

- Inspect one downsampled whole-slide preview first. Open the full-resolution
  source only for uncertain or failed crops.
- Do not paste raw OCR output, full OOXML inspection, or full QA reports into
  context when a compact summary is sufficient.
- Keep OCR off by default. When OCR is needed, run it locally and expose only
  normalized text boxes plus low-confidence regions to the model.
- Run deterministic scripts as black boxes. Read `qa-summary.json`, not
  `qa-report.json`, unless diagnosing a failed check.
- When a region fails, inspect its source/render crops rather than the whole
  slide.
- Reuse cached preview, OCR, crop, and scene-draft artifacts for the same source
  image when available.
- Limit automatic reconstruction repair to one complete pass in `economy`, two
  in `standard`, and three in `strict`.

## Conversational Mode Switching

Support English and Chinese mode requests without requiring command-line
syntax:

- `economy`: “经济档”, “省 token 模式”, “快速模式”, “economy mode”.
- `standard`: “标准档”, “平衡模式”, “standard mode”.
- `strict`: “严格档”, “最高质量模式”, “strict mode”.

Resolve the active mode in this order:

1. An explicit mode in the current request.
2. A mode the user set for subsequent tasks in the current conversation.
3. `economy`.

Treat “这次/本次用严格档” as task-scoped. Treat “接下来/以后默认使用标准档”
as the conversation default until the user changes it. A new conversation
starts in `economy`; do not claim cross-conversation persistence.

When the user asks to switch modes, acknowledge the selected mode briefly and
apply it immediately. Do not ask for confirmation. State the active mode before
starting a reconstruction when it is not already obvious.

## Output Contract

- Rebuild every reviewed word, number, formula, caption, and label as native
  PowerPoint text.
- Rebuild cards, panels, rules, arrows, charts, tables, and simple icons as
  native objects when practical.
- Keep photos, characters, paintings, textures, and dense illustrations as
  bounded local pictures.
- Use one reviewed textless clean plate as the only permitted full-slide image.
- Never put editable text over the same readable text inside a picture.
- Never use a text-bearing full-slide screenshot as a shortcut.
- Preserve source composition. Do not redesign the slide into a new template.

## Lines and Arrows

- Set every reconstructed line and connector, including arrowed lines and
  `native_path` elements used only as strokes, to a fixed 1 pt width unless
  the current user explicitly requests another width. Do not infer stroke
  width from source-image pixels or slide scaling.
- A straight line with an arrowhead must be **one native PowerPoint line or
  connector object with an end-arrow setting**. Never draw the shaft and
  arrowhead as separate objects, even if they are grouped; grouping does not
  make their endpoints continuous.
- Keep the arrowhead attached to the actual line endpoint. Check the final
  PowerPoint render for gaps, breaks, or an arrowhead pointing away from the
  connected line. When segments form a route, make their endpoints meet exactly.
- Treat compiler output as a draft when it creates a separate triangle for a
  `native_line` arrow. Replace that pair in PowerPoint or in the PPTX package
  with one line carrying the arrowhead before delivery. In DrawingML, a 1 pt
  line has `<a:ln w="12700">`; its arrow end belongs inside that same line's
  properties (`a:headEnd` or `a:tailEnd`, according to direction).
- Inspect the delivered PPTX, not just the scene JSON: no detached arrowhead
  shape may remain for a straight arrow line, and each reconstructed line or
  connector must retain its 1 pt stroke after grouping or resizing.

## Modes

Use `economy` unless the user or current conversation state selects another
mode.

### Economy

- Inspect one downsampled whole-slide preview.
- Convert readable text and major semantic structures to native objects.
- Group inseparable decorative marks into a small number of bounded pictures.
- Keep OCR off unless a specific region is unreadable; never load full OCR logs.
- Run scene lint, structural audit, final render, overflow detection, and one
  global comparison.
- Skip baseboard-stage rendering and automatic critical-region comparisons.
- Do not create failed-region crops automatically.
- Perform at most one complete repair pass.

### Standard

- Visually transcribe clear text.
- Keep OCR off unless a small region is ambiguous.
- Run structural, overflow, global, critical-region, and clean-plate QA.
- Print only the compact QA summary.
- Perform at most two full repair passes.

### Strict

- Use local OCR selectively for small or ambiguous regions.
- Use stronger similarity thresholds.
- Check more critical regions and crop every failed region.
- Perform at most three repair passes.

Higher modes increase compute and inspection, not permission to load
unfiltered logs into context.

## Workflow

### 1. Preflight

```bash
python scripts/preflight.py INPUT... \
  --json-out RUN_DIR/preflight.json \
  --fontconfig-file FONTCONFIG_FILE
```

Stop when the input, Artifact Tool, renderer, or required fonts are unavailable.
A missing OCR language is not a blocker when the text is visually reviewable.

### 2. Inventory Once

Inspect the page at full resolution and inventory:

- baseboard;
- structural surfaces;
- complex visual assets;
- native text;
- front decorations.

Create one record for each visible semantic item. Group only genuinely
inseparable decorative marks. Use tight bounds; a full-slide decoration group
destroys clean-plate mask coverage.

### 3. Build the Clean Plate

Use a native fill, source-preserving inpainting, or source composite. Keep it
textless and free of detachable pictures.

For dense collages, prefer one of:

- `clean_plate.reference_image`: compare the rendered baseboard against a
  reviewed clean plate over the full canvas;
- `clean_plate.mask_image`: use a precise white-ignore mask instead of the union
  of coarse rectangles.

Do not lower coverage thresholds to hide imprecise masks.

### 4. Author a Compact Scene

Use scene version `1.2` when `defaults`, `styles`, or `style_ref` reduce repeated
fields. Version `1.1` remains supported. The build step expands both formats to
the same deterministic compiler input.

Keep visible text in `expected_text`. Normalize text to Unicode NFC. Store JSON
as UTF-8.

### 5. Prepare Bounded Visual Assets

Prefer, in order:

1. exact source crop without semantic text;
2. source-preserving local cleanup;
3. regenerated textless asset when cleanup is not reliable.

Declare `contains_readable_text: false` and a concise `complex_reason`.
Generated assets must contain no words, letters, numbers, logos, labels,
signatures, seals, or watermarks.

### 6. Build and Audit

Preferred compact command:

```bash
python scripts/pipeline.py \
  --scene RUN_DIR/scene.json \
  --output RUN_DIR/reconstruction.pptx \
  --run-dir RUN_DIR/pipeline \
  --mode economy \
  --fontconfig-file FONTCONFIG_FILE
```

Pass the resolved conversational mode to `--mode`. Use `--crop-failures` in
`standard` or `strict` when targeted crop review is useful.

The pipeline writes:

- `reconstruction.pptx`;
- `qa/editability-report.json`;
- `qa/qa-report.json`;
- `qa/qa-summary.json`;
- failed-region crops when requested.

Read `qa-summary.json` first. Open the full report only for a named failed check.

### 7. Repair Only Failed Evidence

Fix:

- missing or duplicated text;
- clipping, wrapping, tofu, or mojibake;
- wrong z-order or crop;
- stretched circles or pictures;
- source text remaining inside pictures;
- failed critical regions;
- imprecise clean-plate masks.

Rebuild after each repair. Stop after the active mode's pass limit and report
unresolved limitations rather than entering an unbounded loop.

### 8. Deliver

Deliver the editable `.pptx`, `editability-report.json`, and `qa-report.json`.
State which bounded complex visuals remain pictures. Do not describe picture
pixels as editable artwork.

## Hard Failures

Fail delivery when:

- reviewed text is missing from native PPT text;
- a required inventory item is unmapped;
- the clean plate contains semantic text or detachable visuals;
- a text-bearing picture covers most of the slide;
- an undeclared full-slide picture exists;
- a semantic chart or table is flattened without a stated limitation;
- the PPTX contains zero-byte media or opens with a repair warning;
- text clips, a one-line title wraps, or a circle becomes an oval;
- any declared critical region fails;
- the structural audit disagrees with the scene contract.
- a straight arrow is made from a separate shaft and arrowhead, its visible
  line is broken, or a reconstructed line or connector is not 1 pt without an
  explicit user override.
