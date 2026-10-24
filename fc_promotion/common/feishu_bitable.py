"""飞书多维表格（Bitable）写入客户端。

推广数据库是多维表格（URL 带 table=tbl...），用 bitable records API 追加记录，
不同于 zhihu 项目里 scripts/feishu_append_markdown.py 写 docx 文档。

鉴权：tenant_access_token（企业自建应用），凭据从 zhihu 项目 .env 读取
（FEISHU_APP_ID / FEISHU_APP_SECRET）。
wiki 链接需先把 wiki node token 解析成 bitable 的 app_token。
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

from .logging_utils import get_logger
from .paths import ENV_FILE

log = get_logger("feishu")

API_BASE = "https://open.feishu.cn/open-apis"


class FeishuError(RuntimeError):
    pass


def _request(method: str, path: str, token: str | None = None, **kwargs: Any) -> dict[str, Any]:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.request(method, f"{API_BASE}{path}", headers=headers, timeout=30, **kwargs)
    try:
        payload = resp.json()
    except ValueError as exc:
        raise FeishuError(
            f"{method} {path} 返回非 JSON HTTP {resp.status_code}: {resp.text[:300]}"
        ) from exc
    if resp.status_code >= 400 or payload.get("code") not in (0, None):
        raise FeishuError(
            f"{method} {path} 失败 HTTP {resp.status_code}: "
            f"{json.dumps(payload, ensure_ascii=False)[:1000]}"
        )
    return payload


def parse_bitable_url(url: str) -> tuple[str, str | None]:
    """从飞书多维表格 URL 解析出 (wiki_node_token 或 app_token, table_id)。

    支持两种形态：
      - wiki 链接：.../wiki/<node_token>?table=<table_id>
      - base 链接：.../base/<app_token>?table=<table_id>
    返回的第一个值是 node_token（wiki）或 app_token（base），由调用方据路径类型判断。
    """
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    table_id = parse_qs(parsed.query).get("table", [None])[0]
    for key in ("wiki", "base"):
        if key in parts:
            idx = parts.index(key) + 1
            if idx < len(parts):
                return parts[idx], table_id
    raise ValueError(f"无法解析飞书多维表格 URL：{url}")


class FeishuBitable:
    """面向单张多维表格的追加写入客户端。"""

    def __init__(self, *, app_id: str | None = None, app_secret: str | None = None) -> None:
        import os

        load_dotenv(ENV_FILE, override=False)
        self.app_id = (app_id or os.getenv("FEISHU_APP_ID", "")).strip()
        self.app_secret = (app_secret or os.getenv("FEISHU_APP_SECRET", "")).strip()
        if not self.app_id or not self.app_secret:
            raise FeishuError("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET（请配置在 zhihu 项目 .env）")
        self._token: str | None = None
        self._token_exp = 0.0

    def _tenant_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        payload = _request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        self._token = payload["tenant_access_token"]
        self._token_exp = time.time() + payload.get("expire", 7200)
        return self._token

    def resolve_app_token(self, url_or_token: str) -> str:
        """把 wiki 链接/wiki node token 解析成 bitable app_token。

        传入 base 链接或已是 app_token（bascn.../ 开头）时原样/就地返回。
        """
        token = url_or_token
        if "/" in url_or_token:
            token, _ = parse_bitable_url(url_or_token)
            if "/base/" in url_or_token:
                return token  # 已是 app_token
        # wiki node -> obj_token(bitable app_token)
        payload = _request(
            "GET",
            f"/wiki/v2/spaces/get_node?token={token}",
            self._tenant_token(),
        )
        node = payload.get("data", {}).get("node", {})
        obj_token = node.get("obj_token")
        if node.get("obj_type") != "bitable" or not obj_token:
            # 非 wiki 节点时，有可能传入的本就是 app_token
            if token.startswith("bas"):
                return token
            raise FeishuError(f"wiki 节点不是多维表格：{json.dumps(node, ensure_ascii=False)}")
        return obj_token

    def append_record(self, *, app_token: str, table_id: str, fields: dict[str, Any]) -> str:
        """向表追加一条记录，返回 record_id。fields 的 key 必须与表字段名一致。"""
        payload = _request(
            "POST",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            self._tenant_token(),
            json={"fields": fields},
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        rec = payload.get("data", {}).get("record", {})
        return rec.get("record_id", "")

    def list_field_names(self, *, app_token: str, table_id: str) -> list[str]:
        """列出表字段名，便于写入前核对字段（参考表写法时很有用）。"""
        payload = _request(
            "GET",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            self._tenant_token(),
            params={"page_size": 100},
        )
        return [f.get("field_name", "") for f in payload.get("data", {}).get("items", [])]
