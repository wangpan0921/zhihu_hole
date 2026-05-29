"""配图：优先 OpenAI 生图，失败回退到 Unsplash。"""
from __future__ import annotations

import base64
import hashlib
import time
from pathlib import Path

import requests

from .utils import IMAGES_DIR, env, get_logger, load_config, load_env

log = get_logger("image")


def _safe_filename(prompt: str) -> str:
    h = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:10]
    return f"{int(time.time())}_{h}.png"


def _gen_with_openai(prompt: str, style_hint: str, size: str, model: str) -> bytes:
    from openai import OpenAI

    # 生图允许用一组独立的 key/base_url（公司内网关常常不支持图像生成）
    api_key = env("OPENAI_IMAGE_API_KEY") or env("OPENAI_API_KEY")
    base_url = env("OPENAI_IMAGE_BASE_URL") or env("OPENAI_BASE_URL")
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    full_prompt = f"{prompt}. Style: {style_hint}"
    log.info("OpenAI 生图：model=%s, size=%s, base_url=%s", model, size, base_url or "default")

    # dall-e-3 默认返回 url；gpt-image-1 默认返回 b64_json
    if model.startswith("gpt-image"):
        resp = client.images.generate(model=model, prompt=full_prompt, size=size, n=1)
        b64 = resp.data[0].b64_json
        return base64.b64decode(b64)

    resp = client.images.generate(
        model=model, prompt=full_prompt, size=size, n=1, response_format="b64_json"
    )
    item = resp.data[0]
    if getattr(item, "b64_json", None):
        return base64.b64decode(item.b64_json)
    # 某些模型只返 url
    url = item.url
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def _gen_with_unsplash(prompt: str) -> bytes:
    key = env("UNSPLASH_ACCESS_KEY")
    if not key:
        raise RuntimeError("UNSPLASH_ACCESS_KEY 未配置")

    # 用 prompt 中的关键词搜索
    keywords = " ".join(prompt.split()[:5])
    log.info("Unsplash 搜索：%s", keywords)
    r = requests.get(
        "https://api.unsplash.com/photos/random",
        params={"query": keywords, "orientation": "squarish", "content_filter": "high"},
        headers={"Authorization": f"Client-ID {key}"},
        timeout=30,
    )
    r.raise_for_status()
    photo = r.json()
    img_url = photo["urls"]["regular"]
    img = requests.get(img_url, timeout=60).content
    return img


def get_image(prompt: str) -> Path:
    """根据 prompt 取图，返回本地文件路径。"""
    load_env()
    cfg = load_config()
    img_cfg = cfg["image"]

    prefer = img_cfg.get("prefer", "openai")
    style = img_cfg.get("style", "")
    size = img_cfg.get("size", "1024x1024")
    model = img_cfg.get("openai_model", "dall-e-3")

    out_path = IMAGES_DIR / _safe_filename(prompt)

    last_err: Exception | None = None
    order = ["openai", "unsplash"] if prefer == "openai" else ["unsplash", "openai"]
    for src in order:
        try:
            if src == "openai":
                if not (env("OPENAI_IMAGE_API_KEY") or env("OPENAI_API_KEY")):
                    raise RuntimeError("OPENAI_API_KEY / OPENAI_IMAGE_API_KEY 都未配置，跳过 OpenAI 生图")
                data = _gen_with_openai(prompt, style, size, model)
            else:
                data = _gen_with_unsplash(prompt)
            out_path.write_bytes(data)
            log.info("图片已保存：%s（来源 %s）", out_path, src)
            return out_path
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] 取图失败：%s", src, e)
            last_err = e
            continue

    raise RuntimeError(f"所有图源都失败，最后错误：{last_err}")
