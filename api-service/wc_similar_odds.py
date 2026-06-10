"""世界杯历史同赔匹配引擎

匹配逻辑:
1. 竞彩初盘低赔 ±0.05
2. 低赔终盘变动方向一致（升/降）

数据源: data/worldcup_odds.db 中有竞彩/马会初盘终盘的历史比赛 (2014/2018/2022)
"""

import sqlite3
import os
from typing import Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "worldcup_odds.db")

TEAM_CN = {
    "Qatar": "卡塔尔", "Ecuador": "厄瓜多尔", "Senegal": "塞内加尔",
    "Netherlands": "荷兰", "England": "英格兰", "Iran": "伊朗",
    "USA": "美国", "Wales": "威尔士", "Argentina": "阿根廷",
    "Saudi Arabia": "沙特阿拉伯", "Denmark": "丹麦", "Tunisia": "突尼斯",
    "Mexico": "墨西哥", "Poland": "波兰", "France": "法国",
    "Australia": "澳大利亚", "Morocco": "摩洛哥", "Croatia": "克罗地亚",
    "Germany": "德国", "Japan": "日本", "Spain": "西班牙",
    "Costa Rica": "哥斯达黎加", "Belgium": "比利时", "Canada": "加拿大",
    "Switzerland": "瑞士", "Cameroon": "喀麦隆", "Uruguay": "乌拉圭",
    "South Korea": "韩国", "Portugal": "葡萄牙", "Ghana": "加纳",
    "Brazil": "巴西", "Serbia": "塞尔维亚", "South Africa": "南非",
    "Greece": "希腊", "Nigeria": "尼日利亚", "Algeria": "阿尔及利亚",
    "Slovenia": "斯洛文尼亚", "North Korea": "朝鲜", "Honduras": "洪都拉斯",
    "Chile": "智利", "Italy": "意大利", "New Zealand": "新西兰",
    "Slovakia": "斯洛伐克", "Paraguay": "巴拉圭",
    "Côte d'Ivoire": "科特迪瓦", "Colombia": "哥伦比亚",
    "Russia": "俄罗斯", "Egypt": "埃及", "Iceland": "冰岛",
    "Peru": "秘鲁", "Panama": "巴拿马", "Sweden": "瑞典",
}


def _get_conn():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"worldcup_odds.db not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _get_direction(open_val, close_val):
    if open_val is None or close_val is None:
        return None
    diff = close_val - open_val
    if diff > 0.01:
        return "升"
    elif diff < -0.01:
        return "降"
    else:
        return "平"


def _get_low_odds_info(open_win, open_draw, open_loss, close_win, close_draw, close_loss):
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


def get_history_pool() -> List[Dict]:
    conn = _get_conn()
    rows = conn.execute("""
        SELECT m.id, m.year, m.stage, m.match_date, m.home_team, m.away_team,
               m.home_score, m.away_score, m.result,
               COALESCE(jc.odds_home_open, hk.odds_home_open) as open_win,
               COALESCE(jc.odds_draw_open, hk.odds_draw_open) as open_draw,
               COALESCE(jc.odds_away_open, hk.odds_away_open) as open_loss,
               COALESCE(jc.odds_home_close, hk.odds_home_close) as close_win,
               COALESCE(jc.odds_draw_close, hk.odds_draw_close) as close_draw,
               COALESCE(jc.odds_away_close, hk.odds_away_close) as close_loss,
               CASE WHEN jc.id IS NOT NULL THEN '竞彩' ELSE '马会' END as odds_source
        FROM matches m
        LEFT JOIN odds_snapshot jc ON jc.match_id = m.id AND jc.company_name = '竞彩官方'
        LEFT JOIN odds_snapshot hk ON hk.match_id = m.id AND hk.company_name = '香港马会'
        WHERE m.home_score IS NOT NULL
          AND (jc.odds_home_open IS NOT NULL OR hk.odds_home_open IS NOT NULL)
        ORDER BY m.year, m.match_date
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_similar(open_win: float, open_draw: float, open_loss: float,
                 close_win: float, close_draw: float, close_loss: float,
                 tolerance: float = 0.05) -> Dict:
    """核心匹配: 初盘低赔±tolerance + 低赔变动方向一致"""
    input_low_key, input_low_open, input_direction = _get_low_odds_info(
        open_win, open_draw, open_loss, close_win, close_draw, close_loss
    )
    if input_low_key is None:
        return {"query": {}, "matches": [], "stats": {}}

    low_label = {"win": "胜", "draw": "平", "loss": "负"}[input_low_key]
    pool = get_history_pool()

    matched = []
    for m in pool:
        hist_low_key, hist_low_open, hist_direction = _get_low_odds_info(
            m["open_win"], m["open_draw"], m["open_loss"],
            m["close_win"], m["close_draw"], m["close_loss"]
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
        m["home_team_cn"] = TEAM_CN.get(m["home_team"], m["home_team"])
        m["away_team_cn"] = TEAM_CN.get(m["away_team"], m["away_team"])

        stage_cn = {
            "group": "小组赛", "round_of_16": "1/8决赛",
            "quarter": "1/4决赛", "semi": "半决赛",
            "third": "三四名", "final": "决赛",
        }
        m["stage_cn"] = stage_cn.get(m["stage"], m["stage"])
        matched.append(m)

    matched.sort(key=lambda x: -x["similarity"])
    _attach_asian_odds(matched)
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


def _attach_asian_odds(matches: List[Dict]):
    if not matches:
        return
    conn = _get_conn()
    match_ids = [m["id"] for m in matches]
    placeholders = ",".join("?" * len(match_ids))

    ah_rows = conn.execute(f"""
        SELECT match_id, company, initial_handicap, initial_handicap_value,
               initial_home_odds, initial_away_odds,
               close_handicap, close_handicap_value,
               close_home_odds, close_away_odds
        FROM wc_asian_handicap
        WHERE match_id IN ({placeholders})
        ORDER BY match_id,
                 CASE company WHEN '香港马会' THEN 1 WHEN '澳门' THEN 2
                              WHEN 'Pinnacle' THEN 3 WHEN 'Bet365' THEN 4 ELSE 5 END
    """, match_ids).fetchall()

    ou_rows = conn.execute(f"""
        SELECT match_id, company, initial_line, initial_line_value,
               initial_over_odds, initial_under_odds,
               close_line, close_line_value, close_over_odds, close_under_odds
        FROM wc_over_under
        WHERE match_id IN ({placeholders})
        ORDER BY match_id,
                 CASE company WHEN '香港马会' THEN 1 WHEN '澳门' THEN 2
                              WHEN 'Pinnacle' THEN 3 WHEN 'Bet365' THEN 4 ELSE 5 END
    """, match_ids).fetchall()
    conn.close()

    ah_map = {}
    for r in ah_rows:
        mid = r["match_id"]
        if mid not in ah_map:
            ah_map[mid] = dict(r)

    ou_map = {}
    for r in ou_rows:
        mid = r["match_id"]
        if mid not in ou_map:
            ou_map[mid] = dict(r)

    for m in matches:
        mid = m["id"]
        ah = ah_map.get(mid)
        if ah:
            m["ah_company"] = ah["company"]
            m["ah_initial_handicap"] = ah["initial_handicap"]
            m["ah_initial_value"] = ah["initial_handicap_value"]
            m["ah_initial_home"] = ah["initial_home_odds"]
            m["ah_initial_away"] = ah["initial_away_odds"]
            m["ah_close_handicap"] = ah["close_handicap"]
            m["ah_close_value"] = ah["close_handicap_value"]
            m["ah_close_home"] = ah["close_home_odds"]
            m["ah_close_away"] = ah["close_away_odds"]
        else:
            m["ah_company"] = None

        ou = ou_map.get(mid)
        if ou:
            m["ou_company"] = ou["company"]
            m["ou_initial_line"] = ou["initial_line"]
            m["ou_initial_value"] = ou["initial_line_value"]
            m["ou_initial_over"] = ou["initial_over_odds"]
            m["ou_initial_under"] = ou["initial_under_odds"]
            m["ou_close_line"] = ou["close_line"]
            m["ou_close_value"] = ou["close_line_value"]
            m["ou_close_over"] = ou["close_over_odds"]
            m["ou_close_under"] = ou["close_under_odds"]
        else:
            m["ou_company"] = None


def _calc_stats(matches: List[Dict]) -> Dict:
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

    ah_upper = ah_lower = ah_push = ah_total = 0
    for m in matches:
        if m.get("ah_close_value") is None:
            continue
        ah_total += 1
        adjusted = (m["home_score"] - m["away_score"]) - m["ah_close_value"]
        if abs(adjusted) < 0.01:
            ah_push += 1
        elif adjusted > 0:
            ah_upper += 1
        else:
            ah_lower += 1

    ou_over = ou_under = ou_push = ou_total = 0
    for m in matches:
        if m.get("ou_close_value") is None:
            continue
        ou_total += 1
        diff = (m["home_score"] + m["away_score"]) - m["ou_close_value"]
        if abs(diff) < 0.01:
            ou_push += 1
        elif diff > 0:
            ou_over += 1
        else:
            ou_under += 1

    return {
        "total": total,
        "wins": wins, "draws": draws, "losses": losses,
        "win_pct": round(wins / total * 100, 1),
        "draw_pct": round(draws / total * 100, 1),
        "loss_pct": round(losses / total * 100, 1),
        "low_hit": low_hit,
        "low_hit_pct": round(low_hit / total * 100, 1),
        "ah_total": ah_total, "ah_upper": ah_upper, "ah_lower": ah_lower,
        "ah_upper_pct": round(ah_upper / ah_total * 100, 1) if ah_total else 0,
        "ah_lower_pct": round(ah_lower / ah_total * 100, 1) if ah_total else 0,
        "ou_total": ou_total, "ou_over": ou_over, "ou_under": ou_under,
        "ou_over_pct": round(ou_over / ou_total * 100, 1) if ou_total else 0,
        "ou_under_pct": round(ou_under / ou_total * 100, 1) if ou_total else 0,
    }
