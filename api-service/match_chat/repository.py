"""聊天记录读写。表不存在时抛 ChatStoreUnavailable,不自动建表(本地库=生产库)。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pymysql

from database import get_db


class ChatStoreUnavailable(RuntimeError):
    pass


def _wrap(e: Exception):
    if isinstance(e, pymysql.err.ProgrammingError) and e.args and e.args[0] == 1146:
        raise ChatStoreUnavailable("match_chat_messages 表尚未创建") from e
    raise e


def list_messages(user_id: int, match_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, role, content, verdict_json, sources_json, attachments_n, web_used, created_at "
                "FROM match_chat_messages WHERE user_id=%s AND match_id=%s ORDER BY id DESC LIMIT %s",
                (user_id, match_id, limit),
            )
            rows = list(cur.fetchall() or [])
    except Exception as e:  # noqa: BLE001
        _wrap(e)
    rows.reverse()
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "role": r["role"], "content": r["content"],
            "verdict": json.loads(r["verdict_json"]) if r.get("verdict_json") else None,
            "sources": json.loads(r["sources_json"]) if r.get("sources_json") else [],
            "attachments": r.get("attachments_n") or 0, "webUsed": bool(r.get("web_used")),
            "createdAt": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else None,
        })
    return out


def add_message(user_id: int, match_id: str, role: str, content: str, *,
                verdict: Optional[dict] = None, sources: Optional[list] = None,
                attachments_n: int = 0, web_used: bool = False, ctx_hash: Optional[str] = None) -> int:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO match_chat_messages (user_id, match_id, role, content, verdict_json, "
                "sources_json, attachments_n, web_used, ctx_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, match_id, role, content,
                 json.dumps(verdict, ensure_ascii=False) if verdict else None,
                 json.dumps(sources, ensure_ascii=False) if sources else None,
                 attachments_n, 1 if web_used else 0, ctx_hash),
            )
            return cur.lastrowid
    except Exception as e:  # noqa: BLE001
        _wrap(e)


def clear_messages(user_id: int, match_id: str) -> int:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM match_chat_messages WHERE user_id=%s AND match_id=%s", (user_id, match_id))
            return cur.rowcount
    except Exception as e:  # noqa: BLE001
        _wrap(e)
