#!/usr/bin/env python3
"""Generate a Minecraft-style 3D sequel video for the Herobrine fight.

This is a self-contained renderer for the current repository environment. It
uses deterministic, frame-indexed animation like a Remotion timeline, but draws
the blocky 3D scene directly with Pillow so no npm project setup is required.
"""

from __future__ import annotations

import json
import math
import random
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


OUT_DIR = Path("artifacts/minecraft_herobrine_sequel_video")
WIDTH, HEIGHT = 1280, 720
FPS = 24

SKY_TOP = (15, 20, 34)
SKY_BOTTOM = (44, 62, 86)
GROUND = (45, 91, 54)
GROUND_DARK = (31, 63, 43)
GROUND_FAR = (28, 61, 48)
STONE = (86, 93, 102)
STONE_DARK = (55, 63, 73)
DIAMOND = (85, 231, 236)
DIAMOND_DARK = (24, 145, 155)
ENCHANT = (126, 81, 255)
LIGHTNING = (166, 225, 255)
WHITE = (246, 251, 255)
BLACK = (12, 15, 20)
RED = (202, 47, 47)
GOLD = (240, 198, 82)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


F_TITLE = font(42, True)
F_SUB = font(32, True)
F_SMALL = font(22)
SAMPLE_RATE = 44_100


@dataclass(frozen=True)
class Scene:
    key: str
    title: str
    subtitle: str
    start: float
    end: float


SCENES = [
    Scene("catch", "接住神之一击", "史蒂夫和艾利克斯同时举剑，硬生生挡住 Herobrine 的重击。", 0, 9),
    Scene("offer", "Herobrine 的邀约", "Herobrine 吃惊地望着两人，嘴角勾起一抹笑：你们愿意为我效力吗？", 9, 19),
    Scene("refuse", "坚定回绝", "史蒂夫和艾利克斯：你是谁？从那个祭坛里出来就打我们，还想让我们给你效力？", 19, 30),
    Scene("creator", "创世神宣言", "Herobrine：我是这里的创世神。", 30, 38),
    Scene("clones", "分身围攻", "十几个分身从烟尘中冲出，却被两把附魔钻石剑轻松破解。", 38, 51),
    Scene("storm", "支配之剑", "闪电环绕 Herobrine，他落下并抽出蕴含雷霆之力的支配之剑。", 51, 62),
    Scene("shockwave", "力场爆发", "三把剑撞在一起，强大的力场将史蒂夫和艾利克斯击飞。", 62, 72),
    Scene("notch", "Notch 赶到", "Notch 听闻动静来到此处，与 Herobrine 展开大战。", 72, 84),
    Scene("seal", "险胜封印", "最后 Notch 险胜，将 Herobrine 重新封印进祭坛。", 84, 94),
    Scene("ending", "白光未灭", "艾利克斯发现：只要史蒂夫还在，Herobrine 就不会消失！", 94, 104),
]


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def smoothstep(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp(t, 0.0, 1.0)


def mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


class Renderer:
    def __init__(self, draw: ImageDraw.ImageDraw, time_s: float):
        self.draw = draw
        self.time_s = time_s
        self.items: list[tuple[float, list[tuple[float, float]], tuple[int, int, int]]] = []
        self.yaw = -0.76 + math.sin(time_s * 0.09) * 0.08
        self.pitch = 0.62
        self.scale = 54
        self.cx = WIDTH * 0.51
        self.cy = HEIGHT * 0.56

    def project(self, p: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = p
        cyaw, syaw = math.cos(self.yaw), math.sin(self.yaw)
        xp = x * cyaw - z * syaw
        zp = x * syaw + z * cyaw
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        yp = y * cp - zp * sp
        depth = y * sp + zp * cp
        return self.cx + xp * self.scale, self.cy - yp * self.scale, depth

    def add_poly(self, pts3: Iterable[tuple[float, float, float]], color: tuple[int, int, int]):
        pts = [self.project(p) for p in pts3]
        depth = sum(p[2] for p in pts) / len(pts)
        self.items.append((depth, [(p[0], p[1]) for p in pts], color))

    def cuboid(
        self,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        color: tuple[int, int, int],
        shade: float = 1.0,
    ):
        x, y, z = center
        sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
        v = {
            "lbf": (x - sx, y - sy, z - sz),
            "rbf": (x + sx, y - sy, z - sz),
            "rtf": (x + sx, y + sy, z - sz),
            "ltf": (x - sx, y + sy, z - sz),
            "lbb": (x - sx, y - sy, z + sz),
            "rbb": (x + sx, y - sy, z + sz),
            "rtb": (x + sx, y + sy, z + sz),
            "ltb": (x - sx, y + sy, z + sz),
        }
        faces = [
            ([v["lbf"], v["rbf"], v["rtf"], v["ltf"]], mix(color, BLACK, 0.20 * shade)),
            ([v["rbb"], v["lbb"], v["ltb"], v["rtb"]], mix(color, WHITE, 0.05)),
            ([v["lbb"], v["lbf"], v["ltf"], v["ltb"]], mix(color, BLACK, 0.32 * shade)),
            ([v["rbf"], v["rbb"], v["rtb"], v["rtf"]], mix(color, BLACK, 0.08 * shade)),
            ([v["ltf"], v["rtf"], v["rtb"], v["ltb"]], mix(color, WHITE, 0.16)),
        ]
        for pts, col in faces:
            self.add_poly(pts, col)

    def flush(self):
        for _, pts, color in sorted(self.items, key=lambda x: x[0], reverse=True):
            self.draw.polygon(pts, fill=color)
            self.draw.line(pts + [pts[0]], fill=mix(color, BLACK, 0.35), width=1)


def draw_gradient(img: Image.Image):
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        draw.line((0, y, WIDTH, y), fill=mix(SKY_TOP, SKY_BOTTOM, y / HEIGHT))
    draw.rectangle((0, int(HEIGHT * 0.70), WIDTH, HEIGHT), fill=(17, 29, 27))



def draw_stage_floor(draw: ImageDraw.ImageDraw, time_s: float):
    horizon = int(HEIGHT * 0.66)
    draw.polygon(
        [(0, horizon), (WIDTH, horizon), (WIDTH, HEIGHT), (0, HEIGHT)],
        fill=GROUND_FAR,
    )
    for i in range(18):
        t0 = i / 18
        t1 = (i + 1) / 18
        y0 = int(lerp(horizon, HEIGHT + 70, t0 * t0))
        y1 = int(lerp(horizon, HEIGHT + 70, t1 * t1))
        color = mix(GROUND, GROUND_DARK, 0.35 + 0.35 * (i % 2))
        draw.polygon([(0, y0), (WIDTH, y0), (WIDTH, y1), (0, y1)], fill=color)
    center = WIDTH * 0.52 + math.sin(time_s * 0.18) * 20
    for i in range(-12, 13):
        x = center + i * 86
        spread = i * 28
        draw.line((x, horizon, x + spread, HEIGHT), fill=(57, 104, 66), width=2)
    for i in range(10):
        y = int(lerp(horizon, HEIGHT, (i / 10) ** 1.85))
        draw.line((0, y, WIDTH, y), fill=(58, 108, 67), width=2)

def active_scene(time_s: float) -> Scene:
    for scene in SCENES:
        if scene.start <= time_s < scene.end:
            return scene
    return SCENES[-1]


def scene_progress(scene: Scene, time_s: float) -> float:
    return (time_s - scene.start) / (scene.end - scene.start)


def lightning(draw: ImageDraw.ImageDraw, seed: int, start: tuple[float, float], end: tuple[float, float], width: int = 4):
    rng = random.Random(seed)
    pts = [start]
    steps = 8
    for i in range(1, steps):
        t = i / steps
        x = lerp(start[0], end[0], t) + rng.uniform(-22, 22)
        y = lerp(start[1], end[1], t) + rng.uniform(-18, 18)
        pts.append((x, y))
    pts.append(end)
    draw.line(pts, fill=(224, 249, 255), width=width)
    draw.line(pts, fill=LIGHTNING, width=max(1, width // 2))


def world_positions(scene: Scene, p: float) -> dict[str, tuple[float, float, float]]:
    steve = (-2.2, 1.15, 0.6)
    alex = (-0.6, 1.15, 1.6)
    hero = (1.3, 1.25, -1.2)
    notch = (4.3, 1.25, 1.1)
    if scene.key == "catch":
        hero = (lerp(2.2, 1.0, p), 1.95 + math.sin(p * math.pi) * 0.5, lerp(-2.2, -0.9, p))
    elif scene.key == "offer":
        hero = (1.0, 1.25, -0.8)
    elif scene.key == "refuse":
        steve = (-2.3, 1.15, 0.2)
        alex = (-0.7, 1.15, 1.25)
        hero = (1.1, 1.25, -1.0)
    elif scene.key == "storm":
        hero = (0.9, lerp(2.9, 1.25, smoothstep(p)), -1.0)
    elif scene.key == "shockwave":
        blast = smoothstep(p)
        steve = (lerp(-2.0, -4.5, blast), 1.15 + math.sin(blast * math.pi) * 1.0, lerp(0.5, 1.6, blast))
        alex = (lerp(-0.6, -3.0, blast), 1.15 + math.sin(blast * math.pi) * 0.8, lerp(1.5, 3.0, blast))
        hero = (0.8, 1.25, -0.6)
    elif scene.key in {"notch", "seal"}:
        notch = (lerp(5.8, 2.1, smoothstep(p)) if scene.key == "notch" else 2.0, 1.25, 0.6)
        hero = (0.5 + math.sin(p * math.pi * 4) * 0.8, 1.25, -0.8)
        steve = (-4.5, 1.15, 1.6)
        alex = (-3.0, 1.15, 3.0)
    elif scene.key == "ending":
        steve = (-1.4, 1.15, 0.7)
        alex = (-0.1, 1.15, 1.9)
        hero = (0.5, -0.3, -1.0)
        notch = (2.1, 1.25, 0.4)
    return {"steve": steve, "alex": alex, "hero": hero, "notch": notch}


def draw_sword(r: Renderer, base: tuple[float, float, float], angle: float, color: tuple[int, int, int], long: float = 1.7):
    x, y, z = base
    dx, dz = math.cos(angle), math.sin(angle)
    r.cuboid((x + dx * 0.55, y + 0.05, z + dz * 0.55), (0.14, 0.12, long), color)
    r.cuboid((x - dx * 0.10, y - 0.04, z - dz * 0.10), (0.52, 0.14, 0.16), (91, 62, 35))


def character(
    r: Renderer,
    name: str,
    pos: tuple[float, float, float],
    facing: float,
    sword: bool = False,
    sword_power: bool = False,
    eyes_white: bool = False,
    ghost: bool = False,
):
    alpha_shade = 0.55 if ghost else 1.0
    x, y, z = pos
    if name == "steve":
        skin, shirt, pants, hair = (169, 111, 72), (52, 168, 176), (52, 76, 146), (64, 40, 25)
    elif name == "alex":
        skin, shirt, pants, hair = (207, 139, 84), (92, 180, 83), (87, 105, 152), (205, 106, 42)
    elif name == "notch":
        skin, shirt, pants, hair = (180, 118, 76), (78, 127, 82), (74, 70, 116), (42, 30, 22)
    else:
        skin, shirt, pants, hair = (166, 110, 76), (35, 135, 142), (44, 60, 116), (32, 28, 26)
    skin = mix(skin, WHITE, 0.18) if ghost else skin
    shirt = mix(shirt, WHITE, 0.20) if ghost else shirt
    pants = mix(pants, WHITE, 0.20) if ghost else pants
    r.cuboid((x - 0.18, y - 0.58, z), (0.34, 1.10, 0.34), pants, alpha_shade)
    r.cuboid((x + 0.18, y - 0.58, z), (0.34, 1.10, 0.34), pants, alpha_shade)
    r.cuboid((x, y + 0.18, z), (0.92, 1.20, 0.42), shirt, alpha_shade)
    r.cuboid((x - 0.64, y + 0.13, z), (0.30, 1.08, 0.30), skin, alpha_shade)
    r.cuboid((x + 0.64, y + 0.13, z), (0.30, 1.08, 0.30), skin, alpha_shade)
    r.cuboid((x, y + 1.03, z), (0.76, 0.76, 0.76), skin, alpha_shade)
    r.cuboid((x, y + 1.26, z - 0.03), (0.82, 0.18, 0.82), hair, alpha_shade)
    eye_col = WHITE if (eyes_white or name == "hero") else (30, 55, 75)
    # Eye blocks are tiny cuboids pushed toward the camera-facing side.
    r.cuboid((x - 0.16, y + 1.08, z - 0.40), (0.13, 0.11, 0.04), eye_col)
    r.cuboid((x + 0.16, y + 1.08, z - 0.40), (0.13, 0.11, 0.04), eye_col)
    if sword:
        sword_col = (244, 248, 255) if sword_power else DIAMOND
        draw_sword(r, (x + 0.72, y + 0.35, z - 0.25), facing, sword_col, 1.9)


def draw_world(draw: ImageDraw.ImageDraw, scene: Scene, p: float, time_s: float):
    r = Renderer(draw, time_s)
    # Broken altar.
    for dx, dz in [(-0.6, -1.8), (0.6, -1.8), (-0.6, -0.7), (0.6, -0.7)]:
        r.cuboid((dx, 0.25, dz), (0.9, 0.7, 0.9), STONE)
    r.cuboid((0.0, 0.76, -1.25), (1.6, 0.34, 1.6), STONE_DARK)
    r.cuboid((0.0, 1.04, -1.25), (1.1, 0.22, 1.1), (58, 50, 82))
    pos = world_positions(scene, p)

    if scene.key == "clones":
        for i in range(14):
            a = i / 14 * math.tau + p * 2.8
            radius = 2.6 + math.sin(p * math.pi * 3 + i) * 0.35
            character(r, "hero", (math.cos(a) * radius - 0.1, 1.13, math.sin(a) * radius - 0.2), a, True, False, True, True)

    steve_white = scene.key == "ending" and p > 0.45 and int(time_s * 7) % 2 == 0
    character(r, "steve", pos["steve"], -0.2, True, False, steve_white)
    character(r, "alex", pos["alex"], -0.3, True)
    if scene.key != "ending" or p < 0.62:
        character(r, "hero", pos["hero"], math.pi, True, scene.key in {"storm", "shockwave"}, True)
    if scene.key in {"notch", "seal", "ending"}:
        character(r, "notch", pos["notch"], math.pi, True)
    r.flush()

    # Screen-space effects.
    if scene.key in {"catch", "shockwave"}:
        center = (WIDTH * 0.53, HEIGHT * 0.43)
        radius = int(lerp(42, 260 if scene.key == "shockwave" else 120, smoothstep(p)))
        for k in range(4):
            draw.ellipse(
                (center[0] - radius - k * 16, center[1] - radius * 0.5 - k * 8, center[0] + radius + k * 16, center[1] + radius * 0.5 + k * 8),
                outline=mix(LIGHTNING, ENCHANT, k / 4),
                width=max(2, 8 - k * 2),
            )
    if scene.key in {"storm", "shockwave", "notch"}:
        for i in range(8):
            x = WIDTH * (0.35 + 0.35 * random.Random(int(time_s * 24) + i).random())
            lightning(draw, int(time_s * 60) + i, (x, 35), (WIDTH * 0.54 + i * 5, HEIGHT * 0.42), 5)
    if scene.key == "seal":
        center = (WIDTH * 0.53, HEIGHT * 0.45)
        for i in range(5):
            rr = int(lerp(270, 45, smoothstep(p)) + i * 18)
            draw.ellipse((center[0] - rr, center[1] - rr * 0.42, center[0] + rr, center[1] + rr * 0.42), outline=(110, 220, 255), width=4)
        draw.line((center[0] - 120, center[1] - 85, center[0] + 120, center[1] + 85), fill=WHITE, width=4)
        draw.line((center[0] - 120, center[1] + 85, center[0] + 120, center[1] - 85), fill=WHITE, width=4)
    if scene.key == "clones":
        for i in range(6):
            x = 260 + i * 130 + math.sin(time_s * 5 + i) * 25
            y = 430 + math.cos(time_s * 4 + i) * 35
            draw.arc((x - 70, y - 45, x + 70, y + 45), 20, 310, fill=DIAMOND, width=8)
            draw.arc((x - 88, y - 58, x + 88, y + 58), 40, 250, fill=ENCHANT, width=3)


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
    draw.text((34, 17), "Minecraft 3D: Herobrine 封印续章", font=F_TITLE, fill=WHITE)
    draw.text((WIDTH - 250, 28), f"{time_s:05.1f}s / {SCENES[-1].end:.0f}s", font=F_SMALL, fill=(190, 210, 225))
    draw.rounded_rectangle((34, 92, 760, 172), radius=8, fill=(5, 8, 13, 150), outline=(116, 140, 164, 130), width=2)
    draw.text((58, 104), scene.title, font=F_SUB, fill=(235, 244, 255))
    y = 140
    for line in wrap(draw, scene.subtitle, F_SMALL, 670)[:1]:
        draw.text((58, y), line, font=F_SMALL, fill=(220, 230, 240))
        y += 30
    img.alpha_composite(overlay)


def render_frame(frame_no: int) -> Image.Image:
    time_s = frame_no / FPS
    scene = active_scene(time_s)
    p = scene_progress(scene, time_s)
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    draw_gradient(img.convert("RGB"))
    rgb = Image.new("RGB", (WIDTH, HEIGHT), SKY_TOP)
    draw_gradient(rgb)
    img = rgb.convert("RGBA")
    draw = ImageDraw.Draw(img)
    # Low fog and dust.
    fog = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    fdraw = ImageDraw.Draw(fog)
    for i in range(18):
        x = int((i * 83 + frame_no * 0.8) % (WIDTH + 180)) - 90
        y = int(HEIGHT * 0.58 + math.sin(frame_no * 0.02 + i) * 24)
        fdraw.ellipse((x - 120, y - 30, x + 120, y + 30), fill=(80, 92, 100, 26))
    img.alpha_composite(fog.filter(ImageFilter.GaussianBlur(14)))
    draw_stage_floor(draw, time_s)
    draw_world(draw, scene, p, time_s)
    draw_ui(img, scene, time_s)
    return img.convert("RGB")



def tone(freq: float, duration: float, volume: float, wave_type: str = "sine") -> np.ndarray:
    count = max(1, int(duration * SAMPLE_RATE))
    t = np.arange(count, dtype=np.float32) / SAMPLE_RATE
    if wave_type == "saw":
        data = 2 * ((t * freq) % 1) - 1
    elif wave_type == "noise":
        rng = np.random.default_rng(int(freq * 1000 + duration * 100))
        data = rng.uniform(-1, 1, count).astype(np.float32)
    else:
        data = np.sin(2 * np.pi * freq * t)
    fade_len = min(count // 2, int(SAMPLE_RATE * 0.08))
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
    audio_path = OUT_DIR / "minecraft_herobrine_sequel_soundtrack.wav"
    samples = int(duration_s * SAMPLE_RATE)
    track = np.zeros(samples, dtype=np.float32)
    t = np.arange(samples, dtype=np.float32) / SAMPLE_RATE
    bed = 0.12 * np.sin(2 * np.pi * 47 * t) + 0.08 * np.sin(2 * np.pi * 94 * t)
    pulse = 0.55 + 0.45 * np.sin(2 * np.pi * 0.18 * t)
    track += bed * pulse
    for scene in SCENES:
        add_clip(track, scene.start, tone(82, 0.75, 0.42, "saw"))
    for start in [1.2, 5.4, 52.0, 55.8, 62.2, 72.6, 86.0, 94.3]:
        add_clip(track, start, tone(38, 1.2, 0.55, "sine"))
        add_clip(track, start, tone(110, 0.45, 0.34, "noise"))
    for start in [39.0, 41.5, 44.0, 46.5, 49.0, 63.0, 66.0, 74.0, 77.0, 80.0]:
        add_clip(track, start, tone(260, 0.28, 0.30, "saw"))
        add_clip(track, start + 0.08, tone(520, 0.18, 0.20, "sine"))
    track = np.tanh(track * 0.85)
    pcm = (track * 32767).astype(np.int16)
    with wave.open(str(audio_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    return audio_path


def mux_audio(video_path: Path, audio_path: Path) -> Path:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out_path = video_path.with_name("minecraft_herobrine_sequel_3d_with_sound.mp4")
    cmd = [
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
        "192k",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path

def save_storyboard():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = [
        {"scene": s.key, "title": s.title, "subtitle": s.subtitle, "start": s.start, "end": s.end}
        for s in SCENES
    ]
    (OUT_DIR / "storyboard.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "subtitles.txt").write_text(
        "\n".join(f"{s.start:05.1f}-{s.end:05.1f} {s.title}：{s.subtitle}" for s in SCENES) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    save_storyboard()
    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(exist_ok=True)
    video_path = OUT_DIR / "minecraft_herobrine_sequel_3d_silent.mp4"
    total_frames = int(SCENES[-1].end * FPS)
    preview_frames = {0, 9 * FPS, 19 * FPS, 38 * FPS, 51 * FPS, 62 * FPS, 72 * FPS, 84 * FPS, 94 * FPS, total_frames - 1}

    writer = imageio.get_writer(video_path, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    try:
        for frame_no in range(total_frames):
            frame = render_frame(frame_no)
            if frame_no in preview_frames:
                frame.save(frames_dir / f"frame_{frame_no:04d}.png")
            writer.append_data(np.asarray(frame))
            if frame_no % (FPS * 10) == 0:
                print(f"rendered {frame_no}/{total_frames}")
    finally:
        writer.close()
    audio_path = save_soundtrack(SCENES[-1].end)
    final_path = mux_audio(video_path, audio_path)
    print(final_path)
    print(audio_path)
    print(OUT_DIR / "storyboard.json")
    print(OUT_DIR / "subtitles.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
