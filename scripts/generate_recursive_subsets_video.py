#!/usr/bin/env python3
"""Generate a narrated-subtitle explainer video for the recursive subsets article.

The current environment does not provide a Chinese TTS engine, so this produces
an MP4 with visual narration text and a separate voiceover script.
"""

from __future__ import annotations

import json
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path("artifacts/recursive_subsets_video")
WIDTH, HEIGHT = 1920, 1080
FPS = 24
BG = (247, 249, 252)
INK = (31, 35, 41)
MUTED = (100, 116, 139)
BLUE = (37, 99, 235)
GREEN = (22, 163, 74)
ORANGE = (234, 88, 12)
RED = (220, 38, 38)
CARD = (255, 255, 255)
BORDER = (214, 222, 235)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    if bold:
        candidates.insert(0, "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


F_TITLE = font(54, True)
F_H2 = font(38, True)
F_BODY = font(31)
F_SMALL = font(24)
F_CODE = font(27)
F_STEP = font(42, True)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, ft: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        current = ""
        for ch in para:
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


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill=WHITE if False else CARD, outline=BORDER, radius=8, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_text_block(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, ft: ImageFont.ImageFont, fill=INK, max_width=760, line_gap=12) -> int:
    x, y = xy
    for line in wrap_text(draw, text, ft, max_width):
        draw.text((x, y), line, font=ft, fill=fill)
        y += ft.size + line_gap
    return y


def draw_code(draw: ImageDraw.ImageDraw, x: int, y: int):
    code = [
        "ans.emplace_back(sub);",
        "for (int i = start; i < s; i++) {",
        "    sub.emplace_back(nums[i]);",
        "    subsets(nums, sub, ans, i + 1);",
        "    sub.pop_back();",
        "}",
    ]
    rounded(draw, (x, y, x + 760, y + 255), fill=(15, 23, 42), outline=(30, 41, 59))
    yy = y + 26
    for i, line in enumerate(code):
        color = (226, 232, 240)
        if i == 0:
            color = (134, 239, 172)
        elif i in (2, 4):
            color = (253, 186, 116)
        elif i == 3:
            color = (147, 197, 253)
        draw.text((x + 28, yy), line, font=F_CODE, fill=color)
        yy += 36


def draw_stack(draw: ImageDraw.ImageDraw, x: int, y: int, stack: list[str], active: str | None = None):
    draw.text((x, y), "Call Stack", font=F_H2, fill=INK)
    yy = y + 62
    for item in stack:
        fill = (219, 234, 254) if item == active else CARD
        outline = BLUE if item == active else BORDER
        rounded(draw, (x, yy, x + 520, yy + 76), fill=fill, outline=outline, radius=8, width=3 if item == active else 2)
        draw.text((x + 24, yy + 18), item, font=F_BODY, fill=INK)
        yy += 92


def draw_answer(draw: ImageDraw.ImageDraw, x: int, y: int, ans: list[str]):
    draw.text((x, y), "ans 已收集", font=F_H2, fill=INK)
    yy = y + 60
    line = ""
    for item in ans:
        token = item + "  "
        if len(line + token) > 34:
            draw.text((x, yy), line, font=F_BODY, fill=GREEN)
            yy += 42
            line = token
        else:
            line += token
    if line:
        draw.text((x, yy), line, font=F_BODY, fill=GREEN)


def frame_base(title: str, subtitle: str | None = None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, WIDTH, 92), fill=(255, 255, 255))
    draw.line((0, 92, WIDTH, 92), fill=BORDER, width=2)
    draw.text((64, 24), title, font=F_TITLE, fill=INK)
    if subtitle:
        draw.text((64, 96), subtitle, font=F_SMALL, fill=MUTED)
    return img, draw


def render_scene(scene: dict) -> Image.Image:
    img, draw = frame_base(scene["title"])
    if scene.get("kind") == "intro":
        draw.text((120, 190), "LeetCode 78: 子集", font=F_TITLE, fill=BLUE)
        y = draw_text_block(draw, (120, 290), scene["body"], F_BODY, max_width=880, line_gap=14)
        draw_code(draw, 1040, 220)
        draw.text((1040, 520), "核心：进入节点先收集 sub，递归回来再 pop。", font=F_BODY, fill=INK)
        draw_answer(draw, 1040, 610, ["{}", "{1}", "{1,2}", "{1,2,3}", "{1,3}", "{2}", "{2,3}", "{3}"])
        return img

    if scene.get("kind") == "summary":
        draw.text((120, 190), "最终记住这一句", font=F_TITLE, fill=GREEN)
        draw_text_block(draw, (120, 300), scene["body"], F_BODY, max_width=980, line_gap=18)
        draw_code(draw, 1040, 270)
        draw_answer(draw, 1040, 600, ["{}", "{1}", "{1,2}", "{1,2,3}", "{1,3}", "{2}", "{2,3}", "{3}"])
        return img

    step = scene["step"]
    draw.text((70, 132), f"第 {step} 步", font=F_STEP, fill=BLUE)
    draw_text_block(draw, (70, 202), scene["explain"], F_BODY, max_width=760, line_gap=12)
    draw_stack(draw, 930, 150, scene["stack"], scene.get("active"))
    draw_answer(draw, 930, 735, scene.get("ans", []))
    rounded(draw, (70, 735, 830, 950), fill=CARD, outline=BORDER)
    draw.text((100, 760), "当前动作", font=F_H2, fill=INK)
    draw_text_block(draw, (100, 826), scene["action"], F_BODY, max_width=690)
    return img


def scenes() -> list[dict]:
    s: list[dict] = [
        {
            "kind": "intro",
            "title": "递归求子集：26 步看懂 call stack",
            "body": "这段代码每进入一次 subsets，就把当前 sub 放进 ans；然后从 start 往后选择数字。递归返回时，pop_back 负责恢复现场。",
            "duration": 7.0,
        }
    ]

    data = [
        (1, "main 调用 subsets(nums, sub, ans, 0)，根栈帧创建。", "进入 root，sub 为空，start=0。", ["main", "subsets({})"], "subsets({})", ["{}"]),
        (2, "root 先收集空集，然后 i=0 选择 1，递归进入 {1}。", "push 1，新的 start 是 1。", ["main", "subsets({})", "subsets({1})"], "subsets({1})", ["{}","{1}"]),
        (3, "{1} 栈帧收集 {1}，继续 i=1 选择 2。", "push 2，递归进入 {1,2}。", ["main","subsets({})","subsets({1})","subsets({1,2})"], "subsets({1,2})", ["{}","{1}","{1,2}"]),
        (4, "{1,2} 栈帧选择 3，进入最深的 {1,2,3}。", "push 3，start=3。", ["main","subsets({})","subsets({1})","subsets({1,2})","subsets({1,2,3})"], "subsets({1,2,3})", ["{}","{1}","{1,2}","{1,2,3}"]),
        (5, "{1,2,3} 进入后立即收集；因为 start=3，没有数字可选，返回。", "最深栈帧结束，回到 {1,2}。", ["main","subsets({})","subsets({1})","subsets({1,2})"], "subsets({1,2})", ["{}","{1}","{1,2}","{1,2,3}"]),
        (6, "回到 {1,2} 后，递归调用结束，执行 pop 撤销 3。", "sub 从 {1,2,3} 恢复为 {1,2}。", ["main","subsets({})","subsets({1})","subsets({1,2})"], "subsets({1,2})", ["{}","{1}","{1,2}","{1,2,3}"]),
        (7, "{1,2} 这一层没有更多选择，返回 {1}。", "{1} 栈帧继续执行 pop，撤销 2。", ["main","subsets({})","subsets({1})"], "subsets({1})", ["{}","{1}","{1,2}","{1,2,3}"]),
        (8, "{1} 栈帧的 for 循环继续，i 从 1 走到 2。", "准备跳过 2，改选 3。", ["main","subsets({})","subsets({1})"], "subsets({1})", ["{}","{1}","{1,2}","{1,2,3}"]),
        (9, "{1} 中选择 3，进入 {1,3} 栈帧。", "push 3，start=3。", ["main","subsets({})","subsets({1})","subsets({1,3})"], "subsets({1,3})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}"]),
        (10, "{1,3} 收集后没有后续数字，返回 {1}。", "ans 新增 {1,3}。", ["main","subsets({})","subsets({1})"], "subsets({1})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}"]),
        (11, "回到 {1}，执行 pop 撤销 3。", "sub 恢复为 {1}。", ["main","subsets({})","subsets({1})"], "subsets({1})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}"]),
        (12, "{1} 的循环结束。", "所有以 1 开头的分支都完成。", ["main","subsets({})","subsets({1})"], "subsets({1})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}"]),
        (13, "{1} 栈帧返回 root。", "调用栈回到 subsets({})。", ["main","subsets({})"], "subsets({})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}"]),
        (14, "root 中递归 {1} 返回后，执行 pop 撤销 1。", "sub 从 {1} 恢复为空。", ["main","subsets({})"], "subsets({})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}"]),
        (15, "root 的 for 循环继续，i 从 0 到 1。", "准备选择数字 2。", ["main","subsets({})"], "subsets({})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}"]),
        (16, "root 选择 2，进入 {2} 栈帧。", "push 2，start=2。", ["main","subsets({})","subsets({2})"], "subsets({2})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}"]),
        (17, "{2} 收集后，只能继续选择 3。", "进入 {2,3}。", ["main","subsets({})","subsets({2})","subsets({2,3})"], "subsets({2,3})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}"]),
        (18, "{2,3} 收集后没有后续数字，返回 {2}。", "ans 新增 {2,3}。", ["main","subsets({})","subsets({2})"], "subsets({2})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}"]),
        (19, "回到 {2}，执行 pop 撤销 3。", "sub 恢复为 {2}。", ["main","subsets({})","subsets({2})"], "subsets({2})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}"]),
        (20, "{2} 的循环结束，返回 root。", "以 2 开头的分支完成。", ["main","subsets({})"], "subsets({})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}"]),
        (21, "root 中递归 {2} 返回后，执行 pop 撤销 2。", "sub 再次恢复为空。", ["main","subsets({})"], "subsets({})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}"]),
        (22, "root 的 for 循环继续，i 从 1 到 2。", "准备选择最后一个数字 3。", ["main","subsets({})"], "subsets({})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}"]),
        (23, "root 选择 3，进入 {3} 栈帧。", "push 3，start=3。", ["main","subsets({})","subsets({3})"], "subsets({3})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}","{3}"]),
        (24, "{3} 收集后没有后续数字，返回 root。", "ans 新增 {3}。", ["main","subsets({})"], "subsets({})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}","{3}"]),
        (25, "root 执行最后一次 pop，撤销 3。", "root 的循环结束，sub 为空。", ["main","subsets({})"], "subsets({})", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}","{3}"]),
        (26, "root 返回 main，整个递归结束。", "call stack 清空，main 打印答案。", ["main"], "main", ["{}","{1}","{1,2}","{1,2,3}","{1,3}","{2}","{2,3}","{3}"]),
    ]
    for step, explain, action, stack, active, ans in data:
        s.append({"title": "递归求子集：26 步运行过程", "step": step, "explain": explain, "action": action, "stack": stack, "active": active, "ans": ans, "duration": 6.1})

    s.append({
        "kind": "summary",
        "title": "递归求子集：最后总结",
        "body": "这段代码本质是在一棵选择树上深度优先遍历：进入节点就收集当前路径；向下递归做选择；返回后 pop 撤销选择，再换下一条路。",
        "duration": 10.4,
    })
    return s


def save_voiceover(scenes_: list[dict]):
    lines = []
    for i, sc in enumerate(scenes_, 1):
        if sc.get("kind") == "intro":
            text = sc["body"]
        elif sc.get("kind") == "summary":
            text = sc["body"]
        else:
            text = f"第 {sc['step']} 步。{sc['explain']} {sc['action']}"
        lines.append(f"{i:02d}. {text}")
    (OUT_DIR / "voiceover_script.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scs = scenes()
    save_voiceover(scs)
    (OUT_DIR / "scenes.json").write_text(json.dumps(scs, ensure_ascii=False, indent=2), encoding="utf-8")

    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(exist_ok=True)
    video_path = OUT_DIR / "recursive_subsets_call_stack_explainer_tts_timed.mp4"

    writer = imageio.get_writer(video_path, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    try:
        frame_no = 0
        for scene in scs:
            img = render_scene(scene)
            if scene.get("step") in {1, 8, 16, 23, 26} or scene.get("kind") in {"intro", "summary"}:
                img.save(frames_dir / f"frame_{frame_no:04d}.png")
            repeat = int(scene["duration"] * FPS)
            for _ in range(repeat):
                writer.append_data(np.asarray(img))
                frame_no += 1
    finally:
        writer.close()

    print(video_path)
    print(OUT_DIR / "voiceover_script.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
