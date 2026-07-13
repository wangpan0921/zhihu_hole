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
    kind: str = "content"          # content | quiz_q | quiz_a
    options: list[str] | None = None   # 互动题选项，如 ["A. …", "B. …"]
    answer: str = ""               # 正确选项字母，如 "A"
    question: str = ""             # 互动题题干
    explain: str = ""              # 揭晓解释
    pause: float = 0.0             # 题目屏思考停顿秒数（含倒计时）


@dataclass
class Quiz:
    anchor: str                    # 插在标题包含该关键字的那一节之后
    question: str
    options: list[str]
    answer: str
    explain: str
    pause: float = 4.0


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


def load_quiz(folder: Path) -> list[Quiz]:
    """读取每课的互动题配置 quiz.txt（A方案：弹选项+倒计时+揭晓）。

    不存在则写一个带示例的模板。格式：每题一个 [[quiz]] 块，例如：
        [[quiz]]
        after: 先猜猜看          # 插在标题含「先猜猜看」的那一节之后
        question: 这段代码打印几到几？
        A: 0、1、2
        B: 1、2、3
        C: 报错
        answer: A
        explain: range(3) 从 0 开始数三个。
        pause: 4                 # 思考停顿秒数（含 3-2-1 倒计时）
    """
    path = folder / "quiz.txt"
    if not path.exists():
        path.write_text(
            "# 互动题配置（A方案：弹选项+倒计时+揭晓）。只影响视频，不影响文章。\n"
            "# 每题一个 [[quiz]] 块；after 写要插在其后的那一节标题关键字。\n"
            "# 想加题就照下面的示例取消注释并修改；不需要就留空即可。\n"
            "\n"
            "# [[quiz]]\n"
            "# after: 先猜猜看\n"
            "# question: 这段代码会打印什么？\n"
            "# A: 僵尸 0、僵尸 1、僵尸 2\n"
            "# B: 僵尸 1、僵尸 2、僵尸 3\n"
            "# C: 直接报错\n"
            "# answer: A\n"
            "# explain: range(3) 从 0 开始数三个，所以是 0、1、2。\n"
            "# pause: 4\n",
            encoding="utf-8",
        )
        return []
    quizzes: list[Quiz] = []
    cur: dict | None = None

    def flush():
        if cur and cur.get("question") and cur.get("options"):
            quizzes.append(Quiz(
                anchor=cur.get("after", ""),
                question=cur["question"],
                options=cur["options"],
                answer=cur.get("answer", "").strip().upper(),
                explain=cur.get("explain", ""),
                pause=float(cur.get("pause", 4) or 4),
            ))

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        if line.startswith("[[quiz]]"):
            flush()
            cur = {"options": []}
            continue
        if cur is None or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key in ("a", "b", "c", "d", "e"):
            cur["options"].append(f"{key.upper()}. {val}")
        elif key in ("after", "question", "answer", "explain", "pause"):
            cur[key] = val
    flush()
    return quizzes


def make_silence(seconds: float, out: Path) -> Path:
    subprocess.run(
        [ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=24000:cl=mono", "-t", f"{seconds:.2f}", "-q:a", "9", str(out)],
        check=True,
    )
    return out


def insert_quiz_slides(slides: list[Slide], quizzes: list[Quiz]) -> list[Slide]:
    """按 anchor 把每道题的「出题屏 + 揭晓屏」插到对应小节之后。"""
    for q in quizzes:
        # 定位锚点小节：优先标题（去掉"（续）"）精确等于 anchor，否则取首个包含 anchor 的
        def base(t: str) -> str:
            return t.replace("（续）", "")
        start = -1
        for i, sl in enumerate(slides):
            if sl.kind == "content" and q.anchor and base(sl.title) == q.anchor:
                start = i
                break
        if start < 0:
            for i, sl in enumerate(slides):
                if sl.kind == "content" and q.anchor and q.anchor in base(sl.title):
                    start = i
                    break
        if start < 0:
            idx = len(slides) - 1  # 没匹配到就放最后
        else:
            idx = start
            while (idx + 1 < len(slides) and slides[idx + 1].kind == "content"
                   and base(slides[idx + 1].title) == base(slides[start].title)):
                idx += 1  # 跨过该节的「（续）」分页，插到整节之后
        opt_read = "；".join(o.replace(".", "，", 1) for o in q.options)
        q_slide = Slide(
            title="先猜猜看", blocks=[], accent=(217, 140, 20),
            narration=f"{q.question} 选项：{opt_read}。你选哪个？想一想。",
            kind="quiz_q", options=q.options, answer=q.answer,
            question=q.question, explain=q.explain, pause=q.pause,
        )
        ans_read = q.explain or f"正确答案是 {q.answer}。"
        a_slide = Slide(
            title="揭晓答案", blocks=[], accent=(46, 160, 67),
            narration=f"答案是 {q.answer}。{ans_read}",
            kind="quiz_a", options=q.options, answer=q.answer,
            question=q.question, explain=q.explain,
        )
        slides[idx + 1:idx + 1] = [q_slide, a_slide]
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


PRON_FILE = KID / "pronunciation.txt"


def load_pron() -> list[tuple[str, str]]:
    """读音替换词典：只用于配音，不改字幕。

    文件 kid_coding/pronunciation.txt，每行 `原词=朗读替换`（用同音字纠正多音字）：
        一行=一航     # 让 TTS 读 yī háng 而不是 yī xíng
    按原词长度从长到短应用，避免短词误替换长词的一部分。
    """
    if not PRON_FILE.exists():
        PRON_FILE.write_text(
            "# 读音替换词典（只影响配音，不影响字幕文字）。\n"
            "# 每行：原词 => 朗读替换   用同音字纠正多音字或符号读音；# 开头为注释。\n"
            "# 用 => 分隔，这样原词里含 = 号（如 ==、>=、<=、!=）也不会被切错。\n"
            "一行 => 一航\n",
            encoding="utf-8",
        )
    pairs: list[tuple[str, str]] = []
    for line in PRON_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=>" not in line:
            continue
        src, dst = line.split("=>", 1)
        src, dst = src.strip(), dst.strip()
        if src:
            pairs.append((src, dst))
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def apply_pron(text: str, pairs: list[tuple[str, str]]) -> str:
    for src, dst in pairs:
        text = text.replace(src, dst)
    return text


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
    sec_breaks = "，,、；;：:"

    def inside_mask(s: str) -> list[bool]:
        """标记每个字符是否处于括号/引号内部（内部不允许断句）。"""
        mask = [False] * len(s)
        paren = 0
        inq = False
        for i, ch in enumerate(s):
            if ch in "(（“":
                paren += 1
                mask[i] = True
            elif ch in ")）”":
                mask[i] = True
                paren = max(0, paren - 1)
            elif ch == '"':
                inq = not inq
                mask[i] = True
            else:
                mask[i] = paren > 0 or inq
        return mask

    def chunk(p: str, maxlen: int = 30) -> list[str]:
        out: list[str] = []
        while len(p) > maxlen:
            mask = inside_mask(p)
            lo = max(0, maxlen - 18)
            hi = min(maxlen, len(p) - 1)
            cut = -1
            # 1) 优先在标点处断，且不在括号/引号内部（避免切碎 input("…") 这类）
            for i in range(hi, lo, -1):
                if p[i] in sec_breaks and not mask[i]:
                    cut = i + 1
                    break
            # 2) 其次在空格处断（同样避开括号/引号内部）
            if cut <= 0:
                for i in range(hi, lo, -1):
                    if p[i] == " " and not mask[i]:
                        cut = i + 1
                        break
            if cut <= 0:
                cut = maxlen
            # 把紧跟其后的闭合引号/括号/句末标点并入当前屏，避免被甩到下一屏
            while cut < len(p) and p[cut] in "\"”’）)。！？，、；：,.!?":
                cut += 1
            out.append(p[:cut])
            p = p[cut:]
        if p:
            out.append(p)
        return out

    def sentence_split(line: str) -> list[str]:
        """按句末标点断句，但括号/引号内部的句末标点不算断点。"""
        mask = inside_mask(line)
        parts: list[str] = []
        start = 0
        for i, ch in enumerate(line):
            if ch in "。！？；" and not mask[i]:
                parts.append(line[start:i + 1])
                start = i + 1
        if start < len(line):
            parts.append(line[start:])
        return parts

    segs: list[str] = []
    for line in narr.split("\n"):
        line = line.strip()
        if not line:
            continue
        for p in sentence_split(line):
            p = p.strip()
            if not p:
                continue
            segs.extend(chunk(p))
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


_BG_CACHE: Image.Image | None = None


def _static_bg() -> Image.Image:
    """渐变天空 + 草地泥土条是每帧不变的，只算一次并缓存，渲染时复制即可。"""
    global _BG_CACHE
    if _BG_CACHE is None:
        img = Image.new("RGB", (WIDTH, HEIGHT), SKY_TOP)
        d = ImageDraw.Draw(img)
        for y in range(HEIGHT):
            d.line((0, y, WIDTH, y), fill=blend(SKY_TOP, SKY_BOTTOM, y / HEIGHT))
        gy = HEIGHT - 70
        for bx in range(0, WIDTH, 70):
            d.rectangle((bx, gy, bx + 68, gy + 22), fill=GRASS if (bx // 70) % 2 == 0 else GRASS_DARK)
            d.rectangle((bx, gy + 22, bx + 68, HEIGHT), fill=DIRT)
        _BG_CACHE = img
    return _BG_CACHE.copy()


def canvas(lesson_no: int, corner: str, slide: Slide, local: float) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = _static_bg()
    draw = ImageDraw.Draw(img)
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


def render_quiz(draw, sl: Slide, reveal: bool, countdown: int | None) -> None:
    x = CONTENT_X
    y = CONTENT_TOP
    for line in wrap(draw, sl.question, F_H2, CONTENT_W - 340)[:3]:
        draw.text((x, y), line, font=F_H2, fill=INK)
        y += F_H2.size + 10
    y += 20
    for opt in (sl.options or []):
        letter = opt[:1].upper()
        is_ans = reveal and letter == sl.answer
        card_w = CONTENT_W - 360
        card_h = 84
        if is_ans:
            fill, outline, ow = blend(GREEN, PANEL, 0.72), GREEN, 5
        elif reveal:
            fill, outline, ow = (238, 240, 234), BORDER, 2
        else:
            fill, outline, ow = PANEL, BORDER, 3
        rounded(draw, (x, y, x + card_w, y + card_h), fill, outline=outline, width=ow, radius=12)
        chip = GREEN if is_ans else sl.accent
        rounded(draw, (x + 18, y + 16, x + 70, y + 68), blend(chip, PANEL, 0.15), outline=chip, width=2, radius=10)
        lw, lh = tsize(draw, letter, F_BODY_BOLD)
        draw.text((x + 44 - lw // 2, y + 42 - lh // 2), letter, font=F_BODY_BOLD, fill=INK)
        txt = opt.split(".", 1)[1].strip() if "." in opt else opt
        tl = wrap(draw, txt, F_BODY, card_w - 120)[:1]
        if tl:
            draw.text((x + 92, y + 24), tl[0], font=F_BODY, fill=INK)
        if is_ans:
            draw.text((x + card_w - 56, y + 18), "✓", font=F_H2, fill=GREEN)
        y += card_h + 16
    if countdown is not None:
        cx, cy = WIDTH - 300, CONTENT_TOP + 70
        draw.ellipse((cx - 90, cy - 90, cx + 90, cy + 90), outline=(217, 140, 20), width=8)
        cf = font(120, True)
        s = str(countdown)
        sw, sh = tsize(draw, s, cf)
        draw.text((cx - sw // 2, cy - sh // 2 - 12), s, font=cf, fill=(217, 140, 20))
        tw, _ = tsize(draw, "想一想…", F_BODY_BOLD)
        draw.text((cx - tw // 2, cy + 104), "想一想…", font=F_BODY_BOLD, fill=MUTED)
    if reveal and sl.explain:
        ey = min(y + 8, CONTENT_BOTTOM - 96)
        wl = wrap(draw, "解析：" + sl.explain, F_BODY, CONTENT_W - 48)[:2]
        bh = len(wl) * (F_BODY.size + 8) + 24
        rounded(draw, (x, ey, x + CONTENT_W, ey + bh), blend(GREEN, PANEL, 0.85), outline=GREEN, width=2, radius=12)
        ty = ey + 14
        for line in wl:
            draw.text((x + 24, ty), line, font=F_BODY, fill=INK)
            ty += F_BODY.size + 8


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


def load_or_init_narration(folder: Path, slides: list[Slide]) -> str:
    """朗读稿（配音+字幕的唯一文本来源）读取或初始化。

    - 若 folder/narration.txt 存在：按 `### N | 标题` 分块，按顺序覆盖各页 narration。
      在块内改标点、加换行，即可调整配音停顿与字幕断句（换行 = 一次停顿+断句）。
    - 若不存在：用自动提炼的稿写出该文件，供后续编辑。
    返回 "loaded" 或 "created"。
    """
    path = folder / "narration.txt"
    if path.exists():
        blocks: list[str] = []
        cur: list[str] | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("### "):
                if cur is not None:
                    blocks.append("\n".join(cur).strip())
                cur = []
            elif cur is not None:
                cur.append(line)
        if cur is not None:
            blocks.append("\n".join(cur).strip())
        for i, b in enumerate(blocks):
            if i < len(slides) and b:
                slides[i].narration = b
        return "loaded"
    header = [
        "# 讲解朗读稿（配音与字幕都来自这里；不影响公众号文章正文）。",
        "# 改标点、加换行即可调整配音停顿与字幕断句：换行 = 一次停顿 + 一次断句。",
        "# 每个 ### 块对应视频里的一页，顺序请勿改动。改完重新运行本工具渲染即可。",
        "",
    ]
    for i, sl in enumerate(slides):
        header.append(f"### {i + 1} | {sl.title}")
        header.append(sl.narration)
        header.append("")
    path.write_text("\n".join(header), encoding="utf-8")
    return "created"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, required=True)
    ap.add_argument("--vertical", action="store_true", help="额外输出 9:16 竖屏版")
    ap.add_argument("--narration-only", action="store_true", help="只生成/更新朗读稿 narration.txt，不渲染视频")
    args = ap.parse_args()

    folder, article_path = find_lesson(args.lesson)
    corner = folder.name.split("-", 2)[-1] if "-" in folder.name else folder.name
    title, sections = parse_article(article_path.read_text(encoding="utf-8"))
    if not sections:
        raise SystemExit("文章解析后没有可用内容")
    slides = build_slides(title, sections)

    narr_state = load_or_init_narration(folder, slides)
    narr_path = folder / "narration.txt"
    if args.narration_only:
        print(f"朗读稿{'已生成' if narr_state == 'created' else '已存在'}：{narr_path}")
        print("在其中改标点/加换行调整配音停顿与字幕断句，然后重新运行（不加 --narration-only）渲染。")
        return 0
    if narr_state == "created":
        print(f"（已生成可编辑朗读稿：{narr_path}，本次先用默认稿渲染；想微调停顿就编辑它再重跑）")

    # 互动题（A方案）：读 quiz.txt，把出题屏+揭晓屏插到指定小节之后
    quizzes = load_quiz(folder)
    slides = insert_quiz_slides(slides, quizzes)
    if quizzes:
        print(f"（已插入 {len(quizzes)} 道互动题：弹选项 + 倒计时 + 揭晓）", flush=True)

    workdir = Path(tempfile.mkdtemp(prefix="kidvid_"))
    audio_parts: list[Path] = []
    pron = load_pron()
    dur_pairs: list[tuple[float, float]] = []  # (整屏时长, 口播时长)
    print(f"[1/3] 合成配音（共 {len(slides)} 段）…", flush=True)
    for i, sl in enumerate(slides):
        ap_i = workdir / f"a{i:03d}.mp3"
        tts(apply_pron(sl.narration, pron), ap_i)
        audio_parts.append(ap_i)
        spoken = duration(ap_i)
        total_d = spoken
        if sl.kind == "quiz_q" and sl.pause > 0:  # 出题屏后追加静音停顿（倒计时用）
            sfile = workdir / f"s{i:03d}.mp3"
            make_silence(sl.pause, sfile)
            audio_parts.append(sfile)
            total_d += sl.pause
        dur_pairs.append((total_d, spoken))
        print(f"    配音 {i + 1}/{len(slides)} 完成", flush=True)

    # 分配时间轴（字幕只覆盖口播部分，倒计时静音处不显字幕）
    t = 0.0
    captions: list[Caption] = []
    for sl, (td, sd) in zip(slides, dur_pairs):
        sl.start = t
        sl.end = t + td
        captions.extend(caption_lines(sl.narration, t, sd))
        t += td
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
    print(f"[2/3] 渲染画面（共 {total_frames} 帧，约 {total:.0f} 秒视频）…", flush=True)
    try:
        step = max(1, total_frames // 10)
        for fno in range(total_frames):
            tt = fno / FPS
            sl = active_slide(tt)
            img, draw = canvas(args.lesson, corner, sl, tt - sl.start)
            if sl.kind == "content":
                render_blocks(draw, sl.blocks, sl.accent)
            else:
                countdown = None
                if sl.kind == "quiz_q" and sl.pause > 0:
                    remaining = sl.end - tt
                    if remaining <= sl.pause:
                        countdown = max(1, math.ceil(remaining))
                render_quiz(draw, sl, reveal=(sl.kind == "quiz_a"), countdown=countdown)
            draw_caption(img, active_cap(tt), tt, total, sl.accent)
            writer.append_data(np.asarray(img))
            if fno % step == 0 and fno:
                print(f"    渲染 {fno * 100 // total_frames}%", flush=True)
    finally:
        writer.close()

    print("[3/3] 合成音视频…", flush=True)
    mux(silent, audio_full, final)
    silent.unlink(missing_ok=True)
    print("完成：", final, flush=True)
    if args.vertical:
        vout = folder / f"kid_coding_{args.lesson:02d}_video_vertical.mp4"
        make_vertical(final, vout)
        print("竖屏：", vout, flush=True)
    print(f"lesson={args.lesson} slides={len(slides)} duration={total:.1f}s")
    shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
