#!/usr/bin/env python3
"""Generate a video that explains the recursion directly on the Feishu board."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts
import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


OUT_DIR = Path("artifacts/recursive_subsets_board_video")
BOARD_IMAGE = Path("artifacts/feishu_recursive_subsets_after_success_append/assets/board_VJPddNTLeo0ppTxxEaNcldKonCc_SQc1wvCsyhcLLjbaLeyc4gKenAd.jpg")
BOARD_NODES = Path("artifacts/feishu_recursive_subsets_after_success_append/assets/board_VJPddNTLeo0ppTxxEaNcldKonCc_SQc1wvCsyhcLLjbaLeyc4gKenAd_nodes.json")
WIDTH, HEIGHT = 1920, 1080
FPS = 24
VOICE = "zh-CN-XiaoxiaoNeural"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


F_TITLE = font(44, True)
F_BODY = font(30)
F_SMALL = font(23)
F_STEP = font(54, True)


def load_board():
    image = Image.open(BOARD_IMAGE).convert("RGB")
    nodes = json.loads(BOARD_NODES.read_text(encoding="utf-8"))
    tables = {n["id"]: n for n in nodes if n.get("type") != "connector"}
    connectors = []
    for n in nodes:
        if n.get("type") != "connector":
            continue
        c = n.get("connector", {})
        data = c.get("captions", {}).get("data", [])
        cap = data[0].get("text", "") if data else ""
        start = c.get("start_object", {}).get("id") or c.get("start", {}).get("attached_object", {}).get("id")
        end = c.get("end_object", {}).get("id") or c.get("end", {}).get("attached_object", {}).get("id")
        for part in cap.split("\n"):
            part = part.strip()
            if part.isdigit():
                connectors.append({"step": int(part), "start": start, "end": end, "node": n})
    connectors.sort(key=lambda x: x["step"])
    return image, tables, connectors


def board_bounds(nodes: list[dict]) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for n in nodes:
        xs.extend([n.get("x", 0), n.get("x", 0) + n.get("width", 0)])
        ys.extend([n.get("y", 0), n.get("y", 0) + n.get("height", 0)])
    return min(xs), min(ys), max(xs), max(ys)


def map_box(box, src_bounds, image_size):
    minx, miny, maxx, maxy = src_bounds
    iw, ih = image_size
    x1, y1, x2, y2 = box
    sx = iw / (maxx - minx)
    sy = ih / (maxy - miny)
    return (
        int((x1 - minx) * sx),
        int((y1 - miny) * sy),
        int((x2 - minx) * sx),
        int((y2 - miny) * sy),
    )


def union_boxes(boxes):
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def node_box(n, pad=70):
    return (n["x"] - pad, n["y"] - pad, n["x"] + n["width"] + pad, n["y"] + n["height"] + pad)


def connector_box(n, pad=120):
    return (n["x"] - pad, n["y"] - pad, n["x"] + n["width"] + pad, n["y"] + n["height"] + pad)


def crop_for_step(step, tables, connector):
    boxes = [connector_box(connector["node"])]
    for node_id in [connector["start"], connector["end"]]:
        if node_id in tables:
            boxes.append(node_box(tables[node_id]))
    return union_boxes(boxes)


def wrap(draw, text, ft, max_width):
    lines = []
    cur = ""
    for ch in text:
        if ch == "\n":
            if cur:
                lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if draw.textbbox((0, 0), trial, font=ft)[2] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def draw_overlay(base, step, caption):
    draw = ImageDraw.Draw(base)
    draw.rectangle((0, 0, WIDTH, 96), fill=(255, 255, 255))
    draw.line((0, 96, WIDTH, 96), fill=(210, 220, 235), width=2)
    draw.text((48, 22), "对着飞书画板讲：递归求子集 call stack", font=F_TITLE, fill=(31, 35, 41))
    draw.rounded_rectangle((48, 780, WIDTH - 48, 1030), radius=10, fill=(255, 255, 255), outline=(210, 220, 235), width=2)
    draw.rounded_rectangle((78, 812, 216, 944), radius=10, fill=(37, 99, 235))
    draw.text((104, 839), str(step), font=F_STEP, fill=(255, 255, 255))
    draw.text((236, 815), f"第 {step} 步", font=F_TITLE, fill=(31, 35, 41))
    y = 872
    for line in wrap(draw, caption, F_BODY, WIDTH - 310):
        draw.text((236, y), line, font=F_BODY, fill=(31, 35, 41))
        y += 42


def fit_crop_to_frame(board, src_bounds, crop_box, canvas_size):
    mapped = map_box(crop_box, src_bounds, board.size)
    x1, y1, x2, y2 = mapped
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(board.width, x2), min(board.height, y2)
    crop = board.crop((x1, y1, x2, y2))
    return ImageOps.contain(crop, canvas_size, method=Image.Resampling.LANCZOS)


def draw_full_board_locator(frame, board, src_bounds, crop_box, step, caption):
    draw = ImageDraw.Draw(frame)
    board_fit = ImageOps.contain(board, (1500, 900), method=Image.Resampling.LANCZOS)
    bx, by = (WIDTH - board_fit.width) // 2, 110
    frame.paste(board_fit, (bx, by))
    # Map current crop box into the fitted full-board image.
    x1, y1, x2, y2 = map_box(crop_box, src_bounds, board.size)
    sx, sy = board_fit.width / board.width, board_fit.height / board.height
    rect = (int(bx + x1 * sx), int(by + y1 * sy), int(bx + x2 * sx), int(by + y2 * sy))
    draw.rectangle(rect, outline=(220, 38, 38), width=8)
    draw.rounded_rectangle((42, 36, 430, 96), radius=8, fill=(255, 255, 255), outline=(210, 220, 235), width=2)
    draw.text((64, 45), f"第 {step} 步：先看画板位置", font=F_BODY, fill=(31, 35, 41))
    draw.rounded_rectangle((70, 910, WIDTH - 70, 1040), radius=10, fill=(255, 255, 255), outline=(210, 220, 235), width=2)
    for i, line in enumerate(wrap(draw, caption, F_BODY, WIDTH - 180)[:2]):
        draw.text((100, 930 + i * 40), line, font=F_BODY, fill=(31, 35, 41))


def draw_zoom_frame(frame, board, src_bounds, crop_box, step, caption):
    draw = ImageDraw.Draw(frame)
    crop = fit_crop_to_frame(board, src_bounds, crop_box, (WIDTH - 80, 760))
    x, y = (WIDTH - crop.width) // 2, 30
    frame.paste(crop, (x, y))
    draw.rectangle((x, y, x + crop.width, y + crop.height), outline=(37, 99, 235), width=6)
    # Bottom subtitle band, compact so the board remains large.
    draw.rounded_rectangle((42, 820, WIDTH - 42, 1048), radius=10, fill=(255, 255, 255), outline=(210, 220, 235), width=2)
    draw.rounded_rectangle((70, 848, 188, 966), radius=10, fill=(37, 99, 235))
    draw.text((94, 874), str(step), font=F_STEP, fill=(255, 255, 255))
    draw.text((220, 846), f"第 {step} 步", font=F_TITLE, fill=(31, 35, 41))
    yy = 908
    for line in wrap(draw, caption, F_BODY, WIDTH - 300)[:3]:
        draw.text((220, yy), line, font=F_BODY, fill=(31, 35, 41))
        yy += 40


def draw_return_frame(frame, board, src_bounds, crop_box, step):
    draw = ImageDraw.Draw(frame)
    board_fit = ImageOps.contain(board, (1380, 880), method=Image.Resampling.LANCZOS)
    bx, by = (WIDTH - board_fit.width) // 2, 70
    frame.paste(board_fit, (bx, by))
    x1, y1, x2, y2 = map_box(crop_box, src_bounds, board.size)
    sx, sy = board_fit.width / board.width, board_fit.height / board.height
    rect = (int(bx + x1 * sx), int(by + y1 * sy), int(bx + x2 * sx), int(by + y2 * sy))
    draw.rectangle(rect, outline=(22, 163, 74), width=6)
    draw.rounded_rectangle((52, 940, WIDTH - 52, 1038), radius=10, fill=(255, 255, 255), outline=(210, 220, 235), width=2)
    draw.text((86, 965), f"第 {step} 步结束，回到全图看下一条连线。", font=F_BODY, fill=(31, 35, 41))


def make_frame(board, src_bounds, crop_box, step, caption, mode='zoom'):
    frame = Image.new("RGB", (WIDTH, HEIGHT), (246, 248, 252))
    if mode == 'full':
        draw_full_board_locator(frame, board, src_bounds, crop_box, step, caption)
    elif mode == 'return':
        draw_return_frame(frame, board, src_bounds, crop_box, step)
    else:
        draw_zoom_frame(frame, board, src_bounds, crop_box, step, caption)
    return frame


CAPTIONS = {
    1: "主函数调用子集函数，画板从 main 指向根栈帧。当前路径为空，起点是零。",
    2: "根栈帧先收集空集，然后选择数字一，递归进入 sub 等于一的栈帧。",
    3: "在一这个栈帧中继续向下，选择二，进入一二分支。",
    4: "一二分支再选择三，进入最深的一二三栈帧。",
    5: "一二三已经没有后续数字，收集以后返回一二栈帧。",
    6: "回到一二以后，撤销刚才选择的三，然后返回一栈帧。",
    7: "在一这个栈帧里，先撤销二，当前路径恢复为一。",
    8: "一栈帧的循环继续，准备跳过二，改选三。",
    9: "从一分支选择三，进入一三栈帧。",
    10: "一三被收集后没有后续数字，于是返回一栈帧。",
    11: "回到一栈帧，撤销三，当前路径恢复为一。",
    12: "一栈帧的循环结束，所有以一开头的子集都处理完。",
    13: "一栈帧返回根栈帧，调用栈回到最外层。",
    14: "根栈帧里撤销一，当前路径重新变为空。",
    15: "根栈帧循环继续，准备选择数字二。",
    16: "根栈帧选择二，进入二这个栈帧。",
    17: "二栈帧收集二以后，只能继续选择三，进入二三。",
    18: "二三被收集后返回二栈帧。",
    19: "回到二栈帧，撤销三，当前路径恢复为二。",
    20: "二栈帧循环结束，返回根栈帧。",
    21: "根栈帧撤销二，当前路径又变为空。",
    22: "根栈帧循环继续，准备选择最后一个数字三。",
    23: "根栈帧选择三，进入三这个栈帧。",
    24: "三被收集后没有后续数字，返回根栈帧。",
    25: "根栈帧撤销三，最外层循环结束。",
    26: "根栈帧返回主函数，整个递归过程完成，答案已经全部收集。",
}


def voiceover_text():
    return "\n".join(CAPTIONS[i] for i in range(1, 27)) + "\n"


async def make_tts(text_path: Path, audio_path: Path):
    communicate = edge_tts.Communicate(text_path.read_text(encoding="utf-8"), VOICE, rate="+6%")
    await communicate.save(str(audio_path))


def ffmpeg_mux(video: Path, audio: Path, output: Path):
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
        "128k",
        "-shortest",
        str(output),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def ffmpeg_duration(path: Path) -> float:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    import re

    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not match:
        return 0.0
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    board, tables, connectors = load_board()
    nodes = list(tables.values()) + [c["node"] for c in connectors]
    src_bounds = board_bounds(nodes)
    text_path = OUT_DIR / "board_voiceover_tts.txt"
    audio_path = OUT_DIR / "board_voiceover_zh_cn.mp3"
    text_path.write_text(voiceover_text(), encoding="utf-8")
    asyncio.run(make_tts(text_path, audio_path))

    audio_duration = ffmpeg_duration(audio_path)
    per_step = max(3.0, audio_duration / 26.0)
    silent_video = OUT_DIR / "recursive_subsets_feishu_board_timed.mp4"
    final_video = OUT_DIR / "recursive_subsets_feishu_board_with_voice.mp4"
    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(exist_ok=True)

    writer = imageio.get_writer(silent_video, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    try:
        for item in connectors:
            step = item["step"]
            crop_box = crop_for_step(step, tables, item)
            phases = [
                (make_frame(board, src_bounds, crop_box, step, CAPTIONS[step], 'full'), 0.9),
                (make_frame(board, src_bounds, crop_box, step, CAPTIONS[step], 'zoom'), max(2.2, per_step - 1.4)),
                (make_frame(board, src_bounds, crop_box, step, CAPTIONS[step], 'return'), 0.5),
            ]
            if step in {1, 4, 9, 16, 23, 26}:
                phases[0][0].save(frames_dir / f"step_{step:02d}_full.png")
                phases[1][0].save(frames_dir / f"step_{step:02d}_zoom.png")
            for frame, seconds in phases:
                for _ in range(int(seconds * FPS)):
                    writer.append_data(np.asarray(frame))
    finally:
        writer.close()

    ffmpeg_mux(silent_video, audio_path, final_video)
    print(final_video)
    print(audio_path)
    print(text_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
