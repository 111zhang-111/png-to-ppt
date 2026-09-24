# Layer Decomposition

Use this order before creating any PowerPoint object.

## 1. Classify source items

| Layer | Includes | Excludes |
|---|---|---|
| `baseboard` | paper texture, large photo composition, color fields, footer waves, permanent masks, ambient shadows | readable text, detachable photos, icons, stickers |
| `structure` | cards, frames, panels, tickets, rules, dividers, simple masks and paths | text printed on them |
| `visual_asset` | photos, illustrations, characters, watercolor, textured icons | readable labels and captions |
| `native_text` | every readable word, number, formula, caption, stamp label, page marker | lettering used only as non-readable texture |
| `decoration` | small stars, tape, pins, flourishes, front borders, non-semantic marks | meaningful icons or labels |

Classify by function, not by size. A tiny page number is `native_text`. A large scenic photograph may be part of the `baseboard` when it is inseparable from the overall composition, or a `visual_asset` when it is a detachable framed photo.

## 2. Create an occlusion map

Record a bounding box for every non-baseboard item. Expand masks only enough to include antialiasing, outlines, shadows, and glow. Mark overlaps and which object visually owns each edge.

The source does not reveal the background underneath removed items. Reconstruct only those hidden pixels. Outside the masks, preserve the source pixels and geometry.

## 3. Build the clean plate

Choose one method:

- `native`: reproduce a simple flat or geometric baseboard with native shapes and paths;
- `source_inpaint`: remove masked text and detached objects while preserving unmasked pixels;
- `source_composite`: combine reviewed source regions and local restoration when one inpainting pass would alter the composition.

Do not ask image generation to create a stylistic replacement for the whole slide. If generative editing is needed, constrain it to the masks, compare unchanged regions, and reject any drift in major curves, photo boundaries, colors, or landmarks.

The baseboard root must cover the full slide, sit in the `baseboard` layer, and declare:

- `role: "baseboard_root"`;
- `contains_readable_text: false`;
- `contains_detached_visuals: false`;
- the reviewed clean-plate method.

## 4. Compose the slide

Compile by layer, then by `z` within each layer:

1. baseboard;
2. structure;
3. visual assets;
4. native text;
5. front decoration.

Use `decoration` for a border or flourish that must sit above a photo or text. Do not break layer order with an extreme `z`.

## 5. Stage gates

Inspect three views:

- baseboard only;
- semantic composition without front decoration when useful;
- final slide.

Reject the baseboard when:

- source text remains visible;
- a detached photo or icon is baked in and also added later;
- a white rectangle, polygon, or cloned patch creates a new edge;
- a major curve, photo boundary, footer wave, or paper texture changes outside masks.

Reject the final slide when any critical region fails even if the whole-slide score passes.
