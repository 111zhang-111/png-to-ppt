import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const [inputArg, outputDirArg, scaleArg] = process.argv.slice(2);
if (!inputArg || !outputDirArg) {
  throw new Error("Usage: node render_pptx.mjs INPUT.pptx OUTPUT_DIR [SCALE]");
}

const input = path.resolve(inputArg);
const outputDir = path.resolve(outputDirArg);
const scale = scaleArg ? Number.parseFloat(scaleArg) : 1.30625;
await fs.mkdir(outputDir, { recursive: true });

const presentation = await PresentationFile.importPptx(await FileBlob.load(input));
const slides = Array.isArray(presentation.slides?.items)
  ? presentation.slides.items
  : Array.from(
      { length: presentation.slides.count },
      (_, index) => presentation.slides.getItem(index),
    );

const paths = [];
for (let index = 0; index < slides.length; index += 1) {
  const output = path.join(outputDir, `slide-${index + 1}.png`);
  const preview = await presentation.export({
    slide: slides[index],
    format: "png",
    scale,
  });
  const bytes = Buffer.from(await preview.arrayBuffer());
  await fs.writeFile(output, bytes);
  paths.push(output);
}

console.log(JSON.stringify({ input, outputDir, scale, paths }, null, 2));
