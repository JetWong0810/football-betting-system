"""单场情报:联网搜集(落库,全员共享) + 关联公众号文章中的事实声明(读时合并,不重复存)。

只列客观情报,不给预测。每条带来源站点/日期/核实状态;链接只保留确实出现在搜索结果里的。
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import pymysql

from database import get_db
from .llm import stream_chat

CATS = ["伤停", "阵容", "战意", "赛程", "数据", "教练", "其他"]
SIDES = ("home", "away", "neutral")
MAX_ITEMS = 12

_ART_CAT = {"injury": "伤停", "suspension": "伤停", "lineup": "阵容", "rotation": "阵容", "motivation": "战意",
            "schedule": "赛程", "manager": "教练", "odds": "其他", "other": "其他"}
_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class IntelUnavailable(RuntimeError):
    pass


def _wrap(e: Exception):
    if isinstance(e, pymysql.err.ProgrammingError) and e.args and e.args[0] == 1146:
        raise IntelUnavailable("情报表尚未创建") from e
    raise e


INTEL_SYSTEM = """你是足球赛前情报员。只搜集并核实与指定比赛直接相关的客观事实,不做任何预测、不评价谁会赢。

## 任务
用联网搜索查找该场比赛两队的赛前情报: 伤停与复出、停赛、预计首发/阵型、轮换与体能(赛程密度)、战意(积分形势、出线/保级/争冠需求)、换帅、近期关键数据与交锋。
今天是 {today},开赛时间 {kickoff}。

## 纪律
1. 只采信开赛前近 7 天内发布的信息,且必须与这两支球队直接相关。日期不明、过时、泛泛而谈的一律不要。
2. 只写事实: 谁伤/谁停/谁回归/积分与出线形势/赛程间隔/数据。不要观点、预测、"看好"、赔率走势。不要出现本场比赛结果或比分。
3. 每条一个事实,不超过 40 字,数字与人名与来源一致,不要自行推断补充。
4. source 写站点名;url 必须是搜索结果里出现过的原链接,不确定就留空字符串,不得编造;date 写发布日期 MM-DD。
5. status: 官方渠道(俱乐部/联赛/足协)或至少两个独立站点一致 -> "confirmed";只有单一来源 -> "pending"。
6. 搜不到就少给,宁缺毋滥,没有就返回空数组。最多 {n} 条,优先影响大的(核心球员缺阵、战意)。
7. 文本里不要使用英文双引号。

## 输出
只输出一个 JSON,不要任何其他文字:
{{"items":[{{"side":"home|away|neutral","category":"伤停|阵容|战意|赛程|数据|教练|其他","text":"...","source":"站点","url":"","date":"MM-DD","status":"confirmed|pending"}}]}}
side: home=主队相关, away=客队相关, neutral=两队共同或比赛整体。
"""


def _lock(match_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(match_id, threading.Lock())


def _parse_json(text: str) -> Optional[dict]:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        i, j = t.find("{"), t.rfind("}")
        if i < 0 or j <= i:
            return None
        t = t[i:j + 1]
    try:
        v = json.loads(t)
    except json.JSONDecodeError:
        return None
    return v if isinstance(v, dict) else None


def _norm_url(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower()).rstrip("/")


def clean_items(raw: List[Any], source_urls: List[str]) -> List[Dict[str, Any]]:
    allowed = {_norm_url(u): u for u in source_urls}
    out, seen = [], set()
    for x in raw or []:
        if not isinstance(x, dict):
            continue
        text = str(x.get("text") or "").strip()[:120]
        if len(text) < 6:
            continue
        key = re.sub(r"\W", "", text)[:24]
        if key in seen:
            continue
        seen.add(key)
        url = allowed.get(_norm_url(str(x.get("url") or "")))      # 不在搜索结果里的链接丢弃
        cat = str(x.get("category") or "其他")
        date = str(x.get("date") or "").strip()[:10]
        out.append({
            "side": x.get("side") if x.get("side") in SIDES else "neutral",
            "category": cat if cat in CATS else "其他",
            "text": text,
            "source": str(x.get("source") or "").strip()[:40],
            "url": url,
            "date": date if re.match(r"^(\d{4}-)?\d{2}-\d{2}$", date) else "",
            "status": "confirmed" if x.get("status") == "confirmed" else "pending",
        })
        if len(out) >= MAX_ITEMS:
            break
    return out


def _save(match_id: str, items: List[Dict[str, Any]]) -> None:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM match_intel WHERE match_id=%s", (match_id,))
            for it in items:
                cur.execute(
                    "INSERT INTO match_intel (match_id, side, category, text, source, source_url, pub_date, status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (match_id, it["side"], it["category"], it["text"], it["source"], it["url"], it["date"] or None, it["status"]))
            cur.execute("INSERT INTO match_intel_run (match_id, n) VALUES (%s,%s) "
                        "ON DUPLICATE KEY UPDATE n=VALUES(n), updated_at=NOW()", (match_id, len(items)))
    except Exception as e:  # noqa: BLE001
        _wrap(e)


def _web_items(match_id: str) -> List[Dict[str, Any]]:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, side, category, text, source, source_url, pub_date, status FROM match_intel "
                        "WHERE match_id=%s ORDER BY id", (match_id,))
            rows = list(cur.fetchall() or [])
    except Exception as e:  # noqa: BLE001
        _wrap(e)
    return [{"id": f"w{r['id']}", "origin": "web", "side": r["side"], "category": r["category"], "text": r["text"],
             "source": r["source"], "url": r["source_url"], "date": r["pub_date"] or "", "status": r["status"]}
            for r in rows]


def _article_items(match_id: str) -> List[Dict[str, Any]]:
    """已关联的赛前公众号文章里的事实声明(被反驳的不列)。"""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT c.id, c.article_id, c.claim_type, c.side, c.text, c.verify_status, c.verify_note, "
                "a.account_name, a.publish_time FROM wx_article_claim c "
                "JOIN wx_article_match x ON x.article_id=c.article_id AND x.match_id=c.match_id "
                "JOIN wx_article a ON a.id=c.article_id "
                "WHERE c.match_id=%s AND x.status='linked' AND x.timing='preview' AND c.verify_status<>'contradicted' "
                "ORDER BY c.verify_status='confirmed' DESC, a.publish_time DESC, c.id LIMIT 10", (match_id,))
            rows = list(cur.fetchall() or [])
    except Exception:  # 文章表不可用不影响情报
        return []
    out = []
    for r in rows:
        pt = r["publish_time"]
        out.append({"id": f"a{r['id']}", "origin": "article",
                    "side": r["side"] if r["side"] in ("home", "away") else "neutral",
                    "category": _ART_CAT.get(r["claim_type"], "其他"), "text": r["text"],
                    "source": f"公众号 {r['account_name']}", "url": None,
                    "date": pt.strftime("%m-%d") if pt else "",
                    "status": "confirmed" if r["verify_status"] == "confirmed" else "pending",
                    "note": r.get("verify_note") or "", "articleId": r["article_id"]})
    return out


def list_items(match_id: str) -> Dict[str, Any]:
    web = _web_items(match_id)
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT n, updated_at FROM match_intel_run WHERE match_id=%s", (match_id,))
            run = cur.fetchone()
    except Exception as e:  # noqa: BLE001
        _wrap(e)
    return {"items": web + _article_items(match_id), "searched": bool(run),
            "updatedAt": run["updated_at"].strftime("%m-%d %H:%M") if run and run.get("updated_at") else None}


def get_item(match_id: str, item_id: str) -> Optional[Dict[str, Any]]:
    for it in list_items(match_id)["items"]:
        if it["id"] == item_id:
            return it
    return None


def render_for_prompt(items: List[Dict[str, Any]]) -> str:
    if not items:
        return ""
    SIDE = {"home": "主队", "away": "客队", "neutral": "整体"}
    L = ["\n【已收集情报】(客观情报清单;网络来源为模型联网所得,confirmed=官方或多源一致,pending=单源待核实;公众号来源是二手信息)"]
    for it in items:
        st = "已核实" if it["status"] == "confirmed" else "待核实"
        L.append(f"- [{SIDE[it['side']]}·{it['category']}·{st}] {it['text']} ({it['source']} {it['date']})")
    return "\n".join(L)


def refresh(match_id: str, home: str, away: str, league: str, kickoff: str) -> Iterator[Dict[str, Any]]:
    """联网搜集并落库。事件: status / items / error。同一场同时只允许一个搜集在跑。"""
    lk = _lock(match_id)
    if not lk.acquire(blocking=False):
        yield {"type": "error", "text": "该场情报正在更新,请稍候再看"}
        return
    try:
        system = INTEL_SYSTEM.format(today=datetime.now().strftime("%Y-%m-%d"), kickoff=kickoff, n=MAX_ITEMS)
        user = f"比赛: {league} 主队 {home} vs 客队 {away},开赛 {kickoff}。请搜集赛前情报,只输出 JSON。"
        parsed = None
        urls: List[str] = []
        for attempt in range(2):
            buf: List[str] = []
            failed = False
            for ev in stream_chat(system, [{"role": "user", "content": user}], web=True):
                if ev["type"] == "delta":
                    buf.append(ev["text"])
                elif ev["type"] == "status":
                    yield ev
                elif ev["type"] == "sources":
                    urls = [s["url"] for s in ev["items"]] or urls
                elif ev["type"] == "error":
                    failed = True
                    yield ev
            if failed:
                return
            parsed = _parse_json("".join(buf))
            if parsed is not None:
                break
            yield {"type": "status", "text": "整理结果"}
        if parsed is None:
            yield {"type": "error", "text": "情报整理失败,请重试"}
            return
        items = clean_items(parsed.get("items") or [], urls)
        _save(match_id, items)
        yield {"type": "items", **list_items(match_id)}
    finally:
        lk.release()
