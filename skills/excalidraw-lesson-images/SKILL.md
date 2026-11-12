---
name: excalidraw-lesson-images
description: Generate Excalidraw-style lesson illustrations from Chinese lesson image specs such as 配图.md, especially for kid_coding lessons. Use when asked to create course diagrams, concept illustrations, running-code screenshots, summary cards, or editable .excalidraw/SVG/PNG assets that follow the established hand-drawn Excalidraw style.
---

# Excalidraw 课程配图

## 语言与系列主题

- 本技能的说明、执行过程、校验报告和最终交付说明统一使用中文；代码、命令、路径、API 名称和必要的专有名词可以保留原文。
- Kid coding 系列的概念图、代码运行图、对照图和总结卡默认使用深色背景，必须与系列旧课的深色视觉保持一致。
- 封面、预告等像素风或场景图属于例外：保留为设计好的场景配色，不使用概念图的反色滤镜。

## 目的

根据课程的 `配图.md` 或类似配图规范生成可直接用于文章的课程插图。输出应保持统一的手绘白板风格，并在适用时提供可编辑的 `.excalidraw` 源文件以及 SVG、PNG 导出文件。

This skill is optimized for the `kid_coding` workflow but can be used for any course folder with a Chinese image spec.

## 使用时机

当用户要求以下内容时使用本技能：

- generate Excalidraw-style images for a lesson
- generate images from a `配图.md`
- create concept diagrams, flowcharts, comparison diagrams, warning diagrams, code-running screenshots, summary cards, cover/preview placeholders
- preserve editable `.excalidraw` source files and export `.png`

如果用户只需要写实照片或 AI 光栅插画，使用 `imagegen` 技能；如果规范同时包含 AI 插画和 Excalidraw 概念图，概念图使用确定性的本地 SVG/PNG 生成流程，除非用户明确要求 AI 光栅图。

## 工作流程

1. 完整读取课程的 `配图.md`。
2. 识别每张图片的类型：
   - **Excalidraw concept diagram**: create `.excalidraw`, `.svg`, and `.png`.
   - **Code-running screenshot**: create a consistent editor-like SVG and PNG showing code plus output.
   - **Summary card**: create a vertical SVG and PNG matching the series style.
   - **AI cover/preview prompt**: either use the `imagegen` skill if the user wants AI art, or create a deterministic pixel-style SVG/PNG placeholder that avoids copyrighted game assets.
3. 写入前检查目标课程目录和现有 `images/` 目录，避免覆盖无关文件。
4. 课程有多张图时编写项目内的小型生成脚本，优先采用每课一个脚本的形式，例如 `scripts/generate_lessonNN_images.js`。
5. 将 SVG 和 `.excalidraw` 文件生成到 `<lesson>/images/`。
   - Add the exact credit `公众号：icey66wang` at the bottom-right of every generated image: cover, concept diagram, code screenshot, summary card, and preview.
   - For AI or pixel-art scenes, add the credit deterministically after image generation; do not ask an image model to render the text.
   - For concept diagrams, include the credit as an editable text element in the `.excalidraw` source as well as in the SVG.
6. 优先使用本地无头 Chrome 导出 PNG：

   ```bash
   google-chrome --headless --disable-gpu --no-sandbox \
     --window-size=1200,675 \
     --screenshot=<out>.png \
     file://<in>.svg
   ```

   Use `1200x675` for normal 16:9 article images. Use `900x1200` for vertical summary cards unless the spec says otherwise. Concept-diagram/code-shot/summary SVGs are authored with a dark-mode invert filter, but some rasterizers (including CairoSVG in common local setups) do not apply CSS filters. After export, inspect the actual PNG background pixel: if it is light, apply the same deterministic `invert(93%) hue-rotate(180deg)` transform during rasterization or use a direct dark-theme renderer, then validate again. Pixel-art SVGs (cover/preview) are authored without the filter and export in their normal colors.
7. 校验：
   - parse every `.excalidraw` file as JSON and report element counts
   - confirm every concept-diagram figure that has an SVG also has a matching `.excalidraw` (no silently-skipped exports)
   - check PNG dimensions with `file`
   - run a quick nonblank pixel-stat check with PIL
   - verify important lesson logic in code screenshots matches the article, especially changed numeric examples
   - open the pixel-art PNGs (cover/preview) and sanity-check colors look natural, not inverted/washed out
   - confirm every SVG and `.excalidraw` source contains the exact credit `公众号：icey66wang`, and visually confirm it is present in direct-raster outputs
8. 最终回复列出输出目录、生成文件名、尺寸、校验结果和生成脚本路径。

## 风格规则

- Concept diagrams / code screenshots / summary cards default to **dark mode export**, matching Excalidraw's own "export with dark theme": wrap the drawn content in a group and apply `filter: invert(93%) hue-rotate(180deg)` in the SVG `<style>` (draw everything with normal light-mode colors first, then let the filter invert it — do not hand-pick dark-mode colors element by element). Save `.excalidraw` files with `appState.theme: "dark"` to match.
- For Kid coding outputs, "dark mode export" applies to the final PNG as well as the SVG preview. A CSS filter in the SVG source is not sufficient evidence: verify the raster output visually and with a corner-pixel check (normally near `#121212` for landscape concept/code images). If the selected exporter ignores the filter, perform deterministic post-processing before delivery.
- Exception: pixel-art / AI-style illustrations (cover art, preview-next art, any scene-style pixel illustration) must NOT use the invert filter — inversion produces ugly, wrong-looking scenery (skies, grass, sun, skin tones all shift to broken colors). Render those with `dark: false` (plain light-mode colors) so they look as designed.
- White background for concept diagrams before the invert filter is applied (i.e. author them as if for light mode; the filter turns the white canvas dark and flips other colors accordingly).
- Hand-drawn feel: rough outlines, slightly imperfect shapes, rounded rectangles, arrows, and casual type.
- Use clear semantic color (as authored in light mode, before inversion):
  - green for correct/active/safe
  - orange/yellow for conditions and uncertainty
  - red for warnings, false paths, danger, or dead loops
  - blue for initial values, code structure, or neutral concepts
- Keep text large enough for mobile article reading.
- Avoid dense tables in images; split into cards or lanes.
- Keep code screenshots visually consistent across lessons: dark editor panel, output panel, large monospace text.
- Avoid official Minecraft screenshots, UI, logos, or copied assets. Pixel-style original homage art is acceptable.
- Image credit: every generated image must show the exact text `公众号：icey66wang` at the bottom-right. Keep it readable but secondary, inside a safe margin (about 24 px on 1200x675 images and 18 px on 900x1200 cards), with sufficient contrast against the local background. Do not use the old `icey66wang`-only credit or generator-specific placeholder credits such as `像素工坊 · 少儿编程课`.
- Put the credit in a shared image-wrapper/helper when writing a lesson generator so every output path receives it consistently. For direct raster generation, apply it as a deterministic post-processing overlay.

## Excalidraw 源文件要求

For actual concept diagrams, always save an editable `.excalidraw` file alongside SVG/PNG. Never skip this — every concept-diagram figure (`fig0N_*` diagrams built from shapes/text, not code screenshots or pixel-art covers) must ship all three of `.excalidraw` + `.svg` + `.png`. Before finishing, grep the generator script for every `write("figNN_*.svg", ...)` call and confirm each one has a matching `writeEx("figNN_*.excalidraw", ...)` call; a missing `.excalidraw` for a concept diagram is a bug to fix, not an acceptable gap.

Minimum `.excalidraw` JSON:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [],
  "appState": {
    "gridSize": null,
    "viewBackgroundColor": "#ffffff",
    "theme": "dark"
  },
  "files": {}
}
```

Use element objects with stable fields Excalidraw expects: `id`, `type`, `x`, `y`, `width`, `height`, `strokeColor`, `backgroundColor`, `roughness`, `seed`, `versionNonce`, `isDeleted`, and text fields for text elements.

SVG previews may be more polished than the `.excalidraw` source, but they must preserve the same layout and wording.

Source parity: for every concept diagram, the `.excalidraw` source must contain the same semantic text, panels, data nodes, and arrows as the SVG/PNG. A minimal placeholder source is invalid. Before finishing, compare text-node counts and key labels between the SVG and `.excalidraw`, and regenerate both from the same coordinate/data definitions when they diverge.

The bottom-right `公众号：icey66wang` credit is part of source parity. It must be an editable text element in each concept diagram's `.excalidraw` source, not only a flattened PNG/SVG overlay.

## 实现方式

For repeatable lesson generation, create helpers in the generator script:

- `svgWrap(body, width, height)` for SVG boilerplate, fonts, markers, and hand-drawn filter
- `text`, `multiline`, `rect`, `line`, `arrow`, `poly`, `ellipse` for SVG elements
- `exText`, `exRect`, `exDiamond`, `exArrow`, `writeEx` for `.excalidraw` JSON
- `codeShot(name, title, codeLines, outputLines)` for running-code screenshots
- `summaryCard()` for vertical recap cards

Do not invent a universal framework unless multiple lessons need refactoring. A focused lesson-specific script is usually faster and easier to audit.

## 校验命令

Use these patterns after generation:

```bash
node -e "for (const f of process.argv.slice(1)) { const data=JSON.parse(require('fs').readFileSync(f,'utf8')); console.log(require('path').basename(f), data.type, data.elements.length); }" <files.excalidraw>
```

```bash
file <lesson>/images/*.png
```

```bash
python3 -c "from PIL import Image, ImageStat; import sys, os
for p in sys.argv[1:]:
 im=Image.open(p).convert('RGB')
 stat=ImageStat.Stat(im)
 print(os.path.basename(p), im.size, [round(x,2) for x in stat.stddev])" <files.png>
```

If a tool cannot read a directory because of sandbox restrictions, request the required filesystem escalation instead of silently skipping validation.

## 输出命名

Prefer descriptive names with figure numbers:

- `cover.png`, `cover.svg`
- `fig02_for_vs_while.excalidraw`, `.svg`, `.png`
- `fig03_while_three_parts.excalidraw`, `.svg`, `.png`
- `fig04_run_zombie_counter.svg`, `.png`
- `summary.svg`, `summary.png`
- `preview_next.svg`, `preview_next.png`

Do not overwrite unrelated existing assets. If a filename already exists and the user did not ask to replace it, create a versioned sibling or ask before overwriting.
