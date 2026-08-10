"""竞彩历史同赔匹配引擎 (spf 口径)

镜像 wc_similar_odds.py 的匹配逻辑，数据源换 MySQL jczq_odds_history。
匹配条件: 初盘低赔 ±tolerance + 低赔方同一侧(同为胜/平/负) + 低赔变动方向一致(升/降)

数据口径: 胜平负(spf)。每场取最早 change_time 行=初盘、最晚=终盘；
结果(result)按 raw 比分算主胜/平/客胜。样本: 46673 场有 spf 变动≥2 + 已完赛(2018-2026)。
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pymysql

import settings

logger = logging.getLogger(__name__)

TOLERANCE = 0.03
HIGH_TOLERANCE = 0.1
# 高赔≥该阈值时放宽容差(高赔区间稀疏, ±0.1 样本过少); 初盘/终盘同规则
HIGH_ODDS_WIDE_THRESHOLD = 6.0
HIGH_TOLERANCE_WIDE = 0.15
LOW_LABEL = {"win": "胜", "draw": "平", "loss": "负"}
RESULT_MAP = {"win": "H", "draw": "D", "loss": "A"}

# 日本赛事同赔模式(弹窗开关): 池仅日职/日乙/杯赛 + 与默认同结构放宽容差
# 默认: 低赔±0.03 / 高赔±0.1(≥6→±0.15) → 日本: 低赔±0.05 / 高赔±0.15(初终对称)
JP_LEAGUES = frozenset({"日职", "日职乙", "日乙", "日联杯", "日天皇杯", "日超杯"})
JP_TOLERANCE = 0.05          # 初/终盘低赔 ±0.05(默认 ±0.03)
JP_HIGH_TOLERANCE = 0.15     # 初/终盘高赔 ±0.15(默认 ±0.1; ≥6 仍用 ±0.15)

# 同赛事模式(弹窗开关, 与日本模式独立): 仅匹配本场同赛事(+别名) + 同日本放宽容差
# 不混同国二级/杯赛。日本场仍走 japan_mode, 不走本开关。
# 白名单按 spf 同赔池体量(已完赛且初终盘齐全)选取: 五大联赛及二级 + 北欧/美洲/亚澳等大体量联赛 + 欧冠/欧罗巴。
SAME_LEAGUE_ELIGIBLE = frozenset({
    "英超", "英冠", "英甲",
    "西甲",
    "意甲",
    "德甲", "德乙",
    "法甲", "法乙",
    "葡超",
    "荷甲", "荷乙",
    # 北欧 / 美洲 / 亚澳 / 东欧(池内 ≥300 场; 含改名别名)
    "瑞超", "瑞典超",
    "挪超",
    "美职联", "美职",
    "巴甲",
    "K1联赛", "韩职",
    "澳超",
    "俄超",
    "比甲",
    "阿甲",
    "墨西联",
    # 洲际俱乐部赛事(同名硬过滤, 体量 ≥1000)
    "欧冠",
    "欧罗巴",
})
# 竞彩历史改名: 同赛事模式须一并纳入过滤(否则「瑞超」只能命中 25 场新名)
SAME_LEAGUE_ALIAS_GROUPS = (
    frozenset({"瑞超", "瑞典超"}),
    frozenset({"美职", "美职联"}),
    frozenset({"韩职", "K1联赛"}),
)
SAME_LEAGUE_TOLERANCE = JP_TOLERANCE
SAME_LEAGUE_HIGH_TOLERANCE = JP_HIGH_TOLERANCE


def is_japan_league(league: Optional[str]) -> bool:
    """是否日本本土赛事(日职/日乙/天皇杯/联杯等)。"""
    name = (league or "").strip()
    if name in JP_LEAGUES:
        return True
    # 兜底: 罕见别名
    return name.startswith("日职") or name.startswith("日乙") or name.startswith("日天皇") or name.startswith("日联")


def same_league_name_set(league: Optional[str]) -> frozenset:
    """本场赛事名 + 改名别名集合(无别名则仅自身)。"""
    name = (league or "").strip()
    if not name:
        return frozenset()
    for group in SAME_LEAGUE_ALIAS_GROUPS:
        if name in group:
            return group
    return frozenset({name})


def is_same_league_eligible(league: Optional[str]) -> bool:
    """是否可开「同赛事」同赔开关(大体量联赛/欧冠欧罗巴; 不含日本)。"""
    name = (league or "").strip()
    if not name or is_japan_league(name):
        return False
    return name in SAME_LEAGUE_ELIGIBLE


def _high_odds_tolerance(odds: Optional[float], base: float = HIGH_TOLERANCE,
                         wide: float = HIGH_TOLERANCE_WIDE) -> float:
    """高赔容差: ≥6.0 用 wide, 否则用 base。初盘/终盘共用。"""
    if odds is not None and odds >= HIGH_ODDS_WIDE_THRESHOLD:
        return wide
    return base

# 历史池缓存: 2018-2025 静态数据，进程内只加载一次
_pool_cache: Optional[List[Dict]] = None
_spf_pool_cache: Optional[List[Dict]] = None


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
    """返回 (低赔key, 低赔初盘值, 低赔终盘值, 低赔变动方向)。低赔=初盘最低的那项。"""
    odds_map = [
        ("win", open_win, close_win),
        ("draw", open_draw, close_draw),
        ("loss", open_loss, close_loss),
    ]
    valid = [(k, o, c) for k, o, c in odds_map if o is not None]
    if not valid:
        return None, None, None, None
    low_key, low_open, low_close = min(valid, key=lambda x: x[1])
    direction = _get_direction(low_open, low_close)
    return low_key, low_open, low_close, direction


def _side_high_odds(win, loss):
    """高赔方=主胜/客胜中较高者(对阵双方 underdog), 不含平赔。

    平是中间项, 不参与高赔匹配。缺一侧则返回另一侧; 都缺返回 None。
    """
    cands = [o for o in (win, loss) if o is not None]
    if not cands:
        return None
    return max(cands)


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


def _ah_outcome(home_score: int, away_score: int, hc: Optional[float],
                low_key: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """亚盘盘路结果(标准亚盘: 正=主受让, 负=主让)。

    Net = (主分-客分) + hc。上盘=让球方(favorite):
      - hc<0 主让→主队上盘; hc>0 客让→客队上盘(让球方权威);
      - hc=0 平手盘无让球方, 退用 spf 低赔方(low_key, 'win'主/'loss'客)作上盘(市场favorite)。
    返回 (label, stat): label∈上盘/下盘/走水/半上/半下, stat∈upper/lower/push/half_up/half_down。
    hc 为 None 返回 None。半输半赢: |Net|≈0.25 (quarter线常态)。
    """
    if hc is None:
        return None
    net = (home_score - away_score) + hc
    a = abs(net)
    if a < 1e-9:
        return ("走水", "push")
    if hc == 0:
        # 平手盘: 用 spf 低赔方作上盘(win=主队, loss=客队); low_key 缺则默认主队
        home_is_upper = (low_key != "loss")
    else:
        home_is_upper = hc < 0  # 主让→主队上盘
    upper_covered = net > 0 if home_is_upper else net < 0
    half = abs(a - 0.25) < 1e-9
    if half:
        return ("半上" if upper_covered else "半下", "half_up" if upper_covered else "half_down")
    return ("上盘" if upper_covered else "下盘", "upper" if upper_covered else "lower")


def settle_ah_selection(home_score: int, away_score: int, side: str,
                        line: float) -> Optional[Dict]:
    """结算单侧亚盘选择(模拟投注/赛后核对)。

    side: 'home'|'away'; line: 该侧盘口(标准约定, 主队负=主让)。
    买主 line=H → net=(HS-AS)+H; 买客 line=A → net=(AS-HS)+A。
    返回 {label, units, key}; key∈win/half_win/push/half_lose/lose。
    """
    if side not in ("home", "away") or line is None:
        return None
    try:
        hs, aws = int(home_score), int(away_score)
        ln = float(line)
    except (TypeError, ValueError):
        return None
    if side == "home":
        net = (hs - aws) + ln
    else:
        net = (aws - hs) + ln
    a = abs(net)
    if a < 1e-9:
        return {"label": "走水", "units": 0.0, "key": "push"}
    half = abs(a - 0.25) < 1e-9
    if net > 0:
        if half:
            return {"label": "半赢", "units": 0.5, "key": "half_win"}
        return {"label": "全赢", "units": 1.0, "key": "win"}
    if half:
        return {"label": "半输", "units": -0.5, "key": "half_lose"}
    return {"label": "全输", "units": -1.0, "key": "lose"}


def upper_side_for_hc(hc: Optional[float], low_key: Optional[str] = None) -> Optional[str]:
    """主盘 hc 下上盘侧: home|away。平手盘退用 spf 低赔方(与 _ah_outcome 一致)。"""
    if hc is None:
        return None
    try:
        h = float(hc)
    except (TypeError, ValueError):
        return None
    if abs(h) < 1e-9:
        return "away" if low_key == "loss" else "home"
    return "home" if h < 0 else "away"


def _calc_stats(matches: List[Dict]) -> Dict:
    """统计: 胜平负分布 + 低赔命中率 + 亚盘盘路(纯亚盘口径, 含半输半赢)"""
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

    # 亚盘盘路: 仅对有亚盘让球的场次统计。半上算上盘、半下算下盘(各计1, 不再拆给两边),
    # 走水单独列。保留全上/半上/全下/半下/走水子计数供展示。
    ah_upper = ah_lower = ah_push = ah_total = 0
    full_up = half_up = full_down = half_down = push = 0
    for m in matches:
        out = _ah_outcome(m.get("home_score"), m.get("away_score"), m.get("handicap"),
                          m.get("hist_low_key"))
        if out is None:
            continue
        stat = out[1]
        ah_total += 1
        if stat == "upper":
            ah_upper += 1; full_up += 1
        elif stat == "half_up":
            ah_upper += 1; half_up += 1        # 半上 → 上盘
        elif stat == "half_down":
            ah_lower += 1; half_down += 1      # 半下 → 下盘
        elif stat == "lower":
            ah_lower += 1; full_down += 1
        else:  # push
            ah_push += 1; push += 1

    return {
        "total": total,
        "wins": wins, "draws": draws, "losses": losses,
        "win_pct": round(wins / total * 100, 1),
        "draw_pct": round(draws / total * 100, 1),
        "loss_pct": round(losses / total * 100, 1),
        "low_hit": low_hit,
        "low_hit_pct": round(low_hit / total * 100, 1) if total else 0,
        "ah_total": ah_total, "ah_upper": ah_upper, "ah_lower": ah_lower, "ah_push": ah_push,
        "full_up": full_up, "half_up": half_up, "full_down": full_down, "half_down": half_down,
        "ah_upper_pct": round(ah_upper / ah_total * 100, 1) if ah_total else 0,
        "ah_lower_pct": round(ah_lower / ah_total * 100, 1) if ah_total else 0,
    }


def get_match_jczq_odds(match_id: str, odds_type: str = "nspf") -> Optional[Dict]:
    """取某场竞彩比赛指定口径的初盘/终盘, 组装成 jczq_company dict。

    odds_type: 'nspf'(让球胜平负, 供F6历史同赔匹配历史池) 或 'spf'(胜平负, 供F5竞彩赔率, 同世界杯口径)。
    initial=最早变动行, current=最晚变动行。无记录返回 None。
    """
    sql = """
        SELECT odds_win, odds_draw, odds_loss, change_time
        FROM jczq_odds_history
        WHERE match_id = %s AND odds_type = %s
        ORDER BY change_time
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (match_id, odds_type))
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


def get_match_nspf_odds(match_id: str) -> Optional[Dict]:
    """让球胜平负(nspf)初终盘 — 供 F6 历史同赔匹配 nspf 历史池。"""
    return get_match_jczq_odds(match_id, "nspf")


def get_match_spf_odds(match_id: str) -> Optional[Dict]:
    """胜平负(spf)初终盘 — 供 F5 竞彩赔率因子, 与世界杯口径一致。"""
    return get_match_jczq_odds(match_id, "spf")


def find_similar_nspf(open_win: float, open_draw: float, open_loss: float,
                      close_win: float, close_draw: float, close_loss: float,
                      tolerance: float = TOLERANCE, league: Optional[str] = None,
                      exclude_match_id: Optional[str] = None,
                      require_direction: bool = True,
                      high_tolerance: float = HIGH_TOLERANCE) -> Dict:
    """核心匹配(让球胜平负 nspf 口径): 初/终盘低赔±tolerance+高赔±high_tolerance + 低赔方同侧 + 变动方向一致。

    league 非空时同联赛优先排序; exclude_match_id 剔除预测比赛自身。
    Returns: {query, matches, stats} 与 wc_similar_odds.find_similar 同构。
    """
    return _find_similar(open_win, open_draw, open_loss, close_win, close_draw, close_loss,
                         tolerance, pool_loader=get_nspf_pool, league=league,
                         exclude_match_id=exclude_match_id,
                         require_direction=require_direction,
                         high_tolerance=high_tolerance)


def get_spf_pool() -> List[Dict]:
    """spf(胜平负)历史同赔池: 每场初盘+终盘+比分+亚盘让球, 结果按raw比分算(主胜/平/客胜)。

    让球用亚盘收盘线(jczq_ah_history.close_handicap, 标准亚盘: 正=主受让 负=主让)结算盘路;
    另带 open_handicap 供弹窗展示初→终。无亚盘则 handicap/open_handicap=None。
    过滤: spf变动≥2 + 已完赛。
    """
    global _spf_pool_cache
    if _spf_pool_cache is not None:
        return _spf_pool_cache
    sql = """
        SELECT
            m.match_id, m.match_date, m.league_name,
            m.home_team_name, m.away_team_name,
            m.home_score, m.away_score,
            m.is_single,
            ah.open_handicap AS open_handicap,
            ah.close_handicap AS handicap,
            f.odds_win  AS open_win,  f.odds_draw  AS open_draw,  f.odds_loss  AS open_loss,
            l.odds_win  AS close_win, l.odds_draw  AS close_draw, l.odds_loss  AS close_loss
        FROM (
            SELECT match_id, MIN(change_time) mn, MAX(change_time) mx
            FROM jczq_odds_history
            WHERE odds_type = 'spf'
            GROUP BY match_id
            HAVING COUNT(*) >= 2
        ) t
        JOIN jczq_odds_history f ON f.match_id = t.match_id AND f.odds_type = 'spf' AND f.change_time = t.mn
        JOIN jczq_odds_history l ON l.match_id = t.match_id AND l.odds_type = 'spf' AND l.change_time = t.mx
        JOIN matches m ON m.match_id = t.match_id
        LEFT JOIN jczq_ah_history ah ON ah.match_id = t.match_id
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
        # spf 结果按 raw 比分(不用让球)
        try:
            diff = int(r["home_score"]) - int(r["away_score"])
        except (TypeError, ValueError):
            continue
        if diff > 0:
            result = "H"
        elif diff == 0:
            result = "D"
        else:
            result = "A"
        hc = r["handicap"]
        oh = r.get("open_handicap")
        pool.append({
            "match_id": r["match_id"],
            "match_date": str(r["match_date"]) if r["match_date"] else "",
            "league_name": r["league_name"] or "",
            "home_team": r["home_team_name"] or "",
            "away_team": r["away_team_name"] or "",
            "home_score": int(r["home_score"]),
            "away_score": int(r["away_score"]),
            "is_single": 1 if int(r.get("is_single") or 0) == 1 else 0,
            "open_handicap": float(oh) if oh is not None else None,
            "handicap": float(hc) if hc is not None else None,
            "result": result,
            "open_win": float(r["open_win"]), "open_draw": float(r["open_draw"]), "open_loss": float(r["open_loss"]),
            "close_win": float(r["close_win"]), "close_draw": float(r["close_draw"]), "close_loss": float(r["close_loss"]),
        })
    _spf_pool_cache = pool
    return pool


AH_LINE_TOL = 0.5  # 亚盘相似: |Δ|≥0.5 球 → 该项贡献归零
LEAGUE_SOFT_BOOST = 1.12  # 同联赛软加成(不再硬插队)
# 欧赔结构相似: 低赔为主、高赔过线后参与打分
LOW_ODDS_SIM_WEIGHT = 0.65
HIGH_ODDS_SIM_WEIGHT = 0.35


def _ah_line_sim(hist: Optional[float], query: Optional[float], tol: float = AH_LINE_TOL) -> Optional[float]:
    """亚盘线接近度 [0,1]; 任一侧缺失返回 None。"""
    if hist is None or query is None:
        return None
    try:
        return max(0.0, 1.0 - abs(float(hist) - float(query)) / tol)
    except (TypeError, ValueError):
        return None


def _time_decay_rank(match_date) -> float:
    """时效权重: 近3年1.0 / 3–6年0.85 / 更旧0.7(与 refScore 对齐)。"""
    md = None
    if isinstance(match_date, datetime):
        md = match_date.date()
    elif isinstance(match_date, date):
        md = match_date
    elif match_date:
        try:
            md = datetime.strptime(str(match_date)[:10], "%Y-%m-%d").date()
        except ValueError:
            md = None
    if md is None:
        return 0.85
    age_years = (date.today() - md).days / 365.25
    if age_years <= 3:
        return 1.0
    if age_years <= 6:
        return 0.85
    return 0.7


def _hc_proximity_rank(hist_hc: Optional[float], query_hc: Optional[float]) -> float:
    """终盘盘口接近权重: ≤0.25→1.0 / ≤0.5→0.7 / ≤1.0→0.4 / 更远0.2; 缺一侧中性0.6。"""
    if hist_hc is None or query_hc is None:
        return 0.6
    try:
        delta = abs(float(hist_hc) - float(query_hc))
    except (TypeError, ValueError):
        return 0.6
    if delta <= 0.25:
        return 1.0
    if delta <= 0.5:
        return 0.7
    if delta <= 1.0:
        return 0.4
    return 0.2


def _blend_structural_sim(
    odds_sim: float,
    hist_open_hc: Optional[float],
    hist_close_hc: Optional[float],
    ah_open: Optional[float],
    ah_close: Optional[float],
) -> float:
    """结构相似度[0,1]: 欧赔 + 亚盘分档并入(有多少算多少, 避免缺初盘整段掉崖)。"""
    if ah_open is None and ah_close is None:
        return odds_sim
    s_ah_o = _ah_line_sim(hist_open_hc, ah_open)
    s_ah_c = _ah_line_sim(hist_close_hc, ah_close)
    if s_ah_o is not None and s_ah_c is not None:
        return 0.7 * odds_sim + 0.3 * ((s_ah_o + s_ah_c) / 2)
    if s_ah_c is not None:
        return 0.8 * odds_sim + 0.2 * s_ah_c
    if s_ah_o is not None:
        return 0.85 * odds_sim + 0.15 * s_ah_o
    # 本场有亚盘但历史全缺: 略降权防虚高
    return odds_sim * 0.95


def _find_similar(open_win, open_draw, open_loss, close_win, close_draw, close_loss,
                  tolerance: float, pool_loader, league: Optional[str] = None,
                  exclude_match_id: Optional[str] = None,
                  require_direction: bool = True,
                  high_tolerance: float = HIGH_TOLERANCE,
                  ah_open: Optional[float] = None,
                  ah_close: Optional[float] = None,
                  close_tolerance: Optional[float] = None,
                  league_filter: Optional[frozenset] = None,
                  soft_high: bool = False,
                  high_tolerance_wide: float = HIGH_TOLERANCE_WIDE) -> Dict:
    """共享匹配逻辑: 初盘低赔±tolerance+高赔±high_tolerance, 终盘同理, + 低赔方同侧 + 变动方向一致。

    "上盘球队"(低赔方)必须与预测比赛同一侧(同为胜/平/负的某一项), 初盘与终盘的低赔都在
    ±tolerance 内、高赔都在对应容差内, 且初→终盘变动方向一致。同侧避免主胜低赔匹配到
    客胜低赔的盘口结构相反场次。
    高赔方=主胜/客胜中较高者(对阵双方 underdog), **不含平赔**(平是中间项, 不参与高赔约束)。
    初/终盘高赔≥6.0 时各自容差放宽为 high_tolerance_wide(默认 ±0.15), 否则用 high_tolerance。
    close_tolerance: 终盘低赔容差; None 则与初盘共用 tolerance。
    league_filter: 非空时硬过滤历史联赛(如日本模式仅日职/日乙/杯赛)。
    soft_high: True 时高赔不做硬过滤, 仅参与相似度打分。
    exclude_match_id: 剔除预测比赛自身(已完赛回溯预测时该场在池中会100%自匹配)。
    require_direction=False: 当预测场仅有1条spf快照(open==close, 无真实变动)时,
      放弃"变动方向一致"过滤(此时方向恒为"平"是数据缺失而非真稳定), 仅按初/终盘接近+同侧匹配。

    相似度(展示=排序):
      1) 欧赔结构 = 0.65*低赔初终接近 + 0.35*高赔初终接近(各自容差归一)
      2) 亚盘分档并入: 初+终→0.3; 仅终→0.2; 仅初→0.15; 历史全缺→×0.95
      3) 软因子: 同联赛×1.12 × 时效衰减 × 终盘盘口接近; 封顶100
    排序: 按上述综合相似度降序(同联赛不再硬插队)。
    """
    input_low_key, input_low_open, input_low_close, input_direction = _get_low_odds_info(
        open_win, open_draw, open_loss, close_win, close_draw, close_loss
    )
    if input_low_key is None:
        return {"query": {}, "matches": [], "stats": {}}

    low_label = LOW_LABEL[input_low_key]
    pool = pool_loader()
    league_norm = (league or "").strip()
    close_tol = tolerance if close_tolerance is None else close_tolerance

    # 高赔方: 主/客胜较高者(排除平), 历史高赔须接近本场(soft_high 时仅打分)
    input_high_open = _side_high_odds(open_win, open_loss)
    input_high_close = _side_high_odds(close_win, close_loss)
    if input_high_open is None:
        return {"query": {}, "matches": [], "stats": {}}

    open_high_tol = _high_odds_tolerance(input_high_open, high_tolerance, high_tolerance_wide)
    close_high_tol = _high_odds_tolerance(input_high_close, high_tolerance, high_tolerance_wide)

    matched = []
    for m in pool:
        # 剔除预测比赛自身
        if exclude_match_id and m.get("match_id") == exclude_match_id:
            continue
        # 联赛硬过滤(日本模式等)
        if league_filter is not None:
            hist_lg = (m.get("league_name") or "").strip()
            if hist_lg not in league_filter:
                continue
        hist_low_key, hist_low_open, hist_low_close, hist_direction = _get_low_odds_info(
            m["open_win"], m["open_draw"], m["open_loss"],
            m["close_win"], m["close_draw"], m["close_loss"],
        )
        if hist_low_key is None or hist_direction is None:
            continue
        # 同侧: 历史低赔方须与预测低赔方同一项(同为胜/平/负)
        if hist_low_key != input_low_key:
            continue
        # 初盘低赔 ±tolerance
        if abs(hist_low_open - input_low_open) > tolerance:
            continue
        # 终盘低赔 ±close_tol
        if input_low_close is not None and hist_low_close is not None:
            if abs(hist_low_close - input_low_close) > close_tol:
                continue
        # 高赔方: 初/终各自按赔率档位自适应; soft_high 时跳过硬过滤
        hist_high_open = _side_high_odds(m["open_win"], m["open_loss"])
        if hist_high_open is None:
            continue
        if not soft_high and abs(hist_high_open - input_high_open) > open_high_tol:
            continue
        hist_high_close = None
        if input_high_close is not None:
            hist_high_close = _side_high_odds(m["close_win"], m["close_loss"])
            if hist_high_close is None:
                continue
            if not soft_high and abs(hist_high_close - input_high_close) > close_high_tol:
                continue
        # 初→终盘变动方向一致(预测场无真实变动时跳过此过滤)
        if require_direction and hist_direction != input_direction:
            continue

        # 1) 欧赔结构: 低赔 + 高赔(过线后按容差归一打分)
        sim_low_open = max(0.0, 1 - abs(hist_low_open - input_low_open) / tolerance) if tolerance > 0 else 0.0
        if input_low_close is not None and hist_low_close is not None and close_tol > 0:
            sim_low_close = max(0.0, 1 - abs(hist_low_close - input_low_close) / close_tol)
        else:
            sim_low_close = 0.0
        low_sim = (sim_low_open + sim_low_close) / 2

        sim_high_open = max(0.0, 1 - abs(hist_high_open - input_high_open) / open_high_tol) if open_high_tol > 0 else 0.0
        if input_high_close is not None and hist_high_close is not None and close_high_tol > 0:
            sim_high_close = max(0.0, 1 - abs(hist_high_close - input_high_close) / close_high_tol)
            high_sim = (sim_high_open + sim_high_close) / 2
        else:
            high_sim = sim_high_open
        odds_sim = LOW_ODDS_SIM_WEIGHT * low_sim + HIGH_ODDS_SIM_WEIGHT * high_sim

        # 2) 亚盘分档并入
        structural = _blend_structural_sim(
            odds_sim, m.get("open_handicap"), m.get("handicap"), ah_open, ah_close
        )

        # 3) 软因子: 同联赛 / 时效 / 终盘盘口接近 → 综合相似度(展示即排序键)
        # 改名别名(瑞超/瑞典超等)亦计同联赛
        hist_lg_name = (m.get("league_name") or "").strip()
        same_league = bool(league_norm) and hist_lg_name in same_league_name_set(league_norm)
        w_lg = LEAGUE_SOFT_BOOST if same_league else 1.0
        w_time = _time_decay_rank(m.get("match_date"))
        w_hc = _hc_proximity_rank(m.get("handicap"), ah_close)
        similarity = round(min(100.0, structural * w_lg * w_time * w_hc * 100), 1)

        m["similarity"] = similarity
        m["hist_low_key"] = hist_low_key
        m["hist_low_open"] = hist_low_open
        m["hist_low_close"] = hist_low_close
        m["hist_direction"] = hist_direction
        m["same_league"] = same_league
        m["home_team_cn"] = m["home_team"]
        m["away_team_cn"] = m["away_team"]
        matched.append(m)

    # 综合相似度降序(同联赛/时效/盘口已并入 similarity)
    matched.sort(key=lambda x: -x["similarity"])
    stats = _calc_stats(matched)

    return {
        "query": {
            "open_win": open_win, "open_draw": open_draw, "open_loss": open_loss,
            "close_win": close_win, "close_draw": close_draw, "close_loss": close_loss,
            "low_position": low_label, "low_open": input_low_open, "low_close": input_low_close,
            "high_open": input_high_open, "high_close": input_high_close,
            "direction": input_direction, "tolerance": tolerance,
            "close_tolerance": close_tol,
            "high_tolerance": high_tolerance,
            "high_tolerance_open": open_high_tol,
            "high_tolerance_close": close_high_tol,
            "soft_high": soft_high,
            "ah_open": ah_open, "ah_close": ah_close,
            "league": league_norm or None,
            "league_filter": sorted(league_filter) if league_filter else None,
        },
        "matches": matched,
        "stats": stats,
    }


def find_similar_spf(open_win: float, open_draw: float, open_loss: float,
                    close_win: float, close_draw: float, close_loss: float,
                    tolerance: float = TOLERANCE, league: Optional[str] = None,
                    exclude_match_id: Optional[str] = None,
                    require_direction: bool = True,
                    high_tolerance: float = HIGH_TOLERANCE,
                    ah_open: Optional[float] = None,
                    ah_close: Optional[float] = None,
                    close_tolerance: Optional[float] = None,
                    league_filter: Optional[frozenset] = None,
                    soft_high: bool = False,
                    high_tolerance_wide: float = HIGH_TOLERANCE_WIDE,
                    japan_mode: bool = False,
                    same_league_mode: bool = False) -> Dict:
    """核心匹配(胜平负 spf 口径): 初/终盘低赔±tolerance+高赔±high_tolerance + 低赔方同侧 + 变动方向一致。

    ah_open/ah_close: 本场亚盘初/终(标准负=主让), 传入则相似度分档并入亚盘路径接近度。
    league 非空时同联赛软加成(×1.12)并入相似度; exclude_match_id 剔除预测比赛自身。
    require_direction=False: 预测场仅有1条spf快照(无真实变动)时放弃方向过滤。
    japan_mode=True: 仅匹配日职/日乙/天皇杯等 + 低赔±0.05/高赔±0.15(初终对称, 与默认同结构)。
    same_league_mode=True: 仅匹配 league 同赛事(+改名别名) + 同上放宽容差(与 japan_mode 互斥, 日本场不用)。
    Returns: {query, matches, stats} 与 wc_similar_odds.find_similar 同构。
    """
    if japan_mode:
        tolerance = JP_TOLERANCE
        close_tolerance = JP_TOLERANCE  # 终盘低赔与初盘同容差
        high_tolerance = JP_HIGH_TOLERANCE
        high_tolerance_wide = JP_HIGH_TOLERANCE
        league_filter = JP_LEAGUES
        soft_high = False
    elif same_league_mode:
        league_name = (league or "").strip()
        if not league_name:
            return {"query": {}, "matches": [], "stats": {}}
        tolerance = SAME_LEAGUE_TOLERANCE
        close_tolerance = SAME_LEAGUE_TOLERANCE
        high_tolerance = SAME_LEAGUE_HIGH_TOLERANCE
        high_tolerance_wide = SAME_LEAGUE_HIGH_TOLERANCE
        league_filter = same_league_name_set(league_name)
        soft_high = False
    return _find_similar(open_win, open_draw, open_loss, close_win, close_draw, close_loss,
                         tolerance, pool_loader=get_spf_pool, league=league,
                         exclude_match_id=exclude_match_id,
                         require_direction=require_direction,
                         high_tolerance=high_tolerance,
                         ah_open=ah_open, ah_close=ah_close,
                         close_tolerance=close_tolerance,
                         league_filter=league_filter,
                         soft_high=soft_high,
                         high_tolerance_wide=high_tolerance_wide)


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
