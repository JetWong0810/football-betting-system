"""原型验证:单场「证据账本」取证管线(只读,不写库)。

流程: 身份卡 -> 搜索 -> 硬过滤(时间/屏蔽域) -> 抓正文 -> LLM 分类+抽取
      -> 代码校验(引用片段必须原样出现在正文) -> 交叉验证 -> 输出报告。

用法:
  python3 -m match_chat.proto_evidence --ids 2042688,2042689 --out /tmp/proto
  python3 -m match_chat.proto_evidence --auto 8 --out /tmp/proto
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

logger = logging.getLogger("proto_evidence")
CST = timezone(timedelta(hours=8))

BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
WINDOW_DAYS = 5          # 只认开赛前 N 天内发布的内容
MAX_FETCH = 6            # 每场最多抓正文篇数
TEXT_CAP = 5000          # 送给模型的每篇正文上限

DROP_HOSTS = (
    "facebook.com", "twitter.com", "x.com", "tiktok.com", "reddit.com",
    "wikipedia.org", "youtube.com", "instagram.com",
)


# --------------------------------------------------------------------------- 外部调用
def _headers() -> Dict[str, str]:
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def ds_search(query: str, count: int = 8) -> List[Dict[str, Any]]:
    try:
        r = httpx.post(f"{BASE}/v1/tools/search", headers=_headers(), timeout=25,
                       json={"query": query[:128], "count": count, "need_content": False})
        if r.status_code != 200:
            logger.warning("search %s %s", r.status_code, query[:50])
            return []
        return [x for x in (r.json().get("results") or []) if isinstance(x, dict)]
    except Exception as e:  # noqa: BLE001
        logger.warning("search err %s: %s", query[:50], e)
        return []


def ds_fetch(url: str) -> str:
    try:
        r = httpx.post(f"{BASE}/v1/tools/fetch", headers=_headers(), timeout=30, json={"url": url})
        if r.status_code != 200:
            return ""
        d = r.json() or {}
        return (d.get("content") or d.get("text") or "")[:12000]
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- 身份卡
def list_onsale() -> List[Dict[str, Any]]:
    from database import get_db
    sql = (
        "SELECT match_id, home_team_name, away_team_name, league_name, match_timestamp, "
        "asian_handicap, match_number, is_single FROM matches "
        "WHERE match_id NOT LIKE 'jczq%%' AND home_score IS NULL "
        "AND match_timestamp > UNIX_TIMESTAMP(NOW()) ORDER BY match_timestamp"
    )
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return list(cur.fetchall() or [])


def get_match(mid: str) -> Optional[Dict[str, Any]]:
    from database import get_db
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT match_id, home_team_name, away_team_name, league_name, match_timestamp, "
            "asian_handicap, match_number, is_single FROM matches WHERE match_id=%s", (mid,))
        return cur.fetchone()


def identity_card(m: Dict[str, Any]) -> Dict[str, Any]:
    home, away = m["home_team_name"], m["away_team_name"]
    h_en = a_en = ""
    try:
        from bsd_intel.map import cn_to_en, load_alias_table
        t = load_alias_table()
        h_en, a_en = cn_to_en(home, t) or "", cn_to_en(away, t) or ""
    except Exception as e:  # noqa: BLE001
        logger.debug("alias fail %s", e)
    kick = datetime.fromtimestamp(int(m["match_timestamp"]), CST)
    return {
        "match_id": str(m["match_id"]), "home": home, "away": away,
        "home_en": h_en, "away_en": a_en, "league": m["league_name"],
        "kickoff": kick, "kickoff_str": kick.strftime("%Y-%m-%d %H:%M CST"),
    }


# --------------------------------------------------------------------------- 检索 + 硬过滤
def build_queries(c: Dict[str, Any]) -> List[str]:
    h, a = c["home"], c["away"]
    d = c["kickoff"].strftime("%m月%d日")
    qs = [
        f"{h} {a} 前瞻 阵容 伤停",
        f"{h} 伤病 停赛 首发 {c['league']}",
        f"{a} 伤病 停赛 首发 {c['league']}",
        f"{h} vs {a} {d} 比赛预告",
    ]
    if c["home_en"] and c["away_en"]:
        qs += [f"{c['home_en']} vs {c['away_en']} team news injuries predicted lineup",
               f"{c['home_en']} {c['away_en']} preview"]
    return qs


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(CST)
    except ValueError:
        return None


def retrieve(c: Dict[str, Any]) -> Dict[str, Any]:
    raw: Dict[str, Dict[str, Any]] = {}
    with cf.ThreadPoolExecutor(6) as ex:
        for rows in ex.map(ds_search, build_queries(c)):
            for r in rows:
                u = r.get("url")
                if u and u not in raw:
                    raw[u] = r
    kept, dropped = [], []
    now = datetime.now(CST)
    lo = c["kickoff"] - timedelta(days=WINDOW_DAYS)
    for u, r in raw.items():
        host = re.sub(r"^https?://(www\.)?", "", u).split("/")[0]
        pub = _parse_date(r.get("date"))
        reason = None
        if any(host.endswith(h) for h in DROP_HOSTS):
            reason = "blocked_host"
        elif pub and (pub < lo or pub > now + timedelta(hours=1)):
            reason = f"out_of_window({pub:%m-%d})"
        item = {"url": u, "host": host, "site": r.get("site_name") or host,
                "title": r.get("title") or "", "published": pub.isoformat() if pub else None,
                "authority": r.get("authority"), "score": r.get("rerank_score"),
                "summary": r.get("summary") or r.get("snippet") or ""}
        (dropped if reason else kept).append({**item, "drop": reason} if reason else item)
    kept.sort(key=lambda x: (x.get("authority") or 0, x.get("score") or 0), reverse=True)
    return {"found": len(raw), "kept": kept, "dropped": dropped}


def attach_text(kept: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    top = kept[:MAX_FETCH]
    with cf.ThreadPoolExecutor(6) as ex:
        texts = list(ex.map(lambda s: ds_fetch(s["url"]), top))
    for s, t in zip(top, texts):
        s["text"] = (t if len(t) > len(s["summary"]) else s["summary"])[:TEXT_CAP]
        s["fetched"] = len(t) > len(s["summary"])
    return top


# --------------------------------------------------------------------------- LLM 抽取
SYSTEM = """你是赛前事实抽取器,只依据给定网页文本,禁止使用自身记忆,禁止推断。
你会收到「目标比赛身份卡」和若干来源文本(带编号)。对每个来源:
1. about 判断该来源与目标比赛的关系:
   - this_fixture: 明确在谈目标比赛(同队、同一场)
   - team_news: 只谈其中一队当前(赛前几天内)的状态/伤停,没提目标比赛
   - other_fixture: 谈的是这两队其他场次、他们与别队的比赛
   - past_report: 已完赛战报/历史回顾
   - unrelated: 无关
   队名可能是简繁体或不同译名,以语义判断。
2. fixture_evidence: 若 about=this_fixture,摘录原文中能证明是本场的一句话(原样,≤60字),否则空。
3. items: 仅当 about 为 this_fixture 或 team_news 时抽取,每条:
   {"type":"injury|suspension|lineup|rotation|motivation|schedule|manager|weather|other",
    "side":"home|away","subject":"球员/球队名","statement":"≤40字事实","quote":"原文原样片段≤60字,必须逐字出现在来源文本中"}
   没有就给空数组。不要抽:赔率解读、竞猜推荐、泛泛的"状态不错"。
quote/statement 等字符串内不要出现英文双引号(原文有引号时用「」替换该字符之外的部分,或截取不含引号的片段)。
只输出 JSON: {"sources":[{"id":1,"about":"","fixture_evidence":"","items":[...]}]}"""


def llm_extract(c: Dict[str, Any], sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    try:
        return _llm_extract(c, sources)
    except Exception as e:  # noqa: BLE001
        logger.warning('extract failed (%s), fallback to chunks of 2', e)
    merged: List[Dict[str, Any]] = []
    for off in range(0, len(sources), 2):
        try:
            part = _llm_extract(c, sources[off:off + 2])
        except Exception as e:  # noqa: BLE001
            logger.warning('chunk %s failed: %s', off, e)
            continue
        for x in part.get('sources') or []:
            x['id'] = int(x.get('id', 0)) + off
            merged.append(x)
    return {'sources': merged}


def _llm_extract(c: Dict[str, Any], sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=BASE)
    card = (f"目标比赛: {c['home']}(主,{c['home_en'] or '-'}) vs {c['away']}(客,{c['away_en'] or '-'}), "
            f"{c['league']}, 开赛 {c['kickoff_str']}")
    blocks = [f"[来源{i}] 站点:{s['site']} 发布:{s['published'] or '未知'}\n标题:{s['title']}\n{s['text']}"
              for i, s in enumerate(sources, 1)]
    last = None
    for _ in range(3):
        resp = client.chat.completions.create(
            model=MODEL, temperature=0, max_tokens=4096,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": card + "\n\n" + "\n\n".join(blocks)}],
        )
        txt = (resp.choices[0].message.content or "").strip()
        try:
            return json.loads(txt)
        except json.JSONDecodeError as e:
            last = e
            logger.warning("extract json invalid, retry: %s", e)
    raise last


def _norm(s: str) -> str:
    return re.sub(r"[\s　，。、；：,.;:!?！？\"'“”‘’()（）\[\]【】\-—]+", "", s or "").lower()


def verify(sources: List[Dict[str, Any]], llm: Dict[str, Any]) -> Dict[str, Any]:
    """代码校验: 引用/本场证据必须原样出现在正文中。"""
    items_ok, items_bad, src_out = [], [], []
    by_id = {int(x.get("id", 0)): x for x in (llm.get("sources") or [])}
    for i, s in enumerate(sources, 1):
        r = by_id.get(i, {})
        about = r.get("about", "unrelated")
        hay = _norm(s["text"] + s["title"])
        fe = (r.get("fixture_evidence") or "").strip()
        fe_ok = bool(fe) and _norm(fe) in hay
        accepted = (about == "this_fixture" and fe_ok) or about == "team_news"
        if about == "this_fixture" and not fe_ok:
            about_eff = "this_fixture_UNVERIFIED"
        else:
            about_eff = about
        src_out.append({"id": i, "site": s["site"], "url": s["url"], "published": s["published"],
                        "authority": s["authority"], "about": about, "about_effective": about_eff,
                        "fixture_evidence": fe, "fixture_evidence_ok": fe_ok, "accepted": accepted,
                        "title": s["title"], "fetched": s.get("fetched")})
        for it in (r.get("items") or []):
            q = (it.get("quote") or "").strip()
            ok = bool(q) and _norm(q) in hay
            rec = {**it, "source_id": i, "site": s["site"], "url": s["url"],
                   "published": s["published"], "quote_verified": ok, "source_accepted": accepted}
            (items_ok if (ok and accepted) else items_bad).append(rec)
    return {"sources": src_out, "items_ok": items_ok, "items_bad": items_bad}


def corroborate(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    g: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for it in items:
        g[(it.get("side"), _norm(it.get("subject", "")), it.get("type"))].append(it)
    out = []
    for (side, subj, typ), rows in g.items():
        sites = {r["site"] for r in rows}
        out.append({"side": side, "subject": rows[0].get("subject"), "type": typ,
                    "statement": rows[0].get("statement"), "n_sites": len(sites),
                    "status": "confirmed" if len(sites) >= 2 else "single_source",
                    "evidence": [{"site": r["site"], "url": r["url"], "published": r["published"],
                                  "quote": r.get("quote")} for r in rows]})
    out.sort(key=lambda x: -x["n_sites"])
    return out


# --------------------------------------------------------------------------- BSD 结构化覆盖
def bsd_probe(c: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from bsd_intel.map import get_event_map
        em = get_event_map(c["match_id"])
    except Exception as e:  # noqa: BLE001
        return {"mapped": False, "error": str(e)[:100]}
    if not em:
        return {"mapped": False}
    eid = em.get("bsd_event_id")
    res: Dict[str, Any] = {"mapped": True, "bsd_event_id": eid}
    try:
        from bsd_intel.client import BsdClient
        with BsdClient() as cl:
            lu = cl.get(f"/api/v2/events/{eid}/lineups/").json()
            res["lineup_status"] = lu.get("lineup_status")
            un = lu.get("unavailable_players") or {}
            res["unavailable"] = {k: [(p.get("name"), p.get("reason") or p.get("status")) for p in (v or [])]
                                  for k, v in un.items()} if isinstance(un, dict) else un
            lns = lu.get("lineups") or {}
            res["has_xi"] = {k: len((v or {}).get("players") or []) for k, v in lns.items()} if isinstance(lns, dict) else {}
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[:120]
    return res


# --------------------------------------------------------------------------- 主流程
def run_one(mid: str) -> Dict[str, Any]:
    m = get_match(mid)
    if not m:
        return {"match_id": mid, "error": "not found"}
    c = identity_card(m)
    t0 = time.time()
    ret = retrieve(c)
    srcs = attach_text(ret["kept"])
    llm = llm_extract(c, srcs) if srcs else {"sources": []}
    v = verify(srcs, llm)
    claims = corroborate(v["items_ok"])
    return {
        "card": {k: (str(x) if k == "kickoff" else x) for k, x in c.items()},
        "stats": {"found": ret["found"], "kept": len(ret["kept"]), "dropped": len(ret["dropped"]),
                  "fetched_pages": sum(1 for s in srcs if s.get("fetched")), "analysed": len(srcs),
                  "accepted_sources": sum(1 for s in v["sources"] if s["accepted"]),
                  "items_raw": len(v["items_ok"]) + len(v["items_bad"]),
                  "items_ok": len(v["items_ok"]), "items_rejected": len(v["items_bad"]),
                  "quote_fail": sum(1 for i in v["items_bad"] if not i["quote_verified"]),
                  "claims": len(claims), "confirmed": sum(1 for x in claims if x["status"] == "confirmed"),
                  "secs": round(time.time() - t0, 1)},
        "sources": v["sources"], "claims": claims, "rejected": v["items_bad"],
        "dropped": [{"url": d["url"], "why": d["drop"]} for d in ret["dropped"]],
        "bsd": bsd_probe(c),
    }


def render_md(res: Dict[str, Any]) -> str:
    if "error" in res:
        return f"# {res['match_id']}: {res['error']}\n"
    c, s = res["card"], res["stats"]
    L = [f"# {c['home']} vs {c['away']}  ({c['league']} {c['kickoff_str']})  id={c['match_id']}",
         f"- 统计: {json.dumps(s, ensure_ascii=False)}",
         f"- BSD: {json.dumps(res['bsd'], ensure_ascii=False)}", "", "## 来源判定"]
    for x in res["sources"]:
        L.append(f"- [{x['about_effective']}] {'采纳' if x['accepted'] else '拒绝'} | {x['site']} | "
                 f"{x['published'] or '无日期'} | auth={x['authority']} | {x['title'][:50]}\n  {x['url']}")
        if x["fixture_evidence"]:
            L.append(f"  本场证据({'ok' if x['fixture_evidence_ok'] else '未在原文找到'}): {x['fixture_evidence']}")
    L += ["", "## 通过校验的事实(账本)"]
    for k in res["claims"]:
        L.append(f"- [{k['status']}/{k['n_sites']}站] {k['side']} {k['type']} {k['subject']}: {k['statement']}")
        for e in k["evidence"]:
            L.append(f"    - {e['site']} {e['published'] or ''}: \"{e['quote']}\"")
    L += ["", "## 被拒绝的条目"]
    for r in res["rejected"]:
        why = "引用不在原文" if not r["quote_verified"] else "来源未采纳"
        L.append(f"- ({why}) {r.get('side')} {r.get('type')} {r.get('subject')}: {r.get('statement')} | {r['site']}")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--auto", type=int, default=0)
    ap.add_argument("--out", default="/tmp/proto_evidence")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    ids = [x for x in a.ids.split(",") if x]
    if a.auto:
        ids += [str(m["match_id"]) for m in list_onsale()[:a.auto] if str(m["match_id"]) not in ids]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    agg = []
    for mid in ids:
        try:
            res = run_one(mid)
        except Exception as e:  # noqa: BLE001
            res = {'match_id': mid, 'error': f'{type(e).__name__}: {e}'[:200]}
        (out / f"{mid}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        (out / f"{mid}.md").write_text(render_md(res))
        agg.append(res)
        st = res.get("stats", {})
        print(mid, res.get("card", {}).get("home"), "vs", res.get("card", {}).get("away"), st)
    print("done ->", out)


if __name__ == "__main__":
    main()
