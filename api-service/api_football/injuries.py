"""伤停: 抓取(/injuries + /players/squads 取位置) -> 缓存 -> 渲染成一小段文字给聊天。

设计取舍(防止数据太多干扰分析):
- 只在用户要求关联伤停时才进上下文, 默认不带。
- 只列"缺阵"和"存疑", 每队最多 8 人; 另给按位置的人数汇总, 让模型一眼看出是不是门将/后防/锋线集中缺阵。
- 接口没有出场时间/身价, 无法判断是否主力: 文字里明确写出, 并要求不要仅凭人数改判断。
- 公开伤停通常已计入盘口, 本块用来解释盘口变动或发现尚未被定价的新增缺阵, 不是独立加分项。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database import get_db

from .client import AfClient

logger = logging.getLogger(__name__)

SQUAD_TTL = 7 * 86400
INJ_TTL_FAR = 3 * 3600          # 距开赛 > 24h
INJ_TTL_NEAR = 20 * 60          # 距开赛 <= 24h(临场伤停变化快)
MAX_PER_TEAM = 8
POS_ZH = {"Goalkeeper": "门将", "Defender": "后卫", "Midfielder": "中场", "Attacker": "前锋"}
_BJ = timezone(timedelta(hours=8))


def _mapping(match_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT af_fixture_id, af_home_id, af_away_id, af_league_id, af_season FROM af_fixture_map WHERE match_id=%s", (match_id,))
        return cur.fetchone()


def _kickoff(match_id: str) -> Optional[float]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT match_timestamp t FROM matches WHERE match_id=%s", (match_id,))
        r = cur.fetchone()
    return float(r["t"]) if r and r.get("t") else None


def _squad_positions(c: AfClient, team_id: int) -> Dict[int, str]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT payload_json, fetched_at FROM af_squad_cache WHERE af_team_id=%s", (team_id,))
        r = cur.fetchone()
    if r and r.get("payload_json") and (datetime.utcnow() - r["fetched_at"]).total_seconds() < SQUAD_TTL:
        return {int(k): v for k, v in json.loads(r["payload_json"]).items()}
    pos: Dict[int, str] = {}
    try:
        d = c.get("/players/squads", {"team": team_id})
        for t in d.get("response", []):
            for p in t.get("players", []):
                if p.get("id") and p.get("position"):
                    pos[int(p["id"])] = p["position"]
    except Exception as e:  # noqa: BLE001  位置拿不到不影响伤停本身
        logger.warning("squad 抓取失败 team=%s: %s", team_id, e)
        return {}
    with get_db() as conn:
        conn.cursor().execute(
            "INSERT INTO af_squad_cache (af_team_id, payload_json) VALUES (%s,%s) "
            "ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json), fetched_at=CURRENT_TIMESTAMP",
            (team_id, json.dumps(pos)))
    return pos


def load_cached(match_id: str) -> Optional[Dict[str, Any]]:
    """只读库。返回 {'items': [...], 'fetchedAt': datetime(UTC), 'fixture': id} 或 None。"""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT af_fixture_id, payload_json, fetched_at FROM af_injuries_cache WHERE match_id=%s", (match_id,))
            r = cur.fetchone()
    except Exception as e:  # noqa: BLE001  表未建
        if e.args and e.args[0] == 1146:
            return None
        raise
    if not r or not r.get("payload_json"):
        return None
    return {"items": json.loads(r["payload_json"]), "fetchedAt": r["fetched_at"], "fixture": r["af_fixture_id"]}


def fetch(match_id: str, force: bool = False, client: Optional[AfClient] = None) -> Dict[str, Any]:
    """抓取并缓存。返回 {ok, reason, cached, n}。距开赛近时缓存更短。"""
    mp = _mapping(match_id)
    if not mp:
        return {"ok": False, "reason": "no_mapping"}
    ko = _kickoff(match_id)
    ttl = INJ_TTL_NEAR if (ko and ko - time.time() <= 86400) else INJ_TTL_FAR
    cur_cache = load_cached(match_id)
    if cur_cache and not force and (datetime.utcnow() - cur_cache["fetchedAt"]).total_seconds() < ttl:
        return {"ok": True, "cached": True, "n": len(cur_cache["items"])}
    own = client is None
    c = client or AfClient()
    try:
        d = c.get("/injuries", {"fixture": mp["af_fixture_id"]})
        from . import players as af_players
        stats: Dict[int, Dict[str, Any]] = {}
        if mp.get("af_league_id") and mp.get("af_season"):
            for tid in {mp["af_home_id"], mp["af_away_id"]}:
                if tid:
                    stats[int(tid)] = af_players.team_stats(c, int(tid), int(mp["af_league_id"]), int(mp["af_season"]))
        squad_pos: Dict[int, Dict[int, str]] = {}
        items = []
        for x in d.get("response", []):
            pl, tm = x.get("player") or {}, x.get("team") or {}
            tid = int(tm["id"]) if tm.get("id") else None
            st = stats.get(tid) or {}
            sp = (st.get("players") or {}).get(str(pl.get("id")))
            pos = sp.get("pos") if sp else None
            if not pos and tid and pl.get("id"):                      # 本联赛没出过场: 位置退回 squads(只在需要时才请求)
                if tid not in squad_pos:
                    squad_pos[tid] = _squad_positions(c, tid)
                pos = squad_pos[tid].get(int(pl["id"]))
            item = {"team_id": tid, "team": tm.get("name"), "player_id": pl.get("id"), "name": pl.get("name"),
                    "type": pl.get("type"), "reason": pl.get("reason"), "pos": pos}
            if sp:
                item.update({"role": sp["role"], "apps": sp["apps"], "starts": sp["starts"], "share": sp["share"],
                             "goals": sp["goals"], "games": st.get("games")})
            elif st.get("games"):
                item.update({"role": "无本季联赛出场", "games": st.get("games")})
            items.append(item)
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO af_injuries_cache (match_id, af_fixture_id, payload_json) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE af_fixture_id=VALUES(af_fixture_id), payload_json=VALUES(payload_json), fetched_at=CURRENT_TIMESTAMP",
                (match_id, mp["af_fixture_id"], json.dumps(items, ensure_ascii=False)))
        return {"ok": True, "cached": False, "n": len(items)}
    except Exception as e:  # noqa: BLE001
        logger.warning("伤停抓取失败 %s: %s", match_id, e)
        return {"ok": False, "reason": "error"}
    finally:
        if own:
            c.close()


_ROLE_ORDER = {"主力": 0, "轮换": 1, "边缘": 2, "无本季联赛出场": 3}


def _one(r: Dict[str, Any]) -> str:
    z = POS_ZH.get(r.get("pos") or "", "")
    if r.get("role") in ("主力", "轮换"):
        info = f"{r['role']}·首发 {r.get('starts', 0)}/{r.get('games')}、分钟占比 {int((r.get('share') or 0) * 100)}%" + (f"、进球 {r['goals']}" if r.get("goals") else "")
        return f"{r.get('name')}({z + '·' if z else ''}{info};{r.get('reason') or '原因未知'})"
    return f"{r.get('name')}({z + '·' if z else ''}{r.get('reason') or '原因未知'})"


def _team_line(label: str, name: str, rows: List[Dict[str, Any]]) -> str:
    out = [r for r in rows if r.get("type") == "Missing Fixture"]
    qs = [r for r in rows if r.get("type") != "Missing Fixture"]
    has_role = any(r.get("role") for r in rows)
    out.sort(key=lambda r: (_ROLE_ORDER.get(r.get("role") or "", 4), -(r.get("share") or 0)))
    qs.sort(key=lambda r: (_ROLE_ORDER.get(r.get("role") or "", 4), -(r.get("share") or 0)))
    if has_role:
        key = [r for r in out if r.get("role") == "主力"]
        rot = [r for r in out if r.get("role") == "轮换"]
        rest = [r for r in out if r.get("role") not in ("主力", "轮换")]
        games = next((r.get("games") for r in rows if r.get("games")), None)
        small = f"(本队本联赛仅踢了 {games} 场,样本小,主力判断不稳)" if games is not None and games < 5 else ""
        parts = [f"{label}{name}: 确认缺阵 {len(out)} 人,其中主力 {len(key)}、轮换 {len(rot)}、边缘/无出场 {len(rest)}{small}"]
        cnt: Dict[str, int] = {}
        for r in key:
            z = POS_ZH.get(r.get("pos") or "", "位置未知")
            cnt[z] = cnt.get(z, 0) + 1
        if cnt:
            parts.append("主力缺阵按位置: " + "、".join(f"{k}{v}" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])))
        if key or rot:
            parts.append("缺阵: " + "; ".join(_one(r) for r in (key + rot)[:MAX_PER_TEAM]))
        if rest:
            parts.append("另有基本不出场/边缘球员缺阵(影响很小): " + "、".join(str(r.get("name")) for r in rest[:6]))
        if qs:
            parts.append("存疑: " + "; ".join(_one(r) for r in qs[:3]) + (f" 等共{len(qs)}人" if len(qs) > 3 else ""))
        return "\n".join(parts)
    cnt = {}                                           # 没有球员统计时的降级写法(旧缓存或联赛无数据)
    for r in out:
        z = POS_ZH.get(r.get("pos") or "", "位置未知")
        cnt[z] = cnt.get(z, 0) + 1
    summ = "、".join(f"{k}{v}" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])) or "无"
    parts = [f"{label}{name}: 确认缺阵 {len(out)} 人(按位置: {summ};没有出场数据,无法判断是否主力)"]
    if out:
        parts.append("缺阵: " + "; ".join(_one(r) for r in out[:MAX_PER_TEAM]) + (f" 等共{len(out)}人" if len(out) > MAX_PER_TEAM else ""))
    if qs:
        parts.append("存疑: " + "; ".join(_one(r) for r in qs[:3]) + (f" 等共{len(qs)}人" if len(qs) > 3 else ""))
    return "\n".join(parts)


def render(match_id: str, home: str, away: str, home_id: Optional[int] = None, away_id: Optional[int] = None) -> str:
    c = load_cached(match_id)
    if c is None:
        return ("\n【伤停】本场伤停还没有抓取(或本场未对应到 API-Football)。需要用户说\"请关联本场伤停\"才会抓取;"
                "没有数据时不要凭印象写伤停。")
    mp = _mapping(match_id) or {}
    hid, aid = home_id or mp.get("af_home_id"), away_id or mp.get("af_away_id")
    items = c["items"]
    at = c["fetchedAt"].replace(tzinfo=timezone.utc).astimezone(_BJ).strftime("%m-%d %H:%M")
    rows_h = [r for r in items if r.get("team_id") == hid]
    rows_a = [r for r in items if r.get("team_id") == aid]
    head = f"\n【伤停】(来源 API-Football,抓取于 {at} 北京时间;只收录已公布的伤停,没有记录不等于全员健康)"
    if not items:
        return head + "\n两队均无已公布的伤停记录。"
    note = ("说明: 主力/轮换/边缘按本联赛本赛季的首发率和分钟占比划分,只有\"主力\"缺阵才值得当证据;新援、伤愈复出的球员分钟偏低,不代表不重要;"
            "位置是本赛季最常见位置,可能与常规认知不同,不要仅凭位置下结论。公开伤停通常已计入盘口:把它用来解释盘口变动,"
            "或找出尚未被盘口反映的新增缺阵,不要当作独立加分项。没有出场数据的球队(标注\"无法判断是否主力\")不要凭人数调整倾向。")
    return "\n".join([head, _team_line("主队", home, rows_h), _team_line("客队", away, rows_a), note])
