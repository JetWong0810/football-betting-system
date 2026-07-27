"""竞彩历史同赔匹配引擎 (spf 口径)

镜像 wc_similar_odds.py 的匹配逻辑，数据源换 MySQL jczq_odds_history。
匹配条件: 初盘低赔 ±tolerance + 低赔方同一侧(同为胜/平/负) + 低赔变动方向一致(升/降)

数据口径: 胜平负(spf)。每场取最早 change_time 行=初盘、最晚=终盘；
结果(result)按 raw 比分算主胜/平/客胜。样本: 46673 场有 spf 变动≥2 + 已完赛(2018-2026)。
"""

import logging
from typing import Dict, List, Optional, Tuple

import pymysql

import settings

logger = logging.getLogger(__name__)

TOLERANCE = 0.03
LOW_LABEL = {"win": "胜", "draw": "平", "loss": "负"}
RESULT_MAP = {"win": "H", "draw": "D", "loss": "A"}

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
                      high_tolerance: float = 0.1) -> Dict:
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


def _ah_line_sim(hist: Optional[float], query: Optional[float], tol: float = AH_LINE_TOL) -> Optional[float]:
    """亚盘线接近度 [0,1]; 任一侧缺失返回 None。"""
    if hist is None or query is None:
        return None
    try:
        return max(0.0, 1.0 - abs(float(hist) - float(query)) / tol)
    except (TypeError, ValueError):
        return None


def _find_similar(open_win, open_draw, open_loss, close_win, close_draw, close_loss,
                  tolerance: float, pool_loader, league: Optional[str] = None,
                  exclude_match_id: Optional[str] = None,
                  require_direction: bool = True,
                  high_tolerance: float = 0.1,
                  ah_open: Optional[float] = None,
                  ah_close: Optional[float] = None) -> Dict:
    """共享匹配逻辑: 初盘低赔±tolerance+高赔±high_tolerance, 终盘同理, + 低赔方同侧 + 变动方向一致。

    "上盘球队"(低赔方)必须与预测比赛同一侧(同为胜/平/负的某一项), 初盘与终盘的低赔都在
    ±tolerance 内、高赔都在 ±high_tolerance 内, 且初→终盘变动方向一致。同侧避免主胜低赔匹配到
    客胜低赔的盘口结构相反场次。
    高赔方=主胜/客胜中较高者(对阵双方 underdog), **不含平赔**(平是中间项, 不参与高赔约束)。
    exclude_match_id: 剔除预测比赛自身(已完赛回溯预测时该场在池中会100%自匹配)。
    require_direction=False: 当预测场仅有1条spf快照(open==close, 无真实变动)时,
      放弃"变动方向一致"过滤(此时方向恒为"平"是数据缺失而非真稳定), 仅按初/终盘接近+同侧匹配。

    相似度: 默认低赔初/终接近度均值; 若传入本场亚盘初/终(ah_open/ah_close),
      再并入历史亚盘初/终接近度: 0.7*欧赔相似 + 0.3*亚盘相似(|Δ|/0.5 归一)。
    排序: 同联赛优先, 再按相似度降序(league 非空时生效)。
    """
    input_low_key, input_low_open, input_low_close, input_direction = _get_low_odds_info(
        open_win, open_draw, open_loss, close_win, close_draw, close_loss
    )
    if input_low_key is None:
        return {"query": {}, "matches": [], "stats": {}}

    low_label = LOW_LABEL[input_low_key]
    pool = pool_loader()
    league_norm = (league or "").strip()

    # 高赔方: 主/客胜较高者(排除平), 历史高赔须接近本场
    input_high_open = _side_high_odds(open_win, open_loss)
    input_high_close = _side_high_odds(close_win, close_loss)
    if input_high_open is None:
        return {"query": {}, "matches": [], "stats": {}}

    use_ah_sim = ah_open is not None and ah_close is not None

    matched = []
    for m in pool:
        # 剔除预测比赛自身
        if exclude_match_id and m.get("match_id") == exclude_match_id:
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
        # 终盘低赔 ±tolerance
        if input_low_close is not None and hist_low_close is not None:
            if abs(hist_low_close - input_low_close) > tolerance:
                continue
        # 高赔方 ±high_tolerance (主/客较高者, 不含平; 初盘+终盘)
        hist_high_open = _side_high_odds(m["open_win"], m["open_loss"])
        if hist_high_open is None or abs(hist_high_open - input_high_open) > high_tolerance:
            continue
        if input_high_close is not None:
            hist_high_close = _side_high_odds(m["close_win"], m["close_loss"])
            if hist_high_close is None or abs(hist_high_close - input_high_close) > high_tolerance:
                continue
        # 初→终盘变动方向一致(预测场无真实变动时跳过此过滤)
        if require_direction and hist_direction != input_direction:
            continue

        # 相似度 = 欧赔低赔初/终接近度; 有本场亚盘初终时再并入亚盘路径相似
        sim_open = max(0.0, 1 - abs(hist_low_open - input_low_open) / tolerance)
        if input_low_close is not None and hist_low_close is not None:
            sim_close = max(0.0, 1 - abs(hist_low_close - input_low_close) / tolerance)
        else:
            sim_close = 0.0
        odds_sim = (sim_open + sim_close) / 2
        if use_ah_sim:
            s_ah_o = _ah_line_sim(m.get("open_handicap"), ah_open)
            s_ah_c = _ah_line_sim(m.get("handicap"), ah_close)
            if s_ah_o is not None and s_ah_c is not None:
                ah_sim = (s_ah_o + s_ah_c) / 2
                similarity = round((0.7 * odds_sim + 0.3 * ah_sim) * 100, 1)
            else:
                # 历史无亚盘: 仅用欧赔, 略降权避免无盘场虚高
                similarity = round(odds_sim * 0.95 * 100, 1)
        else:
            similarity = round(odds_sim * 100, 1)

        same_league = bool(league_norm) and (m.get("league_name") or "").strip() == league_norm

        m["similarity"] = similarity
        m["hist_low_key"] = hist_low_key
        m["hist_low_open"] = hist_low_open
        m["hist_low_close"] = hist_low_close
        m["hist_direction"] = hist_direction
        m["same_league"] = same_league
        m["home_team_cn"] = m["home_team"]
        m["away_team_cn"] = m["away_team"]
        matched.append(m)

    # 同联赛优先, 再按相似度降序
    matched.sort(key=lambda x: (-int(x["same_league"]), -x["similarity"]))
    stats = _calc_stats(matched)

    return {
        "query": {
            "open_win": open_win, "open_draw": open_draw, "open_loss": open_loss,
            "close_win": close_win, "close_draw": close_draw, "close_loss": close_loss,
            "low_position": low_label, "low_open": input_low_open, "low_close": input_low_close,
            "high_open": input_high_open, "high_close": input_high_close,
            "direction": input_direction, "tolerance": tolerance, "high_tolerance": high_tolerance,
            "ah_open": ah_open, "ah_close": ah_close,
            "league": league_norm or None,
        },
        "matches": matched,
        "stats": stats,
    }


def find_similar_spf(open_win: float, open_draw: float, open_loss: float,
                    close_win: float, close_draw: float, close_loss: float,
                    tolerance: float = TOLERANCE, league: Optional[str] = None,
                    exclude_match_id: Optional[str] = None,
                    require_direction: bool = True,
                    high_tolerance: float = 0.1,
                    ah_open: Optional[float] = None,
                    ah_close: Optional[float] = None) -> Dict:
    """核心匹配(胜平负 spf 口径): 初/终盘低赔±tolerance+高赔±high_tolerance + 低赔方同侧 + 变动方向一致。

    ah_open/ah_close: 本场亚盘初/终(标准负=主让), 传入则相似度并入亚盘路径接近度。
    league 非空时同联赛优先排序; exclude_match_id 剔除预测比赛自身。
    require_direction=False: 预测场仅有1条spf快照(无真实变动)时放弃方向过滤。
    Returns: {query, matches, stats} 与 wc_similar_odds.find_similar 同构。
    """
    return _find_similar(open_win, open_draw, open_loss, close_win, close_draw, close_loss,
                         tolerance, pool_loader=get_spf_pool, league=league,
                         exclude_match_id=exclude_match_id,
                         require_direction=require_direction,
                         high_tolerance=high_tolerance,
                         ah_open=ah_open, ah_close=ah_close)


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
