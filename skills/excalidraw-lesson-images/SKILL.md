---
name: excalidraw-lesson-images
description: Generate Excalidraw-style lesson illustrations from Chinese lesson image specs such as 配图.md, especially for kid_coding lessons. Use when asked to create course diagrams, concept illustrations, running-code screenshots, summary cards, or editable .excalidraw/SVG/PNG assets that follow the established hand-drawn Excalidraw style.
---

# Excalidraw Lesson Images

## Purpose

Create article-ready lesson images from a lesson's `配图.md` or similar image-production spec. The expected output is a consistent hand-drawn whiteboard style with editable `.excalidraw` source files where appropriate, plus SVG and PNG exports for direct use in articles.

This skill is optimized for the `kid_coding` workflow but can be used for any course folder with a Chinese image spec.

## When To Use

Use this skill when the user asks to:

- generate Excalidraw-style images for a lesson
- generate images from a `配图.md`
- create concept diagrams, flowcharts, comparison diagrams, warning diagrams, code-running screenshots, summary cards, cover/preview placeholders
- preserve editable `.excalidraw` source files and export `.png`

If the request only asks for a photorealistic or AI raster illustration, use the `imagegen` skill instead. If the spec mixes AI illustrations and Excalidraw diagrams, generate deterministic Excalidraw-style SVG/PNG placeholders unless the user explicitly requests AI raster generation.

## Workflow

1. Read the lesson's `配图.md` completely.
2. Identify each image type:
   - **Excalidraw concept diagram**: create `.excalidraw`, `.svg`, and `.png`.
   - **Code-running screenshot**: create a consistent editor-like SVG and PNG showing code plus output.
   - **Summary card**: create a vertical SVG and PNG matching the series style.
   - **AI cover/preview prompt**: either use the `imagegen` skill if the user wants AI art, or create a deterministic pixel-style SVG/PNG placeholder that avoids copyrighted game assets.
3. Check the target lesson folder and existing `images/` directory before writing.
4. Write a small project-local generator script when the lesson has several images. Prefer one script per lesson, named like `scripts/generate_lessonNN_images.js`.
5. Generate SVG and `.excalidraw` files into `<lesson>/images/`.
   - Add the exact credit `公众号：icey66wang` at the bottom-right of every generated image: cover, concept diagram, code screenshot, summary card, and preview.
   - For AI or pixel-art scenes, add the credit deterministically after image generation; do not ask an image model to render the text.
   - For concept diagrams, include the credit as an editable text element in the `.excalidraw` source as well as in the SVG.
6. Export PNG using local headless Chrome when available:

   ```bash
   google-chrome --headless --disable-gpu --no-sandbox \
     --window-size=1200,675 \
     --screenshot=<out>.png \
     file://<in>.svg
   ```

   Use `1200x675` for normal 16:9 article images. Use `900x1200` for vertical summary cards unless the spec says otherwise. Since concept-diagram/code-shot/summary SVGs are authored with a dark-mode invert filter baked in (see Style Rules), the PNG exported straight from the SVG is already dark-mode by default — no extra flag needed. Pixel-art SVGs (cover/preview) are authored without the filter and export in their normal colors.
7. Validate:
   - parse every `.excalidraw` file as JSON and report element counts
   - confirm every concept-diagram figure that has an SVG also has a matching `.excalidraw` (no silently-skipped exports)
   - check PNG dimensions with `file`
   - run a quick nonblank pixel-stat check with PIL
   - verify important lesson logic in code screenshots matches the article, especially changed numeric examples
   - open the pixel-art PNGs (cover/preview) and sanity-check colors look natural, not inverted/washed out
   - confirm every SVG and `.excalidraw` source contains the exact credit `公众号：icey66wang`, and visually confirm it is present in direct-raster outputs
8. Final response: list output directory, generated filenames, dimensions, validation, and the generator script path.

## Style Rules

- Concept diagrams / code screenshots / summary cards default to **dark mode export**, matching Excalidraw's own "export with dark theme": wrap the drawn content in a group and apply `filter: invert(93%) hue-rotate(180deg)` in the SVG `<style>` (draw everything with normal light-mode colors first, then let the filter invert it — do not hand-pick dark-mode colors element by element). Save `.excalidraw` files with `appState.theme: "dark"` to match.
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

## Excalidraw Source Requirements

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

## Implementation Pattern

For repeatable lesson generation, create helpers in the generator script:

- `svgWrap(body, width, height)` for SVG boilerplate, fonts, markers, and hand-drawn filter
- `text`, `multiline`, `rect`, `line`, `arrow`, `poly`, `ellipse` for SVG elements
- `exText`, `exRect`, `exDiamond`, `exArrow`, `writeEx` for `.excalidraw` JSON
- `codeShot(name, title, codeLines, outputLines)` for running-code screenshots
- `summaryCard()` for vertical recap cards

Do not invent a universal framework unless multiple lessons need refactoring. A focused lesson-specific script is usually faster and easier to audit.

## Validation Commands

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

## Output Naming

Prefer descriptive names with figure numbers:

- `cover.png`, `cover.svg`
- `fig02_for_vs_while.excalidraw`, `.svg`, `.png`
- `fig03_while_three_parts.excalidraw`, `.svg`, `.png`
- `fig04_run_zombie_counter.svg`, `.png`
- `summary.svg`, `summary.png`
- `preview_next.svg`, `preview_next.png`

Do not overwrite unrelated existing assets. If a filename already exists and the user did not ask to replace it, create a versioned sibling or ask before overwriting.
