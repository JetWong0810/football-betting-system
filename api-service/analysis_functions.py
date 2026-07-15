"""分析函数注册表

将复杂的多步分析逻辑封装为可注册的函数。
每个函数定义：触发条件(keywords) + 执行逻辑(handler)。

AI 生成 SQL 适合简单的单库单表查询；
分析函数适合：跨库查询、需要外部数据源、多步逻辑、特定业务算法。
"""

import re
from typing import Optional, Dict, Any, List

from nl_query import execute_mysql, execute_sqlite

# 已知球队名(中文)，用于从问题中提取队名
KNOWN_TEAMS = [
    "哥斯达黎加", "沙特阿拉伯", "波黑",
    "墨西哥", "南非", "法国", "巴西", "德国", "阿根廷", "西班牙", "荷兰", "英格兰",
    "葡萄牙", "意大利", "日本", "韩国", "尼日利亚", "喀麦隆", "克罗地亚", "比利时",
    "哥伦比亚", "乌拉圭", "瑞士", "澳大利亚", "伊朗", "沙特", "摩洛哥", "塞内加尔",
    "加纳", "厄瓜多尔", "卡塔尔", "威尔士", "美国", "加拿大", "塞尔维亚", "丹麦",
    "突尼斯", "波兰", "秘鲁", "巴拿马", "冰岛", "瑞典", "俄罗斯",
    "智利", "埃及", "巴拉圭", "捷克",
]


def extract_teams(question: str) -> List[str]:
    """从问题中提取球队名（按长度倒序匹配，优先长队名）"""
    found = []
    for team in sorted(KNOWN_TEAMS, key=len, reverse=True):
        if team in question and team not in found:
            found.append(team)
            if len(found) == 2:
                break
    return found


def find_match_fid(home: str, away: str) -> Optional[Dict]:
    """从MySQL查找比赛的match_id和fid_500"""
    sql = (
        f"SELECT match_id, fid_500, home_team_name, away_team_name FROM matches "
        f"WHERE (home_team_name LIKE '%{home}%' AND away_team_name LIKE '%{away}%') "
        f"   OR (home_team_name LIKE '%{away}%' AND away_team_name LIKE '%{home}%') "
        f"ORDER BY match_date DESC LIMIT 1"
    )
    result = execute_mysql(sql)
    if isinstance(result, str) or not result:
        return None
    return result[0]


def fetch_initial_odds(fid: str) -> Optional[Dict]:
    """从500.com获取竞彩官方初盘赔率"""
    from odds500_service import fetch_all_indices
    try:
        indices = fetch_all_indices(fid)
        for comp in indices.get("european", []):
            if "竞彩" in comp.get("bookmaker", ""):
                return comp.get("initial", {})
    except Exception:
        pass
    return None


# ============================================================
# 分析函数定义
# ============================================================

def find_match_by_question(question: str) -> Optional[Dict]:
    """按问题文本直接搜 matches 表: 找主客队名都出现在问题中的比赛(顺序无关)。

    用于竞彩队名(不在 KNOWN_TEAMS 里)的匹配。
    """
    import pymysql
    import settings
    conn = pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT match_id, fid_500, home_team_name, away_team_name FROM matches
                   WHERE CHAR_LENGTH(home_team_name) >= 2 AND CHAR_LENGTH(away_team_name) >= 2
                     AND %s LIKE CONCAT('%%', home_team_name, '%%')
                     AND %s LIKE CONCAT('%%', away_team_name, '%%')
                   ORDER BY match_date DESC LIMIT 1""",
                (question, question),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return row


def _jczq_similar_rows(match_id: str) -> Optional[Dict[str, Any]]:
    """竞彩 spf(胜平负)历史同赔: 取本场初/终盘, 匹配 jczq_odds_history 全量 spf 池。"""
    from jczq_similar_odds import get_match_spf_odds, find_similar_spf

    jc = get_match_spf_odds(match_id)
    if not jc:
        return None
    init, cur = jc["initial"], jc["current"]
    res = find_similar_spf(
        init["win"], init["draw"], init["lose"],
        cur["win"], cur["draw"], cur["lose"],
    )
    matches = res.get("matches", [])
    stats = res.get("stats", {})
    if not matches or stats.get("total", 0) == 0:
        return None

    rows = []
    for m in matches[:20]:
        hs, aws = m.get("home_score", 0), m.get("away_score", 0)
        hc = m.get("handicap")
        if hc is not None:
            adj = (hs - aws) + hc
            ah = "上盘" if adj > 0 else ("走水" if abs(adj) < 1e-9 else "下盘")
        else:
            ah = "-"
        rows.append({
            "日期": m.get("match_date", ""),
            "联赛": m.get("league_name", ""),
            "主队": m.get("home_team_cn", ""),
            "客队": m.get("away_team_cn", ""),
            "比分": f"{hs}-{aws}",
            "胜平负": {"H": "主胜", "D": "平", "A": "客胜"}.get(m.get("result"), "-"),
            "初盘": f"{m.get('open_win', 0):.2f}/{m.get('open_draw', 0):.2f}/{m.get('open_loss', 0):.2f}",
            "终盘": f"{m.get('close_win', 0):.2f}/{m.get('close_draw', 0):.2f}/{m.get('close_loss', 0):.2f}",
            "盘口结果": ah,
            "相似度": f"{m.get('similarity', 0)}%",
        })

    q = res.get("query", {})
    return {
        "source": "竞彩(同赔)",
        "text": (f"竞彩spf初盘 {init['win']:.2f}/{init['draw']:.2f}/{init['lose']:.2f} → "
                 f"终盘 {cur['win']:.2f}/{cur['draw']:.2f}/{cur['lose']:.2f}，"
                 f"低赔{q.get('low_open', 0):.2f}({q.get('low_position', '')}) 方向{q.get('direction', '')} | "
                 f"匹配{stats.get('total', 0)}场 低赔命中{stats.get('low_hit_pct', 0)}%"),
        "sql": "",
        "rows": rows,
    }


def similar_odds(question: str, **kwargs) -> Optional[Dict[str, Any]]:
    """同赔匹配：找出历史上赔率相近的比赛。优先竞彩nspf池，回退世界杯库。"""
    # 优先: 按问题文本直接搜竞彩比赛(竞彩队名不在 KNOWN_TEAMS)
    match = find_match_by_question(question)
    if not match:
        # 回退: 世界杯队名提取
        teams = extract_teams(question)
        if len(teams) < 2:
            return None
        match = find_match_fid(teams[0], teams[1])
        if not match:
            return None

    match_id = str(match.get("match_id", ""))

    # 优先: 竞彩 nspf 历史同赔池 (jczq_odds_history 全量)
    if match_id.startswith("jczq_"):
        jc_res = _jczq_similar_rows(match_id)
        if jc_res:
            return jc_res

    # 回退: 世界杯同赔 (SQLite)
    fid = str(match.get("fid_500", "")) if match.get("fid_500") else None

    # 获取竞彩初盘
    win_odds = draw_odds = lose_odds = None
    if fid:
        init = fetch_initial_odds(fid)
        if init:
            win_odds = init.get("win")
            draw_odds = init.get("draw")
            lose_odds = init.get("lose")

    # fallback: 用数据库即时赔率
    if not win_odds:
        sql = f"SELECT win_odds, draw_odds, lose_odds FROM odds_win_draw_lose WHERE match_id = '{match_id}' AND odds_type = 'had'"
        fb = execute_mysql(sql)
        if not isinstance(fb, str) and fb:
            win_odds = float(fb[0].get("win_odds") or 0)
            draw_odds = float(fb[0].get("draw_odds") or 0)
            lose_odds = float(fb[0].get("lose_odds") or 0)

    if not win_odds:
        return None

    low_odds = min(o for o in [win_odds, draw_odds, lose_odds] if o and o > 0)

    # 动态容差
    if low_odds < 1.3:
        tolerance = 0.15
    elif low_odds < 1.6:
        tolerance = 0.12
    else:
        tolerance = 0.10

    sql = f"""
    SELECT
        m.year AS '年份',
        m.match_date AS '日期',
        m.home_team AS '主队',
        m.away_team AS '客队',
        m.stage AS '阶段',
        m.home_score AS '主队进球',
        m.away_score AS '客队进球',
        m.result AS '结果',
        o.odds_home_open AS '竞彩初盘主胜',
        o.odds_draw_open AS '竞彩初盘平',
        o.odds_away_open AS '竞彩初盘客胜',
        o.odds_home_close AS '竞彩终盘主胜',
        o.odds_draw_close AS '竞彩终盘平',
        o.odds_away_close AS '竞彩终盘客胜',
        ah.close_handicap_value AS '_handicap'
    FROM matches m
    JOIN odds_snapshot o ON m.id = o.match_id
    LEFT JOIN wc_asian_handicap ah ON m.id = ah.match_id AND ah.company = '澳门'
    WHERE o.company_name = '竞彩官方'
    AND (
        MIN(o.odds_home_open, o.odds_draw_open, o.odds_away_open)
        BETWEEN {low_odds - tolerance} AND {low_odds + tolerance}
    )
    ORDER BY ABS(MIN(o.odds_home_open, o.odds_draw_open, o.odds_away_open) - {low_odds}) ASC
    LIMIT 20
    """

    result = execute_sqlite(sql)
    if isinstance(result, str) or not result:
        return None

    # 计算盘口结果
    rows = []
    for r in result:
        row = dict(r)
        handicap = row.pop("_handicap", None)
        home_score = int(row.get("主队进球") or 0)
        away_score = int(row.get("客队进球") or 0)

        if handicap is not None:
            try:
                hcap = float(handicap)
                if hcap >= 0:
                    diff = home_score - away_score - hcap
                else:
                    diff = away_score - home_score - abs(hcap)

                if diff > 0:
                    row["盘口结果"] = "赢盘"
                elif diff == 0:
                    row["盘口结果"] = "走水"
                else:
                    row["盘口结果"] = "输盘"
            except (ValueError, TypeError):
                row["盘口结果"] = "-"
        else:
            row["盘口结果"] = "-"

        rows.append(row)

    return {
        "source": "世界杯(同赔)",
        "text": f"竞彩初盘: {win_odds}/{draw_odds}/{lose_odds}，匹配低赔 {low_odds}±{tolerance}",
        "sql": sql,
        "rows": rows,
    }


def handicap_win_rate(question: str, **kwargs) -> Optional[Dict[str, Any]]:
    """盘路统计：指定盘口的上/下盘赢盘率"""
    teams = extract_teams(question)
    if len(teams) < 2:
        return None

    match = find_match_fid(teams[0], teams[1])
    if not match:
        return None

    fid = str(match.get("fid_500", "")) if match.get("fid_500") else None
    if not fid:
        return None

    # 获取亚盘数据
    from odds500_service import fetch_all_indices
    try:
        indices = fetch_all_indices(fid)
    except Exception:
        return None

    # 找澳门亚盘
    asian_data = indices.get("asian", [])
    macau_handicap = None
    for item in asian_data:
        if isinstance(item, dict) and "澳门" in item.get("bookmaker", ""):
            init = item.get("initial", {})
            macau_handicap = init.get("handicap")
            break

    if macau_handicap is None:
        return None

    handicap_val = abs(macau_handicap)

    sql = f"""
    SELECT
        COUNT(*) AS '总场次',
        SUM(CASE
            WHEN (ah.initial_handicap_value > 0 AND (m.home_score - m.away_score) > ah.close_handicap_value) OR
                 (ah.initial_handicap_value < 0 AND (m.away_score - m.home_score) > ABS(ah.close_handicap_value))
            THEN 1 ELSE 0 END) AS '上盘赢',
        ROUND(
            SUM(CASE
                WHEN (ah.initial_handicap_value > 0 AND (m.home_score - m.away_score) > ah.close_handicap_value) OR
                     (ah.initial_handicap_value < 0 AND (m.away_score - m.home_score) > ABS(ah.close_handicap_value))
                THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1
        ) AS '上盘赢盘率'
    FROM matches m
    JOIN wc_asian_handicap ah ON m.id = ah.match_id
    WHERE ah.company = '澳门'
    AND ABS(ah.initial_handicap_value) BETWEEN {handicap_val - 0.25} AND {handicap_val + 0.25}
    """

    result = execute_sqlite(sql)
    if isinstance(result, str) or not result:
        return None

    return {
        "source": "世界杯(盘路)",
        "text": f"澳门初盘让球 {macau_handicap} 附近的历史统计",
        "sql": sql,
        "rows": [dict(r) for r in result],
    }


# ============================================================
# 注册表
# ============================================================

ANALYSIS_REGISTRY = [
    {
        "name": "similar_odds",
        "description": "同赔匹配：查找竞彩初盘赔率相似的历史比赛",
        "keywords": [
            "同赔", "相似赔率", "赔率一致", "赔率变动方向基本一致", "赔率相近",
            "同赔率", "赔率接近", "非常像", "非常相似", "很像", "类似的历史",
            "变动方向相似", "变动方向非常像", "赔率盘口以及变动",
            "相似的比赛", "相近的比赛", "历史同赔",
        ],
        "handler": similar_odds,
    },
    {
        "name": "handicap_win_rate",
        "description": "盘路统计：指定比赛盘口对应的历史赢盘率",
        "keywords": ["盘路", "赢盘率", "盘口统计", "同盘"],
        "handler": handicap_win_rate,
    },
]


def try_analysis_function(question: str, model: str = "claude") -> Optional[Dict[str, Any]]:
    """尝试匹配并执行分析函数，返回 None 表示未命中"""

    # 方式1：关键词直接命中
    for entry in ANALYSIS_REGISTRY:
        if any(kw in question for kw in entry["keywords"]):
            result = entry["handler"](question, model=model)
            if result:
                return result

    # 方式2：语义推断 — 包含球队对阵 + 历史相似意图 → 同赔匹配
    teams = extract_teams(question)
    if len(teams) >= 2:
        similarity_signals = ["像", "相似", "一致", "接近", "类似", "历史", "同类", "差不多"]
        odds_signals = ["赔率", "盘口", "赔", "盘", "指数"]
        has_similarity = any(s in question for s in similarity_signals)
        has_odds = any(s in question for s in odds_signals)
        if has_similarity and has_odds:
            result = similar_odds(question, model=model)
            if result:
                return result

    return None
