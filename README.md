# Image to Editable PPTX

Codex skill for reconstructing a PNG, JPG, PDF page, screenshot, or image-only
slide as an editable PowerPoint. Text and simple diagrams become native objects;
photos and complex artwork remain bounded, movable images. The agent prepares a
reviewed `scene.json`, compiles it, and checks the result.

## Install in Codex

Clone this repository as one skill directory so `SKILL.md` sits directly inside
`image-to-editable-pptx`:

```powershell
git clone https://github.com/111zhang-111/png-to-ppt.git "$env:USERPROFILE\.codex\skills\image-to-editable-pptx"
```

On macOS or Linux, clone into `~/.codex/skills/image-to-editable-pptx` instead.
If it is already installed, pull the new commit in that directory. Start a new
Codex turn, then request `$image-to-editable-pptx` with the source image.

## Runtime requirements

- Python 3 with the packages in `requirements.txt` (`pip install -r requirements.txt`).
- Node.js and the private `@oai/artifact-tool` package supplied by an available
  OpenAI presentation runtime. This package is **not** copied into the repo or
  installed from public npm. In Codex, use the workspace dependency loader to
  find its `node_modules` directory and set `CODEX_PRIMARY_RUNTIME_NODE_MODULES`
  or `RUNTIME_NODE_MODULES` to that directory. Set `RUNTIME_NODE` to the
  bundled Node executable when `node` is not on `PATH`.
- An installed font matching the chosen `scene.json` font policy. Fontconfig's
  `fc-match` improves preflight checks; without it, inspect fonts in PowerPoint.
- Tesseract is optional for ambiguous text. A PDF rasterizer is needed when the
  input is a PDF rather than an already rendered page image.

The OpenAI **Presentations** skill is separate. Its `SKILL.md` is neither copied
nor invoked by this repository, and installing that instruction file alone does
not supply `@oai/artifact-tool`. This repository has its own reconstruction
instructions but still needs the runtime package to compile a PPTX. Run
preflight before conversion; `missing_tool:artifact_tool` means the compiler
cannot run in the current environment. The workflow must stop instead of
claiming a successful conversion.

## Workflow

The Codex agent reads `SKILL.md`, reviews the source, prepares `scene.json` as
described in `references/scene-schema.md`, then runs:

```text
python scripts/preflight.py INPUT.png --json-out RUN_DIR/preflight.json
python scripts/pipeline.py --scene RUN_DIR/scene.json --output RUN_DIR/reconstruction.pptx --run-dir RUN_DIR/pipeline --mode economy
```

The pipeline creates one native line per straight arrow, attaches its arrowhead
to that line, and sets semantic lines to 1 pt by default. `line.width_pt` is
available only for an explicit user-requested override. The structural audit
checks these properties on the final PPTX.

This is an agent workflow, not a one-command image recognizer. Fidelity depends
on the reviewed scene, source resolution, fonts, and visual repair. Different
machines or models may need different manual corrections.
