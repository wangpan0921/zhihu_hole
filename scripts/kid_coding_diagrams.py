#!/usr/bin/env python3
"""少儿编程系列·手绘风概念图生成工具（方案 B）。

用自己实现的"抖动线条"（模拟 rough.js 的手绘描边算法）在 PIL 里画箱子/箭头/文字，
风格致敬 excalidraw，但不依赖 Node/浏览器/rough.js —— 纯 Python + Pillow。

每课一个可编辑的 kid_coding/lesson-NN-*/diagrams.txt（不存在会自动生成带示例的模板），
用简单的 DSL 描述"箱子 + 箭头 + 文字"，工具自动排版并画成手绘风 PNG，输出到该课 images/。

用法：
    ./venv/bin/python scripts/kid_coding_diagrams.py --lesson 1
"""
from __future__ import annotations

import argparse
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
KID = ROOT / "kid_coding"
FONT_DIR = ROOT / "assets/fonts"

INK = (32, 34, 38)          # excalidraw 默认描边接近的深色
PAPER = (255, 255, 255)
GRID = (232, 234, 238)

# 手绘图专用配色（浅底 + 深描边，比视频里的主题色更淡，贴近 excalidraw 的柔和色板）
PALETTE = {
    "green": ((176, 240, 190), (43, 138, 62)),
    "blue": ((186, 216, 250), (30, 96, 196)),
    "amber": ((255, 224, 150), (196, 130, 10)),
    "red": ((255, 196, 190), (200, 60, 45)),
    "violet": ((222, 200, 250), (110, 60, 190)),
    "teal": ((176, 232, 224), (20, 120, 110)),
    "gray": ((228, 228, 228), (90, 90, 90)),
}


def _ascii(text: str) -> bool:
    return bool(re.match(r"^[\x00-\x7f]*$", text))


_FONT_CACHE: dict[tuple, ImageFont.FreeTypeFont] = {}


def font_for(text: str, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    key = (bool(_ascii(text)), size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    if _ascii(text):
        candidates = [
            FONT_DIR / ("Kalam-Bold.ttf" if bold else "Kalam-Regular.ttf"),
            FONT_DIR / "Kalam-Regular.ttf",
        ]
    else:
        candidates = [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ]
    for c in candidates:
        if c.exists():
            f = ImageFont.truetype(str(c), size)
            _FONT_CACHE[key] = f
            return f
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


# ---------- 手绘描边基础图元（模拟 rough.js：抖动 + 轻微弧度 + 两遍叠画） ----------
def _quad_points(x0, y0, cx, cy, x1, y1, n=12):
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        pts.append((mt * mt * x0 + 2 * mt * t * cx + t * t * x1,
                     mt * mt * y0 + 2 * mt * t * cy + t * t * y1))
    return pts


def rough_line(draw, x1, y1, x2, y2, rng: random.Random, fill=INK, width=3, passes=2, jitter=2.2):
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 1:
        return
    bow = min(7.0, max(1.5, length * 0.02))
    nx, ny = -(y2 - y1) / length, (x2 - x1) / length
    for _ in range(passes):
        bo = rng.uniform(-bow, bow)
        mx = (x1 + x2) / 2 + nx * bo + rng.uniform(-jitter, jitter)
        my = (y1 + y2) / 2 + ny * bo + rng.uniform(-jitter, jitter)
        sx, sy = x1 + rng.uniform(-jitter, jitter) * 0.6, y1 + rng.uniform(-jitter, jitter) * 0.6
        ex, ey = x2 + rng.uniform(-jitter, jitter) * 0.6, y2 + rng.uniform(-jitter, jitter) * 0.6
        draw.line(_quad_points(sx, sy, mx, my, ex, ey), fill=fill, width=width, joint="curve")


def rough_rect(draw, box, rng: random.Random, fill=None, outline=INK, width=3):
    x1, y1, x2, y2 = box
    if fill:
        draw.rectangle((x1 + 2, y1 + 2, x2 - 2, y2 - 2), fill=fill)
    ov = 4
    rough_line(draw, x1 - ov, y1, x2 + ov, y1, rng, fill=outline, width=width)
    rough_line(draw, x1 - ov, y2, x2 + ov, y2, rng, fill=outline, width=width)
    rough_line(draw, x1, y1 - ov, x1, y2 + ov, rng, fill=outline, width=width)
    rough_line(draw, x2, y1 - ov, x2, y2 + ov, rng, fill=outline, width=width)


def rough_diamond(draw, box, rng: random.Random, fill=None, outline=INK, width=3):
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    pts = [(cx, y1), (x2, cy), (cx, y2), (x1, cy)]
    if fill:
        draw.polygon(pts, fill=fill)
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        rough_line(draw, a[0], a[1], b[0], b[1], rng, fill=outline, width=width)


def rough_ellipse(draw, box, rng: random.Random, fill=None, outline=INK, width=3, n=20):
    x1, y1, x2, y2 = box
    cx, cy, rx, ry = (x1 + x2) / 2, (y1 + y2) / 2, (x2 - x1) / 2, (y2 - y1) / 2
    if fill:
        draw.ellipse(box, fill=fill)
    pts = [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
    for i in range(n):
        rough_line(draw, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], rng, fill=outline, width=width, passes=1)


def rough_arrow(draw, x1, y1, x2, y2, rng: random.Random, fill=INK, width=3):
    rough_line(draw, x1, y1, x2, y2, rng, fill=fill, width=width)
    ang = math.atan2(y2 - y1, x2 - x1)
    hl = 20
    for da in (0.48, -0.48):
        hx = x2 - hl * math.cos(ang - da)
        hy = y2 - hl * math.sin(ang - da)
        rough_line(draw, x2, y2, hx, hy, rng, fill=fill, width=width, passes=1, jitter=1.2)


def wrap(draw, text, ft, max_w):
    out = []
    for para in text.splitlines() or [text]:
        line = ""
        for ch in para:
            box = draw.textbbox((0, 0), line + ch, font=ft)
            if box[2] - box[0] <= max_w:
                line += ch
            else:
                out.append(line)
                line = ch
        out.append(line)
    return out


def draw_text_block(draw, cx, cy, text, size, rng, bold=True, fill=INK, max_w=460):
    """以 (cx,cy) 为中心画多行文字，每个字符略带手写抖动（旋转+偏移）。"""
    ft = font_for(text, size, bold)
    lines = wrap(draw, text, ft, max_w)
    lh = size + 10
    total_h = len(lines) * lh
    y = cy - total_h / 2
    for line in lines:
        box = draw.textbbox((0, 0), line, font=ft)
        w = box[2] - box[0]
        x = cx - w / 2
        draw.text((x + rng.uniform(-1, 1), y + rng.uniform(-1, 1)), line, font=ft, fill=fill)
        y += lh
    return total_h


# ---------- DSL：解析每课 diagrams.txt ----------
@dataclass
class DElem:
    kind: str            # box | text | note
    name: str
    label: str
    big: str = ""
    color: str = "blue"
    shape: str = "rect"   # rect | diamond | ellipse
    box_: tuple[float, float, float, float] = (0, 0, 0, 0)


@dataclass
class DArrow:
    src: str
    dst: str
    label: str = ""


@dataclass
class Diagram:
    title: str = ""
    canvas: tuple[int, int] = (1600, 900)
    elems: list[DElem] = field(default_factory=list)
    arrows: list[DArrow] = field(default_factory=list)


def _split_bar(s: str) -> list[str]:
    return [p.strip() for p in s.split("|")]


def load_diagrams(folder: Path) -> list[Diagram]:
    path = folder / "diagrams.txt"
    if not path.exists():
        path.write_text(
            "# 概念图配置（B方案：手绘风 excalidraw 风格，纯本地渲染，不影响文章正文）。\n"
            "# 每张图一个 [[diagram]] 块；box/text/note 自动从左到右排版（超宽自动换行）；\n"
            "# arrow 用 name -> name 连接两个元素。想加图就取消下面示例的注释并修改。\n"
            "\n"
            "# [[diagram]]\n"
            "# title: 变量 = 贴标签的箱子\n"
            "# box: hp | hp | big=20 | color=amber\n"
            "# note: code | hp = 20\n"
            "# arrow: code -> hp | 放进去\n",
            encoding="utf-8",
        )
        return []
    diagrams: list[Diagram] = []
    cur: Diagram | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s.startswith("#") or not s:
            continue
        if s.startswith("[[diagram]]"):
            if cur:
                diagrams.append(cur)
            cur = Diagram()
            continue
        if cur is None or ":" not in s:
            continue
        key, rest = s.split(":", 1)
        key = key.strip().lower()
        rest = rest.strip()
        if key == "title":
            cur.title = rest
        elif key == "canvas":
            m = re.match(r"(\d+)\s*x\s*(\d+)", rest)
            if m:
                cur.canvas = (int(m.group(1)), int(m.group(2)))
        elif key in ("box", "text", "note"):
            parts = _split_bar(rest)
            name, label = parts[0], (parts[1] if len(parts) > 1 else "")
            e = DElem(kind=key, name=name, label=label)
            for extra in parts[2:]:
                if "=" in extra:
                    k, v = extra.split("=", 1)
                    k = k.strip().lower()
                    if k == "big":
                        e.big = v.strip()
                    elif k == "color":
                        e.color = v.strip().lower()
                    elif k == "shape":
                        e.shape = v.strip().lower()
            cur.elems.append(e)
        elif key == "arrow":
            m = re.match(r"^(.*?)->(.*)$", rest)
            if not m:
                continue
            src = m.group(1).strip()
            tail = _split_bar(m.group(2))
            dst = tail[0].strip()
            lbl = tail[1] if len(tail) > 1 else ""
            cur.arrows.append(DArrow(src=src, dst=dst, label=lbl))
    if cur:
        diagrams.append(cur)
    return diagrams


# ---------- 排版 + 渲染 ----------
def _measure(draw, e: DElem) -> tuple[float, float]:
    if e.kind == "box":
        w = max(220.0, min(420.0, 40 + len(e.label) * 26))
        h = 160.0 if e.big else 120.0
        return w, h
    ft = font_for(e.label, 30, bold=(e.kind == "text"))
    lines = wrap(draw, e.label, ft, 460)
    return 480.0, max(90.0, len(lines) * 40 + 30)


def layout(draw, elems: list[DElem], canvas_w: int, top: int = 230) -> float:
    x, y, row_h = 90.0, float(top), 0.0
    left = 90.0
    for e in elems:
        w, h = _measure(draw, e)
        if x + w > canvas_w - left and x > left:
            x = left
            y += row_h + 60
            row_h = 0.0
        e.box_ = (x, y, x + w, y + h)
        row_h = max(row_h, h)
        x += w + 55
    return y + row_h + 60


def render_diagram(d: Diagram, out: Path) -> None:
    W, H = d.canvas
    img = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(img)
    for gy in range(0, H, 28):
        draw.line((0, gy, W, gy), fill=GRID)
    for gx in range(0, W, 28):
        draw.line((gx, 0, gx, H), fill=GRID)

    total_h = layout(draw, d.elems, W)
    if total_h > H - 40:
        scale = (H - 40) / total_h
        for e in d.elems:
            x1, y1, x2, y2 = e.box_
            e.box_ = (x1, 40 + y1 * scale, x2, 40 + y2 * scale)

    if d.title:
        rng_t = random.Random("title-" + d.title)
        draw_text_block(draw, W / 2, 90, d.title, 46, rng_t, bold=True, fill=INK, max_w=W - 160)
        rough_line(draw, W / 2 - 240, 140, W / 2 + 240, 140, rng_t, width=4)

    by_name: dict[str, DElem] = {e.name: e for e in d.elems}
    for e in d.elems:
        rng = random.Random(e.name + e.label)
        fill, outline = PALETTE.get(e.color, PALETTE["blue"])
        if e.kind == "box":
            if e.shape == "diamond":
                rough_diamond(draw, e.box_, rng, fill=fill, outline=outline)
            elif e.shape == "ellipse":
                rough_ellipse(draw, e.box_, rng, fill=fill, outline=outline)
            else:
                rough_rect(draw, e.box_, rng, fill=fill, outline=outline)
            x1, y1, x2, y2 = e.box_
            cx = (x1 + x2) / 2
            if e.big:
                draw_text_block(draw, cx, y1 + 32, e.label, 24, rng, bold=True, fill=outline, max_w=(x2 - x1) - 24)
                draw_text_block(draw, cx, (y1 + y2) / 2 + 16, e.big, 46, rng, bold=True, fill=INK, max_w=(x2 - x1) - 24)
            else:
                draw_text_block(draw, cx, (y1 + y2) / 2, e.label, 28, rng, bold=True, fill=INK, max_w=(x2 - x1) - 24)
        elif e.kind == "note":
            rough_rect(draw, e.box_, rng, fill=(248, 248, 240), outline=(150, 150, 140), width=2)
            x1, y1, x2, y2 = e.box_
            draw_text_block(draw, (x1 + x2) / 2, (y1 + y2) / 2, e.label, 26, rng, bold=False, fill=INK, max_w=(x2 - x1) - 30)
        else:  # text
            x1, y1, x2, y2 = e.box_
            draw_text_block(draw, (x1 + x2) / 2, (y1 + y2) / 2, e.label, 30, rng, bold=True, fill=INK, max_w=(x2 - x1) - 10)

    for a in d.arrows:
        s, t = by_name.get(a.src), by_name.get(a.dst)
        if not s or not t:
            continue
        sx1, sy1, sx2, sy2 = s.box_
        tx1, ty1, tx2, ty2 = t.box_
        scx, scy = (sx1 + sx2) / 2, (sy1 + sy2) / 2
        tcx, tcy = (tx1 + tx2) / 2, (ty1 + ty2) / 2
        if abs(scx - tcx) >= abs(scy - tcy):
            p1 = (sx2, scy) if tcx >= scx else (sx1, scy)
            p2 = (tx1, tcy) if tcx >= scx else (tx2, tcy)
        else:
            p1 = (scx, sy2) if tcy >= scy else (scx, sy1)
            p2 = (tcx, ty1) if tcy >= scy else (tcx, ty2)
        rng = random.Random(a.src + a.dst + a.label)
        rough_arrow(draw, p1[0], p1[1], p2[0], p2[1], rng, fill=(90, 40, 20), width=4)
        if a.label:
            mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 22
            ft = font_for(a.label, 24, bold=True)
            box = draw.textbbox((0, 0), a.label, font=ft)
            w, h = box[2] - box[0], box[3] - box[1]
            draw.rectangle((mx - w / 2 - 8, my - h / 2 - 4, mx + w / 2 + 8, my + h / 2 + 6), fill=PAPER)
            draw.text((mx - w / 2, my - h / 2), a.label, font=ft, fill=(90, 40, 20))

    img.save(out)


def find_lesson_folder(n: int) -> Path:
    dirs = sorted(KID.glob(f"lesson-{n:02d}-*"))
    if not dirs:
        raise SystemExit(f"找不到第 {n} 课目录")
    return dirs[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, required=True)
    args = ap.parse_args()

    folder = find_lesson_folder(args.lesson)
    diagrams = load_diagrams(folder)
    if not diagrams:
        print(f"第 {args.lesson} 课 diagrams.txt 里没有配置任何 [[diagram]]（已生成/存在示例模板，取消注释即可）：{folder / 'diagrams.txt'}")
        return 0

    outdir = folder / "images"
    outdir.mkdir(exist_ok=True)
    made = []
    for i, d in enumerate(diagrams, 1):
        p = outdir / f"diagram_{i:02d}.png"
        render_diagram(d, p)
        made.append(p)
    print(f"lesson={args.lesson} 生成 {len(made)} 张手绘风概念图 → {outdir}")
    for m in made:
        print(" -", m.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
