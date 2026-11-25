"""北单(北京单场)比赛列表 + 单场数据页(交锋/近期战绩/未来赛事/积分)按需抓取。

设计:
  - 没有定时任务。列表在用户打开北单列表页时刷新(10 分钟内复用);
    单场的盘口赔率(odds500_live)和数据页(本模块 fetch_fenxi)在用户于聊天里要求时才抓。
  - 比赛 ID 用 `bd_{500.com fid}`, 与竞彩 matches 表完全分开; 盘口变动继续写 odds500_*_ticks。
  - 来源 500.com: trade.500.com/bjdc/ (列表) 与 odds.500.com/fenxi/shuju-{fid}.shtml (数据页)。
    与 AI 聊天共用出口 IP, 所以抓取有最小间隔、每小时上限, 遇到防护页直接放弃并用库里已有数据。
失败一律不抛异常, 返回 None / {"ok": False, "reason": ...}。
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from database import get_db

logger = logging.getLogger(__name__)

_BJ = timezone(timedelta(hours=8))
LIST_URL = "https://trade.500.com/bjdc/"
FENXI_URL = "https://odds.500.com/fenxi/shuju-{fid}.shtml"
LIST_TTL = 600
FENXI_TTL = 1800
FENXI_COOLDOWN = 60
HOURLY_CAP = 120
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

_lock = threading.Lock()
_calls: List[float] = []
_last_list = 0.0
_tables_ready = False


def bd_id(fid: Any) -> str:
    return f"bd_{fid}"


def is_bd(match_id: Any) -> bool:
    return str(match_id or "").startswith("bd_")


def fid_of(match_id: str) -> str:
    return str(match_id)[3:]


def ensure_tables() -> None:
    global _tables_ready
    if _tables_ready:
        return
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS bd_matches (
            match_id VARCHAR(40) NOT NULL PRIMARY KEY,
            fid VARCHAR(20) NOT NULL,
            period VARCHAR(10) DEFAULT NULL,
            num INT DEFAULT NULL,
            league VARCHAR(50) DEFAULT NULL,
            home_team VARCHAR(80) NOT NULL,
            away_team VARCHAR(80) NOT NULL,
            kickoff_ts BIGINT DEFAULT NULL,
            rq VARCHAR(8) DEFAULT NULL COMMENT '北单让球数(整数)',
            ah_text VARCHAR(32) DEFAULT NULL COMMENT '500.com 亚盘让球(文字)',
            score VARCHAR(16) DEFAULT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_bd_fid (fid),
            INDEX idx_bd_kick (kickoff_ts)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""")
        cur.execute("""CREATE TABLE IF NOT EXISTS bd_fenxi_cache (
            match_id VARCHAR(40) NOT NULL PRIMARY KEY,
            payload MEDIUMTEXT NOT NULL,
            fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""")
    _tables_ready = True


# ---------------------------------------------------------------- 解析
def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _decode(content: bytes) -> str:
    for enc in ("gb18030", "utf-8"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", "ignore")


def looks_blocked(text: str) -> bool:
    return len(text) < 4000 or "EO_Bot" in text[:3000]


def parse_bd_list(page: str) -> List[Dict[str, Any]]:
    """解析 trade.500.com/bjdc/ 当前期全部场次。开赛时间取自 title="比赛时间:HH:MM", 日期取截止时间的日期(跨零点顺延)。"""
    sel = re.search(r'<option value="(\d+)"[^>]*selected', page)
    period = sel.group(1) if sel else None
    out: List[Dict[str, Any]] = []
    for m in re.finditer(r'<tr[^>]*class="vs_lines[^"]*"[^>]*value="\{([^}]*)\}"[^>]*fid="(\d+)"[^>]*>(.*?)</tr>', page, re.S):
        meta, fid, body = m.group(1), m.group(2), m.group(3)
        g = lambda k: (re.search(k + r":'([^']*)'", meta) or [None, ""])[1]
        end = g("endTime")
        kt = re.search(r"比赛时间[：:]\s*(\d{1,2}:\d{2})", body)
        ko = None
        try:
            if end and kt:
                d = datetime.strptime(end[:16], "%Y-%m-%d %H:%M")
                h, mi = map(int, kt.group(1).split(":"))
                ko = d.replace(hour=h, minute=mi)
                if ko < d:
                    ko += timedelta(days=1)
            elif end:
                ko = datetime.strptime(end[:16], "%Y-%m-%d %H:%M") + timedelta(minutes=10)
        except ValueError:
            ko = None
        rq = re.search(r'<strong class="eng[^"]*">\s*([+-]?\d+)\s*</strong>', body)
        ah = re.search(r'class="asianhand">([^<]*)<', body)
        sc = re.search(r'title="析"[^>]*>\s*(\d+:\d+)\s*<', body)
        num = re.search(r'class="chnum">(\d+)<', body)
        if not g("homeTeam") or not g("guestTeam"):
            continue
        out.append({
            "fid": fid, "matchId": bd_id(fid), "period": period,
            "num": int(num.group(1)) if num else None,
            "league": g("leagueName"), "home": g("homeTeam"), "away": g("guestTeam"),
            "kickoffTs": int(ko.replace(tzinfo=_BJ).timestamp()) if ko else None,
            "rq": rq.group(1) if rq else None, "ahText": _txt(ah.group(1)) if ah else None,
            "score": sc.group(1) if sc else None,
        })
    return out


def _hc_title(row: str) -> str:
    """盘口格子的 title 属性是文字盘口(如'受半球'=主队受让半球), 比数字的正负号更不易误读。"""
    for td in re.findall(r"<td[^>]*>", row):
        t = re.search(r'title="([^"]+)"', td)
        if t and "oddsshow" in td and re.search(r"球|平手", t.group(1)):
            return _html.unescape(t.group(1))
    return ""


def _result_rows(block: str, skip_fid: Optional[str] = None) -> List[Dict[str, Any]]:
    """交锋/近期战绩表行。两种版式: 简版(盘口|半场|赛果|盘路|大小)和带赔率版(半场|赛果|欧赔|亚盘 水 盘口文字 水|盘路|大小)。
    盘口一律给文字(主队视角: '半球'=主让半球, '受半球'=主受让半球)。排除本场自身(隐藏的 bmatch 行)。"""
    rows = []
    for r in re.findall(r'<tr[^>]*class="tr\d[^"]*"[^>]*>.*?</tr>', block, re.S):
        if "bmatch" in r.split(">", 1)[0] or (skip_fid and f"shuju-{skip_fid}" in r):
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(tds) < 6:
            continue
        dz = re.sub(r'<span class="gray">[^<]*</span>', "", tds[2])
        hm = re.search(r'class="dz-l[^"]*"[^>]*>(.*?)</span>', dz, re.S)
        am = re.search(r'class="dz-r[^"]*"[^>]*>(.*?)</span>', dz, re.S)
        em = re.search(r"<em[^>]*>(.*?)</em>", dz, re.S)
        score = re.sub(r"\s+", "", _txt(em.group(1))) if em else ""
        if not hm or not am or not re.match(r"^\d+-\d+$", score):
            continue
        row = {"competition": _txt(tds[0]), "date": _txt(tds[1]), "home": _txt(hm.group(1)), "away": _txt(am.group(1)),
               "score": score, "handicapText": "", "ahWater": "", "euro": "", "half": "", "result": "", "ahResult": "", "ou": ""}
        if "pub_table_pl" in r and len(tds) >= 9:
            row["half"] = re.sub(r"\s+", "", _txt(tds[3]))
            row["result"] = _txt(tds[4])
            row["euro"] = "/".join(_txt(x) for x in re.findall(r"<span[^>]*>(.*?)</span>", tds[5], re.S))
            sp = [_txt(x) for x in re.findall(r"<span[^>]*>(.*?)</span>", tds[6], re.S)]
            if len(sp) == 3:
                row["handicapText"], row["ahWater"] = sp[1], f"{sp[0]}/{sp[2]}"
            row["ahResult"], row["ou"] = _txt(tds[7]), _txt(tds[8])
        else:
            row["handicapText"] = _hc_title(r)
            row["half"] = re.sub(r"\s+", "", _txt(tds[4])) if len(tds) > 4 else ""
            row["result"] = _txt(tds[5]) if len(tds) > 5 else ""
            row["ahResult"] = _txt(tds[6]) if len(tds) > 6 else ""
            row["ou"] = _txt(tds[7]) if len(tds) > 7 else ""
        rows.append(row)
    return rows


def _norm_date(d: str) -> str:
    """'26-11-24' -> '2026-11-24'(与竞彩侧一致, 便于按开赛日截断)。"""
    return f"20{d}" if re.match(r"^\d{2}-\d{2}-\d{2}$", d or "") else d


def _slice(page: str, start_key: str, end_keys: List[str]) -> str:
    i = page.find(start_key)
    if i < 0:
        return ""
    ends = [page.find(k, i + len(start_key)) for k in end_keys]
    ends = [e for e in ends if e > 0]
    return page[i:min(ends) if ends else i + 60000]


def parse_fenxi(page: str, fid: str) -> Dict[str, Any]:
    ids = ["team_jiaozhan", "team_zhanji_1", "team_zhanji_0", "team_zhanji1_1", "team_zhanji1_0", "team_zhanji2_1", "team_zhanji2_0"]
    marks = [f'id="{i}"' for i in ids]
    h2h_blk = _slice(page, 'id="team_jiaozhan"', ['id="team_zhanji_1"'])
    home_blk = _slice(page, 'id="team_zhanji_1"', marks[2:])
    away_blk = _slice(page, 'id="team_zhanji_0"', marks[3:])
    h2h = [] if "暂无数据" in h2h_blk[:600] and "<tr class=\"tr" not in h2h_blk else _result_rows(h2h_blk, fid)
    for lst in (h2h,):
        for r in lst:
            r["date"] = _norm_date(r["date"])
    home_rec, away_rec = _result_rows(home_blk, fid), _result_rows(away_blk, fid)
    for r in home_rec + away_rec:
        r["date"] = _norm_date(r["date"])

    def fixtures(side_tbl: str) -> List[Dict[str, str]]:
        res = []
        for r in re.findall(r'<tr class="tr\d[^"]*"[^>]*>.*?</tr>', side_tbl, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
            if len(tds) < 4:
                continue
            hm = re.search(r'class="dz-l"[^>]*>(.*?)</a>', tds[2], re.S)
            am = re.search(r'class="dz-r"[^>]*>(.*?)</a>', tds[2], re.S)
            if hm and am:
                res.append({"competition": _txt(tds[0]), "date": _txt(tds[1]), "home": _txt(hm.group(1)),
                            "away": _txt(am.group(1)), "gap": _txt(tds[3])})
        return res

    fx = _slice(page, 'id="shuju-fixtures"', ["<!--联赛积分排名-->", 'id="shuju-lineup"'])
    fx_a, fx_b = (fx.split('class="team_b"', 1) + [""])[:2]

    st = _slice(page, "赛前联赛积分排名", ["<!--", 'id="shuju-fixtures"'])
    st_a, st_b = (st.split('class="team_b"', 1) + [""])[:2]
    names = re.findall(r'class="team_name">([^<]*)<span>([^<]*)</span>', st)

    def standing(blk: str) -> Dict[str, List[str]]:
        o = {}
        for r in re.findall(r"<tr[^>]*>.*?</tr>", blk, re.S):
            tds = [_txt(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
            if len(tds) >= 11 and tds[0] in ("总成绩", "主场", "客场"):
                o[tds[0]] = tds[1:]
        return o

    return {
        "h2h": h2h, "homeRecent": home_rec, "awayRecent": away_rec,
        "homeFuture": fixtures(fx_a), "awayFuture": fixtures(fx_b),
        "standings": {"home": standing(st_a), "away": standing(st_b),
                      "homeRank": names[0][1] if names else "", "awayRank": names[1][1] if len(names) > 1 else ""},
    }


# ---------------------------------------------------------------- 抓取
def _throttle() -> Optional[str]:
    now = time.time()
    _calls[:] = [t for t in _calls if now - t < 3600]
    if len(_calls) >= HOURLY_CAP:
        return "rate_limited"
    _calls.append(now)
    return None


def _breaker() -> bool:
    try:
        from odds500_ticks import breaker_open
        return bool(breaker_open())
    except Exception:  # noqa: BLE001
        return False


def _get(url: str, referer: str) -> Optional[str]:
    try:
        r = httpx.get(url, headers={**HEADERS, "Referer": referer}, timeout=20)
        if r.status_code != 200:
            logger.warning("500.com 北单请求 %s -> %s", url, r.status_code)
            return None
        text = _decode(r.content)
        if looks_blocked(text):
            logger.warning("500.com 北单请求 %s 返回防护页/过短内容(%s 字)", url, len(text))
            return None
        return text
    except Exception as e:  # noqa: BLE001
        logger.warning("500.com 北单请求失败 %s: %s", url, e)
        return None


def _upsert_list(items: List[Dict[str, Any]]) -> None:
    rows = [(i["matchId"], i["fid"], i["period"], i["num"], i["league"], i["home"], i["away"], i["kickoffTs"],
             i["rq"], i["ahText"], i["score"]) for i in items]
    with get_db() as conn:
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO bd_matches (match_id, fid, period, num, league, home_team, away_team, kickoff_ts, rq, ah_text, score) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE period=VALUES(period), num=VALUES(num), "
            "league=VALUES(league), home_team=VALUES(home_team), away_team=VALUES(away_team), kickoff_ts=VALUES(kickoff_ts), "
            "rq=VALUES(rq), ah_text=VALUES(ah_text), score=VALUES(score)", rows)


def refresh_list(force: bool = False) -> Dict[str, Any]:
    """刷新北单列表入库。10 分钟内复用; 抓取失败不影响读库。返回 {ok, reason, count}。"""
    global _last_list
    now = time.time()
    if not force and now - _last_list < LIST_TTL:
        return {"ok": True, "cached": True}
    if force and now - _last_list < 30:
        return {"ok": True, "cached": True}
    if _breaker():
        return {"ok": False, "reason": "blocked"}
    if not _lock.acquire(blocking=False):
        return {"ok": True, "cached": True}
    try:
        ensure_tables()
        if _throttle():
            return {"ok": False, "reason": "rate_limited"}
        page = _get(LIST_URL, "https://trade.500.com/")
        if page is None:
            return {"ok": False, "reason": "fetch_failed"}
        items = parse_bd_list(page)
        if not items:
            return {"ok": False, "reason": "parse_empty"}
        _upsert_list(items)
        _last_list = time.time()
        return {"ok": True, "count": len(items), "period": items[0]["period"]}
    except Exception as e:  # noqa: BLE001
        logger.warning("北单列表刷新失败: %s", e)
        return {"ok": False, "reason": "error"}
    finally:
        _lock.release()


def list_matches(hours_back: int = 24) -> List[Dict[str, Any]]:
    ensure_tables()
    since = int(time.time()) - hours_back * 3600
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM bd_matches WHERE kickoff_ts IS NULL OR kickoff_ts >= %s ORDER BY kickoff_ts ASC, num ASC", (since,))
        rows = list(cur.fetchall() or [])
    return [_row_out(r) for r in rows]


def _row_out(r: Dict[str, Any]) -> Dict[str, Any]:
    ts = r.get("kickoff_ts")
    return {"matchId": r["match_id"], "fid": r["fid"], "period": r.get("period"), "num": r.get("num"),
            "league": r.get("league"), "homeTeam": r["home_team"], "awayTeam": r["away_team"],
            "kickoffTs": ts, "kickoff": datetime.fromtimestamp(ts, _BJ).strftime("%Y-%m-%d %H:%M") if ts else None,
            "rq": r.get("rq"), "ahText": r.get("ah_text"), "score": r.get("score")}


def get_match(match_id: str) -> Optional[Dict[str, Any]]:
    if not is_bd(match_id):
        return None
    try:
        ensure_tables()
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM bd_matches WHERE match_id=%s", (match_id,))
            r = cur.fetchone()
        return _row_out(r) if r else None
    except Exception:  # noqa: BLE001
        return None


def load_fenxi(match_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[datetime]]:
    """只读库。返回 (payload, 抓取时间-北京时间)。"""
    try:
        ensure_tables()
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT payload, fetched_at FROM bd_fenxi_cache WHERE match_id=%s", (match_id,))
            r = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None, None
    if not r:
        return None, None
    try:
        data = json.loads(r["payload"])
    except (TypeError, json.JSONDecodeError):
        return None, None
    at = r["fetched_at"].replace(tzinfo=timezone.utc).astimezone(_BJ).replace(tzinfo=None) if r.get("fetched_at") else None
    return data, at


_fenxi_recent: Dict[str, float] = {}


def fetch_fenxi(match_id: str, force: bool = False) -> Dict[str, Any]:
    """按需抓取单场数据页(交锋/近期战绩/未来赛事/积分)并落库。"""
    if not is_bd(match_id):
        return {"ok": False, "reason": "not_bd"}
    now = time.time()
    data, at = load_fenxi(match_id)
    if data and not force and at and now - at.replace(tzinfo=_BJ).timestamp() < FENXI_TTL:
        return {"ok": True, "cached": True, "fetchedAt": at.strftime("%Y-%m-%d %H:%M:%S")}
    if now - _fenxi_recent.get(match_id, 0) < FENXI_COOLDOWN:
        return {"ok": bool(data), "reason": None if data else "cooldown", "cached": True}
    if _breaker():
        return {"ok": False, "reason": "blocked"}
    if _throttle():
        return {"ok": False, "reason": "rate_limited"}
    _fenxi_recent[match_id] = now
    fid = fid_of(match_id)
    page = _get(FENXI_URL.format(fid=fid), "https://trade.500.com/bjdc/")
    if page is None:
        return {"ok": False, "reason": "fetch_failed"}
    try:
        payload = parse_fenxi(page, fid)
        if not (payload["homeRecent"] or payload["awayRecent"] or payload["h2h"]):
            return {"ok": False, "reason": "parse_empty"}
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO bd_fenxi_cache (match_id, payload) VALUES (%s,%s) ON DUPLICATE KEY UPDATE "
                        "payload=VALUES(payload), fetched_at=CURRENT_TIMESTAMP",
                        (match_id, json.dumps(payload, ensure_ascii=False)))
    except Exception as e:  # noqa: BLE001
        logger.warning("北单数据页解析/落库失败 %s: %s", match_id, e)
        return {"ok": False, "reason": "error"}
    return {"ok": True, "fetchedAt": datetime.now(_BJ).strftime("%Y-%m-%d %H:%M:%S"),
            "h2h": len(payload["h2h"]), "home": len(payload["homeRecent"]), "away": len(payload["awayRecent"])}


FENXI_REASON = {
    "blocked": "500.com 当前处于限流退避期", "rate_limited": "抓取次数已达每小时上限", "fetch_failed": "500.com 数据页获取失败",
    "parse_empty": "数据页里没有解析到战绩数据", "cooldown": "刚抓取过,稍后再试", "error": "解析或存储出错", "not_bd": "非北单比赛",
}
