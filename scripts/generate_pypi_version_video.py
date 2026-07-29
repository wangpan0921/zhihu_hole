#!/usr/bin/env python3
"""Generate a narrated PyPI version explainer video without Remotion."""

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


OUT_DIR = Path("artifacts/pypi_version_video")
SOURCE = Path("docs/published/pypi-version.md")
WIDTH, HEIGHT = 1920, 1080
FPS = 24
VOICE = "zh-CN-YunxiNeural"

INK = (17, 24, 39)
MUTED = (82, 96, 113)
PAPER = (248, 250, 252)
WHITE = (255, 255, 255)
LINE = (215, 222, 233)
BLUE = (47, 109, 246)
GREEN = (16, 163, 127)
RED = (229, 72, 77)
PURPLE = (168, 85, 247)
AMBER = (245, 158, 11)
CYAN = (6, 182, 212)
LIME = (132, 204, 22)
DARK = (15, 23, 42)
YELLOW = (251, 191, 36)


@dataclass(frozen=True)
class Caption:
    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Scene:
    key: str
    title: str
    eyebrow: str
    start: float
    end: float
    accent: tuple[int, int, int]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for item in candidates:
        if item and Path(item).exists():
            return ImageFont.truetype(item, size)
    return ImageFont.load_default()


F_HERO = font(76, True)
F_TITLE = font(58, True)
F_H2 = font(40, True)
F_BODY = font(31)
F_BODY_BOLD = font(31, True)
F_SMALL = font(24)
F_CODE = font(34, True)
F_CODE_SMALL = font(26, True)
F_CAPTION = font(34, True)


NARRATION = """每次你运行 pip install，pip 都要在一堆版本里挑一个装给你。
它为什么知道 1.10 比 1.9 新？
为什么 1.0rc1 默认不会被装上？
答案都在 Python 打包生态的版本规范：PEP 440。
先看整体结构。
一个完整版本号可以拆成公共版本和本地版本，中间用加号分隔。
加号左边，例如 1.4.2，是公共版本号，是 PyPI 能接受并参与排序的核心。
加号右边，例如 cpu、cu118、companyfix.1，是本地版本号。
注意，公共 PyPI 禁止上传带本地版本的包。
它主要给私有源、内网重打包、硬件编译变体使用。
公共版本号本身，又可以按顺序拆成 epoch、release、pre、post 和 dev。
epoch 像逃生舱，只有版本方案推倒重来时才需要；release 是最常见的 1.2.3。
pre 表示 alpha、beta、rc 这些预发布；post 是正式发布后的非代码修订；dev 是最早的开发快照。
排序时，pip 不是按字符串比，而是按 PEP 440 的语义逐段比较。
所以 1.10 大于 1.9，因为十真的大于九；1.2 和 1.2.0 则被看成相等。
同一个 1.0 下面，直觉链是：dev 最早，alpha、beta、rc 依次接近正式版。
然后是 1.0 正式版，post 排在它之后，而 local 比同号不带 local 的版本更大。
四类版本的使用场景也很明确。
dev 给 CI 和 nightly，pre 给灰度测试和提前适配。
final 是普通用户默认拿到的稳定版本；post 只修 README、元数据、漏文件这类发布层面问题。
一次典型发布会从 1.2.0.dev1 开始，进入 alpha、beta、rc，最后到 1.2.0。
如果只是文档写错，可以发 1.2.0.post1；如果修了代码 bug，就应该发 1.2.1。
记住这六条：final 正式交付，pre 做测试，post 不修代码，dev 交给自动化，local 留在私有渠道，不自创奇怪格式。
"""


def edge_tts_path() -> str:
    venv_tool = Path(sys.executable).with_name("edge-tts")
    if venv_tool.exists():
        return str(venv_tool)
    found = shutil.which("edge-tts")
    if found:
        return found
    raise RuntimeError("edge-tts executable not found")


def generate_voiceover(text_path: Path, audio_path: Path, vtt_path: Path) -> None:
    cmd = [
        edge_tts_path(),
        "--voice",
        VOICE,
        "--file",
        str(text_path),
        "--write-media",
        str(audio_path),
        "--write-subtitles",
        str(vtt_path),
    ]
    subprocess.run(cmd, check=True)


def parse_timecode(value: str) -> int:
    h, m, rest = value.replace(",", ".").split(":")
    s, ms = rest.split(".")
    return int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1000 + int(ms[:3].ljust(3, "0"))


def parse_vtt(path: Path) -> list[Caption]:
    text = path.read_text(encoding="utf-8")
    captions: list[Caption] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            continue
        start, end = [part.strip() for part in lines[time_index].split("-->")]
        body = " ".join(lines[time_index + 1 :]).strip()
        if body:
            captions.append(Caption(body, parse_timecode(start), parse_timecode(end)))
    return captions


def ffmpeg_duration(path: Path) -> float:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not match:
        return 0.0
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def ffmpeg_mux(video: Path, audio: Path, output: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        str(output),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def make_scenes(captions: list[Caption]) -> list[Scene]:
    def t(index: int, fallback: float) -> float:
        if 0 <= index < len(captions):
            return captions[index].start_ms / 1000
        return fallback

    end = captions[-1].end_ms / 1000 + 1.4
    return [
        Scene("hook", "pip 怎么判断版本新旧？", "PyPI 版本号科普", 0, t(4, 16.8), BLUE),
        Scene("structure", "一个版本号，先拆成两层", "public version + local version", t(4, 16.8), t(10, 48.2), GREEN),
        Scene("public", "公共版本号的五个部件", "PEP 440 public version", t(10, 48.2), t(13, 71.9), RED),
        Scene("sorting", "排序不是按字符串", "version ordering", t(13, 71.9), t(17, 99.7), PURPLE),
        Scene("types", "四类版本，各有分工", "dev / pre / final / post", t(17, 99.7), t(20, 116.5), AMBER),
        Scene("timeline", "一次典型发布怎样演进？", "from nightly to patch", t(20, 116.5), t(22, 131.7), CYAN),
        Scene("advice", "给发布者的 6 条建议", "practical checklist", t(22, 131.7), end, LIME),
    ]


def draw_round(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: tuple[int, int, int], outline: tuple[int, int, int] = LINE, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=8, fill=fill, outline=outline, width=width)


def text_width(draw: ImageDraw.ImageDraw, text: str, ft: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=ft)
    return box[2] - box[0]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, ft: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        current = ""
        for ch in para:
            test = current + ch
            if text_width(draw, test, ft) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def draw_text_block(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, ft: ImageFont.ImageFont, fill: tuple[int, int, int], max_width: int, line_gap: int = 12) -> int:
    for line in wrap_text(draw, text, ft, max_width):
        draw.text((x, y), line, font=ft, fill=fill)
        y += ft.size + line_gap
    return y


def ease(progress: float) -> float:
    progress = max(0.0, min(1.0, progress))
    return 1 - pow(1 - progress, 3)


def blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def base(scene: Scene, local: float, dark: bool = False) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    bg = DARK if dark else PAPER
    img = Image.new("RGB", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        if dark:
            color = blend((15, 23, 42), (23, 37, 84), t * 0.55)
        else:
            color = blend((248, 250, 252), (232, 240, 254), t * 0.45)
        draw.line((0, y, WIDTH, y), fill=color)
    sweep = int(-220 + 220 * ease(local / 1.8))
    draw.rectangle((0, sweep, 12, HEIGHT), fill=scene.accent)
    fg = WHITE if dark else INK
    sub = (203, 213, 225) if dark else MUTED
    draw.text((88, 64), scene.eyebrow, font=F_SMALL, fill=scene.accent)
    draw.text((88, 112), scene.title, font=F_HERO, fill=fg)
    draw.line((88, 216, 640, 216), fill=scene.accent, width=5)
    draw.text((WIDTH - 430, 70), "PEP 440", font=F_TITLE, fill=sub)
    return img, draw


def code_pill(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, active: bool = True, accent: tuple[int, int, int] = BLUE, size: int = 34) -> tuple[int, int, int, int]:
    ft = F_CODE if size >= 32 else F_CODE_SMALL
    w = text_width(draw, text, ft) + 42
    h = 64 if size >= 32 else 50
    fill = accent if active else DARK
    draw_round(draw, (x, y, x + w, y + h), fill=fill, outline=fill)
    draw.text((x + 21, y + (h - ft.size) // 2 - 4), text, font=ft, fill=WHITE)
    return (x, y, x + w, y + h)


def hook_scene(scene: Scene, local: float) -> Image.Image:
    img, draw = base(scene, local, dark=True)
    draw_text_block(draw, 110, 300, "每次安装，pip 都要在候选版本中挑出“最新且可用”的那个。", F_H2, (219, 234, 254), 760)
    x, y = 1080, 280
    versions = ["1.9", "1.10", "1.0rc1", "1.0"]
    active = min(len(versions) - 1, int(local / 3.2))
    for i, value in enumerate(versions):
        yy = y + i * 105
        fill = (30, 41, 59) if i != active else (30, 64, 175)
        draw_round(draw, (x, yy, x + 560, yy + 82), fill=fill, outline=(71, 85, 105))
        draw.text((x + 34, yy + 18), value, font=F_CODE, fill=WHITE)
        label = "candidate" if i != active else "selected?"
        draw.text((x + 340, yy + 25), label, font=F_SMALL, fill=YELLOW if i == active else (148, 163, 184))
    code_pill(draw, 110, 500, "pip install pkg", True, GREEN)
    draw.text((110, 610), "答案：版本号不是普通字符串，而是一套排序语义。", font=F_H2, fill=WHITE)
    return img


def structure_scene(scene: Scene, local: float) -> Image.Image:
    img, draw = base(scene, local)
    parts = [
        ("公共版本号", "2.1.0", "PyPI 接受，参与主要排序", GREEN),
        ("本地版本号", "cu118", "私有源、重打包、编译变体", BLUE),
    ]
    for i, (title, value, note, color) in enumerate(parts):
        x = 210 + i * 810
        draw_round(draw, (x, 330, x + 620, 620), WHITE, outline=blend(color, WHITE, 0.45), width=4)
        draw.text((x + 36, 368), title, font=F_H2, fill=color)
        draw.text((x + 36, 436), value, font=F_HERO, fill=INK)
        draw_text_block(draw, x + 36, 535, note, F_BODY, MUTED, 520)
    draw.text((915, 430), "+", font=F_HERO, fill=INK)
    draw_round(draw, (330, 720, 1590, 830), WHITE, outline=RED, width=4)
    draw.text((370, 750), "公共 PyPI 禁止上传带 +local 的包。", font=F_H2, fill=INK)
    return img


def public_scene(scene: Scene, local: float) -> Image.Image:
    img, draw = base(scene, local)
    items = [
        ("epoch", "1!", "方案重启", RED),
        ("release", "2.3.0", "核心版本", BLUE),
        ("pre", "rc1", "预发布", PURPLE),
        ("post", ".post1", "发布后修订", AMBER),
        ("dev", ".dev2", "开发快照", GREEN),
    ]
    for i, (label, value, note, color) in enumerate(items):
        x = 92 + i * 354
        draw_round(draw, (x, 330, x + 310, 660), WHITE, outline=LINE, width=2)
        draw.rectangle((x, 330, x + 310, 342), fill=color)
        draw.text((x + 26, 376), label, font=F_H2, fill=color)
        ft = F_CODE if len(value) <= 5 else F_CODE_SMALL
        draw.text((x + 26, 466), value, font=ft, fill=INK)
        draw_text_block(draw, x + 26, 560, note, F_BODY, MUTED, 250)
    code_pill(draw, 430, 760, "[N!]N(.N)*[{a|b|rc}N][.postN][.devN]", True, RED, size=34)
    return img


def sorting_scene(scene: Scene, local: float) -> Image.Image:
    img, draw = base(scene, local, dark=True)
    draw_round(draw, (92, 310, 860, 720), (15, 23, 42), outline=(51, 65, 85))
    draw.text((130, 350), "数字逐段比较", font=F_H2, fill=(191, 219, 254))
    code_pill(draw, 140, 450, "1.10", True, GREEN)
    draw.text((370, 456), ">", font=F_HERO, fill=WHITE)
    code_pill(draw, 480, 450, "1.9", False, BLUE)
    code_pill(draw, 140, 565, "1.2", True, BLUE)
    draw.text((370, 570), "=", font=F_HERO, fill=WHITE)
    code_pill(draw, 480, 565, "1.2.0", False, BLUE)

    draw_round(draw, (980, 310, 1810, 720), (15, 23, 42), outline=(51, 65, 85))
    draw.text((1020, 350), "同一个 1.0 的直觉链", font=F_H2, fill=(191, 219, 254))
    chain = ["1.0.dev1", "1.0a1", "1.0b1", "1.0rc1", "1.0", "1.0.post1", "1.0+local"]
    x, y = 1020, 440
    for i, item in enumerate(chain):
        active = local > 2 + i * 1.1
        box = code_pill(draw, x, y, item, active, [GREEN, PURPLE, PURPLE, PURPLE, BLUE, AMBER, CYAN][i], size=26)
        x = box[2] + 16
        if x > 1680:
            x, y = 1020, y + 78
    draw.text((120, 800), "核心直觉：dev 最早，pre 在正式版之前，post 在正式版之后。", font=F_H2, fill=WHITE)
    return img


def types_scene(scene: Scene, local: float) -> Image.Image:
    img, draw = base(scene, local)
    cards = [
        ("dev", "1.0.dev1", "最早", "CI / nightly", "pip 默认跳过"),
        ("pre", "1.0a1 / b1 / rc1", "正式版之前", "灰度测试", "pip 默认跳过"),
        ("final", "1.0", "分水岭", "稳定交付", "pip 默认可见"),
        ("post", "1.0.post1", "正式版之后", "非代码修正", "pip 默认可见"),
    ]
    for i, (label, example, pos, use, visible) in enumerate(cards):
        x = 92 + i * 455
        draw_round(draw, (x, 305, x + 410, 780), WHITE, outline=LINE)
        draw_round(draw, (x + 28, 338, x + 118, 428), scene.accent, outline=scene.accent)
        draw.text((x + 44, x * 0 + 362), label, font=F_CODE_SMALL, fill=WHITE)
        ft = F_CODE_SMALL if len(example) > 14 else F_CODE
        draw.text((x + 28, 470), example, font=ft, fill=INK)
        draw.text((x + 28, 565), f"位置：{pos}", font=F_BODY, fill=INK)
        draw.text((x + 28, 625), f"用途：{use}", font=F_BODY, fill=INK)
        draw.text((x + 28, 685), visible, font=F_BODY_BOLD, fill=GREEN if "可见" in visible else RED)
    return img


def timeline_scene(scene: Scene, local: float) -> Image.Image:
    img, draw = base(scene, local, dark=True)
    items = [
        ("1.2.0.dev1", "内部构建"),
        ("1.2.0a1", "内测"),
        ("1.2.0b1", "公测"),
        ("1.2.0rc1", "候选发布"),
        ("1.2.0", "正式发布"),
        ("1.2.0.post1", "非代码修正"),
        ("1.2.1", "代码修复"),
    ]
    y = 520
    draw.line((150, y, 1770, y), fill=(71, 85, 105), width=8)
    progress = ease(local / max(1, scene.end - scene.start - 1))
    draw.line((150, y, int(150 + 1620 * progress), y), fill=scene.accent, width=8)
    for i, (label, note) in enumerate(items):
        x = 150 + i * 270
        active = progress >= i / (len(items) - 1) - 0.02
        draw.ellipse((x - 22, y - 22, x + 22, y + 22), fill=scene.accent if active else (71, 85, 105), outline=DARK, width=7)
        draw.text((x - 92, y - 140), note, font=F_SMALL, fill=(219, 234, 254))
        ft = F_CODE_SMALL if len(label) > 10 else F_CODE_SMALL
        code_pill(draw, x - 102, y + 58, label, active, GREEN if label == "1.2.0" else scene.accent, size=26)
    return img


def advice_scene(scene: Scene, local: float) -> Image.Image:
    img, draw = base(scene, local)
    items = [
        "正式发布用 1.2.3 这类 final 版本",
        "发布前测试用 a / b / rc",
        "代码 bug 修复用新 patch，不要滥用 post",
        "dev 交给 CI 自动生成",
        "+local 只放私有或内部渠道",
        "拿不准时，用 packaging.version.Version 验证",
    ]
    for i, text in enumerate(items):
        col = i % 2
        row = i // 2
        x = 150 + col * 820
        y = 310 + row * 160
        draw_round(draw, (x, y, x + 720, y + 118), WHITE, outline=LINE)
        draw_round(draw, (x + 24, y + 28, x + 82, y + 86), scene.accent, outline=scene.accent)
        draw.text((x + 42, y + 39), str(i + 1), font=F_SMALL, fill=INK)
        draw_text_block(draw, x + 110, y + 30, text, F_BODY_BOLD, INK, 570)
    return img


def render_scene(scene: Scene, local: float) -> Image.Image:
    if scene.key == "hook":
        return hook_scene(scene, local)
    if scene.key == "structure":
        return structure_scene(scene, local)
    if scene.key == "public":
        return public_scene(scene, local)
    if scene.key == "sorting":
        return sorting_scene(scene, local)
    if scene.key == "types":
        return types_scene(scene, local)
    if scene.key == "timeline":
        return timeline_scene(scene, local)
    return advice_scene(scene, local)


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


def draw_caption(img: Image.Image, caption: Caption | None, t: float, duration: float) -> None:
    draw = ImageDraw.Draw(img)
    bar_w = int(WIDTH * min(1.0, max(0.0, t / duration)))
    draw.rectangle((0, HEIGHT - 9, bar_w, HEIGHT), fill=GREEN)
    if not caption:
        return
    x1, y1, x2, y2 = 250, 908, WIDTH - 250, 1028
    draw_round(draw, (x1, y1, x2, y2), (15, 23, 42), outline=(51, 65, 85))
    lines = wrap_text(draw, caption.text, F_CAPTION, x2 - x1 - 80)[:2]
    yy = y1 + 26 if len(lines) == 2 else y1 + 40
    for line in lines:
        w = text_width(draw, line, F_CAPTION)
        draw.text((x1 + (x2 - x1 - w) // 2, yy), line, font=F_CAPTION, fill=WHITE)
        yy += 44
    local = (int(t * 1000) - caption.start_ms) / max(1, caption.end_ms - caption.start_ms)
    draw.rectangle((x1, y2 - 5, x1 + int((x2 - x1) * max(0, min(1, local))), y2), fill=YELLOW)


def render_video(captions: list[Caption], scenes: list[Scene], silent_video: Path, frame_dir: Path) -> None:
    total_seconds = scenes[-1].end
    total_frames = math.ceil(total_seconds * FPS)
    writer = imageio.get_writer(silent_video, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    try:
        for frame_no in range(total_frames):
            t = frame_no / FPS
            scene = active_scene(scenes, t)
            img = render_scene(scene, t - scene.start)
            draw_caption(img, active_caption(captions, t), t, total_seconds)
            if frame_no in {0, int(18 * FPS), int(72 * FPS), int(116 * FPS), int(136 * FPS)}:
                img.save(frame_dir / f"frame_{frame_no:05d}.png")
            writer.append_data(np.asarray(img))
    finally:
        writer.close()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(exist_ok=True)

    source_text = SOURCE.read_text(encoding="utf-8")
    (OUT_DIR / "source_excerpt.md").write_text(source_text, encoding="utf-8")
    narration_path = OUT_DIR / "narration.txt"
    audio_path = OUT_DIR / "narration.mp3"
    vtt_path = OUT_DIR / "narration.vtt"
    captions_path = OUT_DIR / "captions.json"
    scenes_path = OUT_DIR / "scenes.json"
    silent_video = OUT_DIR / "pypi_version_explainer_silent.mp4"
    final_video = OUT_DIR / "pypi_version_explainer.mp4"

    narration_path.write_text(NARRATION, encoding="utf-8")
    generate_voiceover(narration_path, audio_path, vtt_path)
    captions = parse_vtt(vtt_path)
    if not captions:
        raise RuntimeError("No captions parsed from generated VTT")
    scenes = make_scenes(captions)

    captions_path.write_text(
        json.dumps([caption.__dict__ for caption in captions], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    scenes_path.write_text(
        json.dumps([scene.__dict__ | {"accent": scene.accent} for scene in scenes], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    render_video(captions, scenes, silent_video, frames_dir)
    ffmpeg_mux(silent_video, audio_path, final_video)

    print(final_video)
    print(audio_path)
    print(vtt_path)
    print(f"audio_duration={ffmpeg_duration(audio_path):.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
