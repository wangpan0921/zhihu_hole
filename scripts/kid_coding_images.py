#!/usr/bin/env python3
"""少儿编程系列·自动配图工具（可程序化生成的部分）。

按课程号读取文章，自动生成三类可用 PIL 直接绘制的配图，输出到该课目录的 images/：
  1. cover.png       —— 像素风程序化封面（课程标题 + 系列标签）
  2. run_C.png       —— 每个 ```python 代码块渲染成代码/终端图；能无输入运行的，真跑出输出
  3. summary.png     —— 从「今天你学会了」小节的要点生成总结卡

不覆盖需要手工/AI 的部分：AI 插画封面、excalidraw 概念示意图（见各课 配图.md）。

用法：
    ./venv/bin/python scripts/kid_coding_images.py --lesson 2
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
KID = ROOT / "kid_coding"
W, H = 1600, 900

SKY_TOP = (135, 196, 235)
SKY_BOTTOM = (198, 228, 245)
GRASS = (95, 159, 53)
GRASS_DARK = (74, 128, 40)
DIRT = (134, 96, 67)
INK = (32, 38, 28)
MUTED = (92, 102, 84)
PANEL = (255, 255, 255)
BORDER = (206, 214, 196)
NAVY = (28, 36, 46)
GREEN = (46, 160, 67)
GOLD = (240, 190, 40)
WOOD = (170, 122, 74)
WOOD_DARK = (120, 84, 48)
STICKY = (250, 224, 96)
CODE_BG = (248, 249, 245)
TERM_BG = (24, 28, 33)
TERM_FG = (180, 245, 180)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for c in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if c and Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


F_SERIES = font(30, True)
F_COVER = font(84, True)
F_COVER_SUB = font(40, True)
F_H = font(46, True)
F_BODY = font(34)
F_BODY_B = font(34, True)
F_CODE = font(32, True)
F_LABEL = font(28, True)


def blend(a, b, r):
    return tuple(int(a[i] + (b[i] - a[i]) * r) for i in range(3))


def tsize(d, t, f):
    box = d.textbbox((0, 0), t, font=f)
    return box[2] - box[0], box[3] - box[1]


def wrap(d, text, f, maxw):
    out = []
    for para in text.splitlines() or [text]:
        line = ""
        for ch in para:
            if tsize(d, line + ch, f)[0] <= maxw:
                line += ch
            else:
                out.append(line)
                line = ch
        out.append(line)
    return out


def rounded(d, box, fill, outline=BORDER, width=2, radius=14):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def base_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), SKY_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line((0, y, W, y), fill=blend(SKY_TOP, SKY_BOTTOM, y / H))
    gy = H - 60
    for bx in range(0, W, 60):
        d.rectangle((bx, gy, bx + 58, gy + 20), fill=GRASS if (bx // 60) % 2 == 0 else GRASS_DARK)
        d.rectangle((bx, gy + 20, bx + 58, H), fill=DIRT)
    return img, d


# ---------- markdown 提取 ----------
def parse(md: str):
    lines = md.splitlines()
    title = "本课"
    for ln in lines:
        s = ln.strip()
        if s.startswith("# ") and not s.startswith("## "):
            title = s[2:].strip()
            break
    # 代码块
    codes = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            lang = lines[i].strip()[3:].strip()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            if lang.startswith("python") or lang == "":
                codes.append("\n".join(buf))
        i += 1
    # 今天你学会了 要点
    summary = []
    in_sum = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("## "):
            in_sum = "今天你学会了" in s
            continue
        if in_sum and re.match(r"^\s*[-*]\s+", ln):
            item = re.sub(r"^\s*[-*]\s+", "", ln).strip()
            item = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", item).replace("**", "").replace("`", "")
            summary.append(item)
    return title, codes, summary


def clean_title(t: str) -> str:
    # 去掉破折号副标题，保留主标题更适合封面
    return re.split(r"[——]", t)[0].strip() or t


# ---------- 封面 ----------
def render_cover(title: str, lesson_no: int, corner: str, out: Path):
    img, d = base_canvas()
    # 漂浮方块装饰
    for (x, y, c) in [(1180, 150, GRASS), (1330, 230, WOOD), (1250, 340, GOLD)]:
        d.rectangle((x, y, x + 96, y + 96), fill=c, outline=WOOD_DARK, width=4)
    d.text((80, 90), f"我的世界里学编程 · 第 {lesson_no} 课", font=F_SERIES, fill=GREEN)
    main = clean_title(title)
    lines = wrap(d, main, F_COVER, W - 380)[:3]
    y = 210
    for ln in lines:
        d.text((80, y), ln, font=F_COVER, fill=INK)
        y += F_COVER.size + 18
    d.line((80, y + 6, 520, y + 6), fill=GREEN, width=6)
    d.text((80, H - 150), "跟着史蒂夫，从零打通信奥赛之路", font=F_COVER_SUB, fill=MUTED)
    img.save(out)


# ---------- 代码 / 终端图 ----------
def run_code(code: str) -> str | None:
    if "input(" in code:
        return None  # 需要交互输入，headless 跑不了
    try:
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        out = (p.stdout or "") + (p.stderr or "")
        return out.strip() or "(无输出)"
    except Exception:
        return None


def render_code_image(code: str, output: str | None, idx: int, out: Path):
    code_lines = code.splitlines() or [""]
    out_lines = output.splitlines() if output else []
    img, d = base_canvas()
    x0, y0 = 90, 90
    win_w = W - 180
    # 代码窗口
    ch = 70 + len(code_lines) * (F_CODE.size + 12) + 24
    rounded(d, (x0, y0, x0 + win_w, y0 + ch), CODE_BG, outline=BORDER, width=3, radius=16)
    for i, c in enumerate([(237, 106, 94), (245, 191, 79), (98, 197, 84)]):
        d.ellipse((x0 + 28 + i * 34, y0 + 24, x0 + 48 + i * 34, y0 + 44), fill=c)
    d.text((x0 + 150, y0 + 22), "code.py", font=F_LABEL, fill=MUTED)
    cy = y0 + 70
    for cl in code_lines:
        d.text((x0 + 34, cy), cl, font=F_CODE, fill=INK)
        cy += F_CODE.size + 12
    # 终端输出
    if out_lines:
        ty = y0 + ch + 30
        th = 64 + len(out_lines) * (F_CODE.size + 10) + 20
        rounded(d, (x0, ty, x0 + win_w, ty + th), TERM_BG, outline=TERM_BG, radius=16)
        d.text((x0 + 34, ty + 20), "▶ 运行结果", font=F_LABEL, fill=(150, 160, 170))
        oy = ty + 64
        for ol in out_lines:
            d.text((x0 + 34, oy), ol, font=F_CODE, fill=TERM_FG)
            oy += F_CODE.size + 10
    img.save(out)


# ---------- 总结卡 ----------
def render_summary(title: str, lesson_no: int, items: list[str], out: Path):
    img, d = base_canvas()
    d.text((80, 70), f"第 {lesson_no} 课 · 知识清单", font=F_SERIES, fill=GREEN)
    d.text((80, 118), "今天你学会了", font=F_H, fill=INK)
    d.line((80, 186, 460, 186), fill=GREEN, width=5)
    y = 230
    for it in items[:6]:
        parts = it.split("：", 1)
        key = parts[0].replace("`", "").strip()
        val = parts[1].strip() if len(parts) > 1 else ""
        kf = F_LABEL if tsize(d, key, F_LABEL)[0] <= 240 else font(20, True)
        kw = tsize(d, key, kf)[0]
        chip_w = max(190, kw + 32)
        rounded(d, (80, y, W - 80, y + 88), PANEL, outline=BORDER, width=3, radius=14)
        rounded(d, (100, y + 18, 100 + chip_w, y + 70), blend(GREEN, PANEL, 0.15), outline=GREEN, width=2, radius=10)
        d.text((116, y + 44 - kf.size // 2), key, font=kf, fill=INK)
        vx = 100 + chip_w + 28
        vl = wrap(d, val or key, F_BODY_B, W - 80 - vx - 20)[:1]
        if vl:
            d.text((vx, y + 26), vl[0], font=F_BODY_B, fill=INK)
        y += 104
        if y > H - 120:
            break
    img.save(out)


def find_lesson(n: int):
    dirs = sorted(KID.glob(f"lesson-{n:02d}-*"))
    if not dirs:
        raise SystemExit(f"找不到第 {n} 课目录")
    folder = dirs[0]
    finals = sorted(folder.glob("lesson_*.md"))
    art = finals[0] if finals else (folder / "article.md")
    if not art.exists():
        raise SystemExit(f"第 {n} 课没有文章（lesson_*.md 或 article.md）")
    return folder, art


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, required=True)
    args = ap.parse_args()
    folder, art = find_lesson(args.lesson)
    corner = folder.name.split("-", 2)[-1]
    title, codes, summary = parse(art.read_text(encoding="utf-8"))
    outdir = folder / "images"
    outdir.mkdir(exist_ok=True)

    made = []
    cover = outdir / "cover.png"
    render_cover(title, args.lesson, corner, cover)
    made.append(cover)

    for i, code in enumerate(codes, 1):
        out = run_code(code)
        p = outdir / f"run_{i:02d}.png"
        render_code_image(code, out, i, p)
        made.append(p)

    if summary:
        s = outdir / "summary.png"
        render_summary(title, args.lesson, summary, s)
        made.append(s)

    print(f"lesson={args.lesson} 生成 {len(made)} 张图 → {outdir}")
    for m in made:
        print(" -", m.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
