"""
本地基本面数据重建 - 从 team_history_matches 表组装 F1/F2 兼容的 match_data

替代 500.com 实时抓取的 shuju-{fid}.shtml,用于历史比赛回测 F1/F2。
数据源: MySQL team_history_matches (football-data.co.uk,五大联赛国家)。

严格匹配 F1/F2 数据契约(参见 predict_service.py:739-928,1050-1277):
  - recent 记录: match/result/handicap(负=主让)/asianResult(焦点=列表owner视角)
  - h2h 记录: match/date/handicap(正=主让,与recent相反!)/asianResult(焦点=当前主队视角)
"""

import logging
from typing import Any, Dict, List, Optional

import pymysql

import settings

logger = logging.getLogger(__name__)

RECENT_LIMIT = 15
H2H_LIMIT = 30


def get_conn():
    return pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)


# ---------- 亚盘结算 ----------

def _ah_line_result(margin: float) -> str:
    """单条半/整数盘的结算(已算好margin)。+win/-lose/0push"""
    if margin > 0:
        return "win"
    if margin < 0:
        return "lose"
    return "push"


def _combine_half(r1: str, r2: str) -> str:
    """quarter 球两半盘合并"""
    m = {"win": 1, "push": 0, "lose": -1}
    s = m[r1] + m[r2]
    return {2: "赢", 1: "赢半", 0: "走", -1: "输半", -2: "输"}[s]


def _flip(result: str) -> str:
    """对手视角翻转"""
    return {"赢": "输", "赢半": "输半", "输": "赢", "输半": "赢半", "走": "走"}.get(result, "")


def settle_ah(home_handicap: Optional[float], home_score: Optional[int],
              away_score: Optional[int], focus_is_home: bool) -> str:
    """计算焦点队的亚盘结果。

    Args:
        home_handicap: team_matches.asian_handicap 原值(负=主让,football-data约定)
        home_score/away_score: 全场比分
        focus_is_home: 焦点队是否为该记录的主队

    Returns: "赢"/"赢半"/"输"/"输半"/"走" 或 ""(数据缺失)
    """
    if home_handicap is None or home_score is None or away_score is None:
        return ""
    try:
        L = float(home_handicap)
        diff = int(home_score) - int(away_score)
    except (TypeError, ValueError):
        return ""

    # 先算"主队"的AH结果,再按焦点翻转
    # quarter 球(L*4 为奇数): 拆两条半盘
    q = round(L * 4)
    if q % 2 == 1:
        h1 = L - 0.25
        h2 = L + 0.25
        r1 = _ah_line_result(diff + h1)
        r2 = _ah_line_result(diff + h2)
        home_result = _combine_half(r1, r2)
    else:
        # 半球/整数盘: 单条
        home_result = {"win": "赢", "lose": "输", "push": "走"}[_ah_line_result(diff + L)]

    return home_result if focus_is_home else _flip(home_result)


# ---------- 记录组装 ----------

def _build_recent_record(row: Dict, focus_team: str) -> Dict[str, Any]:
    """组装一条 recent 记录(homeRecent/awayRecent 通用)。

    focus_team: 该列表的owner(主队或客队)。asianResult 取该队视角。
    handicap: recent 约定负=主让,直接用 asian_handicap 原值。
    """
    home_cn = row["home_team_cn"]
    away_cn = row["away_team_cn"]
    hs, as_ = row["ft_home_goals"], row["ft_away_goals"]
    focus_is_home = (focus_team == home_cn)

    # result: 焦点队视角 胜/平/负
    if hs is None or as_ is None:
        result = ""
    elif focus_is_home:
        result = "胜" if hs > as_ else "平" if hs == as_ else "负"
    else:
        result = "胜" if as_ > hs else "平" if hs == as_ else "负"

    ah = row["asian_handicap"]
    asian_result = settle_ah(ah, hs, as_, focus_is_home)

    # match 串: 主队比分:比分客队(中文名,_team_in_match 据此定主客)
    match_str = f"{home_cn}{hs}:{as_}{away_cn}" if (home_cn and away_cn and hs is not None) else ""
    half = f"{row['ht_home_goals']}:{row['ht_away_goals']}" if (row["ht_home_goals"] is not None and row["ht_away_goals"] is not None) else ""

    return {
        "competition": row.get("jczq_league") or "",
        "date": str(row["match_date"]) if row.get("match_date") else "",
        "match": match_str,
        "handicap": str(ah) if ah is not None else "",
        "halfScore": half,
        "result": result,
        "asianResult": asian_result,
        "ouResult": "",
    }


def _build_h2h_record(row: Dict, focus_team: str) -> Dict[str, Any]:
    """组装一条 h2h 记录。

    focus_team: 当前主队(500.com page home)。asianResult 取该队视角。
    handicap: h2h 约定正=该记录主队让,需把 asian_handicap 翻号(原负=主让 -> 正=主让)。
    """
    home_cn = row["home_team_cn"]
    away_cn = row["away_team_cn"]
    hs, as_ = row["ft_home_goals"], row["ft_away_goals"]
    focus_is_home = (focus_team == home_cn)

    ah = row["asian_handicap"]
    asian_result = settle_ah(ah, hs, as_, focus_is_home)

    match_str = f"{home_cn}{hs}:{as_}{away_cn}" if (home_cn and away_cn and hs is not None) else ""
    half = f"{row['ht_home_goals']}:{row['ht_away_goals']}" if (row["ht_home_goals"] is not None and row["ht_away_goals"] is not None) else ""

    # h2h 约定: 正=该记录主队让。asian_handicap 负=主让,翻号得正
    hcap_str = str(-ah) if ah is not None else ""

    return {
        "competition": row.get("jczq_league") or "",
        "date": str(row["match_date"]) if row.get("match_date") else "",
        "match": match_str,
        "halfScore": half,
        "result": "",  # F2 不读此字段
        "handicap": hcap_str,
        "asianResult": asian_result,
        "ouResult": "",
    }


# ---------- 主入口 ----------

def _query_recent(conn, team_cn: str, before_date: str, limit: int) -> List[Dict]:
    sql = """
        SELECT match_date, jczq_league, home_team_cn, away_team_cn,
               ft_home_goals, ft_away_goals, ht_home_goals, ht_away_goals, asian_handicap
        FROM team_history_matches
        WHERE (home_team_cn = %s OR away_team_cn = %s)
          AND match_date < %s
          AND ft_home_goals IS NOT NULL AND ft_away_goals IS NOT NULL
          AND home_team_cn IS NOT NULL AND away_team_cn IS NOT NULL
        ORDER BY match_date DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (team_cn, team_cn, before_date, limit))
        return list(cur.fetchall())


def _query_h2h(conn, home_cn: str, away_cn: str, before_date: str, limit: int) -> List[Dict]:
    sql = """
        SELECT match_date, jczq_league, home_team_cn, away_team_cn,
               ft_home_goals, ft_away_goals, ht_home_goals, ht_away_goals, asian_handicap
        FROM team_history_matches
        WHERE ((home_team_cn = %s AND away_team_cn = %s)
            OR (home_team_cn = %s AND away_team_cn = %s))
          AND match_date < %s
          AND ft_home_goals IS NOT NULL AND ft_away_goals IS NOT NULL
          AND home_team_cn IS NOT NULL AND away_team_cn IS NOT NULL
        ORDER BY match_date DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (home_cn, away_cn, away_cn, home_cn, before_date, limit))
        return list(cur.fetchall())


def build_local_match_data(home_team_cn: str, away_team_cn: str, match_date: str,
                           conn: Optional[pymysql.connections.Connection] = None) -> Dict[str, Any]:
    """从本地历史库重建 match_data,兼容 F1/F2。

    Args:
        home_team_cn: 当前主队竞彩中文名
        away_team_cn: 当前客队竞彩中文名
        match_date: "YYYY-MM-DD"(本场日期,只取此日之前的战绩)
        conn: 可选已有连接(批量回测时复用,避免反复建连)

    Returns: {homeRecent, awayRecent, h2h} 与 odds500_service.fetch_match_data 同构
    """
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    try:
        home_rows = _query_recent(conn, home_team_cn, match_date, RECENT_LIMIT)
        away_rows = _query_recent(conn, away_team_cn, match_date, RECENT_LIMIT)
        h2h_rows = _query_h2h(conn, home_team_cn, away_team_cn, match_date, H2H_LIMIT)
    finally:
        if own_conn:
            conn.close()

    home_recent = [_build_recent_record(r, home_team_cn) for r in home_rows]
    away_recent = [_build_recent_record(r, away_team_cn) for r in away_rows]
    # h2h 焦点 = 当前主队(500.com page home 约定)
    h2h = [_build_h2h_record(r, home_team_cn) for r in h2h_rows]

    return {
        "h2h": h2h,
        "homeRecent": home_recent,
        "awayRecent": away_recent,
        "homeFuture": [],
        "awayFuture": [],
        "homeRank": None,
        "awayRank": None,
    }


# ---------- 自检 ----------

if __name__ == "__main__":
    # settle_ah 单测
    cases = [
        (-0.75, 1, 0, True, "赢半"),   # 主让0.75,1:0 -> 拆-0.5/-1.0: win+push=赢半
        (-0.75, 0, 0, True, "输"),      # 主让0.75,0:0 -> 拆-0.5/-1.0: lose+lose=输
        (-0.5, 0, 0, True, "输"),       # 主让0.5,0:0 -> 主输
        (0, 0, 0, True, "走"),          # 平手,0:0 -> 走
        (-0.25, 0, 0, True, "输半"),    # 主让0.25,0:0 -> 拆0.0/-0.5: push+lose=输半
        (-0.25, 1, 0, True, "赢"),      # 主让0.25,1:0 -> 拆0.0/-0.5: win+win=赢
        (-1.0, 1, 0, True, "走"),       # 主让1,1:0 -> 走
        (-1.0, 2, 0, True, "赢"),       # 主让1,2:0 -> 赢
        (-0.75, 1, 0, False, "输半"),   # 焦点=客,1:0 -> 客输半(翻转主的赢半)
        (-0.5, 0, 0, False, "赢"),      # 焦点=客,0:0 -> 客赢(翻转主的输)
        (0.5, 0, 0, True, "赢"),        # 主受让0.5(主+0.5),0:0 -> margin=0.5>0 主赢
        (None, 1, 0, True, ""),         # 无盘口
    ]
    print("=== settle_ah 单测 ===")
    all_ok = True
    for ah, hs, as_, focus, expect in cases:
        got = settle_ah(ah, hs, as_, focus)
        ok = got == expect
        all_ok = all_ok and ok
        print(f"  settle_ah({ah}, {hs}:{as_}, focus_home={focus}) = '{got}'  期望'{expect}' {'✓' if ok else '✗'}")
    print("全部通过" if all_ok else "有失败!")

    # 重建抽检
    print("\n=== 重建抽检: 阿森纳 vs 切尔西 2026-03-01 ===")
    md = build_local_match_data("阿森纳", "切尔西", "2026-03-01")
    print(f"  homeRecent: {len(md['homeRecent'])} 条, awayRecent: {len(md['awayRecent'])} 条, h2h: {len(md['h2h'])} 条")
    if md["homeRecent"]:
        r = md["homeRecent"][0]
        print(f"  homeRecent[0]: {r['date']} {r['match']} handicap={r['handicap']} result={r['result']} asianResult={r['asianResult']}")
    if md["h2h"]:
        r = md["h2h"][0]
        print(f"  h2h[0]: {r['date']} {r['match']} handicap={r['handicap']} asianResult={r['asianResult']}")
