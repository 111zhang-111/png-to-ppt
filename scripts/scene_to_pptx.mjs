import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const [sceneArg, outputArg, stageArg = "final"] = process.argv.slice(2);
if (!sceneArg || !outputArg) {
  throw new Error("Usage: node scene_to_pptx.mjs SCENE.json OUTPUT.pptx [baseboard|semantic|final]");
}
const allowedStages = new Set(["baseboard", "semantic", "final"]);
if (!allowedStages.has(stageArg)) {
  throw new Error(`Unsupported stage: ${stageArg}`);
}

const scenePath = path.resolve(sceneArg);
const outputPath = path.resolve(outputArg);
const sceneDir = path.dirname(scenePath);
const scene = JSON.parse(await fs.readFile(scenePath, "utf8"));
const slideSize = scene.slide_size ?? { width: 1280, height: 720 };
const presentation = Presentation.create({ slideSize });
const layerOrder = {
  baseboard: 0,
  structure: 1,
  visual_asset: 2,
  native_text: 3,
  decoration: 4,
};

function includedInStage(element) {
  if (stageArg === "baseboard") return element.layer === "baseboard";
  if (stageArg === "semantic") return element.layer !== "decoration";
  return true;
}

function compareElements(a, b) {
  const layerDelta = (layerOrder[a.layer] ?? 999) - (layerOrder[b.layer] ?? 999);
  if (layerDelta !== 0) return layerDelta;
  return a.z - b.z;
}

function positionOf(element) {
  const [left, top, width, height] = element.bbox;
  return { left, top, width, height, ...(element.rotation ? { rotation: element.rotation } : {}) };
}

function lineConfig(value = {}) {
  const fill = value.color ?? value.fill ?? "none";
  return {
    style: value.dash ?? value.style ?? "solid",
    fill,
    width: value.width ?? 0,
  };
}

function textStyle(scene, element) {
  const style = element.style ?? {};
  const policy = scene.font_policy ?? {};
  const outline = style.outline_color
    ? {
        style: style.outline_dash ?? "solid",
        fill: style.outline_color,
        width: style.outline_width ?? 1,
      }
    : undefined;
  return {
    fontSize: style.font_size ?? 20,
    typeface:
      style.font_face ??
      style.east_asian_font ??
      policy.east_asian ??
      policy.latin ??
      "Arial",
    bold: style.bold ?? false,
    italic: style.italic ?? false,
    color: style.color ?? "#111111",
    ...(outline ? { outline } : {}),
    alignment: style.align ?? "left",
    verticalAlignment: style.valign ?? "top",
    wrap: style.wrap === false ? "none" : "square",
    autoFit: style.auto_fit ?? "none",
    lineSpacing: style.line_spacing ?? 1,
    insets: {
      top: style.margin_top ?? style.margin ?? 0,
      right: style.margin_right ?? style.margin ?? 0,
      bottom: style.margin_bottom ?? style.margin ?? 0,
      left: style.margin_left ?? style.margin ?? 0,
    },
  };
}

async function imageBytes(imagePath) {
  const bytes = await fs.readFile(imagePath);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

function contentType(imagePath) {
  const ext = path.extname(imagePath).toLowerCase();
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".webp") return "image/webp";
  if (ext === ".svg") return "image/svg+xml";
  return "image/png";
}

function addArrowHead(slide, element) {
  if (!element.head || element.head === "none") return;
  const [x, y, w, h] = element.bbox;
  const endX = x + w;
  const endY = y + h;
  const angle = (Math.atan2(h, w) * 180) / Math.PI + 90;
  const size = element.head_size ?? Math.max(8, (element.line?.width ?? 2) * 4);
  slide.shapes.add({
    geometry: "triangle",
    name: `${element.id}-head`,
    position: {
      left: endX - size / 2,
      top: endY - size / 2,
      width: size,
      height: size,
      rotation: angle,
    },
    fill: element.line?.color ?? "#111111",
    line: { style: "solid", fill: "none", width: 0 },
  });
}

async function addElement(slide, element) {
  const pos = positionOf(element);
  if (element.type === "native_text") {
    const shape = slide.shapes.add({
      geometry: "textbox",
      name: element.id,
      position: pos,
      fill: "none",
      line: { style: "solid", fill: "none", width: 0 },
      ...(element.shadow ? { shadow: element.shadow } : {}),
    });
    if (Array.isArray(element.runs)) {
      shape.text.set([
        element.runs.map((run) => ({
          run: String(run.text ?? ""),
          textStyle: {
            bold: run.bold,
            italic: run.italic,
            color: run.color,
            fontSize: run.font_size ? `${run.font_size}px` : undefined,
            typeface: run.font_face,
            ...(run.outline_color
              ? {
                  outline: {
                    style: run.outline_dash ?? "solid",
                    fill: run.outline_color,
                    width: run.outline_width ?? 1,
                  },
                }
              : {}),
          },
        })),
      ]);
    } else {
      shape.text = String(element.text ?? "");
    }
    shape.text.style = textStyle(scene, element);
    return;
  }

  if (element.type === "native_shape") {
    slide.shapes.add({
      geometry: element.geometry ?? "rect",
      name: element.id,
      position: pos,
      fill: element.fill ?? "none",
      line: lineConfig(element.line),
      ...(element.radius !== undefined ? { borderRadius: element.radius } : {}),
      ...(element.shadow ? { shadow: element.shadow } : {}),
    });
    return;
  }

  if (element.type === "native_line") {
    const [x, y, w, h] = element.bbox;
    const left = Math.min(x, x + w);
    const top = Math.min(y, y + h);
    const width = Math.max(1, Math.abs(w));
    const height = Math.max(1, Math.abs(h));
    const commands =
      w * h >= 0
        ? [{ moveTo: { x: 0, y: 0 } }, { lineTo: { x: width, y: height } }]
        : [{ moveTo: { x: 0, y: height } }, { lineTo: { x: width, y: 0 } }];
    slide.shapes.add({
      geometry: "custom",
      name: element.id,
      position: { left, top, width, height },
      fill: "none",
      line: lineConfig(element.line),
      customPaths: [{ width, height, commands }],
    });
    addArrowHead(slide, element);
    return;
  }

  if (element.type === "native_path") {
    const [pathWidth, pathHeight] = element.path_size ?? [pos.width, pos.height];
    const commands = (element.points ?? []).map((point, index) =>
      index === 0
        ? { moveTo: { x: point[0], y: point[1] } }
        : { lineTo: { x: point[0], y: point[1] } },
    );
    if (element.closed) commands.push({ close: {} });
    slide.shapes.add({
      geometry: "custom",
      name: element.id,
      position: pos,
      fill: element.fill ?? "none",
      line: lineConfig(element.line),
      customPaths: [{ width: pathWidth, height: pathHeight, commands }],
    });
    return;
  }

  if (element.type === "local_picture" || element.type === "background_texture") {
    const imagePath = path.resolve(sceneDir, element.path);
    const options = {
      blob: await imageBytes(imagePath),
      contentType: contentType(imagePath),
      alt: `${element.id}: ${element.complex_reason ?? "complex visual"}`,
      fit: element.fit ?? "cover",
      position: pos,
      geometry: element.geometry ?? "rect",
      ...(element.radius !== undefined ? { borderRadius: element.radius } : {}),
    };
    if (element.source_crop) {
      const [left, top, right, bottom] = element.source_crop;
      options.crop = { left, top, right: 1 - right, bottom: 1 - bottom };
    }
    slide.images.add(options);
    return;
  }

  if (element.type === "native_table") {
    const values = element.values ?? [];
    const rows = element.rows ?? values.length;
    const columns = element.columns ?? Math.max(0, ...values.map((row) => row.length));
    const table = slide.tables.add({
      rows,
      columns,
      left: pos.left,
      top: pos.top,
      width: pos.width,
      height: pos.height,
      values,
      ...(element.column_widths ? { columnWidths: element.column_widths } : {}),
    });
    table.styleOptions = element.style_options ?? { headerRow: true, bandedRows: false };
    table.borders.assign(lineConfig(element.border ?? { color: "#999999", width: 1 }));
    return;
  }

  if (element.type === "native_chart") {
    slide.charts.add(element.chart_type ?? "bar", {
      position: pos,
      title: element.title,
      categories: element.categories ?? [],
      series: element.series ?? [],
      hasLegend: element.has_legend ?? false,
      legend: element.legend,
      xAxis: element.x_axis,
      yAxis: element.y_axis,
      dataLabels: element.data_labels,
      chartFill: element.chart_fill ?? "none",
      plotAreaFill: element.plot_fill ?? "none",
    });
  }
}

for (const sourceSlide of scene.slides) {
  const slide = presentation.slides.add();
  for (const element of [...sourceSlide.elements].filter(includedInStage).sort(compareElements)) {
    await addElement(slide, element);
  }
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const inspect = await presentation.inspect({
  kind: "slide,textbox,shape,image,table,chart",
  maxChars: 200000,
});
await fs.writeFile(path.join(path.dirname(outputPath), "artifact-inspect.ndjson"), inspect.ndjson);
for (const [index, slide] of presentation.slides.items.entries()) {
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(
    path.join(path.dirname(outputPath), `slide-${String(index + 1).padStart(2, "0")}.layout.json`),
    await layout.text(),
  );
}
const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(outputPath);
