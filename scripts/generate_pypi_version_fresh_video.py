#!/usr/bin/env python3
"""Build a fresh PyPI version-number explainer video without Remotion."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/published/pypi-version.md"
OUT_DIR = ROOT / "artifacts/pypi_version_fresh_video"
WIDTH, HEIGHT = 1920, 1080
FPS = 24
VOICE = "zh-CN-YunxiNeural"

BG = (246, 248, 252)
PANEL = (255, 255, 255)
INK = (18, 24, 38)
MUTED = (86, 99, 120)
BORDER = (210, 220, 235)
NAVY = (16, 24, 39)
BLUE = (37, 99, 235)
TEAL = (13, 148, 136)
GREEN = (22, 163, 74)
AMBER = (217, 119, 6)
RED = (220, 38, 38)
VIOLET = (124, 58, 237)
CYAN = (8, 145, 178)
SLATE = (51, 65, 85)
YELLOW = (250, 204, 21)


@dataclass(frozen=True)
class Caption:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class Scene:
    key: str
    title: str
    start: float
    end: float
    accent: tuple[int, int, int]


NARRATION = """你在安装 Python 包时，pip 不是随便挑一个版本。
它会按照 PEP 440 的规则，先过滤候选，再选择排序上最大的可用版本。
所以一件看似简单的事，背后其实有一整套版本语义。
先看一个完整版本号。
PEP 440 把它分成两层：加号左边是 public version，右边是可选的 local version。
比如 2.1.0+cu118，公共版本是 2.1.0，本地版本是 cu118。
公共版本会进入 PyPI 的主要排序；本地版本通常留给私有源、重打包、硬件编译变体。
注意，公共 PyPI 不允许上传带加号本地版本的包。
公共版本本身又能拆成五个部件：epoch、release、pre、post、dev。
epoch 写成 N 加感叹号，最高优先级，通常只在版本方案推倒重来时使用。
release 就是最常见的 1.2.3；pre 是 a、b、rc；post 是发布后的非代码修订；dev 是开发快照。
排序规则里最容易踩坑的是：它不是字符串比较。
1.10 大于 1.9，因为 release 段按整数逐段比较；1.2 和 1.2.0 被看作相等，因为缺位会补零。
同一个 1.0 附近，顺序可以这样记：dev 最早，然后 alpha、beta、rc，再到正式版。
正式版之后是 post；带 local 的版本，比同号不带 local 的版本更大。
再看 pip 的默认行为。
final 和 post 默认可见，所以普通 pip install 会选它们里面最新的。
pre 和 dev 默认跳过，除非你写 --pre，或者精确指定版本。
这也是为什么 1.0rc1 已经上传了，普通用户还是装不到它。
四类版本各有分工。
dev 给 CI、nightly 和内部快照；pre 给灰度测试、早期用户和提前适配。
final 是正式交付；post 只用来修文档、元数据、漏文件这些发布层面问题。
如果修的是代码 bug，不要发 post，应该发下一个 patch，比如从 1.2.0 到 1.2.1。
一次典型发布会这样走：1.2.0.dev1，然后 a1、b1、rc1，最后到 1.2.0。
如果 README 写错，发 1.2.0.post1；如果代码出 bug，发 1.2.1。
最后记住六条实践建议。
正式发布用 final；发布前测试用 a、b、rc；post 不修代码；dev 交给自动化。
本地版本只放私有渠道；不要自创 1.0-test 这种格式，拿不准就用 packaging.version.Version 验证。
版本号设计得清楚，pip 的默认行为就会帮你把不同成熟度的版本分发给不同的人。
"""


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


F_LOGO = font(30, True)
F_HERO = font(72, True)
F_TITLE = font(54, True)
F_H2 = font(38, True)
F_BODY = font(31)
F_BODY_BOLD = font(31, True)
F_SMALL = font(23)
F_CODE = font(34, True)
F_CODE_SMALL = font(25, True)
F_CAPTION = font(33, True)


def edge_tts_exe() -> str:
    in_venv = Path(sys.executable).with_name("edge-tts")
    if in_venv.exists():
        return str(in_venv)
    found = shutil.which("edge-tts")
    if found:
        return found
    raise RuntimeError("edge-tts executable not found")


def run_tts(text_path: Path, audio_path: Path, vtt_path: Path) -> None:
    subprocess.run(
        [
            edge_tts_exe(),
            "--voice",
            VOICE,
            "--file",
            str(text_path),
            "--write-media",
            str(audio_path),
            "--write-subtitles",
            str(vtt_path),
        ],
        check=True,
    )


def parse_timecode(value: str) -> int:
    hh, mm, rest = value.replace(",", ".").split(":")
    ss, ms = rest.split(".")
    return int(hh) * 3_600_000 + int(mm) * 60_000 + int(ss) * 1000 + int(ms[:3].ljust(3, "0"))


def parse_vtt(path: Path) -> list[Caption]:
    text = path.read_text(encoding="utf-8")
    captions: list[Caption] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        idx = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if idx is None:
            continue
        start, end = [part.strip() for part in lines[idx].split("-->")]
        body = " ".join(lines[idx + 1 :]).strip()
        if body:
            captions.append(Caption(parse_timecode(start), parse_timecode(end), body))
    return captions


def duration(path: Path) -> float:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not match:
        return 0.0
    hh, mm, ss = match.groups()
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def mux(video_path: Path, audio_path: Path, out_path: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            str(out_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def make_offline_captions(text: str) -> list[Caption]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    captions: list[Caption] = []
    cursor = 0
    for line in lines:
        clean = re.sub(r"\s+", " ", line)
        seconds = max(2.4, min(6.8, len(clean) * 0.18))
        start = cursor
        end = start + int(seconds * 1000)
        captions.append(Caption(start, end, clean))
        cursor = end + 170
    return captions


def write_srt(captions: list[Caption], path: Path) -> None:
    def fmt(ms: int) -> str:
        hh, rem = divmod(ms, 3_600_000)
        mm, rem = divmod(rem, 60_000)
        ss, sub = divmod(rem, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{sub:03d}"

    blocks = []
    for i, caption in enumerate(captions, 1):
        blocks.append(f"{i}\n{fmt(caption.start_ms)} --> {fmt(caption.end_ms)}\n{caption.text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def make_scenes(captions: list[Caption]) -> list[Scene]:
    def t(index: int, fallback: float) -> float:
        return captions[index].start_ms / 1000 if 0 <= index < len(captions) else fallback

    return [
        Scene("hook", "pip install 到底在挑什么？", 0, t(4, 18), BLUE),
        Scene("split", "完整版本号先分两层", t(4, 18), t(9, 43), TEAL),
        Scene("parts", "公共版本号的 5 个部件", t(9, 43), t(13, 67), RED),
        Scene("ordering", "排序：不是字符串比较", t(13, 67), t(18, 94), VIOLET),
        Scene("pip", "pip 默认会跳过什么？", t(18, 94), t(23, 119), AMBER),
        Scene("types", "四类版本的分工", t(23, 119), t(27, 143), CYAN),
        Scene("timeline", "一次发布的正常演进", t(27, 143), t(30, 161), GREEN),
        Scene("checklist", "设计版本号的 6 条建议", t(30, 161), captions[-1].end_ms / 1000 + 1.0, BLUE),
    ]


def text_size(draw: ImageDraw.ImageDraw, text: str, ft: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=ft)
    return box[2] - box[0], box[3] - box[1]


def wrap(draw: ImageDraw.ImageDraw, text: str, ft: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [text]:
        line = ""
        for char in para:
            trial = line + char
            if text_size(draw, trial, ft)[0] <= max_width:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = char
        if line:
            lines.append(line)
    return lines


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: tuple[int, int, int], outline: tuple[int, int, int] = BORDER, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=8, fill=fill, outline=outline, width=width)


def draw_block(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, ft: ImageFont.ImageFont, fill: tuple[int, int, int], max_width: int, gap: int = 11) -> int:
    for line in wrap(draw, text, ft, max_width):
        draw.text((x, y), line, font=ft, fill=fill)
        y += ft.size + gap
    return y


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return 1 - (1 - value) ** 3


def blend(a: tuple[int, int, int], b: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * ratio) for i in range(3))


def canvas(scene: Scene, local: float, dark: bool = False) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    top = NAVY if dark else BG
    bottom = (30, 41, 59) if dark else (232, 239, 250)
    img = Image.new("RGB", (WIDTH, HEIGHT), top)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        draw.line((0, y, WIDTH, y), fill=blend(top, bottom, y / HEIGHT))
    bar = int(16 + 520 * ease(local / 1.2))
    draw.rectangle((0, 0, 18, bar), fill=scene.accent)
    fg = (248, 250, 252) if dark else INK
    sub = (203, 213, 225) if dark else MUTED
    draw.text((76, 52), "PyPI VERSION / PEP 440", font=F_LOGO, fill=scene.accent)
    draw.text((76, 104), scene.title, font=F_HERO, fill=fg)
    draw.text((WIDTH - 275, 66), "pip", font=F_TITLE, fill=sub)
    draw.line((76, 214, 720, 214), fill=scene.accent, width=5)
    return img, draw


def code_tag(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color: tuple[int, int, int], active: bool = True, small: bool = False) -> tuple[int, int, int, int]:
    ft = F_CODE_SMALL if small else F_CODE
    pad_x = 22 if small else 28
    pad_y = 13 if small else 16
    w, h = text_size(draw, text, ft)
    box = (x, y, x + w + pad_x * 2, y + h + pad_y * 2)
    fill = color if active else (71, 85, 105)
    rounded(draw, box, fill, outline=fill)
    draw.text((x + pad_x, y + pad_y - 3), text, font=ft, fill=(255, 255, 255))
    return box


def scene_hook(scene: Scene, local: float) -> Image.Image:
    img, draw = canvas(scene, local, dark=True)
    draw_block(draw, 98, 300, "同一个包有很多候选版本。pip 要做的是：选出“最新且允许安装”的那个。", F_H2, (226, 232, 240), 780)
    candidates = [("1.9", "旧版本"), ("1.10", "整数比较更大"), ("1.0rc1", "预发布，默认跳过"), ("1.0", "正式版，可见")]
    for i, (version, note) in enumerate(candidates):
        y = 292 + i * 116
        active = local > 2.2 + i * 1.6
        fill = BLUE if active else (30, 41, 59)
        rounded(draw, (1070, y, 1705, y + 86), fill, outline=(100, 116, 139), width=3 if active else 2)
        draw.text((1106, y + 20), version, font=F_CODE, fill=(255, 255, 255))
        draw.text((1362, y + 27), note, font=F_SMALL, fill=YELLOW if active else (203, 213, 225))
    code_tag(draw, 98, 540, "pip install requests", GREEN)
    draw.text((98, 652), "核心答案：PEP 440 定义了版本的含义和顺序。", font=F_H2, fill=(255, 255, 255))
    return img


def scene_split(scene: Scene, local: float) -> Image.Image:
    img, draw = canvas(scene, local)
    draw.text((116, 288), "例子：", font=F_H2, fill=INK)
    code_tag(draw, 250, 268, "2.1.0+cu118", scene.accent)
    draw.text((840, 300), "=", font=F_HERO, fill=INK)
    panels = [
        ("public version", "2.1.0", "PyPI 接受并参与主要排序", TEAL),
        ("local version", "cu118", "私有源、重打包、编译变体", BLUE),
    ]
    for i, (label, value, note, color) in enumerate(panels):
        x = 185 + i * 810
        rounded(draw, (x, 455, x + 690, 735), PANEL, outline=blend(color, PANEL, 0.35), width=4)
        draw.text((x + 36, 498), label, font=F_H2, fill=color)
        draw.text((x + 36, 570), value, font=F_HERO, fill=INK)
        draw.text((x + 36, 665), note, font=F_BODY, fill=MUTED)
    rounded(draw, (300, 820, 1620, 910), PANEL, outline=RED, width=4)
    draw.text((340, 844), "公共 PyPI 不允许上传带 +local 的包。", font=F_H2, fill=INK)
    return img


def scene_parts(scene: Scene, local: float) -> Image.Image:
    img, draw = canvas(scene, local)
    parts = [
        ("epoch", "1!", "方案重启", RED),
        ("release", "1.2.3", "核心版本", BLUE),
        ("pre", "rc1", "预发布", VIOLET),
        ("post", ".post1", "发布后修订", AMBER),
        ("dev", ".dev2", "开发快照", GREEN),
    ]
    for i, (label, example, note, color) in enumerate(parts):
        x = 90 + i * 356
        rounded(draw, (x, 310, x + 312, 665), PANEL, outline=BORDER)
        draw.rectangle((x, 310, x + 312, 324), fill=color)
        draw.text((x + 26, 368), label, font=F_H2, fill=color)
        draw.text((x + 26, 458), example, font=F_CODE, fill=INK)
        draw_block(draw, x + 26, 560, note, F_BODY, MUTED, 250)
    rounded(draw, (260, 780, 1660, 880), NAVY, outline=NAVY)
    draw.text((314, 811), "[N!]N(.N)*[{a|b|rc}N][.postN][.devN]", font=F_CODE, fill=(255, 255, 255))
    return img


def scene_ordering(scene: Scene, local: float) -> Image.Image:
    img, draw = canvas(scene, local, dark=True)
    rounded(draw, (100, 298, 850, 710), (15, 23, 42), outline=(71, 85, 105))
    draw.text((138, 340), "Release 段按整数逐段比较", font=F_H2, fill=(219, 234, 254))
    code_tag(draw, 150, 450, "1.10", GREEN)
    draw.text((386, 455), ">", font=F_HERO, fill=(255, 255, 255))
    code_tag(draw, 505, 450, "1.9", BLUE)
    code_tag(draw, 150, 570, "1.2", BLUE)
    draw.text((386, 575), "=", font=F_HERO, fill=(255, 255, 255))
    code_tag(draw, 505, 570, "1.2.0", BLUE)

    rounded(draw, (970, 298, 1825, 710), (15, 23, 42), outline=(71, 85, 105))
    draw.text((1010, 340), "同一个 1.0 的顺序", font=F_H2, fill=(219, 234, 254))
    chain = [("1.0.dev1", GREEN), ("1.0a1", VIOLET), ("1.0b1", VIOLET), ("1.0rc1", VIOLET), ("1.0", BLUE), ("1.0.post1", AMBER), ("1.0+local", CYAN)]
    x, y = 1010, 438
    for idx, (label, color) in enumerate(chain):
        active = local > idx * 0.9
        box = code_tag(draw, x, y, label, color, active=active, small=True)
        x = box[2] + 14
        if x > 1660:
            x, y = 1010, y + 84
    draw.text((120, 800), "记忆法：dev 最早，pre 在正式版之前，post 在正式版之后。", font=F_H2, fill=(255, 255, 255))
    return img


def scene_pip(scene: Scene, local: float) -> Image.Image:
    img, draw = canvas(scene, local)
    rows = [
        ("final", "1.0", "默认可见", GREEN),
        ("post", "1.0.post1", "默认可见", GREEN),
        ("pre", "1.0rc1", "默认跳过", RED),
        ("dev", "1.0.dev1", "默认跳过", RED),
    ]
    for i, (kind, example, status, color) in enumerate(rows):
        y = 310 + i * 128
        rounded(draw, (210, y, 1710, y + 92), PANEL, outline=BORDER)
        draw.text((250, y + 25), kind, font=F_H2, fill=color)
        draw.text((520, y + 25), example, font=F_CODE, fill=INK)
        draw.text((1040, y + 26), status, font=F_BODY_BOLD, fill=color)
        if "跳过" in status:
            draw.text((1310, y + 29), "需要 --pre 或精确指定", font=F_SMALL, fill=MUTED)
    rounded(draw, (330, 845, 1590, 930), NAVY, outline=NAVY)
    draw.text((370, 869), "所以：上传了 1.0rc1，不代表普通用户会自动安装它。", font=F_H2, fill=(255, 255, 255))
    return img


def scene_types(scene: Scene, local: float) -> Image.Image:
    img, draw = canvas(scene, local)
    cards = [
        ("dev", "1.0.dev1", "CI / nightly / 内部快照", GREEN),
        ("pre", "1.0a1 / b1 / rc1", "灰度测试、提前适配", VIOLET),
        ("final", "1.0", "正式、稳定、普通用户", BLUE),
        ("post", "1.0.post1", "文档、元数据、漏文件", AMBER),
    ]
    for i, (name, example, usage, color) in enumerate(cards):
        x = 96 + i * 454
        rounded(draw, (x, 310, x + 405, 760), PANEL, outline=BORDER)
        rounded(draw, (x + 28, 346, x + 128, 446), color, outline=color)
        draw.text((x + 49, 374), name, font=F_CODE_SMALL, fill=(255, 255, 255))
        draw_block(draw, x + 28, 500, example, F_CODE_SMALL if len(example) > 12 else F_CODE, INK, 340)
        draw_block(draw, x + 28, 620, usage, F_BODY, MUTED, 330)
    draw.text((125, 846), "修代码 bug：发新的 patch，例如 1.2.1；不要用 post 混过去。", font=F_H2, fill=RED)
    return img


def scene_timeline(scene: Scene, local: float) -> Image.Image:
    img, draw = canvas(scene, local, dark=True)
    items = [
        ("1.2.0.dev1", "内部构建", GREEN),
        ("1.2.0a1", "内测", VIOLET),
        ("1.2.0b1", "公测", VIOLET),
        ("1.2.0rc1", "候选", VIOLET),
        ("1.2.0", "正式", BLUE),
        ("1.2.0.post1", "非代码修正", AMBER),
        ("1.2.1", "代码修复", RED),
    ]
    y = 540
    draw.line((145, y, 1785, y), fill=(71, 85, 105), width=8)
    progress = ease(local / max(1.0, scene.end - scene.start - 0.5))
    draw.line((145, y, 145 + int(1640 * progress), y), fill=scene.accent, width=8)
    for i, (version, note, color) in enumerate(items):
        x = 145 + i * 273
        active = progress + 0.01 >= i / (len(items) - 1)
        draw.ellipse((x - 24, y - 24, x + 24, y + 24), fill=color if active else (71, 85, 105), outline=NAVY, width=7)
        draw.text((x - 76, y - 136), note, font=F_SMALL, fill=(226, 232, 240))
        code_tag(draw, x - 105, y + 60, version, color, active=active, small=True)
    return img


def scene_checklist(scene: Scene, local: float) -> Image.Image:
    img, draw = canvas(scene, local)
    tips = [
        "正式发布用 final：1.2.3",
        "发布前测试用 a / b / rc",
        "post 只修发布层面问题",
        "dev 交给 CI 和 nightly",
        "+local 留在私有渠道",
        "不要自创版本格式",
    ]
    for i, tip in enumerate(tips):
        col, row = i % 2, i // 2
        x, y = 165 + col * 800, 300 + row * 158
        rounded(draw, (x, y, x + 695, y + 112), PANEL, outline=BORDER)
        rounded(draw, (x + 24, y + 26, x + 82, y + 84), scene.accent, outline=scene.accent)
        draw.text((x + 42, y + 36), str(i + 1), font=F_SMALL, fill=(255, 255, 255))
        draw_block(draw, x + 112, y + 30, tip, F_BODY_BOLD, INK, 545)
    rounded(draw, (270, 840, 1650, 928), NAVY, outline=NAVY)
    draw.text((310, 866), "版本号是在向使用者传递稳定性承诺。", font=F_H2, fill=(255, 255, 255))
    return img


def render_scene(scene: Scene, local: float) -> Image.Image:
    return {
        "hook": scene_hook,
        "split": scene_split,
        "parts": scene_parts,
        "ordering": scene_ordering,
        "pip": scene_pip,
        "types": scene_types,
        "timeline": scene_timeline,
        "checklist": scene_checklist,
    }[scene.key](scene, local)


def active_scene(scenes: list[Scene], t: float) -> Scene:
    for scene in scenes:
        if scene.start <= t < scene.end:
            return scene
    return scenes[-1]


def active_caption(captions: list[Caption], t: float) -> Caption | None:
    ms = int(t * 1000)
    for caption in captions:
        if caption.start_ms <= ms < caption.end_ms:
            return caption
    return None


def draw_caption(img: Image.Image, caption: Caption | None, t: float, total: float) -> None:
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, HEIGHT - 10, int(WIDTH * min(1.0, t / total)), HEIGHT), fill=GREEN)
    if caption is None:
        return
    x1, y1, x2, y2 = 255, 905, WIDTH - 255, 1028
    rounded(draw, (x1, y1, x2, y2), NAVY, outline=(71, 85, 105))
    lines = wrap(draw, caption.text, F_CAPTION, x2 - x1 - 90)[:2]
    yy = y1 + 26 if len(lines) == 2 else y1 + 42
    for line in lines:
        w, _ = text_size(draw, line, F_CAPTION)
        draw.text((x1 + (x2 - x1 - w) // 2, yy), line, font=F_CAPTION, fill=(255, 255, 255))
        yy += 44


def render_video(captions: list[Caption], scenes: list[Scene], silent_path: Path, frames_dir: Path) -> None:
    total = scenes[-1].end
    total_frames = math.ceil(total * FPS)
    snapshots = {0, int(total_frames * 0.16), int(total_frames * 0.36), int(total_frames * 0.58), int(total_frames * 0.78), total_frames - 1}
    writer = imageio.get_writer(silent_path, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    try:
        for frame_no in range(total_frames):
            t = frame_no / FPS
            scene = active_scene(scenes, t)
            img = render_scene(scene, t - scene.start)
            draw_caption(img, active_caption(captions, t), t, total)
            if frame_no in snapshots:
                img.save(frames_dir / f"frame_{frame_no:05d}.png")
            writer.append_data(np.asarray(img))
    finally:
        writer.close()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(exist_ok=True)

    source = SOURCE.read_text(encoding="utf-8")
    (OUT_DIR / "source.md").write_text(source, encoding="utf-8")
    narration_path = OUT_DIR / "narration.txt"
    srt_path = OUT_DIR / "captions.srt"
    final_path = OUT_DIR / "pypi_version_fresh_explainer.mp4"

    narration_path.write_text(NARRATION, encoding="utf-8")
    captions = make_offline_captions(NARRATION)
    if not captions:
        raise RuntimeError("No captions generated")

    write_srt(captions, srt_path)
    scenes = make_scenes(captions)
    (OUT_DIR / "storyboard.json").write_text(
        json.dumps([scene.__dict__ | {"accent": scene.accent} for scene in scenes], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "captions.json").write_text(
        json.dumps([caption.__dict__ for caption in captions], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    render_video(captions, scenes, final_path, frames_dir)

    print(final_path)
    print(srt_path)
    print(f"duration={scenes[-1].end:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
