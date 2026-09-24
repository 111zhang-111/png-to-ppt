# QA Contract

Use scripts for full checks and return only compact evidence to the model.

## Economy Mode

Run:

- scene lint;
- PPTX structural audit;
- final render;
- overflow detection;
- one global comparison without automatic critical-region comparisons.

Skip baseboard-stage rendering and failed-region crops. Read only
`qa-summary.json`. Perform at most one complete repair pass.

## Standard Mode

Run:

- scene lint;
- PPTX structural audit;
- baseboard-stage render;
- final render;
- overflow detection;
- global comparison;
- declared critical-region comparisons.

Print `qa-summary.json`. Read `qa-report.json` only for a named failed check.
Inspect only failed-region crops after the first full-slide review.

## Strict Mode

Use stronger similarity defaults, more critical regions, and failed-region
crops. Use local OCR only for ambiguous small text or dense numbers. Do not load
raw OCR output into context; retain only uncertain regions.

## Structural Gates

- Every required inventory id has output evidence.
- Text inventory maps only to native text.
- Every reviewed `expected_text` string appears in native PPT text.
- No replacement characters, mojibake, or zero-byte media exist.
- Exactly one reviewed full-slide `baseboard_root` exists.
- No other full-slide picture exists.
- Every scene element has a named PPT object.
- The PPTX opens without repair.
- Objects remain inside the slide.
- Each straight arrow is one native line or connector with an attached line-end
  arrowhead; no separate arrowhead triangle remains.
- Reconstructed lines and connectors, including `native_path` elements used
  only as strokes, have a 1 pt width unless the user explicitly requested
  another width. Confirm these properties in the final PPTX after any grouping
  or resizing.

## Visual Gates

- Source and render have the same aspect ratio.
- Titles and labels do not wrap unexpectedly.
- Text does not clip or duplicate text still visible in pictures.
- Circles, icons, badges, and photos are not stretched.
- Z-order and crops match the source.
- Every critical region passes its threshold.
- The baseboard comparison passes by one route:
  - source outside tight bounding-box masks;
  - source outside a precise white-ignore mask;
  - full-canvas reviewed clean-plate reference.

Do not reduce thresholds merely to make a sample pass.

## Compact Summary

The compact summary must include:

- overall status;
- failed check names;
- slide count;
- native text, shape, chart, table, and picture counts;
- prohibited full-slide picture count;
- text coverage;
- global similarity;
- failed critical regions;
- baseboard coverage, similarity, and reference mode.

## Iteration Limit

- `economy`: at most one complete repair pass.
- `standard`: at most two complete repair passes.
- `strict`: at most three complete repair passes.

If failures remain, report the exact regions and limitations. Do not enter an
unbounded build-render loop.

## Required Files

Keep:

- `editability-report.json`
- `qa-report.json`
- `qa-summary.json`
- final rendered slide images
- failed-region crops when requested
