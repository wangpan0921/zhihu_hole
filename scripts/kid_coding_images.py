#!/usr/bin/env python3
"""少儿编程系列·自动配图工具（可程序化生成的部分）。

按课程号读取文章，自动生成三类可用 PIL 直接绘制的配图，输出到该课目录的 images/：
  1. cover.png       —— 像素风程序化封面（课程标题 + 系列标签）
  2. run_C.png       —— 每个 ```python 代码块渲染成代码/终端图；能无输入运行的，真跑出输出
  3. summary.png     —— 从「今天你学会了」小节的要点生成总结卡

不覆盖需要手工/AI 的部分：AI 插画封面、excalidraw 概念示意图（见各课 配图.md）。

生成完图片后，会自动读取同目录《配图.md》里每张图的「**插入位置**」，
把 images/ 里「真实存在」的图片以 Markdown 形式插入文章对应位置（幂等，可重复运行）。
没画的图（AI 插画 / excalidraw）会自动跳过，等图片补齐后再次运行即可补插。

用法：
    ./venv/bin/python scripts/kid_coding_images.py --lesson 2              # 生成图片并自动插图
    ./venv/bin/python scripts/kid_coding_images.py --lesson 2 --no-insert  # 只生成图片，不插图
    ./venv/bin/python scripts/kid_coding_images.py --lesson 2 --insert-only  # 只按《配图.md》插图
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
KID = ROOT / "kid_coding"
W, H = 1600, 900

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
GOLD = (240, 190, 40)
WOOD = (170, 122, 74)
WOOD_DARK = (120, 84, 48)
STICKY = (250, 224, 96)
CODE_BG = (248, 249, 245)
TERM_BG = (24, 28, 33)
TERM_FG = (180, 245, 180)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for c in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if c and Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


F_SERIES = font(30, True)
F_COVER = font(84, True)
F_COVER_SUB = font(40, True)
F_H = font(46, True)
F_BODY = font(34)
F_BODY_B = font(34, True)
F_CODE = font(32, True)
F_LABEL = font(28, True)


def blend(a, b, r):
    return tuple(int(a[i] + (b[i] - a[i]) * r) for i in range(3))


def tsize(d, t, f):
    box = d.textbbox((0, 0), t, font=f)
    return box[2] - box[0], box[3] - box[1]


def wrap(d, text, f, maxw):
    out = []
    for para in text.splitlines() or [text]:
        line = ""
        for ch in para:
            if tsize(d, line + ch, f)[0] <= maxw:
                line += ch
            else:
                out.append(line)
                line = ch
        out.append(line)
    return out


def rounded(d, box, fill, outline=BORDER, width=2, radius=14):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def base_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), SKY_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line((0, y, W, y), fill=blend(SKY_TOP, SKY_BOTTOM, y / H))
    gy = H - 60
    for bx in range(0, W, 60):
        d.rectangle((bx, gy, bx + 58, gy + 20), fill=GRASS if (bx // 60) % 2 == 0 else GRASS_DARK)
        d.rectangle((bx, gy + 20, bx + 58, H), fill=DIRT)
    return img, d


# ---------- markdown 提取 ----------
def parse(md: str):
    lines = md.splitlines()
    title = "本课"
    for ln in lines:
        s = ln.strip()
        if s.startswith("# ") and not s.startswith("## "):
            title = s[2:].strip()
            break
    # 代码块
    codes = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            lang = lines[i].strip()[3:].strip()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            if lang.startswith("python") or lang == "":
                codes.append("\n".join(buf))
        i += 1
    # 今天你学会了 要点
    summary = []
    in_sum = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("## "):
            in_sum = "今天你学会了" in s
            continue
        if in_sum and re.match(r"^\s*[-*]\s+", ln):
            item = re.sub(r"^\s*[-*]\s+", "", ln).strip()
            item = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", item).replace("**", "").replace("`", "")
            summary.append(item)
    return title, codes, summary


def clean_title(t: str) -> str:
    # 去掉破折号副标题，保留主标题更适合封面
    return re.split(r"[——]", t)[0].strip() or t


# ---------- 封面 ----------
def render_cover(title: str, lesson_no: int, corner: str, out: Path):
    img, d = base_canvas()
    # 漂浮方块装饰
    for (x, y, c) in [(1180, 150, GRASS), (1330, 230, WOOD), (1250, 340, GOLD)]:
        d.rectangle((x, y, x + 96, y + 96), fill=c, outline=WOOD_DARK, width=4)
    d.text((80, 90), f"我的世界里学编程 · 第 {lesson_no} 课", font=F_SERIES, fill=GREEN)
    main = clean_title(title)
    lines = wrap(d, main, F_COVER, W - 380)[:3]
    y = 210
    for ln in lines:
        d.text((80, y), ln, font=F_COVER, fill=INK)
        y += F_COVER.size + 18
    d.line((80, y + 6, 520, y + 6), fill=GREEN, width=6)
    d.text((80, H - 150), "跟着史蒂夫，从零打通信奥赛之路", font=F_COVER_SUB, fill=MUTED)
    img.save(out)


# ---------- 代码 / 终端图 ----------
def run_code(code: str) -> str | None:
    if "input(" in code:
        return None  # 需要交互输入，headless 跑不了
    try:
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        out = (p.stdout or "") + (p.stderr or "")
        return out.strip() or "(无输出)"
    except Exception:
        return None


def render_code_image(code: str, output: str | None, idx: int, out: Path):
    code_lines = code.splitlines() or [""]
    out_lines = output.splitlines() if output else []
    img, d = base_canvas()
    x0, y0 = 90, 90
    win_w = W - 180
    # 代码窗口
    ch = 70 + len(code_lines) * (F_CODE.size + 12) + 24
    rounded(d, (x0, y0, x0 + win_w, y0 + ch), CODE_BG, outline=BORDER, width=3, radius=16)
    for i, c in enumerate([(237, 106, 94), (245, 191, 79), (98, 197, 84)]):
        d.ellipse((x0 + 28 + i * 34, y0 + 24, x0 + 48 + i * 34, y0 + 44), fill=c)
    d.text((x0 + 150, y0 + 22), "code.py", font=F_LABEL, fill=MUTED)
    cy = y0 + 70
    for cl in code_lines:
        d.text((x0 + 34, cy), cl, font=F_CODE, fill=INK)
        cy += F_CODE.size + 12
    # 终端输出
    if out_lines:
        ty = y0 + ch + 30
        th = 64 + len(out_lines) * (F_CODE.size + 10) + 20
        rounded(d, (x0, ty, x0 + win_w, ty + th), TERM_BG, outline=TERM_BG, radius=16)
        d.text((x0 + 34, ty + 20), "▶ 运行结果", font=F_LABEL, fill=(150, 160, 170))
        oy = ty + 64
        for ol in out_lines:
            d.text((x0 + 34, oy), ol, font=F_CODE, fill=TERM_FG)
            oy += F_CODE.size + 10
    img.save(out)


# ---------- 总结卡 ----------
def render_summary(title: str, lesson_no: int, items: list[str], out: Path):
    img, d = base_canvas()
    d.text((80, 70), f"第 {lesson_no} 课 · 知识清单", font=F_SERIES, fill=GREEN)
    d.text((80, 118), "今天你学会了", font=F_H, fill=INK)
    d.line((80, 186, 460, 186), fill=GREEN, width=5)
    y = 230
    for it in items[:6]:
        parts = it.split("：", 1)
        key = parts[0].replace("`", "").strip()
        val = parts[1].strip() if len(parts) > 1 else ""
        kf = F_LABEL if tsize(d, key, F_LABEL)[0] <= 240 else font(20, True)
        kw = tsize(d, key, kf)[0]
        chip_w = max(190, kw + 32)
        rounded(d, (80, y, W - 80, y + 88), PANEL, outline=BORDER, width=3, radius=14)
        rounded(d, (100, y + 18, 100 + chip_w, y + 70), blend(GREEN, PANEL, 0.15), outline=GREEN, width=2, radius=10)
        d.text((116, y + 44 - kf.size // 2), key, font=kf, fill=INK)
        vx = 100 + chip_w + 28
        vl = wrap(d, val or key, F_BODY_B, W - 80 - vx - 20)[:1]
        if vl:
            d.text((vx, y + 26), vl[0], font=F_BODY_B, fill=INK)
        y += 104
        if y > H - 120:
            break
    img.save(out)


# ---------- 根据《配图.md》把图片插入文章对应位置 ----------
#
# 《配图.md》里每张图都有一行 `- **插入位置**：<描述>`。本模块把这些描述解析成
# 文章里的锚点，再把对应的图片以 Markdown 形式插进去。做到：
#   * 只插入 images/ 里「真实存在」的图片文件（AI 插画 / excalidraw 图没画就跳过）；
#   * 可重复运行（幂等）——已插入过的图不会重复插入；
#   * 找不到锚点时打印告警，不影响其它图。

# 「必配 / 加分 / 运行截图」等标签 -> 图片类型
FIG_HEADER_RE = re.compile(r"^##\s*图\s*(\d+)\s*【([^】]*)】\s*(.*)$")
POS_RE = re.compile(r"^\s*[-*]\s*\*\*插入位置\*\*[：:]\s*(.+?)\s*$")


def parse_illustration_plan(md: str) -> list[dict]:
    """解析《配图.md》，返回每张图的 {num, tags, title, pos} 列表（按图号顺序）。"""
    figs: list[dict] = []
    cur: dict | None = None
    for ln in md.splitlines():
        m = FIG_HEADER_RE.match(ln.strip())
        if m:
            cur = {
                "num": int(m.group(1)),
                "tags": m.group(2),
                "title": m.group(3).strip(),
                "pos": None,
            }
            figs.append(cur)
            continue
        if cur and cur["pos"] is None:
            pm = POS_RE.match(ln)
            if pm:
                cur["pos"] = pm.group(1).strip()
    return figs


def _existing(outdir: Path, name: str) -> str | None:
    return name if (outdir / name).exists() else None


def resolve_image_file(fig: dict, outdir: Path, run_pool: list[str]) -> str | None:
    """把一张「配图计划」映射到 images/ 里真实存在的文件名；映射不到返回 None。

    映射优先级：
      1) 明确的 figNN_*.png（新课的命名约定，与《配图.md》图号对应）；
      2) 封面 -> cover.png；总结卡 -> summary.png；预告图 -> preview_next.png；
      3) 运行截图 -> 按出现顺序取 run_01/run_02…（本脚本程序化生成的命名）。
    """
    tags = fig["tags"]
    num = fig["num"]

    # 1) 与图号对应的 figNN_*.png（若手工/JS 已按约定命名）
    hit = sorted(outdir.glob(f"fig{num:02d}_*.png"))
    if hit:
        return hit[0].name

    # 2) 语义化命名
    if "封面" in tags or num == 1:
        f = _existing(outdir, "cover.png")
        if f:
            return f
    if "总结卡" in tags:
        f = _existing(outdir, "summary.png")
        if f:
            return f
    if "预告" in tags:
        f = _existing(outdir, "preview_next.png")
        if f:
            return f

    # 3) 运行截图 -> 依次消费 run_NN.png
    if "运行截图" in tags and run_pool:
        return run_pool.pop(0)

    return None


def _norm(s: str) -> str:
    """归一化用于「节标题」模糊匹配：去掉空白与常见修饰后缀。"""
    s = re.sub(r"\s+", "", s)
    for suf in ("（I-do）", "(I-do)", "（We-do）", "(We-do)", "（You-do）", "(You-do)"):
        s = s.replace(suf, "")
    return s


def _heading_lines(lines: list[str]) -> list[tuple[int, str]]:
    """返回 [(行号, 标题文本)]，只取 ## / ### 级别的小节标题。"""
    out = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{2,4})\s+(.*)$", ln)
        if m:
            out.append((i, m.group(2).strip()))
    return out


def _section_end(lines: list[str], start: int) -> int:
    """给定某个标题所在行 start，返回该小节内容的结束行（下一个同级或更高级标题之前）。"""
    m = re.match(r"^(#{1,6})\s", lines[start])
    level = len(m.group(1)) if m else 2
    for i in range(start + 1, len(lines)):
        hm = re.match(r"^(#{1,6})\s", lines[i])
        if hm and len(hm.group(1)) <= level:
            return i
    return len(lines)


def _find_quote_anchor(lines: list[str], lo: int, hi: int, needle: str) -> int | None:
    """在 [lo, hi) 里找包含 needle（来自「插入位置」里的反引号片段）的行，返回其后一行。"""
    key = _norm(needle)
    if not key:
        return None
    for i in range(lo, hi):
        if key in _norm(lines[i]):
            return i + 1
    return None


def _seg_before_colon(s: str) -> str:
    """取冒号前的段（如「第三步：…」→「第三步」）；无冒号则原样返回。"""
    return re.split(r"[：:]", s, 1)[0]


def _overlap(a: str, b: str) -> float:
    """两个字符串的字符集重合比例（相对较短者），用于模糊匹配节标题。"""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def _best_heading(section_key: str, headings: list[tuple[int, str]]) -> int | None:
    """在 headings 里为「插入位置」抽出的节标题关键词找最匹配的一项，返回行号。"""
    nk = _norm(section_key)
    if not nk:
        return None
    # 1) 直接包含 / 前缀
    for i, title in headings:
        nt = _norm(title)
        if nk in nt or nt.startswith(nk):
            return i
    # 2) 冒号前的「第N步」等前缀一致（配图与文章常在后半句用词不同）
    key_prefix = _norm(_seg_before_colon(section_key))
    if key_prefix and key_prefix != nk:
        for i, title in headings:
            if _norm(_seg_before_colon(title)) == key_prefix:
                return i
    # 3) 字符重合度最高且过阈值
    best_i, best_score = None, 0.0
    for i, title in headings:
        sc = _overlap(nk, _norm(title))
        if sc > best_score:
            best_i, best_score = i, sc
    return best_i if best_score >= 0.6 else None


def resolve_anchor(pos: str, lines: list[str]) -> int | None:
    """把一句「插入位置」描述解析成文章里的插入行号（在该行之前插入）。找不到返回 None。"""
    headings = _heading_lines(lines)

    # 文章顶部封面：紧跟第一行 `# 标题` 之后
    if "顶部" in pos or "文章顶部" in pos:
        for i, ln in enumerate(lines):
            if re.match(r"^#\s+\S", ln):
                return i + 1
        return 1

    # 文末预告：定位到「下一篇/下期预告」小节
    if "文末" in pos or "预告" in pos:
        for i, title in headings:
            if "预告" in title or "下一篇" in title or "下期" in title:
                return _section_end(lines, i)
        # 没有专门的预告小节，就放到文末
        return len(lines)

    # 从「插入位置」里抽出带书名号「…」的节标题关键词
    quoted = re.findall(r"[「『]([^」』]+)[」』]", pos)
    section_key = quoted[0] if quoted else None

    target_heading_idx = None
    if section_key:
        target_heading_idx = _best_heading(section_key, headings)

    # 「今天你学会了」这类整节图：放在该节标题正下方
    if target_heading_idx is not None and ("学会了" in pos or "知识清单" in pos):
        return target_heading_idx + 1

    if target_heading_idx is not None:
        sec_start = target_heading_idx + 1
        sec_end = _section_end(lines, target_heading_idx)

        # 「节，`xxx` 之后」/「输出 xxx 之后」：优先锚定到代码/输出片段
        code_hints = re.findall(r"`([^`]+)`", pos)
        for hint in code_hints:
            anchor = _find_quote_anchor(lines, sec_start, sec_end, hint)
            if anchor is not None:
                return anchor
        # 「紧接真值表 markdown 之后」这类：退化为节末
        return sec_end

    # 兜底：整篇里找反引号片段
    code_hints = re.findall(r"`([^`]+)`", pos)
    for hint in code_hints:
        anchor = _find_quote_anchor(lines, 0, len(lines), hint)
        if anchor is not None:
            return anchor

    return None


def insert_images(folder: Path, art: Path) -> int:
    """读取同目录《配图.md》，把已生成的图片插入 art 对应位置。返回插入的图片数。"""
    plan_path = folder / "配图.md"
    if not plan_path.exists():
        print("（无《配图.md》，跳过自动插图）")
        return 0

    outdir = folder / "images"
    figs = parse_illustration_plan(plan_path.read_text(encoding="utf-8"))
    lines = art.read_text(encoding="utf-8").splitlines()

    # 运行截图池：本脚本按顺序生成 run_01.png、run_02.png…
    run_pool = sorted(p.name for p in outdir.glob("run_*.png"))

    # 计算每张图 -> (锚点行号, markdown)。先全部算好，再从后往前插，避免行号错位。
    planned: list[tuple[int, int, str]] = []  # (anchor, fig_num, md_line)
    for fig in figs:
        pos = fig.get("pos")
        if not pos:
            continue
        fname = resolve_image_file(fig, outdir, run_pool)
        if not fname:
            print(f"  · 图{fig['num']}【{fig['tags']}】暂无图片文件，跳过")
            continue
        rel = f"images/{fname}"
        # 幂等：文章里已引用过该图就跳过
        if any(rel in ln for ln in lines):
            print(f"  · 图{fig['num']} 已存在（{rel}），跳过")
            continue
        anchor = resolve_anchor(pos, lines)
        if anchor is None:
            print(f"  · 图{fig['num']} 找不到插入位置「{pos}」，跳过")
            continue
        md = f"![图{fig['num']}]({rel})"
        planned.append((anchor, fig["num"], md))

    if not planned:
        print("没有需要插入的新图片。")
        return 0

    # 从后往前插；同一锚点按图号升序稳定排列
    planned.sort(key=lambda t: (t[0], t[1]))
    for anchor, _num, md in sorted(planned, key=lambda t: t[0], reverse=True):
        block = ["", md, ""]
        lines[anchor:anchor] = block

    art.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已插入 {len(planned)} 张图片 → {art.name}")
    for anchor, num, md in planned:
        print(f"  + 图{num}: {md}")
    return len(planned)


def find_lesson(n: int):
    dirs = sorted(KID.glob(f"lesson-{n:02d}-*"))
    if not dirs:
        raise SystemExit(f"找不到第 {n} 课目录")
    folder = dirs[0]
    finals = sorted(folder.glob("lesson_*.md"))
    art = finals[0] if finals else (folder / "article.md")
    if not art.exists():
        raise SystemExit(f"第 {n} 课没有文章（lesson_*.md 或 article.md）")
    return folder, art


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, required=True)
    ap.add_argument(
        "--no-insert",
        action="store_true",
        help="只生成图片，不自动按《配图.md》插入文章（默认会插入）",
    )
    ap.add_argument(
        "--insert-only",
        action="store_true",
        help="不重新生成图片，只把已有图片按《配图.md》插入文章",
    )
    args = ap.parse_args()
    folder, art = find_lesson(args.lesson)
    corner = folder.name.split("-", 2)[-1]
    title, codes, summary = parse(art.read_text(encoding="utf-8"))
    outdir = folder / "images"
    outdir.mkdir(exist_ok=True)

    if not args.insert_only:
        made = []
        cover = outdir / "cover.png"
        render_cover(title, args.lesson, corner, cover)
        made.append(cover)

        for i, code in enumerate(codes, 1):
            out = run_code(code)
            p = outdir / f"run_{i:02d}.png"
            render_code_image(code, out, i, p)
            made.append(p)

        if summary:
            s = outdir / "summary.png"
            render_summary(title, args.lesson, summary, s)
            made.append(s)

        print(f"lesson={args.lesson} 生成 {len(made)} 张图 → {outdir}")
        for m in made:
            print(" -", m.name)

    if not args.no_insert:
        print("按《配图.md》插入图片：")
        insert_images(folder, art)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
