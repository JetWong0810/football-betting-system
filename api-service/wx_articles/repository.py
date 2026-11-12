"""微信知社文章落库。表不存在时抛 WxStoreUnavailable,不自动建表(本地库=生产库)。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

import pymysql

from database import get_db


class WxStoreUnavailable(RuntimeError):
    pass


def _wrap(e: Exception):
    if isinstance(e, pymysql.err.ProgrammingError) and e.args and e.args[0] == 1146:
        raise WxStoreUnavailable("wx_article 表尚未创建") from e
    raise e


def parse_time(s: Any) -> Optional[datetime]:
    """知社 publishTime 形如 2025-08-02 12:36:12(北京时间)。"""
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip()[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def insert_article(p: Dict[str, Any]) -> bool:
    """返回 True=新文章, False=重复(已存在)。"""
    content = p.get("content")
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT IGNORE INTO wx_article (article_id, wxid, account_name, title, description, url, "
                "cover, publish_time, content, raw_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (str(p["id"])[:128], str(p.get("wxid") or "")[:64], str(p.get("name") or "")[:128],
                 str(p.get("title") or "")[:512], p.get("desc"), str(p.get("url") or "")[:1024],
                 (str(p["cover"])[:1024] if p.get("cover") else None), parse_time(p.get("publishTime")),
                 content if isinstance(content, str) and content.strip() else None,
                 json.dumps(p, ensure_ascii=False)),
            )
            return cur.rowcount == 1
    except Exception as e:  # noqa: BLE001
        _wrap(e)
