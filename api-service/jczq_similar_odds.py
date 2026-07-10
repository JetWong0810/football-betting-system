"""竞彩历史同赔匹配引擎 (nspf 口径)

镜像 wc_similar_odds.py 的匹配逻辑，数据源换 MySQL jczq_odds_history。
匹配条件: 初盘低赔 ±tolerance + 低赔变动方向一致(升/降/平)

数据口径: 让球胜平负(nspf)。竞彩历史只有 nspf 变动(无 spf)，故用 nspf。
每场取最早 change_time 行=初盘、最晚=终盘；结果(result)由 (home_score - away_score + handicap) 推导 H/D/A。
样本: 40635 场有 nspf 变动≥2 + 已完赛 + hhad 盘口(2018-2026)。
"""

import logging
from typing import Dict, List, Optional

import pymysql

import settings

logger = logging.getLogger(__name__)

TOLERANCE = 0.05
LOW_LABEL = {"win": "胜", "draw": "平", "loss": "负"}
RESULT_MAP = {"win": "H", "draw": "D", "loss": "A"}

# 历史池缓存: 2018-2025 静态数据，进程内只加载一次
_pool_cache: Optional[List[Dict]] = None


def _get_conn():
    return pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)


def _get_direction(open_val: float, close_val: float) -> Optional[str]:
    """低赔从初盘到终盘的变动方向"""
    if open_val is None or close_val is None:
        return None
    diff = close_val - open_val
    if diff > 0.01:
        return "升"
    if diff < -0.01:
        return "降"
    return "平"


def _get_low_odds_info(open_win, open_draw, open_loss, close_win, close_draw, close_loss):
    """返回 (低赔key, 低赔初盘值, 低赔变动方向)。低赔=初盘最低的那项。"""
    odds_map = [
        ("win", open_win, close_win),
        ("draw", open_draw, close_draw),
        ("loss", open_loss, close_loss),
    ]
    valid = [(k, o, c) for k, o, c in odds_map if o is not None]
    if not valid:
        return None, None, None
    low_key, low_open, low_close = min(valid, key=lambda x: x[1])
    direction = _get_direction(low_open, low_close)
    return low_key, low_open, direction


def get_nspf_pool() -> List[Dict]:
    """加载竞彩 nspf 历史同赔池: 每场初盘(最早)+终盘(最晚)+比分+盘口+推导结果。

    过滤: nspf 变动≥2(有初终盘) + 已完赛(有比分) + hhad 盘口存在。
    """
    global _pool_cache
    if _pool_cache is not None:
        return _pool_cache
    sql = """
        SELECT
            m.match_id, m.match_date, m.league_name,
            m.home_team_name, m.away_team_name,
            m.home_score, m.away_score,
            COALESCE(o.handicap, 0) AS handicap,
            f.odds_win  AS open_win,  f.odds_draw  AS open_draw,  f.odds_loss  AS open_loss,
            l.odds_win  AS close_win, l.odds_draw  AS close_draw, l.odds_loss  AS close_loss
        FROM (
            SELECT match_id, MIN(change_time) mn, MAX(change_time) mx
            FROM jczq_odds_history
            WHERE odds_type = 'nspf'
            GROUP BY match_id
            HAVING COUNT(*) >= 2
        ) t
        JOIN jczq_odds_history f ON f.match_id = t.match_id AND f.odds_type = 'nspf' AND f.change_time = t.mn
        JOIN jczq_odds_history l ON l.match_id = t.match_id AND l.odds_type = 'nspf' AND l.change_time = t.mx
        JOIN matches m ON m.match_id = t.match_id
        LEFT JOIN odds_win_draw_lose o ON o.match_id = t.match_id AND o.odds_type = 'hhad'
        WHERE m.home_score IS NOT NULL AND m.away_score IS NOT NULL
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    finally:
        conn.close()

    pool = []
    for r in rows:
        # 推导让球胜平负结果: (主队净胜 + 让球数) 符号
        try:
            adj = (int(r["home_score"]) - int(r["away_score"])) + float(r["handicap"])
        except (TypeError, ValueError):
            continue
        if adj > 0:
            result = "H"
        elif adj == 0:
            result = "D"
        else:
            result = "A"
        pool.append({
            "match_id": r["match_id"],
            "match_date": str(r["match_date"]) if r["match_date"] else "",
            "league_name": r["league_name"] or "",
            "home_team": r["home_team_name"] or "",
            "away_team": r["away_team_name"] or "",
            "home_score": int(r["home_score"]),
            "away_score": int(r["away_score"]),
            "handicap": float(r["handicap"]),
            "result": result,
            "open_win": float(r["open_win"]), "open_draw": float(r["open_draw"]), "open_loss": float(r["open_loss"]),
            "close_win": float(r["close_win"]), "close_draw": float(r["close_draw"]), "close_loss": float(r["close_loss"]),
        })
    _pool_cache = pool
    return pool


def _calc_stats(matches: List[Dict]) -> Dict:
    """统计: 胜平负分布 + 低赔命中率 + 亚盘上下盘(用 hhad 盘口)"""
    if not matches:
        return {}
    total = len(matches)
    wins = sum(1 for m in matches if m["result"] == "H")
    draws = sum(1 for m in matches if m["result"] == "D")
    losses = sum(1 for m in matches if m["result"] == "A")

    low_hit = 0
    for m in matches:
        if m["hist_low_key"] == "win" and m["result"] == "H":
            low_hit += 1
        elif m["hist_low_key"] == "draw" and m["result"] == "D":
            low_hit += 1
        elif m["hist_low_key"] == "loss" and m["result"] == "A":
            low_hit += 1

    # 亚盘上下盘: hhad 盘口, 主队净胜 - 让球数(负=主让,同 football-data 约定)
    ah_upper = ah_lower = ah_push = ah_total = 0
    for m in matches:
        hc = m.get("handicap")
        if hc is None:
            continue
        ah_total += 1
        adjusted = (m["home_score"] - m["away_score"]) + hc  # 负盘=主让,主队上盘
        if abs(adjusted) < 1e-9:
            ah_push += 1
        elif adjusted > 0:
            ah_upper += 1
        else:
            ah_lower += 1

    return {
        "total": total,
        "wins": wins, "draws": draws, "losses": losses,
        "win_pct": round(wins / total * 100, 1),
        "draw_pct": round(draws / total * 100, 1),
        "loss_pct": round(losses / total * 100, 1),
        "low_hit": low_hit,
        "low_hit_pct": round(low_hit / total * 100, 1) if total else 0,
        "ah_total": ah_total, "ah_upper": ah_upper, "ah_lower": ah_lower,
        "ah_upper_pct": round(ah_upper / ah_total * 100, 1) if ah_total else 0,
        "ah_lower_pct": round(ah_lower / ah_total * 100, 1) if ah_total else 0,
    }


def get_match_nspf_odds(match_id: str) -> Optional[Dict]:
    """取某场竞彩比赛的 nspf 初盘/终盘, 组装成 jczq_company dict。

    供 calc_factor_jczq_odds / calc_factor_jczq_similar_odds 使用。
    initial=最早变动行, current=最晚变动行。变动<1行返回 None。
    """
    sql = """
        SELECT odds_win, odds_draw, odds_loss, change_time
        FROM jczq_odds_history
        WHERE match_id = %s AND odds_type = 'nspf'
        ORDER BY change_time
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (match_id,))
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    first, last = rows[0], rows[-1]
    return {
        "initial": {"win": float(first["odds_win"]), "draw": float(first["odds_draw"]), "lose": float(first["odds_loss"])},
        "current": {"win": float(last["odds_win"]), "draw": float(last["odds_draw"]), "lose": float(last["odds_loss"])},
    }


def find_similar_nspf(open_win: float, open_draw: float, open_loss: float,
                      close_win: float, close_draw: float, close_loss: float,
                      tolerance: float = TOLERANCE) -> Dict:
    """核心匹配: 初盘低赔±tolerance + 低赔变动方向一致。

    Returns: {query, matches, stats} 与 wc_similar_odds.find_similar 同构。
    """
    input_low_key, input_low_open, input_direction = _get_low_odds_info(
        open_win, open_draw, open_loss, close_win, close_draw, close_loss
    )
    if input_low_key is None:
        return {"query": {}, "matches": [], "stats": {}}

    low_label = LOW_LABEL[input_low_key]
    pool = get_nspf_pool()

    matched = []
    for m in pool:
        hist_low_key, hist_low_open, hist_direction = _get_low_odds_info(
            m["open_win"], m["open_draw"], m["open_loss"],
            m["close_win"], m["close_draw"], m["close_loss"],
        )
        if hist_low_key is None or hist_direction is None:
            continue
        if abs(hist_low_open - input_low_open) > tolerance:
            continue
        if hist_direction != input_direction:
            continue

        similarity = 1 - abs(hist_low_open - input_low_open) / tolerance
        m["similarity"] = round(similarity * 100, 1)
        m["hist_low_key"] = hist_low_key
        m["hist_low_open"] = hist_low_open
        m["hist_direction"] = hist_direction
        m["home_team_cn"] = m["home_team"]
        m["away_team_cn"] = m["away_team"]
        matched.append(m)

    matched.sort(key=lambda x: -x["similarity"])
    stats = _calc_stats(matched)

    return {
        "query": {
            "open_win": open_win, "open_draw": open_draw, "open_loss": open_loss,
            "close_win": close_win, "close_draw": close_draw, "close_loss": close_loss,
            "low_position": low_label, "low_open": input_low_open,
            "direction": input_direction, "tolerance": tolerance,
        },
        "matches": matched,
        "stats": stats,
    }


if __name__ == "__main__":
    # 自检: jczq_1 的初/终盘
    print("=== 竞彩 nspf 同赔引擎自检 ===")
    res = find_similar_nspf(1.95, 3.15, 3.26, 2.15, 3.02, 3.00)
    print(f"查询: {res['query']}")
    print(f"匹配场次: {res['stats'].get('total', 0)}")
    if res["stats"].get("total"):
        s = res["stats"]
        print(f"  胜平负: {s['wins']}/{s['draws']}/{s['losses']}  低赔命中: {s['low_hit']}/{s['total']} ({s['low_hit_pct']}%)")
        print(f"  亚盘: 上{s['ah_upper']} 下{s['ah_lower']} (共{s['ah_total']})")
        print(f"  前3场:")
        for m in res["matches"][:3]:
            print(f"    {m['match_date']} {m['league_name']} {m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']} "
                  f"低赔{m['hist_low_open']}({m['hist_direction']}) 相似{m['similarity']}%")
