# Element Routing

Assign a layer before choosing an output type. Read `layer-decomposition.md`, then route by semantic function first and visual complexity second.

In `economy`, preserve useful editability rather than maximizing object count:

- keep readable text, key numbers, major cards, simple lines, and recoverable
  tables or charts native;
- group inseparable tape, torn edges, shadows, brush marks, scribbles, and other
  non-semantic decoration into a small number of tightly bounded pictures;
- do not spend a model pass tracing decorative freehand paths that the user is
  unlikely to edit;
- disclose prominent grouped raster regions in the delivery note.

| Source element | Required output |
|---|---|
| Readable text, number, formula, page marker | `native_text` |
| Card, panel, label background, bubble, badge | `native_shape` plus separate native text |
| Divider, axis, arrow, timeline, simple connector | `native_line` |
| Simple curve, arc, wave, hand-drawn semantic stroke | `native_path` |
| Real row/column grid | `native_table` |
| Data chart with recoverable data | `native_chart` |
| Chart without recoverable data | native axes, paths, markers, and labels |
| Photo, character, watercolor, textured illustration | `local_picture` |
| Paper grain or non-semantic wash | native fill or `background_texture` |

`background_texture` is permitted as a full-slide object only when it is the reviewed textless clean plate. A normal `local_picture` remains bounded to one visual region.

For a straight arrow, `native_line` describes the intended scene element, but
the delivered PPTX must contain one native line or connector with its arrowhead
as a line-end property. A separate triangle is not an acceptable arrowhead.
Use a 1 pt stroke for reconstructed lines and connectors, including
`native_path` elements used only as strokes, unless the user explicitly
specifies another width.

## Native-first rules

- Treat formulas as native text runs and native paths, not screenshots.
- Treat parabola, timeline, card grid, checklist, process arrows, speech bubbles, and map pins as semantic.
- Keep simple icons native when a preset shape or short custom path preserves them.
- Use a picture only when native redraw would visibly destroy source-specific artwork.

## Crop-first rules

- Crop from the source before regenerating.
- Keep a crop bounded to one semantic visual region.
- Exclude readable text. If unavoidable, clean the text from the local crop before overlaying native text.
- Exclude neighboring detachable assets. Do not crop one large mixed region and cover unwanted content with repair rectangles.
- Do not reuse one large crop as evidence for several unrelated regions.
- Do not stretch a crop.

## Decorative text

Decorative typography is still semantic text. Keep the native text object. Prefer native text `outline_color` and `outline_width` for sticker lettering and outlined display type. Do not use duplicate offset text boxes to fake an outline.

When the remaining source-specific lettering texture cannot be reproduced natively, a decorative texture picture may sit behind native text only when:

- the native text remains clearly visible and editable;
- the picture contains no readable duplicate text;
- the output report declares the typography approximation.

## Completeness pass

After the first inventory, scan in this order:

1. top edge and page markers;
2. left and right margins;
3. main title and subtitle;
4. each card or visual region;
5. icons, arrows, lines, bullets, and punctuation;
6. bottom edge, footer, decorations, and navigation;
7. overlaps and occluded objects.
