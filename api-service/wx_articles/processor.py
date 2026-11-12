"""文章处理:关联比赛 -> 抽取事实/观点(原文引用校验) -> 联网核实事实 -> 落库。

CLI 试跑(不落库):
  python3 -m wx_articles.processor --file /tmp/a.txt --publish "2026-11-12 08:00:00" --title "标题" --name "公众号"
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from database import get_db

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
MAX_ATTEMPTS = 3

MARKETS = {"spf", "rqspf", "ah", "ou", "score", "dc", "other"}
CLAIM_TYPES = {"injury", "suspension", "lineup", "rotation", "motivation", "schedule", "manager", "odds", "other"}


# --------------------------------------------------------------------------- 候选比赛
def candidates(publish: datetime) -> List[Dict[str, Any]]:
    """发布前 48h 起到发布后 72h 内开赛的比赛(含刚结束的,用于识别赛后复盘)。"""
    ts = publish.replace(tzinfo=CST).timestamp()
    lo, hi = int(ts - 48 * 3600), int(ts + 72 * 3600)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT match_id, match_number, match_code, league_name, home_team_name, away_team_name, "
            "match_timestamp, home_score, away_score FROM matches "
            "WHERE match_id NOT LIKE 'jczq%%' AND match_timestamp BETWEEN %s AND %s ORDER BY match_timestamp",
            (lo, hi))
        rows = list(cur.fetchall() or [])
    for r in rows:
        r["kickoff"] = datetime.fromtimestamp(int(r["match_timestamp"]), CST).replace(tzinfo=None)
    return rows


def _norm(s: str) -> str:
    return re.sub(r"[\s　，。、；：,.;:!?！？\"'“”‘’()（）\[\]【】\-—·]+", "", s or "").lower()


def name_hit(name: str, text: str) -> int:
    """2=全名命中, 1=前两字命中(简称), 0=未命中。"""
    if not name:
        return 0
    if name in text:
        return 2
    if len(name) >= 3 and name[:2] in text:
        return 1
    return 0


# --------------------------------------------------------------------------- 抽取
EXTRACT_SYSTEM = """你是体育公众号文章的结构化抽取器,只依据给定文章正文,禁止使用自身记忆和推断。
你会收到:文章发布时间、候选比赛清单(含 match_id)、文章标题与正文。

任务:
1. summary: 一句话总结全文(≤80字)。
2. matches: 文章中讨论的、且在候选清单里的比赛,每场一项:
   - match_id: 必须取自候选清单;不在清单里的不要放这里。
   - timing: preview=赛前分析/预测; review=在复盘已完赛的比赛(“昨天…最终…”“已经结束”)。
   - evidence: 文中能证明在谈这场比赛的原句(原样摘录,≤60字)。
   - view: 作者对本场的核心观点(≤60字),没有则空。
   - picks: 作者对本场【明确的赛前推荐】。只收有明确倾向的推荐;分析中的泛泛判断、复盘里的过去推荐一律不收。
       market: spf=胜平负(主胜/平/客胜); rqspf=竞彩让球胜平负; ah=亚盘; ou=大小球; score=比分; dc=双选/不败(如“主场不败”); other。
       selection: 取 home|draw|away|home_draw|away_draw|over|under,比分或其他填原文。
       line: 原文给出的盘口线(如 -0.5、2.5),没有则空。不要自己推断盘口。
       quote: 原文原样片段(≤60字)。
   - claims: 作者陈述的、可被核实的【事实】(伤停、停赛、首发/阵容、轮换、战意、赛程、主帅变动、赔率/盘口变化)。不收纯观点和预测。
       type: injury|suspension|lineup|rotation|motivation|schedule|manager|odds|other
       side: home|away|both(以候选清单里的主客队为准)
       subject: 球员/球队名; text: 事实陈述(≤50字); quote: 原文原样片段(≤60字)。
3. other_matches: 文中提到但不在候选清单里的比赛,每项一句话(例如已完赛很久或其他联赛)。

规则:quote/evidence 必须逐字出现在正文中;字符串内不要出现英文双引号;没有的数组给 []。
只输出 JSON:
{"summary":"","matches":[{"match_id":"","timing":"preview","evidence":"","view":"","picks":[],"claims":[]}],"other_matches":[]}"""


def _client():
    from openai import OpenAI
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return OpenAI(api_key=key, base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))


def _parse_json(txt: str) -> Dict[str, Any]:
    txt = (txt or "").strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def llm_extract(title: str, text: str, publish: datetime, cands: List[Dict[str, Any]]) -> Dict[str, Any]:
    lines = []
    for c in cands:
        fin = f" 已完赛{c['home_score']}-{c['away_score']}" if c.get("home_score") is not None else ""
        lines.append(f"- match_id={c['match_id']} | {c['match_code']} | {c['league_name']} | "
                     f"主{c['home_team_name']} vs 客{c['away_team_name']} | 开赛{c['kickoff']:%m-%d %H:%M}{fin}")
    user = (f"发布时间(北京时间): {publish:%Y-%m-%d %H:%M}\n候选比赛:\n" + ("\n".join(lines) or "(无)") +
            f"\n\n标题: {title}\n正文:\n{text[:12000]}")
    last: Optional[Exception] = None
    for _ in range(3):
        try:
            r = _client().chat.completions.create(
                model=MODEL, temperature=0, max_tokens=8000, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": user}])
            return _parse_json(r.choices[0].message.content or "")
        except Exception as e:  # noqa: BLE001
            last = e
            logger.warning("wx extract retry: %s", e)
    raise last  # type: ignore[misc]


# --------------------------------------------------------------------------- 校验
def verify_extraction(raw: Dict[str, Any], text: str, publish: datetime,
                      cands: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id = {str(c["match_id"]): c for c in cands}
    hay = _norm(text)
    out_matches, dropped = [], []
    for m in raw.get("matches") or []:
        mid = str(m.get("match_id") or "")
        c = by_id.get(mid)
        if not c:
            dropped.append({"why": "match_id不在候选", "match_id": mid})
            continue
        h, a = name_hit(c["home_team_name"], text), name_hit(c["away_team_name"], text)
        ev = (m.get("evidence") or "").strip()
        ev_ok = bool(ev) and _norm(ev) in hay
        if h and a and ev_ok:
            status, conf = "linked", 90 if h + a >= 3 else 75
        elif (h or a) and ev_ok:
            status, conf = "ambiguous", 50
        else:
            dropped.append({"why": "两队/证据句未通过校验", "match_id": mid, "teams": [h, a], "ev_ok": ev_ok})
            continue
        finished = c.get("home_score") is not None
        timing = m.get("timing") if m.get("timing") in ("preview", "review") else "preview"
        pre = publish < c["kickoff"]
        if finished and pre is False:
            timing = "review"
        if not pre:
            timing = "review"        # 发布时间晚于开赛,一律视为赛后
        claims, picks = [], []
        for cl in m.get("claims") or []:
            q = (cl.get("quote") or "").strip()
            if not q or _norm(q) not in hay or not cl.get("text"):
                dropped.append({"why": "claim引用不在正文", "text": cl.get("text")})
                continue
            t = cl.get("type") if cl.get("type") in CLAIM_TYPES else "other"
            s = cl.get("side") if cl.get("side") in ("home", "away", "both") else "both"
            claims.append({"type": t, "side": s, "subject": str(cl.get("subject") or "")[:60],
                           "text": str(cl["text"])[:250], "quote": q[:250]})
        if timing == "preview" and status == "linked":
            for pk in m.get("picks") or []:
                q = (pk.get("quote") or "").strip()
                mk = pk.get("market") if pk.get("market") in MARKETS else "other"
                if not q or _norm(q) not in hay or not pk.get("selection"):
                    dropped.append({"why": "pick引用不在正文", "pick": pk})
                    continue
                picks.append({"market": mk, "line": (str(pk["line"])[:16] if pk.get("line") not in (None, "") else None),
                              "selection": str(pk["selection"])[:32], "quote": q[:250]})
        out_matches.append({"match_id": mid, "status": status, "confidence": conf, "timing": timing,
                            "evidence": ev[:250], "view": str(m.get("view") or "")[:200],
                            "claims": claims, "picks": picks,
                            "label": f"{c['home_team_name']} vs {c['away_team_name']}"})
    return {"summary": str(raw.get("summary") or "")[:300], "matches": out_matches,
            "other_matches": [str(x)[:120] for x in (raw.get("other_matches") or [])][:8], "dropped": dropped}


# --------------------------------------------------------------------------- 联网核实
VERIFY_SYSTEM = """你是足球事实核查员。下面有【本场系统数据】和一篇公众号文章里的若干事实声明。
对每条声明独立核实:
- 用联网搜索查找官方(俱乐部/联赛/足协)或主流体育媒体在近期的报道;不得把这篇公众号文章本身当作证据。
- 数据类声明(赔率/盘口变化)直接用系统数据核对,不必联网。
- 核实对象以「原文」的实际含义为准;若上面的概括比原文更宽泛或更具体,按原文判断。
- status: confirmed=有可靠来源或系统数据支持; contradicted=必须有明确的可靠来源或系统数据直接反证(查不到不等于反驳); unverified=查不到或来源不可靠。
- note: 一句话说明依据(≤60字),含来源站点和日期;查不到就写“未查到可靠来源”。
- impact_dir/impact_level: 若该事实成立,对亚盘盘路的影响。upper=利于上盘(让球方),lower=利于下盘(受让方),neutral=无明显影响;level=high|medium|low|none。这是你的判断,与核实状态无关。亚盘符号:负=主让。
note 等字符串内不要出现英文双引号。
只输出 JSON(不要其他文字): {"results":[{"i":0,"status":"","note":"","impact_dir":"","impact_level":""}]}"""


def verify_claims(match_id: str, label: str, claims: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    from match_chat.context import build_context
    from match_chat.llm import stream_chat
    try:
        ctx = build_context(match_id)["text"]
    except Exception as e:  # noqa: BLE001
        logger.warning("verify ctx fail %s: %s", match_id, e)
        ctx = f"(系统数据读取失败) 比赛: {label}"
    user = f"本场系统数据:\n{ctx}\n\n待核实声明:\n" + "\n".join(
        f"{i}. [{c['type']}/{c['side']}] {c['subject']}: {c['text']}\n   原文: {c['quote']}" for i, c in enumerate(claims))
    last: Optional[Exception] = None
    for attempt in range(2):
        buf: List[str] = []
        srcs: List[Dict[str, str]] = []
        for ev in stream_chat(VERIFY_SYSTEM, [{"role": "user", "content": user}], web=True):
            if ev["type"] == "delta":
                buf.append(ev["text"])
            elif ev["type"] == "sources":
                srcs = ev["items"]
            elif ev["type"] == "error":
                raise RuntimeError(ev["text"])
        try:
            res = _parse_json("".join(buf)).get("results") or []
            if res:
                return res, srcs
            last = ValueError("empty results")
        except Exception as e:  # noqa: BLE001
            last = e
        logger.warning("wx verify parse failed (attempt %s): %s", attempt + 1, last)
    raise RuntimeError(f"核实结果解析失败: {last}")


def apply_verification(match_entry: Dict[str, Any], res: List[Dict[str, Any]], srcs: List[Dict[str, str]]) -> None:
    by_i = {int(r.get("i", -1)): r for r in res if isinstance(r, dict)}
    for i, c in enumerate(match_entry["claims"]):
        r = by_i.get(i) or {}
        c["verify_status"] = r.get("status") if r.get("status") in ("confirmed", "contradicted", "unverified") else "unverified"
        c["verify_note"] = str(r.get("note") or "未查到可靠来源")[:480]
        c["impact_dir"] = r.get("impact_dir") if r.get("impact_dir") in ("upper", "lower", "neutral") else None
        c["impact_level"] = r.get("impact_level") if r.get("impact_level") in ("high", "medium", "low", "none") else None
        c["verify_sources"] = []      # 搜索来源与单条事实无对应关系,不逐条挂载;依据写在 note 里


# --------------------------------------------------------------------------- 主流程
def analyze(title: str, text: str, publish: datetime, verify: bool = True) -> Dict[str, Any]:
    cands = candidates(publish)
    raw = llm_extract(title, text, publish, cands)
    res = verify_extraction(raw, text, publish, cands)
    res["candidates"] = len(cands)
    if verify:
        for m in res["matches"]:
            if m["claims"] and m["timing"] == "preview":
                try:
                    rr, ss = verify_claims(m["match_id"], m["label"], m["claims"])
                    apply_verification(m, rr, ss)
                except Exception as e:  # noqa: BLE001
                    logger.warning("verify fail %s: %s", m["match_id"], e)
                    for c in m["claims"]:
                        c["verify_status"] = "unverified"
                        c["verify_note"] = "核实失败(技术原因),非“查不到”"
    return res


def save_result(art: Dict[str, Any], res: Dict[str, Any]) -> None:
    aid = art["id"]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM wx_article_match WHERE article_id=%s", (aid,))
        cur.execute("DELETE FROM wx_article_claim WHERE article_id=%s", (aid,))
        for m in res["matches"]:
            cur.execute(
                "INSERT INTO wx_article_match (article_id, match_id, timing, status, confidence, evidence) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (aid, m["match_id"], m["timing"], m["status"], m["confidence"], m["evidence"]))
            for c in m["claims"]:
                cur.execute(
                    "INSERT INTO wx_article_claim (article_id, match_id, claim_type, side, subject, text, quote, "
                    "verify_status, verify_note, verify_sources, impact_dir, impact_level) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (aid, m["match_id"], c["type"], c["side"], c["subject"], c["text"], c["quote"],
                     c.get("verify_status", "unverified"), c.get("verify_note"),
                     json.dumps(c.get("verify_sources") or [], ensure_ascii=False),
                     c.get("impact_dir"), c.get("impact_level")))
            for p in m["picks"]:      # 观点入库后不再修改(仅赛后更新 result);重复处理不覆盖
                cur.execute(
                    "INSERT IGNORE INTO wx_article_pick (article_id, wxid, match_id, market, line, selection, quote, pre_match) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,1)",
                    (aid, art.get("wxid") or "", m["match_id"], p["market"], p["line"], p["selection"], p["quote"]))
        if art.get("wxid"):
            cur.execute("INSERT INTO wx_account (wxid, name) VALUES (%s,%s) ON DUPLICATE KEY UPDATE name=VALUES(name)",
                        (art["wxid"], art.get("account_name") or ""))
        cur.execute("UPDATE wx_article SET summary=%s, analysis_json=%s, processed_at=NOW() WHERE id=%s",
                    (res["summary"], json.dumps({k: res[k] for k in ("other_matches", "dropped", "candidates")},
                                                ensure_ascii=False), aid))


# --------------------------------------------------------------------------- 队列
def _claim_one() -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM wx_article WHERE status IN ('pending','failed') AND attempts<%s "
                    "ORDER BY id LIMIT 1", (MAX_ATTEMPTS,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("UPDATE wx_article SET status='processing', attempts=attempts+1 "
                    "WHERE id=%s AND status IN ('pending','failed')", (row["id"],))
        if cur.rowcount != 1:
            return None            # 被别的进程抢走
        cur.execute("SELECT * FROM wx_article WHERE id=%s", (row["id"],))
        return cur.fetchone()


def process_next() -> bool:
    art = _claim_one()
    if not art:
        return False
    try:
        text = art.get("content") or art.get("description") or ""
        publish = art.get("publish_time") or datetime.now(CST).replace(tzinfo=None)
        if len(text.strip()) < 30:
            res = {"summary": "", "matches": [], "other_matches": [], "dropped": [{"why": "无正文"}], "candidates": 0}
        else:
            res = analyze(art["title"], text, publish)
        save_result(art, res)
        status, err = "done", None
    except Exception as e:  # noqa: BLE001
        logger.exception("wx process failed %s", art.get("id"))
        status, err = "failed", f"{type(e).__name__}: {e}"[:250]
    with get_db() as conn:
        conn.cursor().execute("UPDATE wx_article SET status=%s, last_error=%s WHERE id=%s", (status, err, art["id"]))
    return True


def _loop() -> None:
    while True:
        try:
            if not process_next():
                time.sleep(20)
        except Exception:  # noqa: BLE001
            logger.exception("wx worker loop")
            time.sleep(30)


def start_worker() -> None:
    """仅当 WX_WORKER=1 时启动(生产容器开启,本地默认不开,避免共享库被重复处理)。"""
    if os.getenv("WX_WORKER") != "1":
        return
    threading.Thread(target=_loop, name="wx-worker", daemon=True).start()
    logger.info("wx worker started")


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--publish", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    text = Path(a.file).read_text()
    pub = datetime.strptime(a.publish, "%Y-%m-%d %H:%M:%S")
    res = analyze(a.title, text, pub, verify=not a.no_verify)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
