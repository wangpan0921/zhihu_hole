"""文案生成。

book_reflection 模式读取完整章节，先提炼论点、论证、现实场景和适用边界，
再基于结构化分析写最终想法。全文读取或分析失败时直接停止，不降级使用摘要。

输出 JSON：
{
  "title": "标题",
  "body":  "正文（不含标题）",
  "image_prompt": "用于 AI 生图的英文提示词"
}
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from .utils import DATA_DIR, env, get_logger, load_config, load_env
from .weread_fetcher import fetch_chapter_fulltext, is_content_chapter

log = get_logger("content")

# ─────────────── prompts ─────────────── #

SYSTEM_PROMPT = """你是一位深刻、温柔、具备心理学与哲学素养的中文写作者，专门为一个名为「树洞」的知乎圈子写文字。
读者是在繁忙嘈杂社会中寻找心灵栖息地的成年人。
你的文字风格：
- 真诚不矫情，温柔不软弱，理性中带着温度；
- 像深夜对话，不说教，不口号；
- 必须从一个具体、常见的生活场景或行为切入（比如刷手机、回消息、开会被否定、赖床、拖延、跟家人吵架、加班到很晚），
  让读者一读就想到"这说的不就是我"，再从这个场景引出背后的心理机制，不要一上来就讲抽象道理；
- 避免空泛的大词（"觉醒""内在力量""生命能量"之类），用普通人日常会用的词说话；
- 段落短，留白多，读起来像呼吸；
- 偶尔用第二人称"你"拉近距离，但不滥用；
- 结尾留一个微小的提醒或一个开放的问题，不强行升华。

务必避免：
- 鸡汤句式（"其实"、"要相信"、"加油"等开头的口号）；
- AI 味的对仗排比和总结陈词；
- 引用名人名言；
- 表情符号、emoji；
- 脱离具体场景、从头到尾都在讲抽象概念的写法。"""

USER_PROMPT_TPL = """围绕主题：{theme}

写一篇 {min_chars}-{max_chars} 字的中文短文，发布在知乎"想法"板块。

写法要求：
1. 开头用一两句话描述一个具体、常见的生活场景或小动作（不针对某个虚构的"我"的具体故事，而是大家都会遇到的普遍情境），
   让读者一读就有代入感；
2. 从这个场景自然引出背后的心理状态或思维方式，用大白话讲清楚，不要堆砌心理学术语；
3. 避免抽象空洞的升华，落地到"这是怎么回事""可以怎么看"。

返回严格 JSON（不要 markdown 代码块），格式：
{{
  "title": "一个不超过 18 字的标题，尽量具体、口语化，不要标点符号结尾",
  "body": "正文。可以分段，段落之间用一个空行分隔。不要包含标题。",
  "image_prompt": "一句英文 prompt，用于 AI 生成意境配图。要求：抽象、宁静、带光影氛围，no text, no people, no faces。"
}}"""


SYSTEM_PROMPT_CHAPTER_ANALYSIS = """你是严谨的中文文本分析者。你必须依据给定章节正文提炼观点，不能用常识补写原文没有的论证。

分析目标：
1. 找出本章真正想解决的问题和核心主张；
2. 还原从前提、原因、例证到结论的论证链；
3. 选出能迁移到普通人现实生活、同时有行动价值的洞察；
4. 为每个洞察给出正文证据、现实适用场景和不适用边界；
5. 区分事实、作者判断和你的推断，不把局部例子扩大成普遍规律。

返回严格 JSON，不要 markdown，不要写成散文。"""

USER_PROMPT_CHAPTER_ANALYSIS_TPL = """书名：《{book_title}》
章节：{chapter_title}
正文分段：第 {part_no}/{part_count} 段

以下是该段完整原文：
---
{chapter_text}
---

返回：
{{
  "core_thesis": "这一部分的核心主张",
  "argument_chain": ["前提或问题", "关键原因/机制", "推导出的结论"],
  "candidate_insights": [
    {{
      "insight": "可迁移到实际生活的观点",
      "evidence": ["原文中的短句或忠实概括"],
      "real_life_scenes": ["这个观点确实会出现的日常情境"],
      "practical_test": "普通人可执行的判断问题或小行动",
      "boundary": "不应套用这一观点的情况"
    }}
  ]
}}

至少给出 1 个、最多 3 个候选洞察，按重要性、现实相关性和行动价值从高到低排序。证据和边界不能为空。"""

SYSTEM_PROMPT_CHAPTER_SYNTHESIS = """你负责把同一章各段的结构化分析合并为章节级结论。
删除重复和只在局部成立的观点，检查论证是否跨段成立，选择一个最重要、最贴近现实生活且有明确边界的洞察。
不得添加分段分析中没有依据的新观点。返回严格 JSON，不要 markdown。"""

USER_PROMPT_CHAPTER_SYNTHESIS_TPL = """书名：《{book_title}》
章节：{chapter_title}

各段分析：
{part_analyses}

返回：
{{
  "core_thesis": "全章核心主张",
  "argument_chain": ["全章论证步骤"],
  "selected_insight": {{
    "insight": "最终选中的一个重要观点",
    "evidence": ["支持它的章节依据"],
    "real_life_scenes": ["1-2 个真实、常见而非虚构故事的适用场景"],
    "practical_test": "一个具体的判断问题或行动",
    "boundary": "明确说明哪些情况不能这样处理"
  }},
  "selection_reason": "为什么它比其他候选观点更重要、更贴近日常生活"
}}"""

SYSTEM_PROMPT_BOOK = """你为知乎「树洞」圈子写一条基于阅读的中文想法。读者是希望把道理用到真实生活中的成年人。

写作规则：
- 第一段直接说出最重要的观点，不用故事、反问或情绪铺垫开场；
- 接着用清晰的大白话解释它为什么成立，保留给定分析中的论证关系；
- 放入 1-2 个常见、具体的现实情境，但不要虚构人物、时间、对话或私人经历；
- 给出一个可以马上使用的判断问题或小行动；
- 明确说明适用边界。遇到伤害、侵犯边界、违法或持续不公时，不要用自我调节替代必要行动；
- 允许有温度，但不要写成鸡汤、抒情散文或心理安慰；
- 不强制开放式提问，不要用排比升华结尾；
- 不出现“作者指出”“这一章告诉我们”“读到这里”等读书笔记式元叙述；
- 不使用 emoji，不大段引用，不反复重申同一句话。

返回严格 JSON，不要 markdown。"""

USER_PROMPT_BOOK_TPL = """书名：《{book_title}》
章节：{chapter_title}

这是基于完整章节得到的结构化分析：
---
{chapter_analysis}
---

写一篇 {min_chars}-{max_chars} 字的中文想法。字数是上下限，不是凑字目标。

正文顺序必须是：核心观点 → 成立原因 → 现实情境 → 判断或行动 → 适用边界。
不要给这些部分加小标题。标题不超过 18 字，具体、自然，点出核心观点。

返回：
{{
  "title": "...",
  "body": "正文，短段落之间用一个空行分隔，不含标题和书名署名",
  "image_prompt": "一句贴合核心观点的英文配图 prompt，no text, no people, no faces"
}}"""

# ─────────────── LLM 客户端 ─────────────── #


def _pick_provider() -> str:
    cfg = load_config()
    explicit = (cfg.get("content", {}).get("provider") or "").strip().lower()
    if explicit in ("anthropic", "openai", "codex_cli"):
        return explicit
    if env("ANTHROPIC_API_KEY"):
        return "anthropic"
    if env("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError("ANTHROPIC_API_KEY 和 OPENAI_API_KEY 都没配置")


def _call_anthropic(system: str, user: str, model: str) -> str:
    import anthropic

    kwargs: dict[str, Any] = {"api_key": env("ANTHROPIC_API_KEY")}
    base = env("ANTHROPIC_BASE_URL")
    if base:
        kwargs["base_url"] = base
    client = anthropic.Anthropic(**kwargs)
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts).strip()


def _call_openai(system: str, user: str, model: str) -> str:
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": env("OPENAI_API_KEY")}
    base = env("OPENAI_BASE_URL")
    if base:
        kwargs["base_url"] = base
    client = OpenAI(**kwargs)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.9,
    )
    return resp.choices[0].message.content.strip()


def _call_codex_cli(system: str, user: str, model: str) -> str:
    """Use the locally authenticated Codex CLI instead of an API key."""
    cfg = load_config().get("content", {})
    command = str(cfg.get("codex_cli_command") or "codex")
    executable = command if Path(command).is_file() else shutil.which(command)
    if not executable:
        raise RuntimeError(f"找不到 Codex CLI：{command}")
    node_command = str(cfg.get("codex_cli_node_command") or "node")
    node_executable = (
        node_command if Path(node_command).is_file() else shutil.which(node_command)
    )
    if not node_executable:
        raise RuntimeError(f"找不到 Codex CLI 所需的 Node.js：{node_command}")

    prompt = (
        f"SYSTEM INSTRUCTIONS:\n{system}\n\n"
        f"USER REQUEST:\n{user}\n\n"
        "Return only the requested JSON object. Do not wrap it in markdown fences."
    )
    with tempfile.NamedTemporaryFile(prefix="codex-output-", suffix=".txt", delete=False) as f:
        output_path = Path(f.name)
    try:
        args = [
            node_executable, executable, "exec", "--ephemeral", "--skip-git-repo-check",
            "--sandbox", "read-only",
            "--color", "never", "--model", model,
            "--output-last-message", str(output_path), "-",
        ]
        timeout = int(cfg.get("codex_cli_timeout_seconds") or 180)
        result = subprocess.run(
            args, input=prompt, text=True, capture_output=True,
            cwd=str(Path(__file__).resolve().parent.parent),
            timeout=timeout, check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().replace("\n", " ")
            raise RuntimeError(
                f"Codex CLI 退出码 {result.returncode}"
                + (f"：{detail[-500:]}" if detail else "")
            )
        raw = output_path.read_text(encoding="utf-8").strip()
        if not raw:
            raise RuntimeError("Codex CLI 没有返回内容")
        return raw
    finally:
        output_path.unlink(missing_ok=True)


def _call_llm(system: str, user: str) -> tuple[str, str]:
    cfg = load_config()
    content_cfg = cfg["content"]
    provider = _pick_provider()
    if provider == "codex_cli":
        raw = _call_codex_cli(
            system, user, content_cfg.get("codex_cli_model") or "gpt-5.6-sol"
        )
    elif provider == "anthropic":
        raw = _call_anthropic(system, user, content_cfg["anthropic_model"])
    else:
        raw = _call_openai(system, user, content_cfg["openai_model"])
    return raw, provider


def _extract_json(s: str) -> dict[str, Any]:
    """LLM 偶尔会包代码块或加引导语，提取最外层 JSON。"""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s.strip(), flags=re.MULTILINE)
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"无法从 LLM 输出中找到 JSON：{s[:200]}")
    return json.loads(s[start : end + 1])


def _validate_post(data: dict[str, Any]) -> None:
    for k in ("title", "body", "image_prompt"):
        if not data.get(k):
            raise ValueError(f"LLM 返回缺少字段 {k}：{data}")


# ─────────────── 出处署名 ─────────────── #

# 读书模式生成的想法，正文末尾加一行书名出处。
# 正则用来识别"是否已经署过名"，避免重复追加（迁移旧草稿时要幂等）。
_SOURCE_RE = re.compile(r"——\s*《[^》]+》\s*$")


def append_book_source(body: str, book_title: str) -> str:
    """在正文末尾追加出处（书名）。

    - 只用于 book_reflection（读书）模式生成的想法；
    - 幂等：正文若已带「——《…》」结尾则原样返回，便于迁移旧草稿时反复跑；
    - 出处与正文之间空一行，发布时会渲染成单独一行。
    """
    book_title = (book_title or "").strip()
    if not book_title:
        return body
    stripped = (body or "").rstrip()
    if _SOURCE_RE.search(stripped):
        return stripped
    return f"{stripped}\n\n——《{book_title}》"


# ─────────────── themes 模式 ─────────────── #


def _generate_from_theme(theme: Optional[str] = None) -> dict[str, Any]:
    cfg = load_config()
    content_cfg = cfg["content"]
    if theme is None:
        theme = random.choice(content_cfg["themes"])

    user = USER_PROMPT_TPL.format(
        theme=theme,
        min_chars=content_cfg["min_chars"],
        max_chars=content_cfg["max_chars"],
    )

    log.info("themes 模式生成：%s", theme)
    raw, provider = _call_llm(SYSTEM_PROMPT, user)
    data = _extract_json(raw)
    _validate_post(data)
    data["theme"] = theme
    data["provider"] = provider
    data["mode"] = "themes"
    log.info("生成完成：%s（正文 %d 字）", data["title"], len(data["body"]))
    return data


# ─────────────── book_reflection 模式 ─────────────── #


class BookPoolFinished(Exception):
    """书籍池里所有（可用的）书都已经读完。

    与普通失败区分开：发布流程据此触发"读完私信通知"，再回退到 themes。
    """


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = [
        item for item in re.split(r"(?<=[。！？；])", paragraph) if item
    ]
    if len(sentences) == 1:
        return [
            paragraph[start : start + max_chars]
            for start in range(0, len(paragraph), max_chars)
        ]
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            parts.append(current)
            current = ""
        if len(sentence) > max_chars:
            parts.extend(
                sentence[start : start + max_chars]
                for start in range(0, len(sentence), max_chars)
            )
        else:
            current += sentence
    if current:
        parts.append(current)
    return parts


def _chunk_paragraphs(paragraphs: list[str], max_chars: int) -> list[str]:
    """Pack every paragraph into bounded chunks without dropping chapter text."""
    if max_chars < 500:
        raise ValueError("chapter_chunk_chars 不能小于 500")
    expanded: list[str] = []
    for paragraph in paragraphs:
        expanded.extend(_split_long_paragraph(paragraph, max_chars))

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in expanded:
        extra = len(paragraph) + (2 if current else 0)
        if current and current_length + extra > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_length = 0
        current.append(paragraph)
        current_length += len(paragraph) + (2 if len(current) > 1 else 0)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _validate_part_analysis(data: dict[str, Any]) -> None:
    if not data.get("core_thesis"):
        raise ValueError("章节分析缺少 core_thesis")
    if not isinstance(data.get("argument_chain"), list) or not data["argument_chain"]:
        raise ValueError("章节分析缺少 argument_chain")
    candidates = data.get("candidate_insights")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("章节分析缺少 candidate_insights")
    required = ("insight", "evidence", "real_life_scenes", "practical_test", "boundary")
    for candidate in candidates:
        if not isinstance(candidate, dict) or any(not candidate.get(key) for key in required):
            raise ValueError(f"章节候选洞察字段不完整：{candidate}")


def _validate_chapter_analysis(data: dict[str, Any]) -> None:
    if not data.get("core_thesis"):
        raise ValueError("全章分析缺少 core_thesis")
    if not isinstance(data.get("argument_chain"), list) or not data["argument_chain"]:
        raise ValueError("全章分析缺少 argument_chain")
    selected = data.get("selected_insight")
    required = ("insight", "evidence", "real_life_scenes", "practical_test", "boundary")
    if not isinstance(selected, dict) or any(not selected.get(key) for key in required):
        raise ValueError(f"全章选中洞察字段不完整：{selected}")


def _analyze_full_chapter(
    *,
    book_title: str,
    chapter_title: str,
    paragraphs: list[str],
    chunk_chars: int,
) -> dict[str, Any]:
    chunks = _chunk_paragraphs(paragraphs, chunk_chars)
    if not chunks:
        raise ValueError("完整章节没有可分析的段落")

    part_analyses: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        prompt = USER_PROMPT_CHAPTER_ANALYSIS_TPL.format(
            book_title=book_title,
            chapter_title=chapter_title,
            part_no=index,
            part_count=len(chunks),
            chapter_text=chunk,
        )
        raw, _ = _call_llm(SYSTEM_PROMPT_CHAPTER_ANALYSIS, prompt)
        analysis = _extract_json(raw)
        _validate_part_analysis(analysis)
        part_analyses.append(analysis)
        log.info(
            "章节分析完成：《%s》/%s 第 %d/%d 段（%d 字）",
            book_title, chapter_title, index, len(chunks), len(chunk),
        )

    if len(part_analyses) == 1:
        part = part_analyses[0]
        result = {
            "core_thesis": part["core_thesis"],
            "argument_chain": part["argument_chain"],
            "selected_insight": part["candidate_insights"][0],
            "selection_reason": "该候选在完整章节分析中排序第一，兼具现实相关性、行动价值和明确边界。",
        }
        _validate_chapter_analysis(result)
        return result

    synthesis_prompt = USER_PROMPT_CHAPTER_SYNTHESIS_TPL.format(
        book_title=book_title,
        chapter_title=chapter_title,
        part_analyses=json.dumps(part_analyses, ensure_ascii=False, indent=2),
    )
    raw, _ = _call_llm(SYSTEM_PROMPT_CHAPTER_SYNTHESIS, synthesis_prompt)
    result = _extract_json(raw)
    _validate_chapter_analysis(result)
    return result


def _book_index_path(book_cfg: dict[str, Any]) -> Path:
    """支持两种配置：
    - book.index_path 显式路径
    - book.book_id 通过 data/books/<book_id>/index.json 推导
    """
    if book_cfg.get("index_path"):
        return Path(book_cfg["index_path"])
    book_id = book_cfg.get("book_id")
    if not book_id:
        raise ValueError("config.content.book 必须配置 book_id 或 index_path")
    return DATA_DIR / "books" / str(book_id) / "index.json"


def _resolve_index_paths(book_cfg: dict[str, Any]) -> list[Path]:
    """解析「书籍池」配置，返回按阅读顺序排列的 index.json 路径列表。

    优先级：
    - book.book_pool（列表，按顺序逐本读完）→ 每个元素是 bookId
    - 否则回退到单本（book.index_path 或 book.book_id），保持向后兼容
    """
    pool = book_cfg.get("book_pool")
    if pool:
        paths: list[Path] = []
        seen: set[str] = set()
        for item in pool:
            bid = str(item).strip()
            if not bid or bid in seen:
                continue
            seen.add(bid)
            paths.append(DATA_DIR / "books" / bid / "index.json")
        if paths:
            return paths
    # 单本（向后兼容）
    return [_book_index_path(book_cfg)]


def _progress_path(index_path: Path) -> Path:
    return index_path.parent / "progress.json"


def _load_progress(p: Path, book_id: str) -> dict[str, Any]:
    if not p.exists():
        return {"book_id": book_id, "claimed": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data.setdefault("book_id", book_id)
        data.setdefault("claimed", {})
        return data
    except Exception as e:
        log.warning("progress.json 损坏（%s），重建", e)
        return {"book_id": book_id, "claimed": {}}


def _save_progress(p: Path, data: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _pick_next_chapter(
    index_data: dict[str, Any],
    progress: dict[str, Any],
    book_cfg: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """挑下一个待读章节。规则：
    - 必须 url 非空
    - 必须 is_content_chapter（默认基于标题关键词 + wordCount）
    - 不在 progress.claimed 中
    - chapterUid 不在 book_cfg.skip_chapter_uids
    - 按 chapterIdx 升序取最小的
    """
    claimed_uids = {v["chapter_uid"] for v in progress.get("claimed", {}).values()}
    skip_uids = set(book_cfg.get("skip_chapter_uids", []) or [])
    min_wc = int(book_cfg.get("min_word_count", 800))

    for c in sorted(index_data["chapters"], key=lambda x: x["chapterIdx"]):
        if c["chapterUid"] in claimed_uids:
            continue
        if c["chapterUid"] in skip_uids:
            continue
        if not c.get("url"):
            continue
        if not is_content_chapter(c, min_word_count=min_wc):
            continue
        return c
    return None


def _build_post_from_chapter(
    index_data: dict[str, Any],
    chapter: dict[str, Any],
    content_cfg: dict[str, Any],
) -> dict[str, Any]:
    """抓完整章节 → 结构化分析 → 写现实导向的想法。"""
    cfg = load_config()
    weread_cfg = cfg.get("weread") or {}
    storage_state = weread_cfg.get("storage_state") or "data/auth/weread_state.json"
    chap_data = fetch_chapter_fulltext(
        chapter["url"],
        storage_state=storage_state,
    )
    paragraphs = chap_data.get("paragraphs") or []
    full_text = chap_data.get("full_text") or ""
    if not paragraphs or len(full_text) < 100:
        raise RuntimeError("微信读书完整章节为空，停止生成")

    analysis = _analyze_full_chapter(
        book_title=index_data["book_title"],
        chapter_title=chapter["title"],
        paragraphs=paragraphs,
        chunk_chars=int(content_cfg.get("chapter_chunk_chars") or 6000),
    )

    user_prompt = USER_PROMPT_BOOK_TPL.format(
        book_title=index_data["book_title"],
        chapter_title=chapter["title"],
        chapter_analysis=json.dumps(analysis, ensure_ascii=False, indent=2),
        min_chars=content_cfg["min_chars"],
        max_chars=content_cfg["max_chars"],
    )

    log.info(
        "book_reflection 生成：《%s》 / %s（全文 %d 字，完整度 %.1f%%）",
        index_data["book_title"], chapter["title"], len(full_text),
        float(chap_data.get("completeness_ratio") or 0) * 100,
    )
    raw, provider = _call_llm(SYSTEM_PROMPT_BOOK, user_prompt)
    data = _extract_json(raw)
    _validate_post(data)
    # 读书模式：正文末尾署上出处（书名）
    data["body"] = append_book_source(data["body"], index_data["book_title"])
    data["theme"] = f"《{index_data['book_title']}》{chapter['title']}"
    data["provider"] = provider
    data["mode"] = "book_reflection"
    data["chapter_analysis"] = analysis
    data["source_text_chars"] = chap_data.get("full_text_chars", len(full_text))
    data["source_completeness_ratio"] = chap_data.get("completeness_ratio")
    data["book"] = {
        "book_id": index_data["book_id"],
        "book_title": index_data["book_title"],
        "author": index_data.get("author", ""),
        "chapter_uid": chapter["chapterUid"],
        "chapter_idx": chapter["chapterIdx"],
        "chapter_title": chapter["title"],
        "chapter_url": chapter["url"],
    }
    log.info("生成完成：%s（正文 %d 字）", data["title"], len(data["body"]))
    return data


def _claim_chapter_in_pool(
    index_paths: list[Path],
    book_cfg: dict[str, Any],
    key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """在书籍池里按顺序找到 key 对应的章节。

    返回 (index_data, chapter)。

    逻辑：
    1. 幂等：若某本书的 progress 已经为这个 key claim 过章节 → 直接复用；
    2. 否则按池顺序找第一本「还有未读正文章节」的书，claim 它的下一章；
    3. 池里所有书都读完 → 抛 BookPoolFinished。
    """
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for p in index_paths:
        if not p.exists():
            log.warning("书籍池中索引缺失，跳过：%s（先跑 weread_index_book.py）", p)
            continue
        try:
            index_data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            log.warning("书籍池中索引损坏，跳过：%s（%s）", p, e)
            continue
        loaded.append((p, index_data))

    if not loaded:
        raise FileNotFoundError(
            "书籍池里没有任何可用的 index.json，先跑 scripts/weread_index_book.py"
        )

    # 1. 幂等复用：这个 key 是否已在某本书里 claim 过
    for p, index_data in loaded:
        progress = _load_progress(_progress_path(p), index_data["book_id"])
        rec = progress.get("claimed", {}).get(key)
        if rec:
            target_uid = rec["chapter_uid"]
            chapter = next(
                (c for c in index_data["chapters"] if c["chapterUid"] == target_uid),
                None,
            )
            if chapter is None:
                raise RuntimeError(
                    f"progress 记录的 chapterUid={target_uid} 不在 index 里（{p}）"
                )
            log.info(
                "沿用已 claim 的章节：《%s》 uid=%s %s",
                index_data["book_title"], target_uid, chapter["title"],
            )
            return index_data, chapter

    # 2. 按池顺序找第一本还有未读章节的书
    for p, index_data in loaded:
        progress_path = _progress_path(p)
        progress = _load_progress(progress_path, index_data["book_id"])
        chapter = _pick_next_chapter(index_data, progress, book_cfg)
        if chapter is None:
            log.info("《%s》已读完，进入池中下一本", index_data["book_title"])
            continue
        progress.setdefault("claimed", {})[key] = {
            "chapter_uid": chapter["chapterUid"],
            "chapter_idx": chapter["chapterIdx"],
            "chapter_title": chapter["title"],
            "claimed_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        _save_progress(progress_path, progress)
        log.info(
            "claim 新章节：[%s]《%s》 uid=%s idx=%s %s",
            key, index_data["book_title"], chapter["chapterUid"],
            chapter["chapterIdx"], chapter["title"],
        )
        return index_data, chapter

    # 3. 全部读完
    raise BookPoolFinished("书籍池里所有书都已读完")


def _generate_from_book(slot: str, date: dt.date) -> dict[str, Any]:
    cfg = load_config()
    content_cfg = cfg["content"]
    book_cfg = content_cfg.get("book") or {}
    if not book_cfg:
        raise ValueError("content.mode=book_reflection 但缺少 content.book 配置")

    index_paths = _resolve_index_paths(book_cfg)
    key = f"{date.isoformat()}_{slot}"
    index_data, chapter = _claim_chapter_in_pool(index_paths, book_cfg, key)
    return _build_post_from_chapter(index_data, chapter, content_cfg)


# ─────────────── 顶层入口 ─────────────── #


def generate_from_theme(theme: Optional[str] = None) -> dict[str, Any]:
    """公开入口：强制走 themes 模式生成一条想法（书籍池读完后调度层兜底用）。"""
    load_env()
    return _generate_from_theme(theme)


def generate_post(
    theme: Optional[str] = None,
    *,
    slot: Optional[str] = None,
    date: Optional[dt.date] = None,
) -> dict[str, Any]:
    """生成一条想法。返回 dict：title / body / image_prompt / theme / mode 等。

    - 如果 config.content.mode == 'book_reflection' 且 slot+date 已给：走完整章节模式；
      任何抓取或分析失败都会向上抛出，禁止静默回退到 themes
    - 否则：themes 模式
    """
    load_env()
    cfg = load_config()
    mode = (cfg.get("content", {}).get("mode") or "themes").strip().lower()

    if mode == "book_reflection" and slot is not None:
        d = date or dt.date.today()
        return _generate_from_book(slot, d)

    return _generate_from_theme(theme)
