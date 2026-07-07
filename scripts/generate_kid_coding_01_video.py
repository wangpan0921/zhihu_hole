#!/usr/bin/env python3
"""《我的世界里学编程·第1课：变量》讲解视频生成器。

纯 Python 渲染（PIL 画帧 + edge-tts 配音 + ffmpeg 合成），不依赖 Remotion / 浏览器。
参照 scripts/generate_pypi_version_fresh_video.py 的自包含范式改写，主题换成
Minecraft 风格的少儿编程讲解。

用法：
    ./venv/bin/python scripts/generate_kid_coding_01_video.py
"""
from __future__ import annotations

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
OUT_DIR = ROOT / "artifacts/kid_coding_01_video"
WIDTH, HEIGHT = 1920, 1080
FPS = 24
VOICE = "zh-CN-XiaoyiNeural"

# Minecraft-ish palette
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
BLUE = (37, 99, 235)
AMBER = (217, 140, 20)
RED = (214, 61, 47)
GOLD = (240, 190, 40)
WOOD = (170, 122, 74)
WOOD_DARK = (120, 84, 48)
STICKY = (250, 224, 96)


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


# 每行一条字幕；按场景分组（见 SCENE_LINES）
NARRATION_LINES = [
    # hook 0-2
    "你在《我的世界》里挖了一整晚，血量还剩多少？身上有几个金币？",
    "这些数字随时都在变。游戏能活起来，靠的就是不停地记录和更新这些数字。",
    "那么，游戏到底是怎么记住这些数字的？答案就是今天的主角：变量。",
    # box 3-5
    "变量，就像一个贴了标签的箱子。",
    "写一行，h p 等于 20，意思就是：造一个叫 h p 的箱子，往里面放个 20。",
    "记住，这个等号不念等于，念放进去，方向是从右往左。",
    # account 6-8
    "我们给史蒂夫建一份家底：名字、血量、还有金币。",
    "文字要用引号包起来，数字不用。电脑就靠引号来区分文字和数字。",
    "井号后面是注释，是写给人看的悄悄话，电脑会自动跳过。",
    # print 9-10
    "用 print，就能让电脑把这些数字显示到屏幕上。",
    "它是你和程序之间的第一扇窗户。",
    # goldchange 11-14
    "现在让数字变起来。史蒂夫打了个僵尸，爆出十个金币。",
    "关键就是这一行：gold 等于 gold 加 10。",
    "先算右边，0 加 10 等于 10；再把这个 10，放回左边的 gold 箱子。",
    "说白了，就是把箱子里的钱掏出来，加上 10，再塞回去。",
    # input 15-16
    "最后，用 input，让电脑反过来问你一句。",
    "你输入名字，它就回你一句欢迎语。这一刻，程序第一次和你对话了。",
    # summary 17-18
    "今天你学会了：变量、等号、引号规则、print、input，还有注释。",
    "再厉害的程序，扒到最底下，也不过是一个个箱子里的数字，在变来变去。",
]

SCENE_LINES = {
    "hook": (0, 3),
    "box": (3, 6),
    "account": (6, 9),
    "print": (9, 11),
    "goldchange": (11, 15),
    "input": (15, 17),
    "summary": (17, 19),
}

SCENE_META = [
    ("hook", "游戏怎么记住这些数字？", GREEN),
    ("box", "变量：贴了标签的箱子", WOOD_DARK),
    ("account", "给史蒂夫开个户", BLUE),
    ("print", "让电脑开口说话", AMBER),
    ("goldchange", "见证奇迹：数字会变了", RED),
    ("input", "让程序认识你", BLUE),
    ("summary", "今天你学会了", GREEN),
]


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
F_HERO = font(70, True)
F_TITLE = font(52, True)
F_H2 = font(40, True)
F_BODY = font(33)
F_BODY_BOLD = font(33, True)
F_SMALL = font(25)
F_CODE = font(40, True)
F_CODE_SMALL = font(30, True)
F_NUM = font(80, True)
F_CAPTION = font(35, True)


def edge_tts_exe() -> str:
    in_venv = Path(sys.executable).with_name("edge-tts")
    if in_venv.exists():
        return str(in_venv)
    found = shutil.which("edge-tts")
    if found:
        return found
    raise RuntimeError("edge-tts executable not found")


def run_tts(text_path: Path, audio_path: Path) -> None:
    subprocess.run(
        [
            edge_tts_exe(),
            "--voice",
            VOICE,
            "--rate=-4%",
            "--file",
            str(text_path),
            "--write-media",
            str(audio_path),
        ],
        check=True,
    )


def duration(path: Path) -> float:
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
    hh, mm, ss = match.groups()
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def mux(video_path: Path, audio_path: Path, out_path: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg, "-y", "-i", str(video_path), "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out_path),
        ],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def build_captions(lines: list[str], total: float) -> list[Caption]:
    """按字符数把总时长按比例分配给每行，保证字幕正好铺满音频。"""
    weights = [max(6, len(re.sub(r"\s+", "", ln))) for ln in lines]
    tot_w = sum(weights)
    captions: list[Caption] = []
    cursor = 0.0
    for ln, w in zip(lines, weights):
        seg = total * (w / tot_w)
        start = cursor
        end = cursor + seg
        captions.append(Caption(int(start * 1000), int(end * 1000), ln))
        cursor = end
    return captions


def make_scenes(captions: list[Caption]) -> list[Scene]:
    scenes: list[Scene] = []
    for key, title, accent in SCENE_META:
        lo, hi = SCENE_LINES[key]
        start = captions[lo].start_ms / 1000
        end = captions[hi - 1].end_ms / 1000
        scenes.append(Scene(key, title, start, end, accent))
    return scenes


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


def rounded(draw, box, fill, outline=BORDER, width=2, radius=12) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_block(draw, x, y, text, ft, fill, max_width, gap=12) -> int:
    for line in wrap(draw, text, ft, max_width):
        draw.text((x, y), line, font=ft, fill=fill)
        y += ft.size + gap
    return y


def ease(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return 1 - (1 - v) ** 3


def blend(a, b, r):
    return tuple(int(a[i] + (b[i] - a[i]) * r) for i in range(3))


def crate(draw, box, label: str, number: str, label_color=WOOD_DARK) -> None:
    """画一个贴标签的木箱子。"""
    x1, y1, x2, y2 = box
    rounded(draw, box, WOOD, outline=WOOD_DARK, width=5, radius=10)
    # 木纹交叉
    draw.line((x1, (y1 + y2) // 2, x2, (y1 + y2) // 2), fill=WOOD_DARK, width=3)
    draw.line(((x1 + x2) // 2, y1, (x1 + x2) // 2, y2), fill=WOOD_DARK, width=3)
    # 数字
    if number:
        w, h = text_size(draw, number, F_NUM)
        draw.text(((x1 + x2 - w) // 2, (y1 + y2 - h) // 2 - 6), number, font=F_NUM, fill=INK)
    # 便利贴标签
    sx1, sy1 = x1 - 12, y1 - 34
    rounded(draw, (sx1, sy1, sx1 + 150, sy1 + 66), STICKY, outline=AMBER, width=3, radius=6)
    draw.text((sx1 + 20, sy1 + 12), label, font=F_CODE_SMALL, fill=INK)


def canvas(scene: Scene, local: float) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), SKY_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        draw.line((0, y, WIDTH, y), fill=blend(SKY_TOP, SKY_BOTTOM, y / HEIGHT))
    # 底部草地/泥土条（像素方块感）
    gy = HEIGHT - 70
    for bx in range(0, WIDTH, 70):
        draw.rectangle((bx, gy, bx + 68, gy + 22), fill=GRASS if (bx // 70) % 2 == 0 else GRASS_DARK)
        draw.rectangle((bx, gy + 22, bx + 68, HEIGHT), fill=DIRT)
    # 左侧进度强调条
    bar = int(24 + 460 * ease(local / 1.2))
    draw.rectangle((0, 0, 16, bar), fill=scene.accent)
    draw.text((72, 50), "我的世界里学编程 · 第 1 课", font=F_LOGO, fill=scene.accent)
    draw.text((72, 100), scene.title, font=F_HERO, fill=INK)
    draw.text((WIDTH - 250, 60), "变量", font=F_TITLE, fill=MUTED)
    draw.line((72, 200, 700, 200), fill=scene.accent, width=5)
    return img, draw


def code_line(draw, x, y, text, ft=F_CODE) -> None:
    w, h = text_size(draw, text, ft)
    rounded(draw, (x - 18, y - 12, x + w + 18, y + h + 14), (244, 246, 240), outline=BORDER, width=2, radius=8)
    draw.text((x, y), text, font=ft, fill=INK)


def sc_hook(s: Scene, local: float) -> Image.Image:
    img, draw = canvas(s, local)
    draw_block(draw, 90, 300, "游戏里的血量、金币、名字，随时都在变——", F_H2, INK, 820)
    draw_block(draw, 90, 360, "它们，就是“变量”。", F_H2, GREEN, 820)
    data = [("血量", "20", GREEN), ("金币", "0", GOLD), ("名字", "史蒂夫", BLUE)]
    for i, (label, val, _c) in enumerate(data):
        appear = ease((local - 0.6 - i * 0.7) / 0.6)
        if appear <= 0:
            continue
        x = 1080
        y = 292 + i * 162
        crate(draw, (x, y, x + 620, y + 118), label, val if val.isdigit() else "")
        if not val.isdigit():
            w, h = text_size(draw, val, F_H2)
            draw.text((x + (620 - w) // 2, y + (118 - h) // 2 - 4), val, font=F_H2, fill=INK)
    draw.text((90, 560), "问题：程序到底怎么“记住”它们？", font=F_H2, fill=INK)
    return img


def sc_box(s: Scene, local: float) -> Image.Image:
    img, draw = canvas(s, local)
    draw.text((90, 300), "把一个数字，放进贴着标签的箱子里。", font=F_H2, fill=INK)
    crate(draw, (240, 420, 240 + 460, 420 + 300), "hp", "20")
    code_line(draw, 900, 470, "hp = 20")
    # 箭头：20 放进 hp
    ax = ease((local - 1.0) / 0.8)
    if ax > 0:
        draw.line((1180, 540, 760, 560), fill=RED, width=6)
        draw.polygon([(760, 560), (792, 544), (792, 578)], fill=RED)
        draw.text((900, 600), "把 20 放进 hp 箱子", font=F_BODY_BOLD, fill=RED)
    draw.text((900, 690), "= 不念“等于”，念“放进去”（从右往左）", font=F_BODY, fill=MUTED)
    return img


def sc_account(s: Scene, local: float) -> Image.Image:
    img, draw = canvas(s, local)
    lines = ['name = "史蒂夫"', "hp = 20", "gold = 0"]
    for i, ln in enumerate(lines):
        if ease((local - i * 0.5) / 0.4) <= 0:
            continue
        code_line(draw, 110, 310 + i * 90, ln)
    # 引号 vs 数字
    panels = [('"史蒂夫"', "加引号 = 文字", BLUE), ("20", "不加 = 数字", GREEN)]
    for i, (val, note, color) in enumerate(panels):
        x = 900 + i * 470
        rounded(draw, (x, 300, x + 420, 560), PANEL, outline=blend(color, PANEL, 0.3), width=4)
        w, _ = text_size(draw, val, F_CODE)
        draw.text((x + (420 - w) // 2, 370), val, font=F_CODE, fill=INK)
        draw.text((x + 40, 480), note, font=F_BODY_BOLD, fill=color)
    draw.text((110, 640), "# 井号后面是注释，写给人看，电脑会跳过", font=F_BODY, fill=MUTED)
    return img


def sc_print(s: Scene, local: float) -> Image.Image:
    img, draw = canvas(s, local)
    draw.text((90, 300), "用 print，让电脑把内容显示到屏幕上：", font=F_H2, fill=INK)
    code_line(draw, 110, 380, 'print(name, "现在的血量是", hp)')
    # 输出黑框
    if ease((local - 1.0) / 0.6) > 0:
        rounded(draw, (110, 500, 1100, 640), NAVY, outline=NAVY, radius=10)
        draw.text((140, 540), ">>> 史蒂夫 现在的血量是 20", font=F_CODE_SMALL, fill=(180, 245, 180))
    draw.text((110, 700), "print 是你和程序之间的第一扇窗户。", font=F_BODY, fill=MUTED)
    return img


def sc_goldchange(s: Scene, local: float) -> Image.Image:
    img, draw = canvas(s, local)
    draw.text((90, 300), "gold = gold + 10  到底发生了什么？", font=F_H2, fill=INK)
    step = local
    # 第①步
    rounded(draw, (110, 400, 700, 720), PANEL, outline=BORDER, width=3, radius=12)
    draw.text((140, 420), "① 先算右边", font=F_BODY_BOLD, fill=RED)
    crate(draw, (250, 500, 250 + 300, 500 + 150), "gold", "0")
    draw.text((150, 680), "gold + 10  →  0 + 10", font=F_CODE_SMALL, fill=INK)
    # ①→② 箭头
    a12 = ease((step - 1.2) / 0.4)
    if a12 > 0:
        xend = 700 + int(40 * a12)
        draw.line((700, 560, xend, 560), fill=AMBER, width=6)
        draw.polygon([(xend, 560), (xend - 22, 548), (xend - 22, 572)], fill=AMBER)
    # 第②步（数字弹出）
    a2 = ease((step - 1.4) / 0.6)
    if a2 > 0:
        rounded(draw, (740, 400, 1180, 720), PANEL, outline=BORDER, width=3, radius=12)
        draw.text((770, 420), "② 得出结果", font=F_BODY_BOLD, fill=AMBER)
        pop = font(int(50 + 40 * a2), True)  # 数字从小弹到大
        w, h = text_size(draw, "10", pop)
        draw.text((960 - w // 2, 560 - h // 2), "10", font=pop, fill=AMBER)
    # ②→③ 箭头
    a23 = ease((step - 2.4) / 0.4)
    if a23 > 0:
        xend = 1180 + int(40 * a23)
        draw.line((1180, 560, xend, 560), fill=GREEN, width=6)
        draw.polygon([(xend, 560), (xend - 22, 548), (xend - 22, 572)], fill=GREEN)
    # 第③步
    if ease((step - 2.6) / 0.6) > 0:
        rounded(draw, (1220, 400, 1810, 720), PANEL, outline=BORDER, width=3, radius=12)
        draw.text((1250, 420), "③ 放回左边", font=F_BODY_BOLD, fill=GREEN)
        crate(draw, (1360, 500, 1360 + 300, 500 + 150), "gold", "10")
        draw.text((1250, 680), "gold 变成了 10", font=F_CODE_SMALL, fill=GREEN)
    draw.text((110, 760), "就是：把钱掏出来，加 10，再塞回去。", font=F_BODY, fill=MUTED)
    return img


def sc_input(s: Scene, local: float) -> Image.Image:
    img, draw = canvas(s, local)
    draw.text((90, 300), "用 input，让电脑反过来问你：", font=F_H2, fill=INK)
    code_line(draw, 110, 380, 'player = input("请输入你的角色名：")', ft=F_CODE_SMALL)
    code_line(draw, 110, 450, 'print("欢迎来到我的世界，", player)', ft=F_CODE_SMALL)
    if ease((local - 1.2) / 0.6) > 0:
        rounded(draw, (110, 560, 1200, 720), NAVY, outline=NAVY, radius=10)
        draw.text((140, 585), "请输入你的角色名：苦力怕克星", font=F_CODE_SMALL, fill=(180, 245, 180))
        draw.text((140, 645), "欢迎来到我的世界， 苦力怕克星", font=F_CODE_SMALL, fill=(180, 245, 180))
    draw.text((110, 760), "这一刻，程序第一次和你对话了。", font=F_BODY, fill=MUTED)
    return img


def sc_summary(s: Scene, local: float) -> Image.Image:
    img, draw = canvas(s, local)
    chips = [
        ("变量", "贴标签的箱子"),
        ("=", "把右边放进左边"),
        ('" "', "文字加引号，数字不加"),
        ("print", "显示到屏幕"),
        ("input", "听你说话"),
        ("#", "写给人的注释"),
    ]
    for i, (k, v) in enumerate(chips):
        if ease((local - i * 0.4) / 0.4) <= 0:
            continue
        col, row = i % 2, i // 2
        x, y = 120 + col * 850, 300 + row * 150
        rounded(draw, (x, y, x + 780, y + 118), PANEL, outline=BORDER, width=3, radius=12)
        rounded(draw, (x + 24, y + 26, x + 150, y + 92), blend(s.accent, PANEL, 0.15), outline=s.accent, width=2, radius=8)
        kw, _ = text_size(draw, k, F_CODE_SMALL)
        draw.text((x + 87 - kw // 2, y + 40), k, font=F_CODE_SMALL, fill=INK)
        draw.text((x + 180, y + 40), v, font=F_BODY_BOLD, fill=INK)
    return img


RENDERERS = {
    "hook": sc_hook, "box": sc_box, "account": sc_account, "print": sc_print,
    "goldchange": sc_goldchange, "input": sc_input, "summary": sc_summary,
}


def active_scene(scenes: list[Scene], t: float) -> Scene:
    for s in scenes:
        if s.start <= t < s.end:
            return s
    return scenes[-1]


def active_caption(captions: list[Caption], t: float) -> Caption | None:
    ms = int(t * 1000)
    for c in captions:
        if c.start_ms <= ms < c.end_ms:
            return c
    return None


def draw_caption(img: Image.Image, cap: Caption | None, t: float, total: float) -> None:
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, HEIGHT - 8, int(WIDTH * min(1.0, t / total)), HEIGHT), fill=GREEN)
    if cap is None:
        return
    x1, y1, x2, y2 = 220, 900, WIDTH - 220, 1024
    rounded(draw, (x1, y1, x2, y2), NAVY, outline=(60, 72, 60), radius=12)
    lines = wrap(draw, cap.text, F_CAPTION, x2 - x1 - 80)[:2]
    yy = y1 + 24 if len(lines) == 2 else y1 + 42
    for line in lines:
        w, _ = text_size(draw, line, F_CAPTION)
        draw.text((x1 + (x2 - x1 - w) // 2, yy), line, font=F_CAPTION, fill=(255, 255, 255))
        yy += 46


def render_video(captions, scenes, silent_path: Path) -> None:
    total = scenes[-1].end
    total_frames = math.ceil(total * FPS)
    writer = imageio.get_writer(silent_path, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    try:
        for frame_no in range(total_frames):
            t = frame_no / FPS
            scene = active_scene(scenes, t)
            img = RENDERERS[scene.key](scene, t - scene.start)
            draw_caption(img, active_caption(captions, t), t, total)
            writer.append_data(np.asarray(img))
    finally:
        writer.close()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    narration_text = "\n".join(NARRATION_LINES)
    narration_path = OUT_DIR / "narration.txt"
    audio_path = OUT_DIR / "narration.mp3"
    silent_path = OUT_DIR / "silent.mp4"
    final_path = OUT_DIR / "kid_coding_01_variable.mp4"

    narration_path.write_text(narration_text, encoding="utf-8")
    run_tts(narration_path, audio_path)
    total = duration(audio_path)
    if total <= 0:
        raise RuntimeError("无法获取音频时长")
    # 结尾留 1 秒
    captions = build_captions(NARRATION_LINES, total)
    scenes = make_scenes(captions)
    # 把最后一个场景延伸到音频结束 + 0.8s
    scenes[-1] = Scene(scenes[-1].key, scenes[-1].title, scenes[-1].start, total + 0.8, scenes[-1].accent)

    render_video(captions, scenes, silent_path)
    mux(silent_path, audio_path, final_path)

    print(final_path)
    print(f"duration={total:.2f}s frames={math.ceil((total + 0.8) * FPS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
