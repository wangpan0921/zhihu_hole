#!/usr/bin/env python3
"""少儿编程系列·统一讲解视频生成工具。

按课程号读取该课文章（优先定稿 lesson_NN_主题.md，否则 article.md，否则 docs 里
已发布/待发布的同号文章），自动把 Markdown 分节成幻灯片、逐节 edge-tts 配音、
渲染 Minecraft 风格讲解视频，输出到该课目录。

用法：
    ./venv/bin/python scripts/kid_coding_video.py --lesson 1
    ./venv/bin/python scripts/kid_coding_video.py --lesson 2 --vertical

设计为「通用模板渲染」：任何一篇符合本系列写法的文章都能生成一致风格的视频，
不需要为每课手写场景。
"""
from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
KID = ROOT / "kid_coding"
WIDTH, HEIGHT = 1920, 1080
FPS = 24
VOICE = "zh-CN-XiaoyiNeural"

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
CODE_BG = (244, 246, 240)
ACCENTS = [(46, 160, 67), (120, 84, 48), (37, 99, 235), (217, 140, 20), (214, 61, 47), (124, 58, 237), (8, 145, 178)]

CONTENT_X = 96
CONTENT_TOP = 300
CONTENT_BOTTOM = 858
CONTENT_W = WIDTH - CONTENT_X - 96


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


F_LOGO = font(30, True)
F_HERO = font(66, True)
F_TITLE = font(50, True)
F_H2 = font(44, True)
F_BODY = font(34)
F_BODY_BOLD = font(34, True)
F_CODE = font(32, True)
F_QUOTE = font(32)
F_CAPTION = font(35, True)


# ---------- markdown 解析 ----------
@dataclass
class Block:
    kind: str  # para | code | quote | item
    text: str


@dataclass
class Section:
    title: str
    blocks: list[Block] = field(default_factory=list)


def parse_article(md: str) -> tuple[str, list[Section]]:
    lines = md.splitlines()
    title = "本课"
    start = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("# ") and not s.startswith("## "):
            title = s[2:].strip()
            start = i + 1
            break
    sections: list[Section] = []
    cur = Section("引入")
    raw: list[str] = []

    def flush_blocks(sec: Section, raw_lines: list[str]) -> None:
        i = 0
        n = len(raw_lines)
        while i < n:
            ln = raw_lines[i]
            if ln.strip().startswith("```"):
                code: list[str] = []
                i += 1
                while i < n and not raw_lines[i].strip().startswith("```"):
                    code.append(raw_lines[i])
                    i += 1
                i += 1
                sec.blocks.append(Block("code", "\n".join(code)))
                continue
            if ln.strip() == "":
                i += 1
                continue
            if ln.lstrip().startswith(">"):
                q = re.sub(r"^\s*>\s?", "", ln)
                i += 1
                while i < n and raw_lines[i].lstrip().startswith(">"):
                    q += " " + re.sub(r"^\s*>\s?", "", raw_lines[i])
                    i += 1
                sec.blocks.append(Block("quote", q.strip()))
                continue
            if re.match(r"^\s*[-*]\s+", ln) or ln.lstrip().startswith(("🟢", "🔴")):
                item = re.sub(r"^\s*[-*]\s+", "", ln).strip()
                sec.blocks.append(Block("item", item))
                i += 1
                continue
            para = [ln.strip()]
            i += 1
            while i < n and raw_lines[i].strip() != "" and not raw_lines[i].strip().startswith(("```", ">", "-", "*", "#", "🟢", "🔴")):
                para.append(raw_lines[i].strip())
                i += 1
            sec.blocks.append(Block("para", " ".join(para)))

    for ln in lines[start:]:
        if ln.strip().startswith("## "):
            flush_blocks(cur, raw)
            if cur.blocks or cur.title != "引入":
                sections.append(cur)
            cur = Section(ln.strip()[3:].strip())
            raw = []
        else:
            raw.append(ln)
    flush_blocks(cur, raw)
    if cur.blocks:
        sections.append(cur)

    # 丢弃「系列导航」这种纯导航区块
    for sec in sections:
        sec.blocks = [b for b in sec.blocks if not (b.kind == "quote" and "系列导航" in b.text)]
    sections = [s for s in sections if s.blocks]
    return title, sections


# ---------- 文本清洗 & 朗读稿 ----------
def strip_md(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = s.replace("**", "").replace("`", "")
    s = s.replace("🟢", "基础关，").replace("🔴", "进阶关，")
    s = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", s)
    return s.strip()


def speakable(block: Block) -> str:
    if block.kind == "code":
        return ""
    return strip_md(block.text)


# ---------- 渲染辅助 ----------
def blend(a, b, r):
    return tuple(int(a[i] + (b[i] - a[i]) * r) for i in range(3))


def ease(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return 1 - (1 - v) ** 3


def tsize(draw, text, ft):
    box = draw.textbbox((0, 0), text, font=ft)
    return box[2] - box[0], box[3] - box[1]


def wrap(draw, text, ft, max_w):
    out = []
    for para in text.splitlines() or [text]:
        line = ""
        for ch in para:
            if tsize(draw, line + ch, ft)[0] <= max_w:
                line += ch
            else:
                if line:
                    out.append(line)
                line = ch
        out.append(line)
    return out


def rounded(draw, box, fill, outline=BORDER, width=2, radius=12):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


_DUMMY = ImageDraw.Draw(Image.new("RGB", (10, 10)))


def block_height(block: Block) -> int:
    if block.kind == "code":
        n = len(block.text.splitlines()) or 1
        return 28 + n * (F_CODE.size + 12) + 24
    if block.kind == "quote":
        lines = wrap(_DUMMY, strip_md(block.text), F_QUOTE, CONTENT_W - 60)
        return 24 + len(lines) * (F_QUOTE.size + 12) + 22
    if block.kind == "item":
        lines = wrap(_DUMMY, strip_md(block.text), F_BODY, CONTENT_W - 60)
        return len(lines) * (F_BODY.size + 12) + 14
    lines = wrap(_DUMMY, strip_md(block.text), F_BODY, CONTENT_W)
    return len(lines) * (F_BODY.size + 12) + 18


def paginate(blocks: list[Block]) -> list[list[Block]]:
    pages: list[list[Block]] = []
    cur: list[Block] = []
    h = 0
    avail = CONTENT_BOTTOM - CONTENT_TOP
    for b in blocks:
        bh = block_height(b)
        if cur and h + bh > avail:
            pages.append(cur)
            cur = [b]
            h = bh
        else:
            cur.append(b)
            h += bh
    if cur:
        pages.append(cur)
    return pages or [[]]


# ---------- 幻灯片 ----------
@dataclass
class Slide:
    title: str
    blocks: list[Block]
    accent: tuple
    narration: str
    start: float = 0.0
    end: float = 0.0


@dataclass
class Caption:
    start_ms: int
    end_ms: int
    text: str


def build_slides(title: str, sections: list[Section]) -> list[Slide]:
    slides: list[Slide] = []
    for si, sec in enumerate(sections):
        accent = ACCENTS[si % len(ACCENTS)]
        pages = paginate(sec.blocks)
        for pi, page in enumerate(pages):
            narr = " ".join(x for x in (speakable(b) for b in page) if x)
            if not narr:
                narr = sec.title
            head = sec.title if pi == 0 else sec.title + "（续）"
            slides.append(Slide(head, page, accent, narr))
    return slides


# ---------- TTS ----------
def edge_tts_exe() -> str:
    p = Path(sys.executable).with_name("edge-tts")
    if p.exists():
        return str(p)
    found = shutil.which("edge-tts")
    if found:
        return found
    raise RuntimeError("edge-tts not found")


def tts(text: str, out: Path) -> None:
    subprocess.run(
        [edge_tts_exe(), "--voice", VOICE, "--rate=-4%", "--text", text, "--write-media", str(out)],
        check=True,
    )


def ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(path: Path) -> float:
    proc = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not m:
        return 3.0
    hh, mm, ss = m.groups()
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def concat_audio(parts: list[Path], out: Path) -> None:
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True)


def mux(video: Path, audio: Path, out: Path) -> None:
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(audio), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)], check=True)


def make_vertical(src: Path, out: Path) -> None:
    fc = "[0:v]split=2[bg][fg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:3[bgb];[fg]scale=1080:-2[fgs];[bgb][fgs]overlay=(W-w)/2:(H-h)/2[v]"
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "aac", "-b:a", "160k", str(out)], check=True)


# ---------- 画面 ----------
def caption_lines(narr: str, start: float, dur: float) -> list[Caption]:
    parts = re.split(r"(?<=[。！？；])", narr)
    segs: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        while len(p) > 34:
            segs.append(p[:34])
            p = p[34:]
        segs.append(p)
    if not segs:
        segs = [narr]
    segs = [s.lstrip("，,、；;。！？：: ") for s in segs]
    segs = [s for s in segs if s]
    if not segs:
        segs = [narr]
    weights = [max(4, len(s)) for s in segs]
    tot = sum(weights)
    caps: list[Caption] = []
    cur = start
    for s, w in zip(segs, weights):
        seg = dur * (w / tot)
        caps.append(Caption(int(cur * 1000), int((cur + seg) * 1000), s))
        cur += seg
    return caps


def canvas(lesson_no: int, corner: str, slide: Slide, local: float) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), SKY_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        draw.line((0, y, WIDTH, y), fill=blend(SKY_TOP, SKY_BOTTOM, y / HEIGHT))
    gy = HEIGHT - 70
    for bx in range(0, WIDTH, 70):
        draw.rectangle((bx, gy, bx + 68, gy + 22), fill=GRASS if (bx // 70) % 2 == 0 else GRASS_DARK)
        draw.rectangle((bx, gy + 22, bx + 68, HEIGHT), fill=DIRT)
    bar = int(24 + 460 * ease(local / 1.0))
    draw.rectangle((0, 0, 16, bar), fill=slide.accent)
    draw.text((72, 50), f"我的世界里学编程 · 第 {lesson_no} 课", font=F_LOGO, fill=slide.accent)
    lines = wrap(draw, slide.title, F_HERO, WIDTH - 420)[:1]
    draw.text((72, 100), lines[0] if lines else slide.title, font=F_HERO, fill=INK)
    c2 = wrap(draw, corner, F_TITLE, 360)[:1]
    if c2:
        cw, _ = tsize(draw, c2[0], F_TITLE)
        draw.text((WIDTH - 96 - cw, 60), c2[0], font=F_TITLE, fill=MUTED)
    draw.line((72, 200, 700, 200), fill=slide.accent, width=5)
    return img, draw


def render_blocks(draw, blocks: list[Block], accent) -> None:
    y = CONTENT_TOP
    for b in blocks:
        if y > CONTENT_BOTTOM:
            break
        if b.kind == "code":
            code_lines = b.text.splitlines() or [""]
            h = len(code_lines) * (F_CODE.size + 12) + 24
            rounded(draw, (CONTENT_X, y, CONTENT_X + CONTENT_W, y + h), CODE_BG, outline=BORDER, width=2, radius=10)
            cy = y + 12
            for cl in code_lines:
                draw.text((CONTENT_X + 22, cy), cl, font=F_CODE, fill=INK)
                cy += F_CODE.size + 12
            y += h + 20
        elif b.kind == "quote":
            txt = strip_md(b.text)
            wl = wrap(draw, txt, F_QUOTE, CONTENT_W - 60)
            h = len(wl) * (F_QUOTE.size + 12) + 24
            draw.rectangle((CONTENT_X, y, CONTENT_X + 6, y + h), fill=accent)
            qy = y + 12
            for l in wl:
                draw.text((CONTENT_X + 28, qy), l, font=F_QUOTE, fill=MUTED)
                qy += F_QUOTE.size + 12
            y += h + 18
        elif b.kind == "item":
            txt = strip_md(b.text)
            wl = wrap(draw, txt, F_BODY, CONTENT_W - 60)
            draw.ellipse((CONTENT_X + 6, y + 14, CONTENT_X + 22, y + 30), fill=accent)
            iy = y
            for l in wl:
                draw.text((CONTENT_X + 44, iy), l, font=F_BODY, fill=INK)
                iy += F_BODY.size + 12
            y = iy + 8
        else:
            txt = strip_md(b.text)
            wl = wrap(draw, txt, F_BODY, CONTENT_W)
            for l in wl:
                if y > CONTENT_BOTTOM:
                    break
                draw.text((CONTENT_X, y), l, font=F_BODY, fill=INK)
                y += F_BODY.size + 12
            y += 8


def draw_caption(img, cap, t, total, accent):
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, HEIGHT - 8, int(WIDTH * min(1.0, t / total)), HEIGHT), fill=accent)
    if cap is None:
        return
    x1, y1, x2, y2 = 200, 900, WIDTH - 200, 1024
    rounded(draw, (x1, y1, x2, y2), NAVY, outline=(60, 72, 60), radius=12)
    lines = wrap(draw, cap.text, F_CAPTION, x2 - x1 - 80)[:2]
    yy = y1 + 24 if len(lines) == 2 else y1 + 42
    for line in lines:
        w, _ = tsize(draw, line, F_CAPTION)
        draw.text((x1 + (x2 - x1 - w) // 2, yy), line, font=F_CAPTION, fill=(255, 255, 255))
        yy += 46


# ---------- 主流程 ----------
def find_lesson(n: int) -> tuple[Path, Path]:
    dirs = sorted(KID.glob(f"lesson-{n:02d}-*"))
    folder = dirs[0] if dirs else None
    article = None
    if folder:
        finals = sorted(folder.glob("lesson_*.md"))
        if finals:
            article = finals[0]
        elif (folder / "article.md").exists():
            article = folder / "article.md"
    if article is None:
        for base in (ROOT / "docs/pending", ROOT / "docs/published"):
            cand = sorted(base.glob(f"kid-coding-{n:02d}-*.md")) if base.exists() else []
            if cand:
                article = cand[0]
                if folder is None:
                    folder = KID / f"lesson-{n:02d}-{cand[0].stem.split('-', 3)[-1]}"
                break
    if article is None or folder is None:
        raise SystemExit(f"找不到第 {n} 课的文章（课程目录或 docs 里都没有）")
    folder.mkdir(parents=True, exist_ok=True)
    return folder, article


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, required=True)
    ap.add_argument("--vertical", action="store_true", help="额外输出 9:16 竖屏版")
    args = ap.parse_args()

    folder, article_path = find_lesson(args.lesson)
    corner = folder.name.split("-", 2)[-1] if "-" in folder.name else folder.name
    title, sections = parse_article(article_path.read_text(encoding="utf-8"))
    if not sections:
        raise SystemExit("文章解析后没有可用内容")
    slides = build_slides(title, sections)

    workdir = Path(tempfile.mkdtemp(prefix="kidvid_"))
    audio_parts: list[Path] = []
    for i, sl in enumerate(slides):
        ap_i = workdir / f"a{i:03d}.mp3"
        tts(sl.narration, ap_i)
        audio_parts.append(ap_i)
    durations = [duration(p) for p in audio_parts]

    # 分配时间轴
    t = 0.0
    captions: list[Caption] = []
    for sl, d in zip(slides, durations):
        sl.start = t
        sl.end = t + d
        captions.extend(caption_lines(sl.narration, t, d))
        t += d
    total = t + 0.6

    audio_full = workdir / "narration.mp3"
    concat_audio(audio_parts, audio_full)

    silent = folder / f"kid_coding_{args.lesson:02d}_silent.mp4"
    final = folder / f"kid_coding_{args.lesson:02d}_video.mp4"

    def active_slide(tt):
        for s in slides:
            if s.start <= tt < s.end:
                return s
        return slides[-1]

    def active_cap(tt):
        ms = int(tt * 1000)
        for c in captions:
            if c.start_ms <= ms < c.end_ms:
                return c
        return None

    total_frames = math.ceil(total * FPS)
    writer = imageio.get_writer(silent, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    try:
        for fno in range(total_frames):
            tt = fno / FPS
            sl = active_slide(tt)
            img, draw = canvas(args.lesson, corner, sl, tt - sl.start)
            render_blocks(draw, sl.blocks, sl.accent)
            draw_caption(img, active_cap(tt), tt, total, sl.accent)
            writer.append_data(np.asarray(img))
    finally:
        writer.close()

    mux(silent, audio_full, final)
    silent.unlink(missing_ok=True)
    print(final)
    if args.vertical:
        vout = folder / f"kid_coding_{args.lesson:02d}_video_vertical.mp4"
        make_vertical(final, vout)
        print(vout)
    print(f"lesson={args.lesson} slides={len(slides)} duration={total:.1f}s")
    shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
