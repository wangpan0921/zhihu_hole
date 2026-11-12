---
name: excalidraw-lesson-images
description: 根据中文课程配图规范生成 Excalidraw 风格的课程插图，尤其适用于 kid_coding 课程；可生成概念图、代码运行图、总结卡和可编辑的 .excalidraw/SVG/PNG 资源。
---

# Excalidraw 课程配图

## 语言与系列主题

- 本技能的说明、执行过程、校验报告和最终交付说明统一使用中文；代码、命令、路径、API 名称和必要的专有名词可以保留原文。
- Kid coding 系列的概念图、代码运行图、对照图和总结卡默认使用深色背景，必须与系列旧课的深色视觉保持一致。
- 封面、预告等像素风或场景图属于例外：保留为设计好的场景配色，不使用概念图的反色滤镜。

## 目的

根据课程的 `配图.md` 或类似配图规范生成可直接用于文章的课程插图。输出应保持统一的手绘白板风格，并在适用时提供可编辑的 `.excalidraw` 源文件以及 SVG、PNG 导出文件。

本技能针对 `kid_coding` 工作流优化，也适用于任何包含中文配图规范的课程目录。

## 使用时机

当用户要求以下内容时使用本技能：

- 为课程生成 Excalidraw 风格的图片；
- 根据 `配图.md` 生成配图；
- 创建概念图、流程图、对照图、警示图、代码运行截图、总结卡和封面/预告占位图；
- 保留可编辑的 `.excalidraw` 源文件并导出 `.png`。

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

- 概念图、代码运行图和总结卡默认使用 **dark mode export**，匹配 Excalidraw 的深色导出：把绘制内容放入一个 SVG 分组，并在 `<style>` 中使用 `filter: invert(93%) hue-rotate(180deg)`；先按浅色主题绘制，再交给滤镜反转，不要逐个元素手工挑深色；`.excalidraw` 的 `appState.theme` 设置为 `dark`。
- 对 Kid coding 产物，“dark mode export”同时适用于最终 PNG 和 SVG 预览。SVG 源码中存在 CSS 滤镜并不能证明栅格图已变深，必须视觉检查并检查角落像素（横版概念图/代码图通常接近 `#121212`）；如果导出器忽略滤镜，交付前执行确定性的后处理。
- 像素风或 AI 场景图（封面、预告和其他场景插画）是例外：禁止使用反色滤镜，否则天空、草地和主体颜色会失真；使用 `dark: false` 输出原始设计颜色。
- 概念图在应用反色滤镜前使用白色画布，即按浅色主题绘制，滤镜负责将画布变为深色并转换其他颜色。
- 保持手绘感：略不规则的描边、圆角矩形、箭头和轻松易读的字体。
- 使用清晰的语义色（按浅色源稿绘制，之后由滤镜转换）：
  - green for correct/active/safe
  - orange/yellow for conditions and uncertainty
  - red for warnings, false paths, danger, or dead loops
  - blue for initial values, code structure, or neutral concepts
- 字号要足够大，适合手机文章阅读。
- 避免在图片中堆叠密集表格，拆成卡片或流程区域。
- 代码截图在各课之间保持统一：深色编辑器面板、输出面板和大号等宽字体。
- 不使用官方 Minecraft 截图、UI、Logo 或复制的官方资源；可以使用原创的泛化像素风场景。
- 每张生成图右下角必须显示精确文本 `公众号：icey66wang`，放在安全边距内（横图约 24 px，竖版卡片约 18 px），清晰但不抢主体；不要使用旧的 `icey66wang` 单独署名或生成器占位署名。
- 编写课程生成器时，将署名放入共享的图片外壳/辅助函数，确保所有输出路径一致；直接生成光栅图时使用确定性的后处理叠加署名。

## Excalidraw 源文件要求

真正的概念图必须始终与 SVG/PNG 一起保存可编辑的 `.excalidraw` 文件。不能省略：每张由形状/文本构成的概念图（不是代码截图或像素风封面）都必须同时交付 `.excalidraw`、`.svg` 和 `.png`。完成前检查生成器中每个 `write("figNN_*.svg", ...)` 是否都有对应的 `writeEx("figNN_*.excalidraw", ...)`，缺少源文件必须修复。

`.excalidraw` JSON 的最小结构：

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

元素对象必须包含 Excalidraw 需要的稳定字段：`id`、`type`、`x`、`y`、`width`、`height`、`strokeColor`、`backgroundColor`、`roughness`、`seed`、`versionNonce`、`isDeleted`；文本元素还要包含文本字段。

SVG 预览可以比 `.excalidraw` 源文件更精致，但布局和文案必须保持一致。

源文件一致性：每张概念图的 `.excalidraw` 必须包含与 SVG/PNG 相同的语义文本、面板、数据节点和箭头；最小占位源文件无效。完成前比较 SVG 与 `.excalidraw` 的文本节点数量和关键标签，发现差异时从同一套坐标/数据定义重新生成。

右下角的 `公众号：icey66wang` 署名属于源文件一致性的一部分，必须作为每张概念图 `.excalidraw` 中的可编辑文本元素存在，不能只叠加在扁平化 PNG/SVG 上。

## 实现方式

为了可重复生成课程配图，可以在生成脚本中提供以下辅助函数：

- `svgWrap(body, width, height)` for SVG boilerplate, fonts, markers, and hand-drawn filter
- `text`, `multiline`, `rect`, `line`, `arrow`, `poly`, `ellipse` for SVG elements
- `exText`, `exRect`, `exDiamond`, `exArrow`, `writeEx` for `.excalidraw` JSON
- `codeShot(name, title, codeLines, outputLines)` for running-code screenshots
- `summaryCard()` for vertical recap cards

除非多课确实需要重构，否则不要创建通用框架；聚焦单课的脚本通常更快，也更容易审计。

## 校验命令

生成后可使用以下命令模式：

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

如果工具因沙箱限制无法读取目录，应申请所需的文件系统权限，不要默默跳过校验。

## 输出命名

优先使用带图号的描述性名称：

- `cover.png`, `cover.svg`
- `fig02_for_vs_while.excalidraw`, `.svg`, `.png`
- `fig03_while_three_parts.excalidraw`, `.svg`, `.png`
- `fig04_run_zombie_counter.svg`, `.png`
- `summary.svg`, `summary.png`
- `preview_next.svg`, `preview_next.png`

不要覆盖无关的现有资源。如果文件名已存在且用户没有要求替换，应创建带版本号的同级文件或先询问。
