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
from functools import lru_cache
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
CONTENT_BOTTOM = 840
CONTENT_W = WIDTH - CONTENT_X - 96


@lru_cache(maxsize=None)
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


def code_visual_lines(value: str, code_font: ImageFont.FreeTypeFont = F_CODE) -> list[str]:
    lines: list[str] = []
    for raw in value.splitlines() or [""]:
        lines.extend(wrap(_DUMMY, raw or " ", code_font, CONTENT_W - 44))
    return lines


def block_height(block: Block) -> int:
    if block.kind == "code":
        n = len(code_visual_lines(block.text)) or 1
        return 28 + n * (F_CODE.size + 12) + 24
    if block.kind == "quote":
        lines = wrap(_DUMMY, strip_md(block.text), F_QUOTE, CONTENT_W - 60)
        return 24 + len(lines) * (F_QUOTE.size + 12) + 22
    if block.kind == "item":
        lines = wrap(_DUMMY, strip_md(block.text), F_BODY, CONTENT_W - 60)
        return len(lines) * (F_BODY.size + 12) + 14
    lines = wrap(_DUMMY, strip_md(block.text), F_BODY, CONTENT_W)
    return len(lines) * (F_BODY.size + 12) + 18


def split_oversized_block(block: Block, avail: int) -> list[Block]:
    if block_height(block) <= avail:
        return [block]
    if block.kind == "code":
        visual_lines = code_visual_lines(block.text)
        max_lines = max(1, (avail - 52) // (F_CODE.size + 12))
        return [
            Block("code", "\n".join(visual_lines[i:i + max_lines]))
            for i in range(0, len(visual_lines), max_lines)
        ]

    parts: list[Block] = []
    current = ""
    for ch in block.text:
        candidate = Block(block.kind, current + ch)
        if current and block_height(candidate) > avail:
            parts.append(Block(block.kind, current.rstrip()))
            current = ch.lstrip()
        else:
            current += ch
    if current:
        parts.append(Block(block.kind, current.rstrip()))
    return parts


def paginate(blocks: list[Block]) -> list[list[Block]]:
    pages: list[list[Block]] = []
    cur: list[Block] = []
    h = 0
    avail = CONTENT_BOTTOM - CONTENT_TOP
    fitted = [part for block in blocks for part in split_oversized_block(block, avail)]
    for b in fitted:
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


def paginate_locked_narration(blocks: list[Block]) -> list[list[Block]]:
    """Reproduce the semantic pages used by an existing hand-edited narration.

    Older narration files were prepared before oversized blocks were split for
    rendering. Keep those blocks on their original semantic screen; the
    renderer handles fitting them or replaces them with a lesson visual.
    """
    pages: list[list[Block]] = []
    cur: list[Block] = []
    height = 0
    avail = CONTENT_BOTTOM - CONTENT_TOP
    for block in blocks:
        if block.kind == "code":
            block_h = 28 + max(1, len(block.text.splitlines())) * (F_CODE.size + 12) + 24
        else:
            block_h = block_height(block)
        if cur and height + block_h > avail:
            pages.append(cur)
            cur = [block]
            height = block_h
        else:
            cur.append(block)
            height += block_h
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
    is_reveal: bool = False        # 本页是否是「揭晓答案」quote 起始的页（用于互动题定位插入点）
    media: Path | None = None      # 可选课程配图；用于长代码/流程等更适合图示的画面


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


def build_slides(title: str, sections: list[Section], locked: bool = False) -> list[Slide]:
    """把每节内容分页成幻灯片。

    如果某一节内含「揭晓」类 quote 块（我们系列里「先预测/先猜猜看之后揭晓答案」的写法），
    且该节之后会插入互动题（quiz.txt 里 after 命中该节），揭晓前的内容和揭晓本身必须分开
    成两页，否则答案会在题目出现前就被读出来/秀在屏幕上。这里统一按「quote 块开头是揭晓」
    做切分，不管有没有配 quiz，保持行为一致、可预期。
    """
    slides: list[Slide] = []
    for si, sec in enumerate(sections):
        accent = ACCENTS[si % len(ACCENTS)]
        pages = paginate_locked_narration(sec.blocks) if locked else paginate(sec.blocks)
        # 展开：若某页内部存在「揭晓」quote，从该 quote 前把这一页切成两页。
        split_pages: list[list[Block]] = []
        for page in pages:
            reveal_idx = next(
                (i for i, b in enumerate(page) if b.kind == "quote" and strip_md(b.text).lstrip().startswith("揭晓")),
                -1,
            )
            if reveal_idx > 0:
                split_pages.append(page[:reveal_idx])
                split_pages.append(page[reveal_idx:])
            else:
                split_pages.append(page)
        for pi, page in enumerate(split_pages):
            narr = " ".join(x for x in (speakable(b) for b in page) if x)
            if not narr:
                narr = sec.title
            head = sec.title if pi == 0 else sec.title + "（续）"
            is_reveal = bool(page) and page[0].kind == "quote" and strip_md(page[0].text).lstrip().startswith("揭晓")
            slides.append(Slide(head, page, accent, narr, is_reveal=is_reveal))
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
        if cur and cur.get("question") and cur.get("opts"):
            options = [f"{ltr}. {txt}".rstrip() for ltr, txt in cur["opts"]]
            quizzes.append(Quiz(
                anchor=cur.get("after", ""),
                question=cur["question"].strip(),
                options=options,
                answer=cur.get("answer", "").strip().upper(),
                explain=cur.get("explain", "").strip(),
                pause=float((cur.get("pause", "4") or "4").strip()),
            ))

    keyre = re.compile(r"^([A-Ea-e]|after|question|answer|explain|pause)\s*[:：]\s*(.*)$")
    last = None  # ("opt", idx) 或 ("field", name)
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s.startswith("#"):
            continue
        if s.startswith("[[quiz]]"):
            flush()
            cur = {"opts": []}
            last = None
            continue
        if cur is None:
            continue
        mk = keyre.match(s)
        if mk:
            k, v = mk.group(1).lower(), mk.group(2)
            if k in ("a", "b", "c", "d", "e"):
                cur["opts"].append([k.upper(), v])
                last = ("opt", len(cur["opts"]) - 1)
            else:
                cur[k] = v
                last = ("field", k)
            continue
        # 续行：接到上一个字段/选项（支持多行选项、多行题干/解析）
        if not s or last is None:
            continue
        if last[0] == "opt":
            i = last[1]
            cur["opts"][i][1] = (cur["opts"][i][1] + "\n" + s).strip("\n")
        else:
            cur[last[1]] = (cur.get(last[1], "") + "\n" + s).strip("\n")
    flush()
    return quizzes


def make_silence(seconds: float, out: Path) -> Path:
    subprocess.run(
        [ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=mono", "-t", f"{seconds:.2f}", "-q:a", "9", str(out)],
        check=True,
    )
    return out


def break_narration(text: str, limit: int = 34) -> str:
    """Keep generated caption lines within the course subtitle width."""
    lines: list[str] = []
    for raw in text.splitlines():
        value = raw.strip()
        while len(value) > limit:
            cut = max(
                (i + 1 for i, ch in enumerate(value[:limit])
                 if ch.isspace() or ch in "，。；：！？、,;:!?"),
                default=limit,
            )
            lines.append(value[:cut].strip())
            value = value[cut:].strip()
        if value:
            lines.append(value)
    return "\n".join(lines)


def insert_quiz_slides(slides: list[Slide], quizzes: list[Quiz]) -> list[Slide]:
    """按 anchor 把每道题的「出题屏 + 揭晓屏」插到对应小节之后。

    若锚点小节内含「揭晓」页（先预测/We-do 类写法在文中自带答案揭晓），插入点必须停在
    揭晓页之前，否则文章画面和朗读会先把答案说穿，题目就失去意义了。没有揭晓页的小节，
    仍然跨过其所有「（续）」分页，插到整节之后（维持原行为）。
    """
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
                   and base(slides[idx + 1].title) == base(slides[start].title)
                   and not slides[idx + 1].is_reveal):
                idx += 1  # 跨过该节的「（续）」分页，但绝不跨过揭晓页

            # 互动题的答案屏已经承担揭晓，不再保留文章中重复的纯揭晓页。
            reveal_idx = idx + 1
            if (reveal_idx < len(slides)
                    and slides[reveal_idx].kind == "content"
                    and base(slides[reveal_idx].title) == base(slides[start].title)
                    and slides[reveal_idx].is_reveal):
                reveal = slides[reveal_idx]
                remaining = [
                    block for block in reveal.blocks
                    if not (block.kind == "quote"
                            and strip_md(block.text).lstrip().startswith("揭晓"))
                ]
                if remaining:
                    reveal.blocks = remaining
                    reveal.is_reveal = False
                    reveal.narration = " ".join(
                        value for value in (speakable(block) for block in remaining) if value
                    ) or reveal.title
                else:
                    slides.pop(reveal_idx)
        q_slide = Slide(
            title="先猜猜看", blocks=[], accent=(217, 140, 20),
            narration=break_narration(f"{q.question}\n请看屏幕选项，想一想。"),
            kind="quiz_q", options=q.options, answer=q.answer,
            question=q.question, explain=q.explain, pause=q.pause,
        )
        ans_read = q.explain or f"正确答案是 {q.answer}。"
        a_slide = Slide(
            title="揭晓答案", blocks=[], accent=(46, 160, 67),
            narration=break_narration(f"答案是 {q.answer}。\n{ans_read}"),
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
    """按 narration.txt 里的换行分屏：每一行 = 一屏字幕 + 一次配音停顿，不再自动按标点/长度重新切分。

    空行会被跳过（不占时长）。每屏时长按该行字数占比分配整段口播时长。
    """
    segs = [ln.strip() for ln in narr.split("\n")]
    segs = [s for s in segs if s]
    if not segs:
        segs = [narr.strip() or narr]
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



_MEDIA_CACHE: dict[Path, Image.Image] = {}


def attach_lesson_media(folder: Path, slides: list[Slide]) -> None:
    """Attach prepared lesson visuals to screens where raw text would be weaker."""
    if not folder.name.startswith("lesson-09-"):
        return
    image_dir = folder / "images"
    mapping = {
        0: "cover.png",
        4: "fig03_eight_lessons.png",
        5: "fig02_break_problem.png",
        9: "fig04_one_turn_pipeline.png",
        10: "fig04_one_turn_pipeline.png",
        13: "fig05_while_three_conditions.png",
        14: "fig05_while_three_conditions.png",
        17: "fig06_run_battle_log.png",
        19: "fig06_run_battle_log.png",
    }
    for index, name in mapping.items():
        path = image_dir / name
        if index < len(slides) and path.exists():
            slides[index].media = path


def render_media(img: Image.Image, draw: ImageDraw.ImageDraw, path: Path) -> None:
    visual = _MEDIA_CACHE.get(path)
    if visual is None:
        visual = Image.open(path).convert("RGB")
        visual.thumbnail((CONTENT_W, CONTENT_BOTTOM - CONTENT_TOP), Image.Resampling.LANCZOS)
        _MEDIA_CACHE[path] = visual
    x = CONTENT_X + (CONTENT_W - visual.width) // 2
    y = CONTENT_TOP + (CONTENT_BOTTOM - CONTENT_TOP - visual.height) // 2
    rounded(draw, (x - 6, y - 6, x + visual.width + 6, y + visual.height + 6),
            PANEL, outline=BORDER, width=2, radius=8)
    img.paste(visual, (x, y))

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
    opts = sl.options or []
    def opt_text(o):
        return o.split(".", 1)[1].strip() if "." in o else o
    multiline = any("\n" in opt_text(o) for o in opts)
    of = font(24) if multiline else F_BODY   # 多行/长选项用小字，避免超出画面
    for opt in opts:
        letter = opt[:1].upper()
        is_ans = reveal and letter == sl.answer
        card_w = CONTENT_W - 360
        wl = wrap(draw, opt_text(opt), of, card_w - 120)
        card_h = max(72, 20 + len(wl) * (of.size + 8))
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
        ty = y + max(16, (card_h - len(wl) * (of.size + 8)) // 2)
        for line in wl:
            draw.text((x + 92, ty), line, font=of, fill=INK)
            ty += of.size + 8
        if is_ans:
            draw.text((x + card_w - 56, y + 18), "✓", font=F_H2, fill=GREEN)
        y += card_h + 14
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


def _render_blocks_fixed(draw, blocks: list[Block], accent) -> None:
    y = CONTENT_TOP
    for b in blocks:
        if y > CONTENT_BOTTOM:
            break
        if b.kind == "code":
            code_lines = code_visual_lines(b.text)
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




def _adaptive_layout(blocks: list[Block], body_size: int):
    body_ft = font(body_size)
    quote_ft = font(body_size)
    code_ft = font(max(14, body_size - 4), True)
    body_gap = max(5, body_size // 3)
    code_gap = max(4, code_ft.size // 3)
    measured = []
    total = 0
    for block in blocks:
        text = strip_md(block.text)
        if block.kind == "code":
            lines = code_visual_lines(block.text, code_ft)
            height = len(lines) * (code_ft.size + code_gap) + 24
        elif block.kind == "quote":
            lines = wrap(_DUMMY, text, quote_ft, CONTENT_W - 60)
            height = len(lines) * (quote_ft.size + body_gap) + 24
        elif block.kind == "item":
            lines = wrap(_DUMMY, text, body_ft, CONTENT_W - 60)
            height = len(lines) * (body_ft.size + body_gap) + 8
        else:
            lines = wrap(_DUMMY, text, body_ft, CONTENT_W)
            height = len(lines) * (body_ft.size + body_gap) + 8
        measured.append((block, lines, height))
        total += height + 8
    return body_ft, quote_ft, code_ft, body_gap, code_gap, measured, total


_BLOCK_LAYOUT_CACHE: dict[tuple[tuple[str, str], ...], tuple] = {}


def render_blocks(draw, blocks: list[Block], accent) -> None:
    key = tuple((block.kind, block.text) for block in blocks)
    layout = _BLOCK_LAYOUT_CACHE.get(key)
    if layout is None:
        available = CONTENT_BOTTOM - CONTENT_TOP
        layout = _adaptive_layout(blocks, 16)
        for size in range(F_BODY.size, 15, -2):
            candidate = _adaptive_layout(blocks, size)
            layout = candidate
            if candidate[-1] <= available:
                break
        _BLOCK_LAYOUT_CACHE[key] = layout

    body_ft, quote_ft, code_ft, body_gap, code_gap, measured, _ = layout
    y = CONTENT_TOP
    for block, lines, height in measured:
        if block.kind == "code":
            rounded(draw, (CONTENT_X, y, CONTENT_X + CONTENT_W, y + height),
                    CODE_BG, outline=BORDER, width=2, radius=8)
            line_y = y + 12
            for line in lines:
                draw.text((CONTENT_X + 22, line_y), line, font=code_ft, fill=INK)
                line_y += code_ft.size + code_gap
        elif block.kind == "quote":
            draw.rectangle((CONTENT_X, y, CONTENT_X + 6, y + height), fill=accent)
            line_y = y + 12
            for line in lines:
                draw.text((CONTENT_X + 28, line_y), line, font=quote_ft, fill=MUTED)
                line_y += quote_ft.size + body_gap
        elif block.kind == "item":
            radius = max(5, body_ft.size // 5)
            draw.ellipse((CONTENT_X + 8, y + body_ft.size // 3,
                          CONTENT_X + 8 + radius * 2, y + body_ft.size // 3 + radius * 2),
                         fill=accent)
            line_y = y
            for line in lines:
                draw.text((CONTENT_X + 44, line_y), line, font=body_ft, fill=INK)
                line_y += body_ft.size + body_gap
        else:
            line_y = y
            for line in lines:
                draw.text((CONTENT_X, line_y), line, font=body_ft, fill=INK)
                line_y += body_ft.size + body_gap
        y += height + 8
def draw_caption(img, cap, t, total, accent):
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, HEIGHT - 8, int(WIDTH * min(1.0, t / total)), HEIGHT), fill=accent)
    if cap is None:
        return
    x1, y1, x2, y2 = 72, 866, WIDTH - 72, 1004
    rounded(draw, (x1, y1, x2, y2), (252, 253, 249), outline=accent, width=3, radius=10)
    caption_font = F_CAPTION
    lines = wrap(draw, cap.text, caption_font, x2 - x1 - 96)
    for size in range(F_CAPTION.size - 1, 17, -1):
        if len(lines) <= 2:
            break
        caption_font = font(size, True)
        lines = wrap(draw, cap.text, caption_font, x2 - x1 - 96)
    line_gap = 10
    text_h = len(lines) * caption_font.size + max(0, len(lines) - 1) * line_gap
    yy = y1 + (y2 - y1 - text_h) // 2
    for line in lines:
        w, _ = tsize(draw, line, caption_font)
        draw.text((x1 + (x2 - x1 - w) // 2, yy), line, font=caption_font, fill=INK)
        yy += caption_font.size + line_gap


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

    - 若 folder/narration.txt 存在且其分块标题与当前幻灯片一一对应：按块覆盖各页 narration
      （尊重你的标点/换行调整）。
    - 若不存在，或文章改动导致分页/标题与朗读稿对不上：用当前文章重新生成朗读稿
      （旧稿备份为 narration.txt.bak），避免错位。
    返回 "created" | "loaded" | "refreshed"。
    """
    path = folder / "narration.txt"

    def write_fresh() -> None:
        header = [
            "# 讲解朗读稿（配音与字幕都来自这里；不影响公众号文章正文）。",
            "# 改标点、加换行即可调整配音停顿与字幕断句：换行 = 一次停顿 + 一次断句。",
            "# 每个 ### 块对应视频里的一页，标题与顺序请勿改动（改文章后本文件会自动重建）。",
            "",
        ]
        for i, sl in enumerate(slides):
            header.append(f"### {i + 1} | {sl.title}")
            header.append(break_narration(sl.narration))
            header.append("")
        path.write_text("\n".join(header), encoding="utf-8")

    if not path.exists():
        write_fresh()
        return "created"

    # 解析已有朗读稿：每块 (标题, 正文)
    titles: list[str] = []
    texts: list[str] = []
    cur: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            if cur is not None:
                texts.append("\n".join(cur).strip())
            head = line[4:].strip()
            titles.append(head.split("|", 1)[1].strip() if "|" in head else head)
            cur = []
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        texts.append("\n".join(cur).strip())

    # 陈旧检测：不自动覆盖手工编辑过的朗读稿。
    expected = [sl.title for sl in slides]
    if titles != expected:
        raise SystemExit(
            f"narration.txt 与当前分页不一致：朗读稿 {len(titles)} 页，画面 {len(expected)} 页。"
            "请先迁移朗读稿；为保护手工修改，文件未被覆盖。"
        )

    for i, b in enumerate(texts):
        if i < len(slides):
            slides[i].narration = b
    return "loaded"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, required=True)
    ap.add_argument("--vertical", action="store_true", help="额外输出 9:16 竖屏版")
    ap.add_argument("--narration-only", action="store_true", help="只生成/更新朗读稿 narration.txt，不渲染视频")
    ap.add_argument("--check-narration", action="store_true", help="逐屏对照“画面实际内容”和“narration.txt 里的朗读文字”，不渲染视频")
    args = ap.parse_args()

    folder, article_path = find_lesson(args.lesson)
    corner = folder.name.split("-", 2)[-1] if "-" in folder.name else folder.name
    title, sections = parse_article(article_path.read_text(encoding="utf-8"))
    if not sections:
        raise SystemExit("文章解析后没有可用内容")
    narr_path = folder / "narration.txt"
    slides = build_slides(title, sections)
    if narr_path.exists():
        narration_titles = []
        for line in narr_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("### "):
                heading = line[4:].strip()
                narration_titles.append(heading.split("|", 1)[1].strip() if "|" in heading else heading)
        if narration_titles != [slide.title for slide in slides]:
            locked_slides = build_slides(title, sections, locked=True)
            if narration_titles == [slide.title for slide in locked_slides]:
                slides = locked_slides
                print(f"（按现有 narration.txt 锁定为 {len(slides)} 个内容画面）", flush=True)

    narr_state = load_or_init_narration(folder, slides)
    attach_lesson_media(folder, slides)
    if args.narration_only:
        tip = {"created": "已生成", "loaded": "已存在"}[narr_state]
        print(f"朗读稿{tip}：{narr_path}")
        print("在其中改标点/加换行调整配音停顿与字幕断句，然后重新运行（不加 --narration-only）渲染。")
        print("手动改完内容后，先跑一次 --check-narration 核对最终画面顺序。")
        return 0
    if narr_state == "created":
        print(f"（已生成可编辑朗读稿：{narr_path}，本次先用默认稿渲染；想微调停顿就编辑它再重跑）")

    # 互动题必须先插入，再按最终屏幕顺序检查或渲染。
    quizzes = load_quiz(folder)
    slides = insert_quiz_slides(slides, quizzes)
    if quizzes:
        print(f"（已插入 {len(quizzes)} 道互动题：弹选项 + 倒计时 + 揭晓）", flush=True)

    if args.check_narration:
        print(f"朗读稿已存在：{narr_path}\n")
        print("逐屏核对：画面是最终视频实际显示的内容，朗读同时用于配音和字幕。\n")
        for i, sl in enumerate(slides):
            if sl.kind == "quiz_q":
                screen_text = sl.question + " / " + " / ".join(sl.options or [])
            elif sl.kind == "quiz_a":
                screen_text = f"答案 {sl.answer} / {sl.explain}"
            else:
                screen_text = " / ".join(b.text.replace("\n", " ") for b in sl.blocks) or "(无正文，仅标题)"
                if sl.media:
                    screen_text = f"配图 {sl.media.name} / {screen_text}"
            print(f"--- 第 {i + 1} 屏 | {sl.kind} | {sl.title} ---")
            print(f"  画面：{screen_text[:240]}")
            print(f"  朗读：{sl.narration[:240]}")
            print()
        return 0

    workdir = Path(tempfile.mkdtemp(prefix="kidvid_"))
    audio_parts: list[Path] = []
    pron = load_pron()
    dur_pairs: list[tuple[float, float]] = []  # (整屏时长, 口播时长)
    print(f"[1/3] 合成配音（共 {len(slides)} 段）…", flush=True)
    for i, sl in enumerate(slides):
        ap_i = workdir / f"a{i:03d}.mp3"
        if sl.narration.strip():
            tts(apply_pron(sl.narration, pron), ap_i)
        else:
            make_silence(4.0, ap_i)
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
        if sl.narration.strip():
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
                if sl.media:
                    render_media(img, draw, sl.media)
                else:
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
