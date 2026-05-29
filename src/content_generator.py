"""文案生成：

支持两种模式：
- themes（默认/兜底）：从主题池随机抽一个，让 LLM 写自我觉醒类短文
- book_reflection：根据 data/books/<bookId>/index.json 按顺序读章节，
  把章节的 AI 摘要喂给 LLM 写 200-500 字读书感悟

通过 config.yaml 的 content.mode 切换；book_reflection 失败时自动回退到 themes。

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
from pathlib import Path
from typing import Any, Optional

from .utils import DATA_DIR, env, get_logger, load_config, load_env
from .weread_fetcher import fetch_chapter, is_content_chapter

log = get_logger("content")

# ─────────────── prompts ─────────────── #

SYSTEM_PROMPT = """你是一位深刻、温柔、具备心理学与哲学素养的中文写作者，专门为一个名为「树洞」的知乎圈子写文字。
读者是在繁忙嘈杂社会中寻找心灵栖息地的成年人。
你的文字风格：
- 真诚不矫情，温柔不软弱，理性中带着温度；
- 像深夜对话，不说教，不口号；
- 用具体的画面、感受、场景，避免空泛的大词；
- 段落短，留白多，读起来像呼吸；
- 偶尔用第二人称"你"拉近距离，但不滥用；
- 结尾留一个微小的提醒或一个开放的问题，不强行升华。

务必避免：
- 鸡汤句式（"其实"、"要相信"、"加油"等开头的口号）；
- AI 味的对仗排比和总结陈词；
- 引用名人名言；
- 表情符号、emoji。"""

USER_PROMPT_TPL = """围绕主题：{theme}

写一篇 {min_chars}-{max_chars} 字的中文短文，发布在知乎"想法"板块。

返回严格 JSON（不要 markdown 代码块），格式：
{{
  "title": "一个不超过 18 字的标题，不要标点符号结尾",
  "body": "正文。可以分段，段落之间用一个空行分隔。不要包含标题。",
  "image_prompt": "一句英文 prompt，用于 AI 生成意境配图。要求：抽象、宁静、带光影氛围，no text, no people, no faces。"
}}"""


SYSTEM_PROMPT_BOOK = """你是一位深刻、温柔、具备心理学与哲学素养的中文写作者，专门为一个名为「树洞」的知乎圈子写文字。
读者是在繁忙嘈杂社会中寻找心灵栖息地的成年人。

你会拿到一段心理学/哲学类的素材。你的任务是：把这段素材里的洞察吸收进自己的思考，写一篇看上去像作者自己在静下来想问题的中文短文。读者不会知道、也不该看出这是基于某本书的某一节——它读起来要像一个人对某个心理现象、某种处境、某个人性侧面的自然思考。

---
关键要求（务必遵守）：

1. **绝对不要留下"在转述书"的痕迹**。不要出现：
   - "这一节"、"这一章"、"本节"、"章节"、"这本书"、"书里"、"原文"
   - "作者认为/强调/指出/提到/写道"、"作者用 XX 作比喻"
   - "读到这里"、"读完"、"看完这一节"
   - 任何让人意识到"在做读书笔记"的元叙述。
   把素材里的观点、概念、比喻、论证，当作你自己正在向自己讲清楚的东西展开。

2. **不要编造第一人称的具体情节**。不要写"那天深夜我盯着代码"、"周一早会我把方案推到屏幕上"、"同事对我说……"这类虚构的场景、对话、动作。
   要表达个人体会时，用观察、思辨、抽象描述。例如可以写"被否定的瞬间，人会本能地想反击，那股反击的能量像被关回笼子的动物"——这是抽象层面的观察，不是搬演具体场景。

3. **可以引用原文**，用引号清楚标注，引用数量不限，但：
   - 不要交代引文出处（不要"《XX》里说"、"作者写道"、"有学者指出"）；
   - 让引文像一句被你记下的好话，自然嵌进思路；
   - 不要堆砌大段引用替代自己的讲解。

4. **从一个观察、一个反问、一个概念切入**，围绕一个心理现象、一个内在状态、一个人性悖论展开思考；让素材里的洞察被吸收为你思考的一部分，而不是被陈列。

---
文字风格：
- 像深夜的自言自语，不像课堂笔记；
- 真诚不矫情，理性中带温度；
- 段落短，留白多，读起来像呼吸；
- 偶尔用第二人称"你"拉近距离，但不滥用；
- 结尾留一个微小的提醒或开放问题，不强行升华。

务必避免：
- 任何"读书笔记"风的元叙述（"作者"、"这一节"、"书里"、"读到这里"等）；
- 鸡汤句式（"其实"、"要相信"、"加油"等开头的口号）；
- AI 味的对仗排比和总结陈词；
- 表情符号、emoji；
- 虚构第一人称的具体场景、对话、动作；
- 大段引用代替自己的讲解。"""

USER_PROMPT_BOOK_TPL = """以下是供你思考的素材（一段心理学/哲学类内容的 AI 摘要）：

---
{chapter_summary}
---

任务：把素材里的核心洞察吸收进自己的思考，写一篇 {min_chars}-{max_chars} 字的中文短文，发表在知乎"想法"板块。
**字数是上下限不是目标**：想法讲清楚就停，宁可贴近 {min_chars} 字也不要为了凑长度反复重申、补充无关展开或多余排比。

要点：
1. 读者不应看出这是基于某本书的某一节——不要出现"这一节"、"作者"、"书里"、"原文"、"读到这里"等任何让人意识到"在转述书"的字眼；
2. 把素材里的观点、概念、比喻、论证当作你此刻正在思考、正在向自己讲清楚的内容自然展开，而不是陈列；
3. 不要编造任何第一人称的具体情节（"那天我……""昨晚我……""同事对我说……"），需要谈个人体会时用观察、思辨、抽象语言；
4. 可以引用原文（用引号），引用数量不限，但要服务于上下文逻辑，**不要交代出处**，不要大段堆砌；
5. 从一个观察、反问或概念切入，围绕一个心理现象/内在状态/人性悖论展开；
6. 标题不超过 18 字，点出这篇短文的核心思考，不要标点结尾，不要照抄素材里出现的任何小标题；
7. 结尾可以留一个开放问题或微小提醒，不强行升华。

返回严格 JSON（不要 markdown 代码块），格式：
{{
  "title": "...",
  "body": "正文，可分段，段落之间用一个空行分隔，不要包含标题",
  "image_prompt": "一句英文 prompt 用于 AI 生图：抽象、宁静、带光影氛围，no text, no people, no faces"
}}"""

# ─────────────── LLM 客户端 ─────────────── #


def _pick_provider() -> str:
    cfg = load_config()
    explicit = (cfg.get("content", {}).get("provider") or "").strip().lower()
    if explicit in ("anthropic", "openai"):
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


def _call_llm(system: str, user: str) -> tuple[str, str]:
    cfg = load_config()
    content_cfg = cfg["content"]
    provider = _pick_provider()
    if provider == "anthropic":
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


def _generate_from_book(slot: str, date: dt.date) -> dict[str, Any]:
    cfg = load_config()
    content_cfg = cfg["content"]
    book_cfg = content_cfg.get("book") or {}
    if not book_cfg:
        raise ValueError("content.mode=book_reflection 但缺少 content.book 配置")

    index_path = _book_index_path(book_cfg)
    if not index_path.exists():
        raise FileNotFoundError(
            f"找不到书的索引 {index_path}，先跑 scripts/weread_index_book.py"
        )
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    book_id = index_data["book_id"]

    progress_path = _progress_path(index_path)
    progress = _load_progress(progress_path, book_id)

    key = f"{date.isoformat()}_{slot}"
    claimed = progress.setdefault("claimed", {})

    if key in claimed:
        target_uid = claimed[key]["chapter_uid"]
        chapter = next(
            (c for c in index_data["chapters"] if c["chapterUid"] == target_uid),
            None,
        )
        if chapter is None:
            raise RuntimeError(f"progress 记录的 chapterUid={target_uid} 不在 index 里")
        log.info("沿用已 claim 的章节：uid=%s %s", target_uid, chapter["title"])
    else:
        chapter = _pick_next_chapter(index_data, progress, book_cfg)
        if chapter is None:
            raise RuntimeError("书已经全部发完了，回退到 themes 模式")
        claimed[key] = {
            "chapter_uid": chapter["chapterUid"],
            "chapter_idx": chapter["chapterIdx"],
            "chapter_title": chapter["title"],
            "claimed_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        _save_progress(progress_path, progress)
        log.info(
            "claim 新章节：[%s] uid=%s idx=%s %s",
            key, chapter["chapterUid"], chapter["chapterIdx"], chapter["title"],
        )

    # 抓章节摘要
    chap_data = fetch_chapter(chapter["url"])
    summary = chap_data.get("description") or ""
    if len(summary) < 50:
        raise RuntimeError(
            f"章节摘要为空或太短（{len(summary)} 字），可能页面结构变化或登录态失效"
        )

    user_prompt = USER_PROMPT_BOOK_TPL.format(
        book_title=index_data["book_title"],
        author=index_data.get("author", ""),
        chapter_title=chapter["title"],
        chapter_summary=summary,
        min_chars=content_cfg["min_chars"],
        max_chars=content_cfg["max_chars"],
    )

    log.info(
        "book_reflection 生成：《%s》 / %s（摘要 %d 字）",
        index_data["book_title"], chapter["title"], len(summary),
    )
    raw, provider = _call_llm(SYSTEM_PROMPT_BOOK, user_prompt)
    data = _extract_json(raw)
    _validate_post(data)
    data["theme"] = f"《{index_data['book_title']}》{chapter['title']}"
    data["provider"] = provider
    data["mode"] = "book_reflection"
    data["book"] = {
        "book_id": book_id,
        "book_title": index_data["book_title"],
        "author": index_data.get("author", ""),
        "chapter_uid": chapter["chapterUid"],
        "chapter_idx": chapter["chapterIdx"],
        "chapter_title": chapter["title"],
        "chapter_url": chapter["url"],
    }
    log.info("生成完成：%s（正文 %d 字）", data["title"], len(data["body"]))
    return data


# ─────────────── 顶层入口 ─────────────── #


def generate_post(
    theme: Optional[str] = None,
    *,
    slot: Optional[str] = None,
    date: Optional[dt.date] = None,
) -> dict[str, Any]:
    """生成一条想法。返回 dict：title / body / image_prompt / theme / mode 等。

    - 如果 config.content.mode == 'book_reflection' 且 slot+date 已给：尝试书籍模式，
      失败时自动回退到 themes
    - 否则：themes 模式
    """
    load_env()
    cfg = load_config()
    mode = (cfg.get("content", {}).get("mode") or "themes").strip().lower()

    if mode == "book_reflection" and slot is not None:
        d = date or dt.date.today()
        try:
            return _generate_from_book(slot, d)
        except Exception as e:
            log.warning("book_reflection 失败，回退到 themes：%s", e)
            # 不向上抛错；继续走 themes

    return _generate_from_theme(theme)
