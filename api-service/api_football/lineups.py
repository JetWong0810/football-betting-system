"""官方首发: 抓取(/fixtures/lineups, 另取两队上一场首发算轮换人数) -> 缓存 -> 渲染成一小段文字给聊天。

设计取舍(防止数据太多干扰分析):
- 只在用户要求关联首发/阵容时才进上下文。
- 只给: 阵型、教练、按位置的首发名单(11 人)、较上一场的首发变化人数、与伤停名单的交叉提示。不列替补, 不列球员数据。
- 官方首发通常开赛前约 1 小时才公布, 没公布时明确说没有, 不让模型编"预计首发"。
- 首发是尚未被定价的新信息, 但接口不给公布时间: 不能说"盘口已反应/未反应", 只能对照盘口最近变动的时间。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from database import get_db

from .client import AfClient
from .injuries import _kickoff, _mapping, load_cached as load_injuries

logger = logging.getLogger(__name__)

TTL_PUBLISHED = 6 * 3600        # 已公布: 首发不会再变, 长缓存
TTL_UNPUBLISHED = 5 * 60        # 未公布: 临近开赛要尽快发现
FINISHED = {"FT", "AET", "PEN"}
POS_ZH = {"G": "门将", "D": "后卫", "M": "中场", "F": "前锋"}
_BJ = timezone(timedelta(hours=8))


def _team_xi(t: Dict[str, Any]) -> Dict[str, Any]:
    xi = [{"id": (x.get("player") or {}).get("id"), "name": (x.get("player") or {}).get("name"),
           "pos": (x.get("player") or {}).get("pos"), "grid": (x.get("player") or {}).get("grid")} for x in t.get("startXI") or []]
    return {"team_id": (t.get("team") or {}).get("id"), "team": (t.get("team") or {}).get("name"),
            "formation": t.get("formation"), "coach": (t.get("coach") or {}).get("name"), "coach_id": (t.get("coach") or {}).get("id"), "xi": xi}


def parse_lineups(resp: List[Dict[str, Any]]) -> Optional[Dict[str, Dict[str, Any]]]:
    """接口返回 -> {team_id: {...}}; 不足两队(未公布)返回 None。"""
    teams = [_team_xi(t) for t in resp or []]
    teams = [t for t in teams if t["team_id"] and len(t["xi"]) >= 9]
    return {str(t["team_id"]): t for t in teams} if len(teams) >= 2 else None


def rotation(cur_ids: List[int], prev_ids: List[int]) -> int:
    """本场首发相对上一场首发换了几人(按球员 id)。"""
    return len(set(cur_ids) - set(prev_ids))


def _prev_xi(c: AfClient, team_id: int, cur_fixture: int) -> Optional[Dict[str, Any]]:
    """该队上一场已完赛比赛(任何赛事)的首发。last=1 可能返回当场本身, 所以取 last=2 再过滤。"""
    try:
        for f in c.get("/fixtures", {"team": team_id, "last": 2}).get("response", []):
            if f["fixture"]["id"] == cur_fixture or f["fixture"]["status"]["short"] not in FINISHED:
                continue
            lu = parse_lineups(c.get("/fixtures/lineups", {"fixture": f["fixture"]["id"]}).get("response", []))
            t = (lu or {}).get(str(team_id))
            if not t:
                return None
            return {"ids": [x["id"] for x in t["xi"]], "date": f["fixture"]["date"][:10],
                    "opp": f["teams"]["away" if f["teams"]["home"]["id"] == team_id else "home"]["name"], "comp": f["league"]["name"]}
    except Exception as e:  # noqa: BLE001  轮换信息拿不到不影响首发本身
        logger.warning("上一场首发抓取失败 team=%s: %s", team_id, e)
    return None


def load_cached(match_id: str) -> Optional[Dict[str, Any]]:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT published, payload_json, fetched_at FROM af_lineup_cache WHERE match_id=%s", (match_id,))
            r = cur.fetchone()
    except Exception as e:  # noqa: BLE001
        if e.args and e.args[0] == 1146:
            return None
        raise
    if not r:
        return None
    return {"published": bool(r["published"]), "data": json.loads(r["payload_json"]) if r.get("payload_json") else {},
            "fetchedAt": r["fetched_at"]}


def fetch(match_id: str, force: bool = False, client: Optional[AfClient] = None) -> Dict[str, Any]:
    mp = _mapping(match_id)
    if not mp:
        return {"ok": False, "reason": "no_mapping"}
    cached = load_cached(match_id)
    if cached and not force:
        age = (datetime.utcnow() - cached["fetchedAt"]).total_seconds()
        if age < (TTL_PUBLISHED if cached["published"] else TTL_UNPUBLISHED):
            return {"ok": True, "cached": True, "published": cached["published"]}
    own = client is None
    c = client or AfClient()
    try:
        fid = int(mp["af_fixture_id"])
        lu = parse_lineups(c.get("/fixtures/lineups", {"fixture": fid}).get("response", []))
        data: Dict[str, Any] = {}
        if lu:
            from . import players as af_players
            for tid, t in lu.items():
                if mp.get("af_league_id") and mp.get("af_season"):
                    st = af_players.team_stats(c, int(tid), int(mp["af_league_id"]), int(mp["af_season"]))
                    if st.get("games"):
                        t["games"] = st["games"]
                        t["regulars"] = sorted(
                            [{"id": int(pid), "name": p["name"], "share": p["share"], "starts": p["starts"], "goals": p["goals"]}
                             for pid, p in st["players"].items() if p["role"] == "主力"], key=lambda r: -(r["share"] or 0))
                prev = _prev_xi(c, int(tid), fid)
                if prev:
                    t["rotation"] = rotation([x["id"] for x in t["xi"]], prev["ids"])
                    t["prev"] = {k: prev[k] for k in ("date", "opp", "comp")}
            data = {"teams": lu, "home_id": mp["af_home_id"], "away_id": mp["af_away_id"]}
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO af_lineup_cache (match_id, af_fixture_id, published, payload_json) VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE af_fixture_id=VALUES(af_fixture_id), published=VALUES(published), "
                "payload_json=VALUES(payload_json), fetched_at=CURRENT_TIMESTAMP",
                (match_id, fid, 1 if lu else 0, json.dumps(data, ensure_ascii=False)))
        return {"ok": True, "cached": False, "published": bool(lu)}
    except Exception as e:  # noqa: BLE001
        logger.warning("首发抓取失败 %s: %s", match_id, e)
        return {"ok": False, "reason": "error"}
    finally:
        if own:
            c.close()


def _xi_text(t: Dict[str, Any]) -> str:
    groups: Dict[str, List[str]] = {"G": [], "D": [], "M": [], "F": []}
    for x in t["xi"]:
        groups.setdefault(x.get("pos") or "?", []).append(x.get("name") or "?")
    body = "; ".join(f"{POS_ZH[k]} {'、'.join(v)}" for k, v in groups.items() if v and k in POS_ZH)
    rot = ""
    if t.get("rotation") is not None and t.get("prev"):
        p = t["prev"]
        rot = f"。较上一场({p['date']} {p['comp']} 对 {p['opp']})首发换了 {t['rotation']} 人"
    return f"阵型 {t.get('formation') or '未知'},教练 {t.get('coach') or '未知'}。首发: {body}{rot}"


def regulars_missing(t: Dict[str, Any], injured: Dict[str, str]) -> str:
    """本季常规主力里没进首发的人(按分钟占比排序, 最多 6 个), 并标注是否在伤停名单里。没有统计数据返回空串。"""
    if not t.get("regulars"):
        return ""
    in_xi = {x["id"] for x in t["xi"]}
    miss = [r for r in t["regulars"] if r["id"] not in in_xi][:6]
    if not miss:
        return f"本季常规主力(共 {len(t['regulars'])} 人)全部在首发。"
    def f(r):
        tag = f"、{injured[r['name']]}" if r["name"] in injured else "、不在伤停名单,可能是轮换/战术安排"
        return f"{r['name']}(分钟占比 {int((r['share'] or 0) * 100)}%{tag})"
    small = f"(样本仅 {t['games']} 场)" if t.get("games") and t["games"] < 5 else ""
    return f"本季常规主力未首发{small}: " + "; ".join(f(r) for r in miss)


def render(match_id: str, home: str, away: str) -> str:
    c = load_cached(match_id)
    if c is None:
        return ("\n【官方首发】本场首发还没有抓取(或本场未对应到 API-Football)。需要用户说\"请关联本场首发\"才会抓取;"
                "没有数据时不要凭印象写首发,也不要编造预计首发。")
    at = c["fetchedAt"].replace(tzinfo=timezone.utc).astimezone(_BJ).strftime("%m-%d %H:%M")
    if not c["published"]:
        return (f"\n【官方首发】(来源 API-Football,查询于 {at} 北京时间)官方首发尚未公布。通常开赛前约 1 小时公布,"
                "这个来源不提供预计首发,所以现在无法判断首发;不要编造,可以建议用户临近开赛再问。")
    d = c["data"]
    teams = d.get("teams") or {}
    th, ta = teams.get(str(d.get("home_id"))), teams.get(str(d.get("away_id")))
    if not th or not ta:
        return f"\n【官方首发】(来源 API-Football,查询于 {at})返回的球队与本场对不上,不能使用。"
    inj = load_injuries(match_id)
    injured_by_name = {}
    if inj:
        for x in inj["items"]:
            injured_by_name[x["name"]] = "在伤停名单(缺阵)" if x.get("type") == "Missing Fixture" else "在伤停名单(存疑)"
    lines = [f"\n【官方首发】(来源 API-Football,查询于 {at} 北京时间;接口不给公布时间,不能判断盘口是否已反映)",
             f"主队{home}: {_xi_text(th)}", f"客队{away}: {_xi_text(ta)}"]
    ko = _kickoff(match_id)
    for lab, nm, t, is_home in (("主队", home, th, True), ("客队", away, ta, False)):
        rm = regulars_missing(t, injured_by_name)
        if rm:
            lines.append(f"{lab}{nm}: {rm}")
        try:
            from .style_text import lineup_compare_text
            from .team_style import team_matches
            cmp_line = lineup_compare_text(lab, nm, t["xi"], t.get("formation"), t.get("coach"),
                                           team_matches(int(t["team_id"]), before_ts=ko), is_home, t.get("coach_id"))
            if cmp_line:
                lines.append(cmp_line)
        except Exception:  # noqa: BLE001  本赛季比赛库不可用不影响首发本身
            logger.exception("首发对比计算失败 %s", match_id)
    if inj:
        names = {x["name"]: x for x in inj["items"] if x.get("type") == "Missing Fixture"}
        hit = [x["name"] for t in (th, ta) for x in t["xi"] if x.get("name") in names]
        if hit:
            lines.append("交叉提示: 伤停名单里标为缺阵的球员出现在首发: " + "、".join(hit) + "(两份数据来源可能不同步,以官方首发为准,并说明伤停数据可能过时)")
    lines.append("说明: \"阵容对比\"是相对该队自己本赛季习惯的描述,阵型/换人和进球的关系没有回测,只作端倪,不是方向证据;轮换人数只是粗略指标,杯赛/欧战前后轮换更常见;\"常规主力\"按本联赛本赛季的分钟占比和首发率划分,"
                 "赛季初期样本小时不稳。常规主力没进首发又不在伤停名单,多半是轮换或战术安排,要结合赛程判断,不要直接当作利空。"
                 "首发是尚未被定价的新信息,但只有和盘口最新变动方向对照后才能作为证据。")
    return "\n".join(lines)
