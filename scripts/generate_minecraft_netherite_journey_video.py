#!/usr/bin/env python3
"""Generate a Minecraft-style video about Steve and Alex's Netherite journey."""

from __future__ import annotations

import json
import math
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


OUT_DIR = Path("artifacts/minecraft_netherite_journey_video")
WIDTH, HEIGHT = 1280, 720
FPS = 24
SAMPLE_RATE = 44100

BLACK = (8, 10, 14)
WHITE = (246, 250, 255)
SKY = (126, 178, 229)
GRASS = (74, 137, 68)
DIRT = (114, 78, 45)
NETHER_TOP = (38, 10, 16)
NETHER_BOTTOM = (95, 25, 18)
NETHERRACK = (113, 36, 37)
LAVA = (245, 106, 20)
GOLD = (245, 199, 72)
DIAMOND = (91, 226, 235)
NETHERITE = (65, 61, 67)
PURPLE = (112, 47, 171)
MAGENTA = (192, 62, 221)
STONE = (102, 108, 116)
CHEST = (154, 91, 32)
ANCIENT = (88, 66, 54)


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


F_TITLE = font(42, True)
F_SUB = font(30, True)
F_BODY = font(23, True)
F_SMALL = font(20)


@dataclass(frozen=True)
class Scene:
    key: str
    title: str
    subtitle: str
    start: float
    end: float


SCENES = [
    Scene("portal", "下界传送门完成", "史蒂夫和艾利克斯点燃黑曜石门，紫色漩涡把两人吸入下界。", 0, 8),
    Scene("nether", "抵达下界", "他们的目标很明确：找到猪灵堡垒，拿到升级模板，再挖 16 个远古残骸。", 8, 16),
    Scene("bastion", "猪灵堡垒", "两人戴上金头盔，小心走进堡垒，开始寻找宝箱。", 16, 25),
    Scene("brutes", "猪灵蛮兵拦路", "几只猪灵蛮兵冲了出来，史蒂夫和艾利克斯拔剑解决了它们。", 25, 34),
    Scene("template1", "第一个升级模板", "宝箱打开，里面正好躺着一个下界合金升级模板。", 34, 43),
    Scene("template2", "又过了一段时间", "他们继续探索，又找到了第二个升级模板。", 43, 51),
    Scene("barter", "以物易物", "两人用金锭和猪灵交易，换到了两瓶抗火药水。", 51, 60),
    Scene("lava", "潜入岩浆底下", "喝下抗火药水后，他们钻进岩浆湖底，开始寻找远古残骸。", 60, 70),
    Scene("debris", "过了亿点点时间", "一镐又一镐，他们终于凑齐了 16 个远古残骸。", 70, 80),
    Scene("duplicate", "返回主世界", "回到家后，他们用钻石复制了两个锻造模板。", 80, 88),
    Scene("smith", "升级下界合金", "锻造台前，钻石盔甲被升级成下界合金，再用金锭压上纹理。", 88, 100),
    Scene("stand", "圆满的旅行", "两人拍手庆祝，把来之不易的盔甲放上盔甲架，永远记住这次旅程。", 100, 112),
]


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp(t)


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(lerp(x, y, t)) for x, y in zip(a, b))


def active_scene(time_s: float) -> Scene:
    for scene in SCENES:
        if scene.start <= time_s < scene.end:
            return scene
    return SCENES[-1]


def progress(scene: Scene, time_s: float) -> float:
    return clamp((time_s - scene.start) / (scene.end - scene.start))


def draw_gradient(draw: ImageDraw.ImageDraw, top: tuple[int, int, int], bottom: tuple[int, int, int]):
    for y in range(HEIGHT):
        draw.line((0, y, WIDTH, y), fill=mix(top, bottom, y / HEIGHT))


def pixel(draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, color, outline=(20, 20, 24), width=3):
    draw.rectangle((x, y, x + w, y + h), fill=color, outline=outline, width=width)


def floor(draw: ImageDraw.ImageDraw, nether: bool, frame: int):
    horizon = 470
    base = NETHERRACK if nether else GRASS
    dark = (70, 24, 26) if nether else (54, 104, 53)
    draw.rectangle((0, horizon, WIDTH, HEIGHT), fill=dark)
    for i in range(11):
        y = int(lerp(horizon, HEIGHT + 60, (i / 10) ** 1.8))
        draw.line((0, y, WIDTH, y), fill=mix(base, BLACK, 0.35), width=3)
    for i in range(-12, 13):
        x = WIDTH / 2 + i * 80 + math.sin(frame * 0.01) * 22
        draw.line((x, horizon, x + i * 36, HEIGHT), fill=mix(base, BLACK, 0.18), width=2)
    if nether:
        for i in range(8):
            x = (i * 190 + frame * 0.45) % (WIDTH + 180) - 90
            y = 575 + (i % 3) * 34
            pixel(draw, x, y, 118, 28, LAVA, (126, 38, 16), 3)


def portal(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float, frame: int, active: float = 1.0):
    w, h = int(150 * scale), int(240 * scale)
    obs = (25, 20, 35)
    pixel(draw, x, y, w, 28 * scale, obs, (58, 42, 83), 4)
    pixel(draw, x, y + h - 28 * scale, w, 28 * scale, obs, (58, 42, 83), 4)
    pixel(draw, x, y, 28 * scale, h, obs, (58, 42, 83), 4)
    pixel(draw, x + w - 28 * scale, y, 28 * scale, h, obs, (58, 42, 83), 4)
    for i in range(8):
        t = (i / 8 + frame * 0.018) % 1
        col = mix(PURPLE, MAGENTA, abs(math.sin(t * math.pi)))
        draw.ellipse((x + 38 * scale, y + 38 * scale + t * (h - 90 * scale), x + w - 38 * scale, y + 92 * scale + t * (h - 90 * scale)), fill=(*col, int(90 * active)))
    draw.rectangle((x + 34 * scale, y + 34 * scale, x + w - 34 * scale, y + h - 34 * scale), outline=(220, 112, 255), width=max(2, int(4 * scale)))


def character(draw: ImageDraw.ImageDraw, x: float, y: float, name: str, frame: int, scale: float = 1.0, armor: str = "diamond", gold_helmet: bool = False, clap: float = 0.0):
    skin = (176, 116, 74) if name == "steve" else (210, 139, 86)
    shirt = (55, 170, 176) if name == "steve" else (92, 184, 83)
    hair = (63, 39, 24) if name == "steve" else (205, 103, 42)
    pants = (49, 75, 147)
    if armor == "netherite":
        shirt = NETHERITE
        pants = (47, 45, 51)
    elif armor == "diamond":
        shirt = DIAMOND
    walk = math.sin(frame * 0.18 + x * 0.01) * 5 * scale
    s = scale
    pixel(draw, x + 35*s, y, 58*s, 58*s, skin)
    pixel(draw, x + 35*s, y, 58*s, 16*s, GOLD if gold_helmet else hair)
    pixel(draw, x + 50*s, y + 28*s, 8*s, 8*s, BLACK, BLACK, 1)
    pixel(draw, x + 72*s, y + 28*s, 8*s, 8*s, BLACK, BLACK, 1)
    pixel(draw, x + 28*s, y + 58*s, 72*s, 82*s, shirt)
    arm_l = -28 if clap > 0.5 else -8
    arm_r = 28 if clap > 0.5 else 8
    draw.rectangle((x + 8*s, y + 66*s, x + 33*s, y + 140*s), fill=skin, outline=(82, 54, 38), width=max(2, int(3*s)))
    draw.rectangle((x + 95*s, y + 66*s, x + 120*s, y + 140*s), fill=skin, outline=(82, 54, 38), width=max(2, int(3*s)))
    if clap > 0:
        draw.line((x + 28*s, y + 92*s, x + 60*s, y + 104*s), fill=skin, width=int(16*s))
        draw.line((x + 100*s, y + 92*s, x + 68*s, y + 104*s), fill=skin, width=int(16*s))
    pixel(draw, x + 34*s, y + 140*s, 28*s, 60*s + walk, pants)
    pixel(draw, x + 66*s, y + 140*s, 28*s, 60*s - walk, pants)
    if armor == "netherite":
        draw.line((x + 32*s, y + 96*s, x + 98*s, y + 118*s), fill=GOLD, width=max(3, int(5*s)))


def piglin(draw: ImageDraw.ImageDraw, x: float, y: float, brute: bool, frame: int, defeated: float = 0.0):
    skin = (212, 136, 104) if not brute else (162, 83, 79)
    wobble = math.sin(frame * 0.22 + x) * 5
    y += defeated * 52
    alpha = 1 - defeated * 0.55
    def m(c): return mix(c, BLACK, 1 - alpha)
    pixel(draw, x + wobble, y, 70, 64, m(skin), (74, 39, 42), 4)
    pixel(draw, x + wobble + 12, y + 64, 46, 88, m((78, 54, 65) if brute else (112, 74, 48)), (45, 31, 34), 4)
    pixel(draw, x + wobble - 18, y + 16, 22, 34, m(skin), (74, 39, 42), 3)
    pixel(draw, x + wobble + 66, y + 16, 22, 34, m(skin), (74, 39, 42), 3)
    pixel(draw, x + wobble + 21, y + 28, 8, 8, BLACK, BLACK, 1)
    pixel(draw, x + wobble + 43, y + 28, 8, 8, BLACK, BLACK, 1)
    if brute and defeated < 0.6:
        draw.rectangle((x + wobble + 58, y + 80, x + wobble + 120, y + 94), fill=(84, 73, 78), outline=BLACK, width=3)


def chest(draw: ImageDraw.ImageDraw, x: int, y: int, open_p: float = 0.0):
    pixel(draw, x, y + 40 - open_p * 28, 150, 48, CHEST, (75, 45, 22), 5)
    pixel(draw, x, y + 88, 150, 78, CHEST, (75, 45, 22), 5)
    pixel(draw, x + 62, y + 92, 26, 28, GOLD, (104, 72, 22), 3)


def template_icon(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0):
    s = scale
    pixel(draw, x, y, 82*s, 100*s, (210, 207, 174), (82, 75, 60), max(2, int(4*s)))
    draw.rectangle((x + 18*s, y + 20*s, x + 64*s, y + 30*s), fill=(72, 69, 66))
    draw.rectangle((x + 18*s, y + 44*s, x + 64*s, y + 54*s), fill=NETHERITE)
    draw.rectangle((x + 18*s, y + 68*s, x + 46*s, y + 78*s), fill=GOLD)


def item_label(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color: tuple[int, int, int]):
    draw.rounded_rectangle((x, y, x + 235, y + 56), radius=8, fill=(8, 12, 18, 190), outline=(185, 200, 215), width=2)
    draw.text((x + 18, y + 14), text, font=F_BODY, fill=color)


def draw_bastion(draw: ImageDraw.ImageDraw, frame: int):
    for i in range(5):
        x = 90 + i * 238
        h = 260 + (i % 2) * 82
        pixel(draw, x, 250 - (i % 2) * 60, 168, h, (55, 44, 48), (26, 23, 28), 5)
        pixel(draw, x + 36, 300, 62, 72, (20, 16, 18), (7, 7, 8), 3)
    draw.rectangle((0, 430, WIDTH, 462), fill=(38, 30, 34))


def draw_smithing_table(draw: ImageDraw.ImageDraw, x: int, y: int):
    pixel(draw, x, y, 240, 112, (102, 69, 46), (47, 29, 18), 5)
    pixel(draw, x + 22, y + 18, 74, 48, (62, 67, 72), (28, 31, 34), 4)
    pixel(draw, x + 112, y + 18, 74, 48, (62, 67, 72), (28, 31, 34), 4)
    pixel(draw, x + 196, y + 22, 32, 70, (48, 50, 55), (20, 20, 22), 4)


def armor_stand(draw: ImageDraw.ImageDraw, x: int, y: int, frame: int):
    draw.line((x + 80, y + 55, x + 80, y + 215), fill=(134, 92, 48), width=10)
    draw.line((x + 30, y + 215, x + 130, y + 215), fill=(134, 92, 48), width=12)
    pixel(draw, x + 48, y, 64, 54, NETHERITE, (25, 24, 29), 4)
    pixel(draw, x + 30, y + 58, 100, 92, NETHERITE, (25, 24, 29), 4)
    pixel(draw, x + 32, y + 150, 44, 78, NETHERITE, (25, 24, 29), 4)
    pixel(draw, x + 84, y + 150, 44, 78, NETHERITE, (25, 24, 29), 4)
    for off in [16, 44, 75]:
        draw.line((x + 35, y + off, x + 126, y + off + 28), fill=GOLD, width=4)
    glow = 0.35 + 0.2 * math.sin(frame * 0.08)
    draw.ellipse((x - 24, y - 20, x + 184, y + 250), outline=(245, 199, 72, int(180 * glow)), width=5)


def particles(draw: ImageDraw.ImageDraw, frame: int, color: tuple[int, int, int], count: int, area: tuple[int, int, int, int]):
    x0, y0, x1, y1 = area
    for i in range(count):
        x = x0 + ((i * 89 + frame * (1 + i % 3)) % max(1, x1 - x0))
        y = y0 + ((i * 61 + frame * (2 + i % 2)) % max(1, y1 - y0))
        size = 5 + (i % 4) * 3
        draw.rectangle((x, y, x + size, y + size), fill=color)


def draw_scene(draw: ImageDraw.ImageDraw, scene: Scene, p: float, frame: int):
    nether = scene.key in {"nether", "bastion", "brutes", "template1", "template2", "barter", "lava", "debris"}
    draw_gradient(draw, NETHER_TOP if nether else SKY, NETHER_BOTTOM if nether else (210, 238, 255))
    if nether:
        particles(draw, frame, (221, 92, 32), 22, (0, 70, WIDTH, 460))
    else:
        for i in range(4):
            x = (i * 310 + frame * 0.35) % (WIDTH + 220) - 120
            draw.rectangle((x, 95 + i * 28, x + 150, 128 + i * 28), fill=WHITE)
    floor(draw, nether, frame)

    if scene.key == "portal":
        portal(draw, 510, 180, 1.25, frame, 1)
        character(draw, 285 + p * 130, 435, "steve", frame, 0.86, "none")
        character(draw, 830 - p * 120, 435, "alex", frame, 0.86, "none")
        particles(draw, frame, MAGENTA, 18, (470, 165, 780, 465))
    elif scene.key == "nether":
        portal(draw, 120, 185, 1.1, frame, 0.9)
        character(draw, 420, 430, "steve", frame, 0.9, "diamond")
        character(draw, 570, 430, "alex", frame, 0.9, "diamond")
        item_label(draw, 830, 210, "目标：猪灵堡垒", GOLD)
        item_label(draw, 830, 280, "升级模板 x2", (210, 207, 174))
        item_label(draw, 830, 350, "远古残骸 x16", (196, 154, 103))
    elif scene.key in {"bastion", "brutes", "template1", "template2"}:
        draw_bastion(draw, frame)
        character(draw, 290, 430, "steve", frame, 0.86, "diamond", True)
        character(draw, 420, 430, "alex", frame, 0.86, "diamond", True)
        if scene.key == "bastion":
            chest(draw, 825, 430, p)
        elif scene.key == "brutes":
            for i in range(4):
                defeated = clamp((p - i * 0.16) * 1.9)
                piglin(draw, 720 + i * 96, 386 + (i % 2) * 22, True, frame, defeated)
            draw.line((410, 492, 635, 438), fill=DIAMOND, width=10)
            draw.line((545, 490, 735, 452), fill=DIAMOND, width=10)
        else:
            chest(draw, 805, 420, 1)
            template_icon(draw, 965, 342 - int(math.sin(frame * 0.12) * 8), 1.25)
            item_label(draw, 902, 270, "升级模板 +1" if scene.key == "template1" else "升级模板 +1", (232, 225, 181))
    elif scene.key == "barter":
        piglin(draw, 650, 380, False, frame, 0)
        character(draw, 330, 430, "steve", frame, 0.86, "diamond", True)
        character(draw, 455, 430, "alex", frame, 0.86, "diamond", True)
        for i in range(5):
            pixel(draw, 540 + i * 36, 520 - i % 2 * 12, 28, 20, GOLD, (108, 78, 20), 3)
        for i in range(2):
            pixel(draw, 830 + i * 84, 418, 46, 82, (242, 132, 52), (120, 54, 24), 4)
            pixel(draw, 840 + i * 84, 390, 26, 30, (220, 235, 238), (90, 101, 105), 3)
        item_label(draw, 800, 315, "抗火药水 x2", (255, 170, 90))
    elif scene.key == "lava":
        draw.rectangle((0, 430, WIDTH, HEIGHT), fill=LAVA)
        for i in range(20):
            y = 430 + (i * 31 + frame * 1.8) % 290
            draw.line((0, y, WIDTH, y + math.sin(i) * 18), fill=(255, 174, 48), width=5)
        character(draw, 395, 320 + math.sin(frame * 0.06) * 12, "steve", frame, 0.72, "diamond", True)
        character(draw, 535, 342 + math.cos(frame * 0.06) * 12, "alex", frame, 0.72, "diamond", True)
        particles(draw, frame, (255, 218, 89), 30, (0, 445, WIDTH, HEIGHT))
    elif scene.key == "debris":
        draw.rectangle((0, 150, WIDTH, HEIGHT), fill=(88, 31, 34))
        for i in range(16):
            x = 140 + (i % 8) * 120
            y = 230 + (i // 8) * 105
            show = clamp((p * 18 - i) * 0.7)
            pixel(draw, x, y, 72, 58, mix((75, 42, 38), ANCIENT, show), (44, 28, 27), 4)
            if show > 0.5:
                draw.text((x + 22, y + 15), "古", font=F_SMALL, fill=(207, 158, 105))
        character(draw, 410, 500, "steve", frame, 0.72, "diamond", True)
        character(draw, 560, 500, "alex", frame, 0.72, "diamond", True)
        item_label(draw, 845, 530, f"远古残骸 {min(16, int(p * 18))}/16", (216, 170, 112))
    elif scene.key == "duplicate":
        character(draw, 280, 430, "steve", frame, 0.86, "diamond")
        character(draw, 430, 430, "alex", frame, 0.86, "diamond")
        for i in range(2):
            template_icon(draw, 740 + i * 115, 300, 1.0)
        for i in range(6):
            pixel(draw, 720 + i * 58, 470, 42, 42, DIAMOND, (21, 116, 130), 3)
        item_label(draw, 770, 220, "钻石复制模板 x2", DIAMOND)
    elif scene.key == "smith":
        draw_smithing_table(draw, 510, 430)
        character(draw, 250, 422, "steve", frame, 0.84, "diamond")
        character(draw, 850, 422, "alex", frame, 0.84, "diamond")
        glow = clamp(math.sin(p * math.pi) * 1.3)
        pixel(draw, 560, 310, 64, 64, DIAMOND, (21, 116, 130), 4)
        pixel(draw, 650, 310, 64, 64, NETHERITE, (24, 23, 29), 4)
        for i in range(3):
            draw.line((520, 260 + i * 30, 760, 330 + i * 15), fill=mix(GOLD, WHITE, glow), width=6)
        item_label(draw, 523, 210, "钻石甲 -> 下界合金", (185, 180, 190))
        item_label(draw, 523, 275, "金锭纹理", GOLD)
    else:
        armor_stand(draw, 560, 270, frame)
        clap = 1 if int(frame / 8) % 2 == 0 else 0
        character(draw, 300, 430, "steve", frame, 0.86, "none", False, clap)
        character(draw, 820, 430, "alex", frame, 0.86, "none", False, clap)
        particles(draw, frame, GOLD, 24, (420, 180, 860, 520))


def wrap(draw: ImageDraw.ImageDraw, text: str, ft: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        trial = current + ch
        if draw.textbbox((0, 0), trial, font=ft)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def draw_ui(img: Image.Image, scene: Scene, time_s: float):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, WIDTH, 78), fill=(5, 8, 13, 172))
    draw.text((34, 17), "Minecraft: 下界合金圆满旅行", font=F_TITLE, fill=WHITE)
    draw.text((WIDTH - 246, 28), f"{time_s:05.1f}s / {SCENES[-1].end:.0f}s", font=F_SMALL, fill=(196, 211, 225))
    draw.rounded_rectangle((34, 94, 850, 176), radius=8, fill=(5, 8, 13, 154), outline=(205, 216, 228, 120), width=2)
    draw.text((58, 104), scene.title, font=F_SUB, fill=(248, 250, 252))
    for i, line in enumerate(wrap(draw, scene.subtitle, F_SMALL, 770)[:1]):
        draw.text((58, 140 + i * 27), line, font=F_SMALL, fill=(226, 232, 240))
    img.alpha_composite(overlay)


def render_frame(frame_no: int) -> Image.Image:
    time_s = frame_no / FPS
    scene = active_scene(time_s)
    p = progress(scene, time_s)
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    draw_scene(draw, scene, p, frame_no)
    haze = Image.new("RGBA", img.size, (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(haze)
    if scene.key in {"nether", "bastion", "brutes", "template1", "template2", "barter", "lava", "debris"}:
        for i in range(14):
            x = int((i * 119 + frame_no * 0.7) % (WIDTH + 160)) - 80
            y = 140 + ((i * 53 + frame_no) % 380)
            hdraw.ellipse((x - 90, y - 28, x + 90, y + 28), fill=(110, 58, 42, 28))
    img.alpha_composite(haze.filter(ImageFilter.GaussianBlur(12)))
    draw_ui(img, scene, time_s)
    return img.convert("RGB")


def tone(freq: float, duration: float, volume: float, wave_type: str = "sine") -> np.ndarray:
    count = max(1, int(duration * SAMPLE_RATE))
    t = np.arange(count, dtype=np.float32) / SAMPLE_RATE
    if wave_type == "noise":
        rng = np.random.default_rng(int(freq * 1000 + duration * 100))
        data = rng.uniform(-1, 1, count).astype(np.float32)
    elif wave_type == "saw":
        data = 2 * ((t * freq) % 1) - 1
    else:
        data = np.sin(2 * np.pi * freq * t)
    fade_len = min(count // 2, int(SAMPLE_RATE * 0.06))
    if fade_len > 0:
        fade = np.linspace(0, 1, fade_len, dtype=np.float32)
        data[:fade_len] *= fade
        data[-fade_len:] *= fade[::-1]
    return data * volume


def add_clip(track: np.ndarray, start_s: float, clip: np.ndarray):
    start = int(start_s * SAMPLE_RATE)
    end = min(len(track), start + len(clip))
    if end > start:
        track[start:end] += clip[: end - start]


def save_soundtrack(duration_s: float) -> Path:
    audio = OUT_DIR / "minecraft_netherite_journey_soundtrack.wav"
    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    track = 0.10 * np.sin(2 * np.pi * 48 * t) + 0.045 * np.sin(2 * np.pi * 96 * t)
    track *= 0.65 + 0.35 * np.sin(2 * np.pi * 0.14 * t)
    for sc in SCENES:
        add_clip(track, sc.start, tone(90, 0.55, 0.34, "saw"))
    for start in [1.5, 7.4, 60.5, 80.0, 88.6, 99.5, 104.0]:
        add_clip(track, start, tone(42, 1.1, 0.48))
        add_clip(track, start, tone(180, 0.35, 0.25, "noise"))
    for start in [26, 28, 30.2, 32.2, 35.2, 44.5, 52, 54.5, 72, 74.8, 77.5, 90.5, 94.5]:
        add_clip(track, start, tone(310, 0.22, 0.25, "saw"))
        add_clip(track, start + 0.06, tone(620, 0.16, 0.16))
    track = np.tanh(track * 0.9)
    pcm = (track * 32767).astype(np.int16)
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    return audio


def mux_audio(video: Path, audio: Path) -> Path:
    out = OUT_DIR / "minecraft_netherite_journey_with_sound.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([
        ffmpeg, "-y", "-i", str(video), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)
    ], check=True)
    return out


def save_storyboard():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = [{"scene": s.key, "title": s.title, "subtitle": s.subtitle, "start": s.start, "end": s.end} for s in SCENES]
    (OUT_DIR / "storyboard.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "subtitles.txt").write_text("\n".join(f"{s.start:05.1f}-{s.end:05.1f} {s.title}：{s.subtitle}" for s in SCENES) + "\n", encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    save_storyboard()
    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(exist_ok=True)
    silent = OUT_DIR / "minecraft_netherite_journey_silent.mp4"
    total = int(SCENES[-1].end * FPS)
    preview = {int(s.start * FPS) for s in SCENES} | {total - 1}
    writer = imageio.get_writer(silent, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    try:
        for frame in range(total):
            img = render_frame(frame)
            if frame in preview:
                img.save(frames_dir / f"frame_{frame:04d}.png")
            writer.append_data(np.asarray(img))
            if frame % (FPS * 10) == 0:
                print(f"rendered {frame}/{total}")
    finally:
        writer.close()
    audio = save_soundtrack(SCENES[-1].end)
    final = mux_audio(silent, audio)
    print(final)
    print(audio)
    print(OUT_DIR / "storyboard.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
