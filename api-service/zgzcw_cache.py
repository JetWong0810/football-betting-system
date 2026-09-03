"""足彩网预抓缓存: 预测/指数页只读库, 不开 Playwright。"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from database import get_db

logger = logging.getLogger(__name__)

_EMPTY_FORM = {
    "h2h": [],
    "homeRecent": [],
    "awayRecent": [],
    "homeFuture": [],
    "awayFuture": [],
}

_MAINSTREAM_AH = ["Pinnacle", "Bet365", "皇冠", "威廉希尔", "澳门", "立博"]


def _loads(raw) -> Any:
    if raw in (None, ""):
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def get_fenxi_cache(match_id: str) -> Optional[Dict[str, Any]]:
    if not match_id:
        return None
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT asian_json, euro_json, form_json, ou_json, "
                "asian_fetched_at, euro_fetched_at, form_fetched_at, "
                "ou_fetched_at, ticks_fetched_at "
                "FROM jczq_fenxi_cache WHERE match_id=%s",
                (match_id,),
            )
            return cur.fetchone()
    except Exception as e:
        logger.warning(f"读 fenxi 缓存失败 {match_id}: {e}")
        return None


def _ah_history_row(match_id: str) -> Optional[Dict[str, Any]]:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT open_handicap, close_handicap, open_home_odds, open_away_odds, "
                "close_home_odds, close_away_odds FROM jczq_ah_history "
                "WHERE match_id=%s AND company LIKE 'Bet365%%' LIMIT 1",
                (match_id,),
            )
            return cur.fetchone()
    except Exception as e:
        logger.warning(f"读亚盘历史失败 {match_id}: {e}")
        return None


def _neg(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return -float(val)
    except (TypeError, ValueError):
        return None


def asian_from_db(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    """拼 500 同构 asian_data。history 负=主让 → 列表正=主让。"""
    ah = _ah_history_row(match.get("match_id") or "")
    if ah and ah.get("close_handicap") is not None:
        return [{
            "bookmaker": "Bet365",
            "cid": 2,
            "initial": {
                "home": ah.get("open_home_odds"),
                "handicap": _neg(ah.get("open_handicap")),
                "away": ah.get("open_away_odds"),
            },
            "current": {
                "home": ah.get("close_home_odds"),
                "handicap": _neg(ah.get("close_handicap")),
                "away": ah.get("close_away_odds"),
            },
        }]
    raw = match.get("asian_handicap")
    if raw is None:
        return []
    try:
        hc = float(raw)
    except (TypeError, ValueError):
        return []
    return [{
        "bookmaker": "Bet365",
        "cid": 2,
        "initial": {},
        "current": {
            "home": match.get("asian_home_odds"),
            "handicap": hc,
            "away": match.get("asian_away_odds"),
        },
    }]


def apply_asian_handicap(match_info: Dict[str, Any], asian_data: Optional[List[Dict]]) -> None:
    """500 原值正=主让 → match_info.handicap 负=主让。"""
    if not asian_data:
        return
    curr_handicaps = []
    open_handicaps = []
    for c in asian_data:
        if c.get("bookmaker") in _MAINSTREAM_AH:
            h = (c.get("current") or {}).get("handicap")
            if h is not None:
                curr_handicaps.append(float(h))
            oh = (c.get("initial") or {}).get("handicap")
            if oh is not None:
                open_handicaps.append(float(oh))
    if not curr_handicaps:
        for c in asian_data:
            h = (c.get("current") or {}).get("handicap")
            if h is not None:
                curr_handicaps.append(float(h))
    if curr_handicaps:
        curr_handicaps.sort()
        match_info["handicap"] = -curr_handicaps[len(curr_handicaps) // 2]
    if open_handicaps:
        open_handicaps.sort()
        match_info["handicap_open"] = -open_handicaps[len(open_handicaps) // 2]


def _form_from_local(match: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    home = match.get("home_team_name")
    away = match.get("away_team_name")
    date = match.get("match_date")
    if not home or not away or not date:
        return None
    try:
        from local_match_data import build_local_match_data
        md = build_local_match_data(home, away, str(date)[:10])
    except Exception as e:
        logger.warning(f"本地基本面失败: {e}")
        return None
    if md and (md.get("homeRecent") or md.get("awayRecent") or md.get("h2h")):
        return md
    return None


def _try_500(fid: str, kind: str):
    if not fid:
        return None
    try:
        from odds500_service import fetch_asian_handicap, fetch_european_odds, fetch_match_data
        if kind == "form":
            return fetch_match_data(fid)
        if kind == "asian":
            return fetch_asian_handicap(fid)
        if kind == "euro":
            return fetch_european_odds(fid)
    except Exception as e:
        logger.warning(f"500 {kind} 兜底失败 fid={fid}: {e}")
    return None


def load_predict_inputs(match: Dict[str, Any]) -> Tuple[Optional[Dict], List, Optional[Dict]]:
    """返回 (match_data, asian_data, euro_data)。API 不开浏览器。"""
    cache = get_fenxi_cache(match.get("match_id") or "")
    form = _loads((cache or {}).get("form_json"))
    asian = _loads((cache or {}).get("asian_json"))
    euro = _loads((cache or {}).get("euro_json"))
    if isinstance(asian, dict):
        asian = asian.get("companies") or []
    if not isinstance(asian, list):
        asian = []
    if not asian:
        asian = asian_from_db(match)

    fid_500 = str(match.get("fid_500") or "").strip()
    if not form or not (form.get("homeRecent") or form.get("awayRecent")):
        form = _form_from_local(match) or form
    if (not form or not (form.get("homeRecent") or form.get("awayRecent"))) and fid_500:
        form = _try_500(fid_500, "form") or form
    if not asian and fid_500:
        asian = _try_500(fid_500, "asian") or []
    if (not euro or not euro.get("companies")) and fid_500:
        euro = _try_500(fid_500, "euro") or euro

    if form:
        if match.get("home_team_rank") and not form.get("homeRank"):
            form["homeRank"] = match.get("home_team_rank")
        if match.get("away_team_rank") and not form.get("awayRank"):
            form["awayRank"] = match.get("away_team_rank")
        if match.get("home_team_name") and not form.get("homeTeamName"):
            form["homeTeamName"] = match.get("home_team_name")
        if match.get("away_team_name") and not form.get("awayTeamName"):
            form["awayTeamName"] = match.get("away_team_name")
        for key, name in (
            ("homeTeamAliases", match.get("home_team_name")),
            ("awayTeamAliases", match.get("away_team_name")),
        ):
            if not name:
                continue
            aliases = list(form.get(key) or [])
            if name not in aliases:
                aliases.append(name)
            form[key] = aliases
    return form, asian or [], euro


def load_match_form(match: Dict[str, Any]) -> Dict[str, Any]:
    form, _, _ = load_predict_inputs(match)
    return form or dict(_EMPTY_FORM)


def _fmt_ts(ts) -> str:
    if ts is None:
        return ""
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    return str(ts)[:19]


def _companies(blob) -> List[Dict[str, Any]]:
    data = _loads(blob)
    if isinstance(data, dict):
        data = data.get("companies") or []
    if not isinstance(data, list):
        return []
    return data


def _euro_summary_rows(companies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not companies:
        return []
    try:
        from odds500_service import _calc_euro_summary
        summary = _calc_euro_summary(companies)
    except Exception:
        summary = {}
    rows = []
    for label, key in (("最大值", "max"), ("最小值", "min"), ("平均值", "avg")):
        block = summary.get(key) or {}
        if not block:
            continue
        rows.append({
            "bookmaker": label,
            "initial": block.get("initial") or {},
            "current": block.get("current") or {},
            "returnRate": block.get("returnRate") or 0,
        })
    return rows + companies


def load_indices(match: Dict[str, Any]) -> Dict[str, Any]:
    """指数页只读库, 不开浏览器。fid 返回 fid_zgzcw 供前端 history 查询。"""
    cache = get_fenxi_cache(match.get("match_id") or "") or {}
    euro = _companies(cache.get("euro_json"))
    asian = _companies(cache.get("asian_json"))
    ou = _companies(cache.get("ou_json"))
    if not asian:
        asian = asian_from_db(match)
    return {
        "fid": str(match.get("fid_zgzcw") or "").strip(),
        "indices": {
            "european": _euro_summary_rows(euro),
            "asian": asian,
            "overUnder": ou,
        },
    }


def find_match_by_fid(fid: str) -> Optional[Dict[str, Any]]:
    if not fid:
        return None
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM matches WHERE fid_zgzcw=%s OR fid_500=%s LIMIT 1",
                (fid, fid),
            )
            return cur.fetchone()
    except Exception as e:
        logger.warning(f"按 fid 查比赛失败 {fid}: {e}")
        return None


def list_ah_ticks(match_id: str, cid: int = 2) -> List[Dict[str, Any]]:
    if not match_id:
        return []
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT tick_time, home_odds, handicap, handicap_text, away_odds "
                "FROM jczq_ah_ticks WHERE match_id=%s AND cid=%s "
                "ORDER BY tick_time DESC",
                (match_id, cid),
            )
            out = []
            for r in cur.fetchall() or []:
                out.append({
                    "home": float(r["home_odds"]) if r.get("home_odds") is not None else None,
                    "handicap": float(r["handicap"]) if r.get("handicap") is not None else None,
                    "handicapText": r.get("handicap_text") or "",
                    "away": float(r["away_odds"]) if r.get("away_odds") is not None else None,
                    "time": _fmt_ts(r.get("tick_time")),
                })
            return out
    except Exception as e:
        logger.warning(f"读亚盘 ticks 失败 {match_id}: {e}")
        return []


def _two_point_history(item: Optional[Dict[str, Any]], kind: str, fetched_at) -> List[Dict[str, Any]]:
    if not item:
        return []
    ini = item.get("initial") or {}
    cur = item.get("current") or {}
    now_s = _fmt_ts(fetched_at) or "即时"
    if kind == "european":
        curr_row = {
            "win": cur.get("win"),
            "draw": cur.get("draw"),
            "lose": cur.get("lose"),
            "returnRate": item.get("returnRate"),
            "time": now_s,
        }
        init_row = {
            "win": ini.get("win"),
            "draw": ini.get("draw"),
            "lose": ini.get("lose"),
            "returnRate": item.get("returnRate"),
            "time": "初盘",
        }
        if any(init_row.get(k) is not None for k in ("win", "draw", "lose")):
            return [curr_row, init_row]
        return [curr_row]
    if kind == "asian":
        curr_row = {
            "home": cur.get("home"),
            "handicap": cur.get("handicap"),
            "handicapText": cur.get("handicapText") or "",
            "away": cur.get("away"),
            "time": now_s,
        }
        init_row = {
            "home": ini.get("home"),
            "handicap": ini.get("handicap"),
            "handicapText": ini.get("handicapText") or "",
            "away": ini.get("away"),
            "time": "初盘",
        }
        if any(init_row.get(k) is not None for k in ("home", "handicap", "away")):
            return [curr_row, init_row]
        return [curr_row]
    curr_row = {
        "over": cur.get("over"),
        "line": cur.get("line"),
        "under": cur.get("under"),
        "time": now_s,
    }
    init_row = {
        "over": ini.get("over"),
        "line": ini.get("line"),
        "under": ini.get("under"),
        "time": "初盘",
    }
    if any(init_row.get(k) is not None for k in ("over", "line", "under")):
        return [curr_row, init_row]
    return [curr_row]


def _pick_company(companies: List[Dict[str, Any]], cid: int) -> Optional[Dict[str, Any]]:
    for c in companies:
        try:
            if int(c.get("cid") or 0) == int(cid):
                return c
        except (TypeError, ValueError):
            continue
    return None


def load_odds_history(
    match: Optional[Dict[str, Any]],
    kind: str,
    cid: int,
) -> List[Dict[str, Any]]:
    """赔率变动只读库。Bet365 亚盘优先 ticks; 其余用初/即时两点。"""
    if not match:
        return []
    cache = get_fenxi_cache(match.get("match_id") or "") or {}
    if kind == "asian" and int(cid) == 2:
        ticks = list_ah_ticks(match.get("match_id") or "", cid=2)
        if ticks:
            return ticks
        asian = _companies(cache.get("asian_json")) or asian_from_db(match)
        item = _pick_company(asian, cid) or (asian[0] if asian else None)
        return _two_point_history(item, "asian", cache.get("asian_fetched_at"))
    if kind == "european":
        euro = _companies(cache.get("euro_json"))
        item = _pick_company(euro, cid)
        return _two_point_history(item, "european", cache.get("euro_fetched_at"))
    if kind == "overunder":
        ou = _companies(cache.get("ou_json"))
        item = _pick_company(ou, cid)
        return _two_point_history(item, "overunder", cache.get("ou_fetched_at"))
    return []
