# Font Policy

## Goals

- preserve Unicode text without mojibake;
- keep Chinese, English, and mixed runs editable;
- prevent font substitution from changing wrapping;
- render without tofu or repair warnings.

## Required behavior

1. Normalize text to Unicode NFC.
2. Store JSON as UTF-8 without ASCII escaping.
3. Reject `�`, common UTF-8/legacy-codepage mojibake, and unreviewed OCR.
4. Set explicit Latin, East Asian, and complex-script typefaces in DrawingML.
5. Use explicit font size, wrap, alignment, margins, and line breaks.
6. Avoid automatic fit unless the source clearly requires it.
7. Re-render after font patching.

## Default families

- Cross-platform Chinese: `Noto Sans CJK SC`.
- Windows Chinese fallback: `Microsoft YaHei`.
- English: `Arial`.
- Serif Chinese when requested and installed: `Noto Serif CJK SC`.

Do not bundle proprietary fonts. Run font preflight and record the resolved file. A fontconfig substitution to an unrelated family is not a pass.
If the selected open font is installed in a task-local directory, run preflight,
build, and QA with the same `FONTCONFIG_FILE`; do not validate with one font
configuration and render with another.

## Decorative source fonts

When the exact source font is unavailable:

- preserve the semantic text as native;
- select the closest installed family by category and weight;
- match size, color, native outline, shadow, spacing, and rotation;
- disclose the font approximation in QA;
- never rasterize semantic text merely to hide the substitution.

## Mixed runs

Split mixed-color or mixed-weight phrases into structured runs. Keep formulas and Latin tokens in the same semantic text box when they read as one phrase.
