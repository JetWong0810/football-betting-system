"""预测服务模块 - 7因子亚盘方向预测 (与世界杯体系对齐)

因子体系:
  F1 近期状态 (权重1.5) - 量化子因素投票(场均分/赢盘率/主客场) + AI辅助1票
  F2 实力定位 (权重1.0) - 量化子因素(排名匹配) + AI底蕴判断(3次投票)
  F3 市场信号 (权重2.0) - 初盘+亚盘调盘/诱盘/Sharp + 欧赔辅助(矛盾信亚盘)
  F4 市场热度 (权重2.0) - 多公司水位共识(资金流向, 预测时逆向)
  F5 竞彩赔率 (权重1.5) - 竞彩nspf初盘→终盘低赔变动方向
  F6 历史同赔 (权重1.5) - 匹配竞彩历史nspf同赔率比赛结果分布
  F7 单关修正 (权重1.5) - 结合F4的单关逆向规则

注: calc_factor2(交锋历史) 保留供 backtest_factors.py 回测，不进 live 因子集。
"""
import json
import logging
import math
import os
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from jczq_similar_odds import find_similar_spf, get_match_nspf_odds, get_match_spf_odds, _ah_outcome

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

FACTOR_WEIGHTS = {
    "近期状态": 1.5,
    "实力定位": 1.0,
    "市场信号": 2.0,   # 升级：初盘+亚盘变动+欧赔变动+亚欧一致性
    "市场热度": 2.0,
    "竞彩赔率": 1.5,   # nspf初盘→终盘低赔变动方向(与世界杯对齐)
    "历史同赔": 1.5,   # 竞彩nspf历史同赔匹配(与世界杯对齐,nspf口径)
    "单关修正": 1.5,
}

FACTOR_NAMES = list(FACTOR_WEIGHTS.keys())

# 盘口先验权重：作为方向基准偏移，相当于一个中等因子，2个真实因子可覆盖
PRIOR_WEIGHT = 1.5

# 先验缓存(避免每次预测查库)
_prior_cache: Dict[float, Optional[float]] = {}


def load_handicap_prior(handicap: Optional[float]) -> Optional[Dict[str, Any]]:
    """加载盘口先验赢盘率(竞彩口径)。

    Args:
        handicap: 系统内盘口值(负值=主队让球)

    Returns:
        {"upper_rate": 排除走水后的上盘赢盘率, "sample": 样本数} 或 None
    """
    if handicap is None:
        bucket = 0.0
    else:
        # 真实亚盘小数盘口映射到最近的竞彩整数桶
        # 系统内: 负值=主队让球，按四舍五入到整数
        bucket = float(round(float(handicap)))

    if bucket in _prior_cache:
        cached = _prior_cache[bucket]
        return cached

    try:
        import pymysql
        import settings as _settings
        conn = pymysql.connect(**_settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
        try:
            with conn.cursor() as c:
                c.execute(
                    "SELECT decided_upper_rate, (upper_count+lower_count) AS decided "
                    "FROM handicap_priors WHERE handicap=%s", (bucket,))
                row = c.fetchone()
                # 小样本(<50)或无数据时回退全局基准
                if not row or row["decided"] < 50 or row["decided_upper_rate"] is None:
                    c.execute(
                        "SELECT decided_upper_rate, (upper_count+lower_count) AS decided "
                        "FROM handicap_priors WHERE handicap=0")
                    row = c.fetchone()
                if row and row["decided_upper_rate"] is not None:
                    result = {"upper_rate": float(row["decided_upper_rate"]), "sample": int(row["decided"])}
                else:
                    result = None
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[predict] 加载盘口先验失败: {e}")
        result = None

    _prior_cache[bucket] = result
    return result


def _get_client() -> OpenAI:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


# ============================================================
# F4 市场信号 - 初盘分析 + 亚盘变动(盘口/诱盘/Sharp) + 欧赔辅助
# 与市场热度划界: 本因子看庄家调盘态度(正向); 热度看资金水位共识(逆向)
# ============================================================

# 主流公司(高权重)
_SHARP_BOOKS = ["Pinnacle"]
_MAINSTREAM_BOOKS = ["Bet365", "皇冠", "澳门", "威廉希尔", "立博"]
# 亚盘公司投票权重: Sharp > Bet365/皇冠 > 其余
_ASIAN_BOOK_WEIGHTS = {
    "Pinnacle": 2.0,
    "Bet365": 1.2,
    "皇冠": 1.2,
    "威廉希尔": 1.0,
    "澳门": 0.8,
    "立博": 0.8,
}

UP, DOWN, NEU = "upper", "lower", "neutral"


def _get_asian_companies(asian_data: List[Dict], priority_books: List[str] = None) -> List[Dict]:
    """按优先级获取亚盘公司数据"""
    if not priority_books:
        priority_books = _SHARP_BOOKS + _MAINSTREAM_BOOKS
    result = []
    for book in priority_books:
        c = next((x for x in asian_data if x.get("bookmaker") == book), None)
        if c:
            result.append(c)
    if not result and asian_data:
        result.append(asian_data[0])
    return result


def _book_weight(book: str) -> float:
    return float(_ASIAN_BOOK_WEIGHTS.get(book, 0.6))


def _calc_sub_opening(asian_data: List[Dict], is_home_let: bool) -> Dict[str, Any]:
    """子因素1: 初盘信号 - 多公司一致性 + 初盘水位位置(庄家开盘态度)"""
    companies = _get_asian_companies(asian_data)
    if not companies:
        return {"direction": NEU, "score": 5, "desc": "无初盘数据", "consistency": "unknown"}

    init_handicaps = []
    init_waters = []
    weighted_water = 0.0
    water_w_sum = 0.0
    for c in companies:
        ini = c.get("initial", {})
        book = c.get("bookmaker", "")
        h = ini.get("handicap")
        if h is not None:
            init_handicaps.append(abs(float(h)))
        w = ini.get("home") if is_home_let else ini.get("away")
        if w is not None:
            init_waters.append(float(w))
            bw = _book_weight(book)
            weighted_water += float(w) * bw
            water_w_sum += bw

    # 初盘一致性：多公司盘口差异
    consistency = "unknown"
    if len(init_handicaps) >= 2:
        spread = max(init_handicaps) - min(init_handicaps)
        if spread <= 0.125:
            consistency = "high"
        elif spread <= 0.25:
            consistency = "medium"
        else:
            consistency = "low"

    direction = NEU
    score = 5
    desc_parts = []

    if water_w_sum > 0:
        avg_water = weighted_water / water_w_sum
        if avg_water <= 0.85:
            direction = UP
            score = 7
            desc_parts.append(f"初盘上盘低水{avg_water:.2f}(庄家看好上盘)")
        elif avg_water >= 1.00:
            direction = DOWN
            score = 7
            desc_parts.append(f"初盘上盘高水{avg_water:.2f}(庄家看淡上盘)")
        elif avg_water >= 0.95:
            direction = DOWN
            score = 6
            desc_parts.append(f"初盘上盘偏高水{avg_water:.2f}(略看淡上盘)")
        elif avg_water <= 0.88:
            direction = UP
            score = 6
            desc_parts.append(f"初盘上盘偏低水{avg_water:.2f}(略看好上盘)")
        else:
            desc_parts.append(f"初盘上盘中水{avg_water:.2f}(均衡)")
    else:
        avg_water = None

    if consistency == "high":
        desc_parts.append("多公司初盘高度一致")
    elif consistency == "low":
        desc_parts.append("各公司初盘分歧大")
        score = max(5, score - 1)

    desc = "，".join(desc_parts) if desc_parts else "初盘数据不足"
    return {"direction": direction, "score": score, "desc": desc, "consistency": consistency,
            "avg_water": avg_water}


def _calc_sub_asian_move(asian_data: List[Dict], is_home_let: bool) -> Dict[str, Any]:
    """子因素2: 亚盘变动 — 盘口升降 + 诱盘 + Pinnacle优先

    与市场热度划界:
    - 本因子: 庄家调盘态度(盘口升降)、诱盘(升盘+升水/降盘+降水)、Sharp单独信号 → 正向
    - 热度因子: 多公司同盘口水位共识(资金追捧) → 逆向
    不再用「≥4家水位同向」做主信号，避免与热度双重解读同一水位。
    """
    companies = _get_asian_companies(asian_data)
    if not companies:
        return {"direction": NEU, "score": 5, "desc": "无亚盘变动数据", "pinnacle_dir": None}

    # per-book: hcap_dir / water_change / trap
    upgrade_w = 0.0
    downgrade_w = 0.0
    trap_upper_w = 0.0   # 升盘+上盘升水 → 诱上 → 信号偏下
    trap_lower_w = 0.0   # 降盘+上盘降水 → 诱下 → 信号偏上
    true_up_w = 0.0      # 升盘且非诱上
    true_down_w = 0.0
    pinnacle_dir = None
    pinnacle_trap = None
    desc_bits = []

    for c in companies:
        ini = c.get("initial", {})
        cur = c.get("current", {})
        book = c.get("bookmaker", "unknown")
        bw = _book_weight(book)

        if is_home_let:
            init_w, curr_w = ini.get("home"), cur.get("home")
        else:
            init_w, curr_w = ini.get("away"), cur.get("away")

        init_h, curr_h = ini.get("handicap"), cur.get("handicap")
        if init_h is None or curr_h is None:
            continue

        init_depth = abs(float(init_h))
        curr_depth = abs(float(curr_h))
        water_change = None
        if init_w is not None and curr_w is not None:
            water_change = float(curr_w) - float(init_w)

        hcap_dir = NEU
        if curr_depth > init_depth + 1e-9:
            hcap_dir = UP
            upgrade_w += bw
        elif curr_depth < init_depth - 1e-9:
            hcap_dir = DOWN
            downgrade_w += bw

        is_trap_upper = hcap_dir == UP and water_change is not None and water_change >= 0.03
        is_trap_lower = hcap_dir == DOWN and water_change is not None and water_change <= -0.03

        if is_trap_upper:
            trap_upper_w += bw
        elif is_trap_lower:
            trap_lower_w += bw
        elif hcap_dir == UP:
            true_up_w += bw
        elif hcap_dir == DOWN:
            true_down_w += bw

        if book in _SHARP_BOOKS:
            if is_trap_upper:
                pinnacle_trap = DOWN  # 诱上 → 信号下
                pinnacle_dir = DOWN
            elif is_trap_lower:
                pinnacle_trap = UP
                pinnacle_dir = UP
            elif hcap_dir in (UP, DOWN):
                pinnacle_dir = hcap_dir
            elif water_change is not None:
                # Sharp 单独水位: 仅作弱信号(热度主责水位共识)
                if water_change <= -0.08:
                    pinnacle_dir = UP
                elif water_change >= 0.08:
                    pinnacle_dir = DOWN

    direction = NEU
    score = 5

    # 1) 诱盘优先(庄家调盘与水位背离)
    if trap_upper_w >= 1.5 and trap_upper_w > trap_lower_w:
        direction, score = DOWN, 8 if trap_upper_w >= 2.5 else 7
        desc_bits.append(f"诱上盘(升盘+升水,权{trap_upper_w:.1f})→偏下盘")
    elif trap_lower_w >= 1.5 and trap_lower_w > trap_upper_w:
        direction, score = UP, 8 if trap_lower_w >= 2.5 else 7
        desc_bits.append(f"诱下盘(降盘+降水,权{trap_lower_w:.1f})→偏上盘")
    # 2) 真升/降盘(无诱盘特征)
    elif true_up_w >= 2.0 and true_up_w > true_down_w + 0.5:
        direction, score = UP, 8 if true_up_w >= 3.0 else 7
        desc_bits.append(f"升盘看好上盘(权{true_up_w:.1f})")
    elif true_down_w >= 2.0 and true_down_w > true_up_w + 0.5:
        direction, score = DOWN, 8 if true_down_w >= 3.0 else 7
        desc_bits.append(f"降盘看淡上盘(权{true_down_w:.1f})")
    elif true_up_w >= 1.2 and true_up_w > true_down_w:
        direction, score = UP, 6
        desc_bits.append(f"少数升盘弱信号(权{true_up_w:.1f})")
    elif true_down_w >= 1.2 and true_down_w > true_up_w:
        direction, score = DOWN, 6
        desc_bits.append(f"少数降盘弱信号(权{true_down_w:.1f})")
    # 3) Pinnacle 单独明确
    elif pinnacle_dir in (UP, DOWN):
        direction = pinnacle_dir
        score = 7 if pinnacle_trap else 6
        tag = "诱盘" if pinnacle_trap else "调盘/水位"
        desc_bits.append(f"Pinnacle{tag}指向{'上盘' if pinnacle_dir == UP else '下盘'}")
    else:
        desc_bits.append(
            f"盘口变动不足(升权{upgrade_w:.1f}/降权{downgrade_w:.1f}，诱上{trap_upper_w:.1f}/诱下{trap_lower_w:.1f})"
        )

    # Pinnacle 与多数冲突时降分、不硬翻
    if direction != NEU and pinnacle_dir in (UP, DOWN) and pinnacle_dir != direction:
        score = max(5, score - 1)
        desc_bits.append("与Pinnacle分歧(降置信)")

    desc = "，".join(desc_bits)
    return {"direction": direction, "score": score, "desc": desc,
            "pinnacle_dir": pinnacle_dir}


def _calc_sub_euro_move(euro_data: Dict, is_home_let: bool) -> Dict[str, Any]:
    """子因素3: 欧赔变动 - 胜平负赔率趋势(辅助, 矛盾时不主导)"""
    companies = euro_data.get("companies", []) if euro_data else []
    if not companies:
        return {"direction": NEU, "score": 5, "desc": "无欧赔数据"}

    # 选取主流公司
    priority = _SHARP_BOOKS + _MAINSTREAM_BOOKS
    selected = []
    for book in priority:
        c = next((x for x in companies if x.get("bookmaker") == book), None)
        if c:
            selected.append(c)
    if not selected:
        selected = companies[:5]

    upper_signals = 0
    lower_signals = 0
    descs = []

    for c in selected:
        ini = c.get("initial", {})
        cur = c.get("current", {})
        book = c.get("bookmaker", "")

        if is_home_let:
            init_upper_odds = ini.get("win")
            curr_upper_odds = cur.get("win")
            init_lower_odds = ini.get("lose")
            curr_lower_odds = cur.get("lose")
        else:
            init_upper_odds = ini.get("lose")
            curr_upper_odds = cur.get("lose")
            init_lower_odds = ini.get("win")
            curr_lower_odds = cur.get("win")

        if not all([init_upper_odds, curr_upper_odds, init_lower_odds, curr_lower_odds]):
            continue

        upper_change = curr_upper_odds - init_upper_odds

        if upper_change <= -0.05:
            upper_signals += 1
        elif upper_change >= 0.05:
            lower_signals += 1

        init_draw = ini.get("draw")
        curr_draw = cur.get("draw")
        if init_draw and curr_draw:
            draw_change = curr_draw - init_draw
            if draw_change >= 0.10:
                descs.append(f"{book}平赔升{draw_change:+.2f}(不看好平)")

    if not selected:
        return {"direction": NEU, "score": 5, "desc": "无有效欧赔公司"}

    total = upper_signals + lower_signals
    if total == 0:
        return {"direction": NEU, "score": 5, "desc": "欧赔整体稳定"}

    if upper_signals > lower_signals:
        direction = UP
        ratio = upper_signals / len(selected)
        desc = f"{upper_signals}/{len(selected)}家欧赔看好上盘"
    elif lower_signals > upper_signals:
        direction = DOWN
        ratio = lower_signals / len(selected)
        desc = f"{lower_signals}/{len(selected)}家欧赔看好下盘"
    else:
        direction = NEU
        ratio = 0
        desc = "欧赔方向分歧"

    if ratio >= 0.6:
        score = 7
    elif ratio >= 0.4:
        score = 6
    else:
        score = 5
        direction = NEU
        desc = "欧赔信号弱"

    if descs:
        desc += "，" + descs[0]
    return {"direction": direction, "score": score, "desc": desc}


def calc_factor4(asian_data: List[Dict], is_home_let: bool,
                 euro_data: Optional[Dict] = None) -> Dict[str, Any]:
    """市场信号: 初盘 + 亚盘调盘/诱盘/Sharp + 欧赔辅助

    与市场热度分工: 本因子正向跟庄家调盘; 热度逆向读资金水位。
    亚欧矛盾时信亚盘(欧赔降权), 不再「信欧赔翻方向」。
    """
    if not asian_data and not euro_data:
        return {"name": "市场信号", "score": 5, "direction": "neutral",
                "reason": "无市场数据", "details": []}

    sub_opening = _calc_sub_opening(asian_data or [], is_home_let)
    sub_asian = _calc_sub_asian_move(asian_data or [], is_home_let)
    sub_euro = _calc_sub_euro_move(euro_data, is_home_let)

    details = [
        {"name": "初盘信号", "direction": sub_opening["direction"],
         "score": sub_opening["score"], "desc": sub_opening["desc"]},
        {"name": "亚盘变动", "direction": sub_asian["direction"],
         "score": sub_asian["score"], "desc": sub_asian["desc"]},
        {"name": "欧赔变动", "direction": sub_euro["direction"],
         "score": sub_euro["score"], "desc": sub_euro["desc"]},
    ]

    asian_dir = sub_asian["direction"]
    euro_dir = sub_euro["direction"]
    opening_dir = sub_opening["direction"]
    consistency_bonus = 0
    consistency_desc = ""

    # 欧赔权重: 与亚盘矛盾时归零(不参与方向投票)
    euro_w = 1.0
    if asian_dir != NEU and euro_dir != NEU:
        if asian_dir == euro_dir:
            consistency_bonus = 1
            consistency_desc = "亚欧一致(信号增强)"
        else:
            euro_w = 0.0
            consistency_bonus = -1
            consistency_desc = "亚欧矛盾(信亚盘，欧赔仅参考)"

    # 综合投票: 初盘1.2 / 亚盘2.5 / 欧赔≤1.0
    dir_votes = {UP: 0.0, DOWN: 0.0, NEU: 0.0}
    subs = [sub_opening, sub_asian, sub_euro]
    sub_weights = [1.2, 2.5, euro_w]

    for sub, w in zip(subs, sub_weights):
        d = sub["direction"]
        if w > 0 and d in (UP, DOWN):
            dir_votes[d] += w

    # Pinnacle 额外加权
    pin_dir = sub_asian.get("pinnacle_dir")
    if pin_dir in (UP, DOWN):
        dir_votes[pin_dir] += 0.8

    # 初盘与亚盘变动一致性
    if opening_dir != NEU and asian_dir != NEU:
        if opening_dir == asian_dir:
            consistency_bonus += 1
            consistency_desc += ("，" if consistency_desc else "") + "初盘态度与变动一致"
        else:
            consistency_desc += ("，" if consistency_desc else "") + "初盘与变动矛盾(可能有新信息)"

    if dir_votes[UP] > dir_votes[DOWN] and dir_votes[UP] > 0:
        direction = UP
    elif dir_votes[DOWN] > dir_votes[UP] and dir_votes[DOWN] > 0:
        direction = DOWN
    else:
        direction = NEU

    active_scores = [s["score"] for s in subs if s["direction"] != NEU]
    if active_scores:
        base_score = sum(active_scores) / len(active_scores)
    else:
        base_score = 5.0
    score = max(3, min(9, round(base_score + consistency_bonus)))

    if direction == NEU:
        score = 5

    stability = sub_opening.get("consistency", "unknown")

    reason_parts = []
    for sub in subs:
        if sub["direction"] != NEU:
            reason_parts.append(sub["desc"])
    if consistency_desc:
        reason_parts.append(consistency_desc)
    reason = "；".join(reason_parts) if reason_parts else "市场信号平稳无明确方向"

    if consistency_desc:
        details.append({"name": "一致性验证", "direction": direction,
                        "score": consistency_bonus, "desc": consistency_desc})

    return {"name": "市场信号", "score": score, "direction": direction,
            "reason": reason, "details": details, "stability": stability}


# ============================================================
# F5 市场热度 - 多公司水位一致性(量化) + 用户手动输入(可选)
# ============================================================

def _parse_manual_heat(desc: str, is_home_let: bool) -> Optional[Dict[str, Any]]:
    """解析用户手动输入的市场热度描述

    识别"上盘热/下盘热/主队热/客队热"等，转为逆向方向。
    上盘热 -> 大众追捧上盘 -> 逆向偏下盘(lower)
    """
    if not desc:
        return None
    d = desc.strip()
    upper_hot = any(k in d for k in ["上盘热", "上盘受追", "上盘过热", "热上盘"])
    lower_hot = any(k in d for k in ["下盘热", "下盘受追", "下盘过热", "热下盘"])
    # 主客队热度映射到上下盘
    home_hot = "主队热" in d or "主热" in d
    away_hot = "客队热" in d or "客热" in d
    if home_hot:
        if is_home_let:
            upper_hot = True
        else:
            lower_hot = True
    if away_hot:
        if is_home_let:
            lower_hot = True
        else:
            upper_hot = True

    if upper_hot and not lower_hot:
        return {"name": "市场热度", "score": 7, "direction": "upper",
                "reason": "手动输入：上盘热"}
    if lower_hot and not upper_hot:
        return {"name": "市场热度", "score": 7, "direction": "lower",
                "reason": "手动输入：下盘热"}
    return None


def calc_factor5(asian_data: List[Dict], is_home_let: bool,
                 market_heat_desc: Optional[str] = None) -> Dict[str, Any]:
    """F5 市场热度: 盘口变动 + 同盘口水位一致性(资金流向) + 用户手动输入

    与市场信号划界: 本因子看资金追捧(水位共识), calc_prediction 中逆向解读;
    市场信号看庄家调盘/诱盘/Sharp, 正向跟庄家意图。

    核心逻辑:
    1. 先看盘口变动: 升盘=庄家看好上盘(热), 降盘=庄家看淡上盘(冷)
    2. 再看同盘口下的水位变动: 降水=资金追上盘(热), 升水=上盘遇冷
    3. 盘口变深后的水位升高是自然补偿，不算遇冷

    逆向解读: 上盘热→偏下盘, 上盘冷→偏上盘
    """
    # 1. 用户手动输入优先
    manual = _parse_manual_heat(market_heat_desc, is_home_let)
    if manual:
        return manual

    # 2. 需要亚盘数据
    if not asian_data:
        return {"name": "市场热度", "score": 5, "direction": "neutral", "reason": "无亚盘数据，热度不明"}

    # 3. 统计盘口变动和同盘口水位变动
    upgrade = 0   # 升盘(盘口变深)公司数
    downgrade = 0  # 降盘(盘口变浅)公司数
    same_drops = 0  # 同盘口下上盘降水
    same_rises = 0  # 同盘口下上盘升水
    total = 0

    for c in asian_data:
        i = c.get("initial", {})
        cur = c.get("current", {})
        ih = i.get("handicap")
        ch = cur.get("handicap")
        if is_home_let:
            iv, cv = i.get("home"), cur.get("home")
        else:
            iv, cv = i.get("away"), cur.get("away")
        if iv is None or cv is None or ih is None or ch is None:
            continue

        total += 1
        handicap_diff = float(ch) - float(ih)

        if handicap_diff > 0.01:
            upgrade += 1
        elif handicap_diff < -0.01:
            downgrade += 1
        else:
            # 同盘口，水位变动才反映资金流向
            wc = cv - iv
            if wc <= -0.03:
                same_drops += 1
            elif wc >= 0.03:
                same_rises += 1

    if total < 4:
        return {"name": "市场热度", "score": 5, "direction": "neutral", "reason": "公司样本不足，热度不明"}

    # 4. 综合判断
    # 升盘占多数 = 庄家主动加深盘口 = 看好上盘 = 上盘热 = 逆向偏下盘
    upgrade_ratio = upgrade / total if total else 0
    downgrade_ratio = downgrade / total if total else 0

    if upgrade_ratio >= 0.6:
        score = 7 if upgrade_ratio >= 0.75 else 6
        return {"name": "市场热度", "score": score, "direction": "upper",
                "reason": f"{upgrade}/{total}家升盘(盘口加深)，庄家看好上盘，上盘热"}

    if downgrade_ratio >= 0.6:
        score = 7 if downgrade_ratio >= 0.75 else 6
        return {"name": "市场热度", "score": score, "direction": "lower",
                "reason": f"{downgrade}/{total}家降盘(盘口变浅)，庄家看淡上盘，下盘热"}

    # 盘口无明显方向时，看同盘口下的水位变动
    same_moved = same_drops + same_rises
    if same_moved >= 3:
        drop_ratio = same_drops / same_moved
        rise_ratio = same_rises / same_moved

        if drop_ratio >= 0.75:
            return {"name": "市场热度", "score": 7, "direction": "upper",
                    "reason": f"同盘口{same_drops}/{same_moved}家上盘降水，资金追上盘，上盘热"}
        elif drop_ratio >= 0.6:
            return {"name": "市场热度", "score": 6, "direction": "upper",
                    "reason": f"同盘口{same_drops}/{same_moved}家上盘降水，上盘略热"}
        elif rise_ratio >= 0.75:
            return {"name": "市场热度", "score": 7, "direction": "lower",
                    "reason": f"同盘口{same_rises}/{same_moved}家上盘升水，下盘热"}
        elif rise_ratio >= 0.6:
            return {"name": "市场热度", "score": 6, "direction": "lower",
                    "reason": f"同盘口{same_rises}/{same_moved}家上盘升水，下盘略热"}

    # 混合信号
    parts = []
    if upgrade:
        parts.append(f"{upgrade}家升盘")
    if downgrade:
        parts.append(f"{downgrade}家降盘")
    if same_drops:
        parts.append(f"{same_drops}家同盘降水")
    if same_rises:
        parts.append(f"{same_rises}家同盘升水")
    return {"name": "市场热度", "score": 5, "direction": "neutral",
            "reason": f"信号分歧({'，'.join(parts)})，热度不明"}


# ============================================================
# F1 近期状态 - 量化子因素投票 + AI辅助
# ============================================================

# 角色赢盘等沿用较平缓衰减
_TIME_DECAY = [1.5, 1.5, 1.5, 1.0, 1.0, 1.0, 0.6, 0.6, 0.6, 0.6, 0.4, 0.4, 0.4, 0.4, 0.4]

# 加权场均分：更陡，近况主导（仍保留至15场作低权填充，不硬删）
_PPG_TIME_DECAY = [2.0, 1.5, 1.2, 1.0, 0.8, 0.6, 0.45, 0.35, 0.25, 0.2, 0.15, 0.12, 0.1, 0.08, 0.06]

# 赛事含金量（降权不删除，避免样本被抽干）
_FRIENDLY_MARKERS = ("友谊", "友赛", "热身")
_CUP_MARKERS = ("杯", "杯赛")
# 欧战/洲际正式赛事：全权
_EURO_MARKERS = ("欧冠", "欧联", "欧协", "亚冠", "世俱", "俱乐部世界杯", "欧洲超级杯")


def _competition_form_weight(competition: Optional[str]) -> float:
    """正式赛1.0 / 杯赛0.7 / 友谊赛0.2。不识别则按联赛1.0。"""
    c = (competition or "").strip()
    if not c:
        return 1.0
    if any(k in c for k in _FRIENDLY_MARKERS):
        return 0.2
    if any(k in c for k in _EURO_MARKERS):
        return 1.0
    if any(k in c for k in _CUP_MARKERS):
        return 0.7
    return 1.0


def _build_role_cover_metrics(records: List[Dict], team: str) -> Dict[str, Any]:
    """按让球/受让角色分统赢盘率（带时间衰减）

    通过handicap字段判断该队在每场比赛中是让球方还是受让方：
    - 主队队名出现在match前半且handicap为负值 → 主队让球
    - 以此推断本队在每场中的角色
    """
    as_upper_win = as_upper_lose = 0.0  # 作为让球方的加权赢/输
    as_lower_win = as_lower_lose = 0.0  # 作为受让方的加权赢/输

    for i, r in enumerate(records):
        decay = _TIME_DECAY[i] if i < len(_TIME_DECAY) else 0.5
        # 友谊赛盘路噪声大，大幅降权（多数本就无盘会被跳过）
        decay *= _competition_form_weight(r.get("competition"))
        if decay < 0.05:
            continue
        ar = (r.get("asianResult") or "").strip()
        if ar not in ("赢", "赢半", "输", "输半"):
            continue

        is_win = ar in ("赢", "赢半")
        hcap_str = r.get("handicap", "")
        if not hcap_str:
            continue
        try:
            hcap_val = float(hcap_str)
        except (ValueError, TypeError):
            continue

        is_home = _team_in_match(team, r.get("match", ""))
        if is_home is None:
            continue

        # 500.com近期战绩的handicap: 负值=该行主队让球, 正值=该行客队让球
        # 本队是主队且handicap<0 → 本队让球(上盘)
        # 本队是主队且handicap>0 → 客队让球, 本队受让(下盘)
        # 本队是客队且handicap>0 → 本队让球(上盘)
        # 本队是客队且handicap<0 → 主队让球, 本队受让(下盘)
        if is_home:
            team_is_upper = hcap_val < 0
        else:
            team_is_upper = hcap_val > 0

        if team_is_upper:
            if is_win:
                as_upper_win += decay
            else:
                as_upper_lose += decay
        else:
            if is_win:
                as_lower_win += decay
            else:
                as_lower_lose += decay

    as_upper_total = as_upper_win + as_upper_lose
    as_lower_total = as_lower_win + as_lower_lose

    return {
        "as_upper_cover_rate": as_upper_win / as_upper_total if as_upper_total > 0.5 else None,
        "as_upper_sample": as_upper_total,
        "as_lower_cover_rate": as_lower_win / as_lower_total if as_lower_total > 0.5 else None,
        "as_lower_sample": as_lower_total,
    }


def _weighted_ppg(records: List[Dict], team: str,
                  home_only: Optional[bool] = None) -> Dict[str, Any]:
    """带时间衰减 + 赛事降权的场均积分。

    不硬删场次：友谊赛/无盘场降权后仍可填充样本。
    home_only 非空时为「主客场匹配」模式：无盘降权更轻、有效权重门槛更低
    （场地切片本身样本更少，联赛无盘仍有主客信息量）。

    Returns:
        {ppg, weight, n, friendly_share}
        ppg 为 None 表示有效权重不足。
    """
    venue_mode = home_only is not None
    min_weight = 0.9 if venue_mode else 2.0
    total_pts = 0.0
    total_weight = 0.0
    friendly_weight = 0.0
    n = 0

    for i, r in enumerate(records):
        if home_only is not None:
            is_home = _team_in_match(team, r.get("match", ""))
            if is_home is None:
                continue
            if home_only and not is_home:
                continue
            if not home_only and is_home:
                continue

        decay = _PPG_TIME_DECAY[i] if i < len(_PPG_TIME_DECAY) else 0.05
        comp_w = _competition_form_weight(r.get("competition"))
        # 无亚盘场：综合状态降权更多；主客切片保留更多联赛信息
        hcap = (r.get("handicap") or "").strip()
        if hcap not in ("", "-"):
            ah_w = 1.0
        else:
            ah_w = 0.75 if venue_mode else 0.5
        w = decay * comp_w * ah_w
        if w < 0.01:
            continue

        res = (r.get("result") or "").strip()
        if res not in ("胜", "平", "负"):
            continue
        pts = 3 if res == "胜" else 1 if res == "平" else 0
        total_pts += pts * w
        total_weight += w
        n += 1
        if comp_w <= 0.25:
            friendly_weight += w

    ppg = total_pts / total_weight if total_weight >= min_weight else None
    friendly_share = (friendly_weight / total_weight) if total_weight > 0 else 0.0
    return {
        "ppg": round(ppg, 2) if ppg is not None else None,
        "weight": round(total_weight, 2),
        "n": n,
        "friendly_share": round(friendly_share, 2),
    }


def _ppg_direction(upper: Dict[str, Any], lower: Dict[str, Any],
                   *, venue_mode: bool = False) -> Tuple[str, str]:
    """根据两边加权PPG与有效样本量给出方向 + 文案。"""
    u_ppg, l_ppg = upper.get("ppg"), lower.get("ppg")
    u_w, l_w = float(upper.get("weight") or 0), float(lower.get("weight") or 0)
    min_need = 0.9 if venue_mode else 2.0

    if u_ppg is None or l_ppg is None:
        return "neutral", (
            f"有效样本不足(上盘权{u_w:.1f}/下盘权{l_w:.1f}，需≥{min_need:g})"
        )

    diff = u_ppg - l_ppg
    min_w = min(u_w, l_w)
    # 两边有效权重严重不对称且偏少 → 不硬比
    # 主客切片天然更稀，不对称阈值更松；极大分差仍可出方向
    asym_floor = 1.5 if venue_mode else 4.0
    asym_ratio = 3.5 if venue_mode else 2.5
    if min_w < asym_floor and max(u_w, l_w) >= min_w * asym_ratio:
        if venue_mode and abs(diff) >= 0.8:
            pass  # 场地分差极大，不对称也认
        else:
            return "neutral", (
                f"上盘方{u_ppg:.2f}(权{u_w:.1f}) vs 下盘方{l_ppg:.2f}(权{l_w:.1f})，"
                f"样本不对称"
            )

    # 有效样本越弱，阈值越大
    if min_w >= 5.0:
        thr = 0.30
    elif min_w >= 3.0:
        thr = 0.40
    else:
        thr = 0.50

    fri_hint = ""
    u_fs, l_fs = upper.get("friendly_share") or 0, lower.get("friendly_share") or 0
    if u_fs >= 0.25 or l_fs >= 0.25:
        fri_hint = f"，友谊赛占比上{u_fs:.0%}/下{l_fs:.0%}"

    desc = f"上盘方{u_ppg:.2f}(权{u_w:.1f}) vs 下盘方{l_ppg:.2f}(权{l_w:.1f}){fri_hint}"
    if diff >= thr:
        return "upper", desc
    if diff <= -thr:
        return "lower", desc
    return "neutral", desc


def _resolve_side_aliases(sporttery_name: str, page_name: Optional[str],
                          records: List[Dict],
                          extra_aliases: Optional[List[str]] = None) -> List[str]:
    """竞彩名 + 500页面名 + 页面/DB别名 + 战绩自推断 → 匹配别名列表。"""
    inferred = None
    # 已有页面名或显式别名时不必再推断
    if not page_name and not extra_aliases:
        inferred = _infer_self_name_from_records(records)
    return _team_aliases(sporttery_name, page_name, inferred, extra_aliases or [])


def calc_factor1(match_data: Optional[Dict], match_info: Dict,
                 ai_f1_list: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """F1 近期状态：3个量化子因素 + 1个AI子因素(3次投票取多数)

    子因素:
      1. 加权场均分对比（带时间衰减）
      2. 角色匹配赢盘率（让球方/受让方分统）
      3. 主客场身份匹配场均分
      4. AI综合判断（3次调用取多数，不一致则舍弃）

    方向由多数决定，score由一致性程度决定。
    返回包含details字段展示各子因素细节。
    """
    handicap = match_info.get("handicap")
    is_home_let = handicap is not None and float(handicap) < 0
    home = match_info.get("home_team", "主队")
    away = match_info.get("away_team", "客队")

    if not match_data:
        return {"name": "近期状态", "score": 5, "direction": "neutral",
                "reason": "无基本面数据", "details": []}

    home_recent = match_data.get("homeRecent", [])[:15]
    away_recent = match_data.get("awayRecent", [])[:15]

    if not home_recent and not away_recent:
        return {"name": "近期状态", "score": 5, "direction": "neutral",
                "reason": "无近期战绩数据", "details": []}

    # 500.com 近期明细用页面队名/team_id 别名；竞彩名可能不同(如阿拉木图≠凯拉特)
    home_aliases = _resolve_side_aliases(
        home, match_data.get("homeTeamName"), home_recent,
        extra_aliases=match_data.get("homeTeamAliases"))
    away_aliases = _resolve_side_aliases(
        away, match_data.get("awayTeamName"), away_recent,
        extra_aliases=match_data.get("awayTeamAliases"))

    upper_aliases = home_aliases if is_home_let else away_aliases
    lower_aliases = away_aliases if is_home_let else home_aliases
    upper_recent = home_recent if is_home_let else away_recent
    lower_recent = away_recent if is_home_let else home_recent

    details = []

    # --- 子因素1: 加权场均分对比（赛事降权+陡衰减+样本量门槛） ---
    upper_ppg_m = _weighted_ppg(upper_recent, upper_aliases)
    lower_ppg_m = _weighted_ppg(lower_recent, lower_aliases)
    sub1_dir, sub1_desc = _ppg_direction(upper_ppg_m, lower_ppg_m)
    details.append({"name": "加权场均分", "direction": sub1_dir, "desc": sub1_desc})

    # --- 子因素2: 角色匹配赢盘率 ---
    sub2_dir = "neutral"
    upper_role = _build_role_cover_metrics(upper_recent, upper_aliases)
    lower_role = _build_role_cover_metrics(lower_recent, lower_aliases)
    upper_cover = upper_role["as_upper_cover_rate"]
    lower_cover = lower_role["as_lower_cover_rate"]
    u_sample = upper_role["as_upper_sample"]
    l_sample = lower_role["as_lower_sample"]
    if u_sample < 2.0:
        upper_cover = None
    if l_sample < 2.0:
        lower_cover = None

    sub2_desc_parts = []
    if upper_cover is not None:
        sub2_desc_parts.append(f"上盘让球赢盘率{upper_cover:.0%}(权{u_sample:.1f})")
    if lower_cover is not None:
        sub2_desc_parts.append(f"下盘受让赢盘率{lower_cover:.0%}(权{l_sample:.1f})")
    if sub2_desc_parts:
        sub2_desc = "，".join(sub2_desc_parts)
    else:
        sub2_desc = (f"样本不足(上盘角色权{u_sample:.1f}/"
                     f"下盘角色权{l_sample:.1f}，需≥2)")

    if upper_cover is not None and lower_cover is not None:
        cover_diff = upper_cover - lower_cover
        if cover_diff >= 0.15:
            sub2_dir = "upper"
        elif cover_diff <= -0.15:
            sub2_dir = "lower"
        elif upper_cover >= 0.55:
            sub2_dir = "upper"
        elif lower_cover >= 0.55:
            sub2_dir = "lower"
        elif upper_cover <= 0.35:
            sub2_dir = "lower"
        elif lower_cover <= 0.35:
            sub2_dir = "upper"
    elif upper_cover is not None:
        if upper_cover >= 0.55:
            sub2_dir = "upper"
        elif upper_cover <= 0.4:
            sub2_dir = "lower"
    elif lower_cover is not None:
        if lower_cover >= 0.55:
            sub2_dir = "lower"
        elif lower_cover <= 0.4:
            sub2_dir = "upper"
    details.append({"name": "角色赢盘率", "direction": sub2_dir, "desc": sub2_desc})

    # --- 子因素3: 主客场身份匹配（同套降权PPG） ---
    sub3_dir = "neutral"
    upper_is_home = is_home_let
    upper_matched = _weighted_ppg(upper_recent, upper_aliases, home_only=upper_is_home)
    lower_matched = _weighted_ppg(lower_recent, lower_aliases, home_only=not upper_is_home)
    u_label = "主场" if upper_is_home else "客场"
    l_label = "客场" if upper_is_home else "主场"
    sub3_dir, sub3_raw = _ppg_direction(upper_matched, lower_matched, venue_mode=True)
    if upper_matched.get("ppg") is not None and lower_matched.get("ppg") is not None:
        sub3_desc = (
            f"上盘{u_label}{upper_matched['ppg']:.2f}(权{upper_matched['weight']:.1f}) vs "
            f"下盘{l_label}{lower_matched['ppg']:.2f}(权{lower_matched['weight']:.1f})"
        )
        if "样本不对称" in sub3_raw or "有效样本不足" in sub3_raw:
            sub3_dir = "neutral"
            if "有效样本不足" in sub3_raw:
                sub3_desc = (
                    f"主客场样本不足(上盘{u_label}权{upper_matched['weight']:.1f}/"
                    f"下盘{l_label}权{lower_matched['weight']:.1f})"
                )
            elif "样本不对称" in sub3_raw:
                sub3_desc += "，样本不对称"
    else:
        sub3_desc = (
            f"主客场样本不足(上盘{u_label}权{upper_matched['weight']:.1f}/"
            f"下盘{l_label}权{lower_matched['weight']:.1f})"
        )
        sub3_dir = "neutral"
    details.append({"name": "主客场匹配", "direction": sub3_dir, "desc": sub3_desc})

    # --- 子因素4: AI判断（3次取多数） ---
    sub4_dir = "neutral"
    sub4_desc = ""
    if ai_f1_list:
        ai_dirs = [f.get("direction", "neutral") for f in ai_f1_list if f]
        ai_upper = ai_dirs.count("upper")
        ai_lower = ai_dirs.count("lower")
        ai_reasons = [f.get("reason", "") for f in ai_f1_list if f]

        if ai_upper >= 2:
            sub4_dir = "upper"
            sub4_desc = f"3次AI: {ai_upper}次上盘/{ai_lower}次下盘"
        elif ai_lower >= 2:
            sub4_dir = "lower"
            sub4_desc = f"3次AI: {ai_upper}次上盘/{ai_lower}次下盘"
        else:
            sub4_dir = "neutral"
            sub4_desc = f"AI不稳定({ai_upper}上/{ai_lower}下/{3-ai_upper-ai_lower}中性)，舍弃"

        if ai_reasons:
            sub4_desc += f"（{ai_reasons[0]}）"
    else:
        sub4_desc = "AI未调用"
    details.append({"name": "AI综合", "direction": sub4_dir, "desc": sub4_desc})

    # --- 投票汇总 ---
    votes = [sub1_dir, sub2_dir, sub3_dir, sub4_dir]
    upper_votes = votes.count("upper")
    lower_votes = votes.count("lower")

    if upper_votes > lower_votes:
        direction = "upper"
        majority = upper_votes
    elif lower_votes > upper_votes:
        direction = "lower"
        majority = lower_votes
    else:
        direction = "neutral"
        majority = 0

    if majority >= 4:
        score = 8
    elif majority == 3:
        score = 7
    else:
        score = 5

    # 构建reason(简短版)
    if direction == "neutral":
        upper_parts = []
        lower_parts = []
        for label, d in [("场均分", sub1_dir), ("赢盘率", sub2_dir), ("场地", sub3_dir), ("AI", sub4_dir)]:
            if d == "upper":
                upper_parts.append(label)
            elif d == "lower":
                lower_parts.append(label)
        if upper_parts and lower_parts:
            reason = f"方向分歧({'+'.join(upper_parts)}↑ vs {'+'.join(lower_parts)}↓)"
        else:
            reason = "近期状态无明确信号"
    else:
        reasons = []
        if sub1_dir != "neutral":
            reasons.append(f"场均分{'优' if sub1_dir == direction else '劣'}")
        if sub2_dir != "neutral":
            reasons.append(f"赢盘率{'优' if sub2_dir == direction else '劣'}")
        if sub3_dir != "neutral":
            tag = "主场" if (direction == "upper") == upper_is_home else "客场"
            reasons.append(f"{tag}{'强' if sub3_dir == direction else '弱'}")
        if sub4_dir != "neutral":
            reasons.append(f"AI{'同向' if sub4_dir == direction else '反向'}")
        reason = "，".join(reasons[:3]) if reasons else "近期状态偏向明确"

    return {"name": "近期状态", "score": score, "direction": direction,
            "reason": reason, "details": details}


# ============================================================
# F2 交锋历史 - 量化子因素：有效性/加权赢盘/盘口变化/AI辅助
# ============================================================

HOME_ADVANTAGE = 0.4

_H2H_TIME_WEIGHTS = [
    (180, 1.0),
    (365, 0.7),
    (730, 0.4),
]
_H2H_TIME_DEFAULT = 0.15


def _h2h_time_weight(date_str: str, today: str) -> float:
    """根据交锋日期距今天数返回时间衰减权重"""
    from datetime import datetime
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        t = datetime.strptime(today, "%Y-%m-%d")
    except (ValueError, TypeError):
        return _H2H_TIME_DEFAULT
    days = (t - d).days
    if days < 0:
        days = 0
    for threshold, weight in _H2H_TIME_WEIGHTS:
        if days <= threshold:
            return weight
    return _H2H_TIME_DEFAULT


def _parse_h2h_record(record: Dict, upper_team: str, lower_team: str,
                      current_handicap: float, today: str,
                      focus_is_upper: bool = False) -> Optional[Dict]:
    """解析单条H2H记录，提取标准化信息

    Args:
        focus_is_upper: 500.com页面主队(focus team)是否为上盘方。
            asianResult始终从focus team视角报告。

    Returns:
        {time_weight, is_win_upper, is_win_lower, is_push, ...}
        or None if record unusable
    """
    match_text = record.get("match", "")
    date = record.get("date", "")
    handicap_str = record.get("handicap", "")
    asian_result = (record.get("asianResult") or "").strip()

    if not match_text or not date:
        return None

    time_weight = _h2h_time_weight(date, today)

    # 判断当前上盘队在这条记录中的主客身份(用于盘口换算)
    upper_is_home = _team_in_match(upper_team, match_text)
    if upper_is_home is None:
        lower_is_home = _team_in_match(lower_team, match_text)
        if lower_is_home is None:
            return None
        upper_is_home = not lower_is_home

    # 赢盘结果：500.com的asianResult是从"当前比赛页面主队(focus team)"视角
    # 不是该条记录各自主队的视角
    is_focus_win = asian_result in ("赢", "赢半")
    is_focus_lose = asian_result in ("输", "输半")
    is_push = asian_result in ("走", "走盘", "走水")

    if focus_is_upper:
        is_win_upper = is_focus_win
        is_win_lower = is_focus_lose
    else:
        is_win_upper = is_focus_lose
        is_win_lower = is_focus_win

    # 盘口统一换算到上盘队视角的"纯实力差"（去除主场优势）
    # 目标：diff > 0 表示历史盘口反映出上盘更强于当前评估 → 当前盘口给少了 → 上盘实力下降
    # 500.com h2h的handicap: 正值=该条记录主队让球, 负值=主队受让(客队让)
    normalized_handicap_diff = None
    if handicap_str:
        try:
            h_val = float(handicap_str)
        except (ValueError, TypeError):
            h_val = None
        if h_val is not None:
            # 历史：h_val正=记录主队让球, 盘口 = 主队纯实力 + 主场优势
            # 上盘队纯实力差 = 上盘队让球数 - 主场优势(如果上盘是主) 或 + 主场优势(如果上盘是客)
            if upper_is_home:
                # 上盘是该记录主队 → 让球=h_val → 纯实力 = h_val - HOME_ADVANTAGE
                hist_upper_strength = h_val - HOME_ADVANTAGE
            else:
                # 上盘是该记录客队 → 主队让h_val意味着主队比客强
                # 上盘(客)纯实力 = -h_val + HOME_ADVANTAGE (客场补偿)
                # 即: 盘口反映主队让h_val,包含了上盘队的客场劣势
                hist_upper_strength = -h_val + HOME_ADVANTAGE

            # 当前上盘队纯实力差：上盘让|current_handicap|球
            # current_handicap < 0 → 主队让球=主队是上盘, 让球数=|current_handicap|
            # 上盘是主场时: 纯实力 = 让球数 - HOME_ADVANTAGE
            # 上盘是客场时: 纯实力 = 让球数 + HOME_ADVANTAGE
            is_upper_home_now = current_handicap < 0
            let_amount = abs(current_handicap)
            if is_upper_home_now:
                current_upper_strength = let_amount - HOME_ADVANTAGE
            else:
                current_upper_strength = let_amount + HOME_ADVANTAGE

            normalized_handicap_diff = hist_upper_strength - current_upper_strength

    return {
        "time_weight": time_weight,
        "is_win_upper": is_win_upper,
        "is_win_lower": is_win_lower,
        "is_push": is_push,
        "has_result": asian_result in ("赢", "赢半", "输", "输半", "走", "走盘", "走水"),
        "handicap_diff": normalized_handicap_diff,
    }


def calc_factor2(match_data: Optional[Dict], match_info: Dict,
                 ai_f2_list: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """F2 交锋历史：量化子因素投票 + AI辅助

    子因素:
      1. 有效性评估（场次×时间权重 → 决定score上限）
      2. 加权赢盘率（时间衰减加权的交锋盘路）
      3. 盘口变化分析（历史盘口vs当前盘口的实力差变化）
      4. AI辅助判断（3次调用取多数，不一致则舍弃）

    Returns:
        {"name": "交锋历史", "score": int, "direction": str, "reason": str, "details": [...]}
    """
    from datetime import date as date_type

    handicap = match_info.get("handicap")
    if handicap is None:
        return {"name": "交锋历史", "score": 5, "direction": "neutral",
                "reason": "无盘口数据", "details": []}

    current_handicap = float(handicap)
    is_home_let = current_handicap < 0
    home = match_info.get("home_team", "主队")
    away = match_info.get("away_team", "客队")

    if not match_data:
        return {"name": "交锋历史", "score": 5, "direction": "neutral",
                "reason": "无基本面数据", "details": []}

    h2h = match_data.get("h2h", [])
    if not h2h:
        return {"name": "交锋历史", "score": 5, "direction": "neutral",
                "reason": "无交锋记录", "details": []}

    home_aliases = _resolve_side_aliases(
        home, match_data.get("homeTeamName"), match_data.get("homeRecent") or [],
        extra_aliases=match_data.get("homeTeamAliases"))
    away_aliases = _resolve_side_aliases(
        away, match_data.get("awayTeamName"), match_data.get("awayRecent") or [],
        extra_aliases=match_data.get("awayTeamAliases"))
    upper_team = home_aliases if is_home_let else away_aliases
    lower_team = away_aliases if is_home_let else home_aliases

    today = date_type.today().strftime("%Y-%m-%d")
    match_date = match_info.get("match_date", "")

    # 过滤掉当前比赛本身(500.com h2h会包含本场,日期可能差1天)
    if match_date:
        from datetime import datetime, timedelta
        try:
            md = datetime.strptime(match_date, "%Y-%m-%d")
            exclude_start = (md - timedelta(days=1)).strftime("%Y-%m-%d")
            exclude_end = (md + timedelta(days=1)).strftime("%Y-%m-%d")
            h2h = [r for r in h2h if not (exclude_start <= r.get("date", "") <= exclude_end)]
        except (ValueError, TypeError):
            h2h = [r for r in h2h if r.get("date", "") != match_date]
    elif h2h:
        first_date = h2h[0].get("date", "")
        if first_date >= today:
            h2h = h2h[1:]

    if not h2h:
        return {"name": "交锋历史", "score": 5, "direction": "neutral",
                "reason": "无历史交锋记录", "details": []}

    # 解析所有H2H记录
    # 500.com h2h的asianResult始终从页面主队(home_team)视角报告
    focus_is_upper = is_home_let  # 主队让球=主队是上盘
    parsed = []
    for r in h2h:
        p = _parse_h2h_record(r, upper_team, lower_team, current_handicap, today, focus_is_upper)
        if p:
            parsed.append(p)

    if not parsed:
        return {"name": "交锋历史", "score": 5, "direction": "neutral",
                "reason": "交锋记录无法解析", "details": []}

    details = []

    # --- 子因素1: 有效性评估 ---
    effective_weight = sum(p["time_weight"] for p in parsed)
    total_count = len(parsed)
    recent_count = sum(1 for p in parsed if p["time_weight"] >= 0.7)

    if effective_weight < 0.5:
        sub1_level = "invalid"
        sub1_desc = f"{total_count}场交锋但加权有效值{effective_weight:.1f}(过低)"
    elif effective_weight < 1.0:
        sub1_level = "low"
        sub1_desc = f"{total_count}场(近期{recent_count}场)，有效值{effective_weight:.1f}"
    elif effective_weight < 2.0:
        sub1_level = "medium"
        sub1_desc = f"{total_count}场(近期{recent_count}场)，有效值{effective_weight:.1f}"
    else:
        sub1_level = "high"
        sub1_desc = f"{total_count}场(近期{recent_count}场)，有效值{effective_weight:.1f}"
    details.append({"name": "有效性", "direction": "neutral", "desc": sub1_desc})

    if sub1_level == "invalid":
        return {"name": "交锋历史", "score": 5, "direction": "neutral",
                "reason": f"交锋{total_count}场但时间久远，无参考价值", "details": details}

    score_cap = {"low": 6, "medium": 8, "high": 10}[sub1_level]

    # --- 子因素2: 加权赢盘率 ---
    sub2_dir = "neutral"
    upper_cover_w = 0.0
    lower_cover_w = 0.0
    total_cover_w = 0.0

    for p in parsed:
        if not p["has_result"]:
            continue
        if p["is_push"]:
            continue
        w = p["time_weight"]
        if p["is_win_upper"]:
            upper_cover_w += w
        elif p["is_win_lower"]:
            lower_cover_w += w
        total_cover_w += w

    if total_cover_w > 0.5:
        upper_rate = upper_cover_w / total_cover_w
        lower_rate = lower_cover_w / total_cover_w
        sub2_desc = f"上盘赢盘{upper_rate:.0%} vs 下盘赢盘{lower_rate:.0%}(加权)"
        if upper_rate >= 0.65:
            sub2_dir = "upper"
        elif lower_rate >= 0.65:
            sub2_dir = "lower"
        elif upper_rate >= 0.55:
            sub2_dir = "upper"
        elif lower_rate >= 0.55:
            sub2_dir = "lower"
    else:
        sub2_desc = "有结果的交锋样本不足"
    details.append({"name": "加权赢盘率", "direction": sub2_dir, "desc": sub2_desc})

    # --- 子因素3: 盘口变化分析 ---
    sub3_dir = "neutral"
    diffs_with_weight = [(p["handicap_diff"], p["time_weight"])
                         for p in parsed if p["handicap_diff"] is not None]

    if diffs_with_weight:
        total_w = sum(w for _, w in diffs_with_weight)
        avg_diff = sum(d * w for d, w in diffs_with_weight) / total_w if total_w > 0 else 0

        # avg_diff > 0: 历史上上盘队实力差比现在大 → 上盘队实力在下降 → 偏下盘
        # avg_diff < 0: 历史上上盘队实力差比现在小 → 上盘队实力在上升 → 偏上盘
        if avg_diff >= 0.5:
            sub3_dir = "lower"
            sub3_desc = f"盘口缩小{avg_diff:.2f}球(上盘实力下降趋势)"
        elif avg_diff >= 0.25:
            sub3_dir = "lower"
            sub3_desc = f"盘口略缩{avg_diff:.2f}球(上盘略弱于历史)"
        elif avg_diff <= -0.5:
            sub3_dir = "upper"
            sub3_desc = f"盘口加深{-avg_diff:.2f}球(上盘实力上升趋势)"
        elif avg_diff <= -0.25:
            sub3_dir = "upper"
            sub3_desc = f"盘口略深{-avg_diff:.2f}球(上盘略强于历史)"
        else:
            sub3_desc = f"盘口变化{avg_diff:+.2f}球(格局稳定)"
    else:
        sub3_desc = "历史盘口数据不足"
    details.append({"name": "盘口变化", "direction": sub3_dir, "desc": sub3_desc})

    # --- 子因素4: AI辅助（3次取多数） ---
    sub4_dir = "neutral"
    if ai_f2_list:
        ai_dirs = [f.get("direction", "neutral") for f in ai_f2_list if f]
        ai_upper = ai_dirs.count("upper")
        ai_lower = ai_dirs.count("lower")
        ai_reasons = [f.get("reason", "") for f in ai_f2_list if f]

        if ai_upper >= 2:
            sub4_dir = "upper"
            sub4_desc = f"3次AI: {ai_upper}次上盘/{ai_lower}次下盘"
        elif ai_lower >= 2:
            sub4_dir = "lower"
            sub4_desc = f"3次AI: {ai_upper}次上盘/{ai_lower}次下盘"
        else:
            sub4_desc = f"AI不一致({ai_upper}上/{ai_lower}下/{len(ai_dirs)-ai_upper-ai_lower}中)，舍弃"

        if ai_reasons:
            sub4_desc += f"（{ai_reasons[0]}）"
    else:
        sub4_desc = "AI未调用"
    details.append({"name": "AI辅助", "direction": sub4_dir, "desc": sub4_desc})

    # --- 投票汇总 ---
    votes = [sub2_dir, sub3_dir, sub4_dir]
    upper_votes = votes.count("upper")
    lower_votes = votes.count("lower")

    if upper_votes > lower_votes:
        direction = "upper"
        majority = upper_votes
    elif lower_votes > upper_votes:
        direction = "lower"
        majority = lower_votes
    else:
        direction = "neutral"
        majority = 0

    if majority >= 3:
        score = 8
    elif majority == 2:
        score = 7
    else:
        score = 5

    score = min(score, score_cap)

    # 构建reason
    if direction == "neutral":
        parts_u = [n for n, d in [("赢盘", sub2_dir), ("盘口", sub3_dir), ("AI", sub4_dir)] if d == "upper"]
        parts_l = [n for n, d in [("赢盘", sub2_dir), ("盘口", sub3_dir), ("AI", sub4_dir)] if d == "lower"]
        if parts_u and parts_l:
            reason = f"方向分歧({'+'.join(parts_u)}↑ vs {'+'.join(parts_l)}↓)"
        else:
            reason = "交锋历史无明确信号"
    else:
        reasons = []
        if sub2_dir == direction:
            reasons.append(f"赢盘率偏{'上' if direction == 'upper' else '下'}")
        if sub3_dir == direction:
            reasons.append("盘口趋势支撑")
        if sub4_dir == direction:
            reasons.append("AI同向")
        reason = "，".join(reasons[:3]) if reasons else "交锋历史偏向明确"

    return {"name": "交锋历史", "score": score, "direction": direction,
            "reason": reason, "details": details}


# ============================================================
# F3 实力定位 - 排名对比(量化) + AI底蕴判断(3次投票) + 身价展示
# ============================================================


def parse_league_rank(raw: Any) -> Optional[int]:
    """解析联赛排名: 19 / '19' / '[巴甲19]' → 19；'[欧冠]' / 空 → None。"""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    s = str(raw).strip()
    if not s or s in ("0", "-", "None", "null"):
        return None
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def _rank_label(raw: Any, parsed: Optional[int]) -> str:
    """排名展示文案辅助。"""
    if parsed is not None:
        return f"第{parsed}"
    s = str(raw).strip() if raw not in (None, "") else ""
    if s and "[" in s and not re.search(r"\d", s):
        return "无联赛排名(杯赛)"
    return "无排名"


def calc_factor3(match_info: Dict, ai_f3_list: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """F3 实力定位: 排名对比(量化) + AI底蕴判断(3次投票)

    核心逻辑：大众第一印象谁更强（不考虑盘口深浅）
    子因素:
      1. 排名对比: 上盘方排名是否明显优于下盘方(计入方向)
      2. AI底蕴判断: 3次调用取多数投票(计入方向)
      3. 身价对比: 仅展示/喂AI，不参与方向合成(避免与让球方向系统性同向)
    """
    details = []
    handicap = match_info.get("handicap")
    is_home_let = handicap is not None and float(handicap) < 0

    home_rank_raw = match_info.get("home_rank")
    away_rank_raw = match_info.get("away_rank")
    home_rank = parse_league_rank(home_rank_raw)
    away_rank = parse_league_rank(away_rank_raw)

    # --- 子因素1: 排名对比 ---
    sub1_dir = "neutral"
    sub1_desc = "无排名数据"

    if home_rank is not None and away_rank is not None:
        upper_rank = home_rank if is_home_let else away_rank
        lower_rank = away_rank if is_home_let else home_rank
        rank_diff = lower_rank - upper_rank  # 正值=上盘方排名靠前(数字小)

        if rank_diff >= 10:
            sub1_dir = "upper"
            sub1_desc = f"上盘方排名第{upper_rank}，下盘方第{lower_rank}，实力差距大"
        elif rank_diff >= 5:
            sub1_dir = "upper"
            sub1_desc = f"上盘方排名第{upper_rank}，下盘方第{lower_rank}，上盘方实力占优"
        elif rank_diff >= 2:
            sub1_desc = f"上盘方排名第{upper_rank}，下盘方第{lower_rank}，实力接近"
        elif rank_diff >= 0:
            sub1_desc = f"双方排名接近(第{upper_rank} vs 第{lower_rank})"
        else:
            sub1_dir = "lower"
            sub1_desc = f"下盘方排名({lower_rank})反而高于上盘方({upper_rank})，下盘实力更强"
    else:
        home_lab = _rank_label(home_rank_raw, home_rank)
        away_lab = _rank_label(away_rank_raw, away_rank)
        league = str(match_info.get("league") or "")
        cup_leagues = ("欧冠", "欧联", "欧协联", "足总杯", "联赛杯", "国王杯", "德国杯", "意大利杯", "法国杯", "世界杯", "亚洲杯", "美洲杯")
        raw_cup = (
            (home_rank_raw and "[" in str(home_rank_raw) and not re.search(r"\d", str(home_rank_raw)))
            or (away_rank_raw and "[" in str(away_rank_raw) and not re.search(r"\d", str(away_rank_raw)))
        )
        if raw_cup or any(k in league for k in cup_leagues):
            sub1_desc = f"杯赛/无联赛排名(主{home_lab} 客{away_lab})"
        elif home_rank is not None or away_rank is not None:
            sub1_desc = f"排名不全(主{_rank_label(home_rank_raw, home_rank)} 客{_rank_label(away_rank_raw, away_rank)})"
        else:
            sub1_desc = "无排名数据"
    details.append({"name": "排名对比", "direction": sub1_dir, "desc": sub1_desc})

    # --- 子因素2: AI底蕴判断（3次投票取多数） ---
    sub2_dir = "neutral"
    sub2_desc = "AI未返回结果"

    if ai_f3_list:
        ai_dirs = [f.get("direction", "neutral") for f in ai_f3_list if f]
        ai_upper = ai_dirs.count("upper")
        ai_lower = ai_dirs.count("lower")
        ai_reasons = [f.get("reason", "") for f in ai_f3_list if f]

        if ai_upper >= 2:
            sub2_dir = "upper"
            reason_text = next((r for r in ai_reasons if r), "上盘底蕴占优")
            sub2_desc = f"3次AI判断{ai_upper}次看上盘: {reason_text}"
        elif ai_lower >= 2:
            sub2_dir = "lower"
            reason_text = next((r for r in ai_reasons if r), "盘口高估上盘")
            sub2_desc = f"3次AI判断{ai_lower}次看下盘: {reason_text}"
        else:
            ai_neutral = ai_dirs.count("neutral")
            sub2_desc = f"AI判断无共识(上{ai_upper}/下{ai_lower}/中{ai_neutral})，无明确底蕴偏向"
    details.append({"name": "AI底蕴判断", "direction": sub2_dir, "desc": sub2_desc})

    # --- 子因素3: 身价对比(仅展示，不计入方向投票) ---
    worth = match_info.get("squad_worth") or {}
    hw = worth.get("home_worth")
    aw = worth.get("away_worth")
    if hw is not None and aw is not None and hw > 0 and aw > 0:
        ratio = worth.get("ratio") or ""
        ht = worth.get("home_worth_text") or f"€{hw:g}万"
        at = worth.get("away_worth_text") or f"€{aw:g}万"
        if hw > aw * 1.15:
            cmp = "主队身价更高"
        elif aw > hw * 1.15:
            cmp = "客队身价更高"
        else:
            cmp = "双方身价接近"
        ratio_part = f"，比{ratio}" if ratio else ""
        sub3_desc = f"主队{ht} vs 客队{at}{ratio_part}（{cmp}）"
    else:
        sub3_desc = "无身价数据"
    # direction 固定 neutral：不参与下方 upper_signals/lower_signals
    details.append({"name": "身价对比", "direction": "neutral", "desc": sub3_desc})

    # --- 综合结论(仅排名+AI，身价不投票) ---
    vote_details = [d for d in details if d["name"] != "身价对比"]
    upper_signals = sum(1 for d in vote_details if d["direction"] == "upper")
    lower_signals = sum(1 for d in vote_details if d["direction"] == "lower")

    # 排名+AI两个子因素都一致时才输出方向，避免单一AI判断产生系统性偏移
    both_agree = (upper_signals == 2 or lower_signals == 2)

    if upper_signals > lower_signals:
        reason = "上盘方实力底蕴占优"
        if both_agree:
            return {"name": "实力定位", "score": 7, "direction": "upper",
                    "reason": reason, "details": details}
        else:
            return {"name": "实力定位", "score": 6, "direction": "upper",
                    "reason": reason + "(仅AI判断)", "details": details}
    elif lower_signals > upper_signals:
        reason = "下盘方实力底蕴占优"
        if both_agree:
            return {"name": "实力定位", "score": 7, "direction": "lower",
                    "reason": reason, "details": details}
        else:
            return {"name": "实力定位", "score": 6, "direction": "lower",
                    "reason": reason + "(仅AI判断)", "details": details}
    else:
        return {"name": "实力定位", "score": 5, "direction": "neutral",
                "reason": "双方实力定位接近", "details": details}


# ============================================================
# 近期状态量化指标 - 代码算客观数据，喂给 AI 推理(F1/F2)
# ============================================================

def _team_aliases(*names) -> List[str]:
    """去重队名别名,长名优先(避免短名误匹配)。接受 str / 可迭代。"""
    out: List[str] = []
    for n in names:
        if n is None:
            continue
        if isinstance(n, (list, tuple, set)):
            for x in n:
                s = str(x).strip() if x is not None else ""
                if s and s not in out:
                    out.append(s)
            continue
        s = str(n).strip()
        if s and s not in out:
            out.append(s)
    return sorted(out, key=len, reverse=True)


def _any_alias_in(aliases: List[str], text: str) -> bool:
    for a in aliases:
        if a and a in text:
            return True
    return False


def _infer_self_name_from_records(records: List[Dict]) -> Optional[str]:
    """从近期战绩推断本队500队名:几乎每场都出现的那一侧队名。"""
    if not records:
        return None
    from collections import Counter
    import re
    counter: Counter = Counter()
    usable = 0
    for r in records[:15]:
        mt = (r.get("match") or "").strip()
        m = re.search(r"\d+:\d+", mt)
        if not m:
            continue
        home = mt[:m.start()].strip()
        away = mt[m.end():].strip()
        # 去掉残留空格/方括号尾巴
        home = re.sub(r"\[\d+\]", "", home).strip()
        away = re.sub(r"\[\d+\]", "", away).strip()
        if home:
            counter[home] += 1
        if away:
            counter[away] += 1
        usable += 1
    if not counter or usable < 2:
        return None
    best, cnt = counter.most_common(1)[0]
    # 本队应约等于 usable 次(每场出现一次)
    if cnt >= max(2, (usable + 1) // 2):
        return best
    return None


def _team_in_match(team, match_text: str) -> Optional[bool]:
    """判断本队在该场是主队还是客队。match格式: '主队比分:比分客队'
    team 可为单名或别名列表(竞彩名/500名)。
    返回 True=主场, False=客场, None=无法判断(未命中任何别名时绝不能猜成客场)
    """
    aliases = _team_aliases(team)
    if not aliases or not match_text:
        return None
    import re
    m = re.search(r"\d+:\d+", match_text)
    if not m:
        # 退化：看最长别名在文本前半还是后半
        for a in aliases:
            idx = match_text.find(a)
            if idx >= 0:
                return idx < len(match_text) / 2
        return None
    before = match_text[:m.start()]
    after = match_text[m.end():]
    in_home = _any_alias_in(aliases, before)
    in_away = _any_alias_in(aliases, after)
    if in_home and not in_away:
        return True
    if in_away and not in_home:
        return False
    return None


def build_form_metrics(records: List[Dict], team) -> Dict[str, Any]:
    """统计近期状态客观指标(供AI推理)

    team: 单名或别名列表(竞彩名+500.com名)。
    Returns: 含积分/场均分/胜平负/不败/主客场拆分/赢盘率/样本量
    """
    win = draw = lose = 0
    points = 0
    cover_win = cover_lose = cover_push = 0
    home_points = home_games = 0
    away_points = away_games = 0
    # 计算最近不败连续场次(从最新一场往前)
    unbeaten_streak = 0
    streak_broken = False
    unknown_side = 0

    for i, r in enumerate(records):
        res = (r.get("result") or "").strip()
        pts = 3 if res == "胜" else 1 if res == "平" else 0
        if res == "胜":
            win += 1
        elif res == "平":
            draw += 1
        elif res == "负":
            lose += 1
        points += pts

        # 不败连续(最新场在列表前部)
        if not streak_broken:
            if res in ("胜", "平"):
                unbeaten_streak += 1
            elif res == "负":
                streak_broken = True

        # 主客场拆分
        is_home = _team_in_match(team, r.get("match", ""))
        if is_home is True:
            home_points += pts
            home_games += 1
        elif is_home is False:
            away_points += pts
            away_games += 1
        else:
            unknown_side += 1

        # 赢盘统计
        ar = (r.get("asianResult") or "").strip()
        if ar in ("赢", "赢半"):
            cover_win += 1
        elif ar in ("输", "输半"):
            cover_lose += 1
        elif ar in ("走", "走盘", "走水"):
            cover_push += 1

    total = len(records)
    cover_decided = cover_win + cover_lose
    return {
        "total": total,
        "win": win, "draw": draw, "lose": lose,
        "points": points,
        "ppg": round(points / total, 2) if total else None,  # 场均积分
        "unbeaten_streak": unbeaten_streak,
        "home_ppg": round(home_points / home_games, 2) if home_games else None,
        "away_ppg": round(away_points / away_games, 2) if away_games else None,
        "home_games": home_games,
        "away_games": away_games,
        "unknown_side": unknown_side,
        "cover_win": cover_win, "cover_lose": cover_lose, "cover_push": cover_push,
        "cover_decided": cover_decided,
        "cover_rate": round(cover_win / cover_decided, 2) if cover_decided else None,
    }


def _avg_abs_handicap(records: List[Dict]) -> Optional[float]:
    """近期被开出的平均盘口绝对值(反映市场对该队的实力定价深度)"""
    vals = []
    for r in records:
        h = r.get("handicap")
        if h in (None, ""):
            continue
        try:
            vals.append(abs(float(h)))
        except (ValueError, TypeError):
            continue
    return sum(vals) / len(vals) if vals else None


def _format_form_metrics(metrics: Dict[str, Any], team_label: str) -> str:
    """把量化指标格式化成 prompt 文本"""
    lines = [f"  {team_label}:"]
    lines.append(f"    近{metrics['total']}场战绩: {metrics['win']}胜{metrics['draw']}平{metrics['lose']}负，"
                 f"场均{metrics['ppg']}分，最近{metrics['unbeaten_streak']}场不败")
    parts = []
    if metrics["home_ppg"] is not None:
        parts.append(f"主场场均{metrics['home_ppg']}分")
    if metrics["away_ppg"] is not None:
        parts.append(f"客场场均{metrics['away_ppg']}分")
    if parts:
        lines.append("    " + "，".join(parts))
    if metrics["cover_decided"] > 0:
        lines.append(f"    亚盘赢盘记录: {metrics['cover_win']}赢{metrics['cover_lose']}输"
                     f"{metrics['cover_push']}走(赢盘率{metrics['cover_rate']}，仅{metrics['cover_decided']}场有盘口样本)")
    else:
        lines.append(f"    亚盘赢盘记录: 近期缺少盘口样本，赢盘率不可靠")
    return "\n".join(lines)


# ============================================================
# F6 单关修正 - 规则计算
# ============================================================

def calc_factor6(is_single: bool, f5_direction: str, f5_score: int) -> Dict[str, Any]:
    """F6: 单关放大修正

    市场热度direction表示哪边热(upper=上盘热)，单关场次放大该热度信号。
    direction跟随市场热度(表示哪边热)，calc_prediction中统一逆向处理。
    """
    if not is_single:
        return {"name": "单关修正", "score": 5, "direction": "neutral", "reason": "非单关，不触发"}

    if f5_direction == "upper" and f5_score >= 7:
        return {"name": "单关修正", "score": 8, "direction": "upper",
                "reason": "单关+上盘过热"}
    elif f5_direction == "lower" and f5_score >= 7:
        return {"name": "单关修正", "score": 8, "direction": "lower",
                "reason": "单关+下盘过热"}
    elif f5_direction == "upper" and f5_score >= 6:
        return {"name": "单关修正", "score": 6, "direction": "upper",
                "reason": "单关+上盘略热"}
    elif f5_direction == "lower" and f5_score >= 6:
        return {"name": "单关修正", "score": 6, "direction": "lower",
                "reason": "单关+下盘略热"}
    else:
        return {"name": "单关修正", "score": 5, "direction": "neutral",
                "reason": "单关但热度中性，不触发"}


# ============================================================
# F1/F2/F3 AI辅助 - DeepSeek 推理(代码喂量化指标)
# (F4市场信号、F5市场热度、F6单关 已纯量化计算)
# ============================================================

AI_FACTORS_PROMPT = """你是一个专业的足球亚洲盘口分析师。根据提供的比赛数据，从以下3个维度分析让球盘方向（上盘=让球方赢盘，下盘=受让方赢盘）。

**核心原则（必须牢记）：**
亚盘分析的是"赢盘"而非"赢球"。判断方向时，一切都要围绕**盘口深度**这个标尺：
- 上盘方(让球方)需要净胜超过盘口才算赢盘，盘口越深(如让1.25/1.5/2球)，赢盘难度越大。
- "球队强、状态好、名气大" 不等于 "能赢盘"。强队让深盘时，即使赢球也常常输盘。
- 受让方(下盘)只要不输超过盘口(甚至小负/平局)就赢盘，盘口越深对下盘越有利。
- 冷门往往出现在：市场一边倒看好强队赢深盘，但强队赢球不赢盘 → 下盘爆冷。

**分析维度：**

1. **近期状态**：我已为你算好双方近期客观指标(场均积分、不败场次、主客场场均分、亚盘赢盘率)。请综合判断哪方状态更适合赢下当前盘口。
   - 注意区分"状态好"和"能赢盘"：上盘方状态压倒且盘口不深→偏上盘；上盘方状态平平或盘口很深→偏下盘。
   - **赢盘率样本不足(少于5场)时不要当作强信号**，以场均积分等完整样本指标为主。
   - 关注主客场：主队看主场场均分，客队看客场场均分。

2. **交锋历史**：分析双方近期交锋，**重点看亚盘赢盘记录(asianResult)而非单纯胜负**，并关注类似盘口下的表现。
   - 上盘方历史多次赢盘 → 偏上盘；上盘方历史常赢球但输盘，或交锋胶着 → 偏下盘。

3. **实力定位**：从大众第一印象判断哪支球队整体实力更强（不考虑盘口深浅，盘口由其他因子分析）。
   - 评估维度：历史底蕴(豪门/劲旅/中游/保级队/升班马)、联赛地位、欧战经历、阵容配置档次、教练水平。
   - 若提供了联赛排名/球队身价，可作参考，但杯赛常无联赛排名；身价接近时勿过度解读。
   - 上盘方(让球方)综合实力底蕴明显强于下盘方 → upper；下盘方底蕴反而更强或双方接近 → lower或neutral。
   - 这是纯粹的"大众认为谁更强"，不需要考虑盘口是否合理。

请严格按以下JSON格式输出(必须包含全部3个因子)：

{
  "factors": [
    {"name": "近期状态", "score": 1到10的整数, "direction": "upper或lower或neutral", "reason": "简短原因，25字以内"},
    {"name": "交锋历史", "score": 1到10的整数, "direction": "upper或lower或neutral", "reason": "简短原因，25字以内"},
    {"name": "实力定位", "score": 1到10的整数, "direction": "upper或lower或neutral", "reason": "简短原因，25字以内"}
  ]
}

评分规则：
- score: 该因子对该方向的支撑强度(1极弱-10极强)
- 7-10分: 有明确信号指向该方向
- 5-6分: 信号弱或中性
- 1-4分: 不应出现(如果偏向另一方，切换direction而非给低分)
- 数据不足时: score=5, direction="neutral"
- 只输出JSON"""


def build_ai_prompt(match_info: Dict, match_data: Optional[Dict] = None) -> str:
    """构建 F1近期状态/F2交锋历史/F3实力定位 的分析 prompt"""
    parts = []

    home = match_info.get("home_team", "主队")
    away = match_info.get("away_team", "客队")
    league = match_info.get("league", "未知联赛")
    handicap = match_info.get("handicap")

    is_home_let = handicap is not None and float(handicap) < 0
    upper_team = home if is_home_let else away
    lower_team = away if is_home_let else home

    parts.append(f"联赛: {league}")
    parts.append(f"上盘方(让球方): {upper_team}")
    parts.append(f"下盘方(受让方): {lower_team}")

    if handicap is not None:
        h = abs(float(handicap))
        # 标注盘口深度，提示AI赢盘难度
        if h >= 1.5:
            depth = "深盘，上盘赢盘难度大"
        elif h >= 1.0:
            depth = "中等盘口"
        elif h > 0:
            depth = "浅盘"
        else:
            depth = "平手盘"
        parts.append(f"盘口: {upper_team}让{h}球（{depth}），上盘方需净胜超过{h}球才赢盘")

    if match_info.get("home_rank"):
        hr = parse_league_rank(match_info["home_rank"])
        parts.append(f"{home}排名: {('第'+str(hr)) if hr is not None else match_info['home_rank']}")
    if match_info.get("away_rank"):
        ar = parse_league_rank(match_info["away_rank"])
        parts.append(f"{away}排名: {('第'+str(ar)) if ar is not None else match_info['away_rank']}")

    worth = match_info.get("squad_worth") or {}
    if worth.get("home_worth") is not None and worth.get("away_worth") is not None:
        ht = worth.get("home_worth_text") or f"€{worth['home_worth']}万"
        at = worth.get("away_worth_text") or f"€{worth['away_worth']}万"
        ratio = worth.get("ratio") or ""
        ratio_part = f"，身价比{ratio}" if ratio else ""
        parts.append(f"球队身价: {home} {ht} vs {away} {at}{ratio_part}")

    # 近期战绩数据
    if match_data:
        home_recent = match_data.get("homeRecent", [])[:10]
        away_recent = match_data.get("awayRecent", [])[:10]
        h2h = match_data.get("h2h", [])[:10]

        # 代码算好的客观指标(供F1近期状态推理)
        # 匹配战绩明细用500队名别名(竞彩名可能不同,如阿拉木图≠凯拉特)
        if home_recent or away_recent:
            home_aliases = _resolve_side_aliases(
                home, match_data.get("homeTeamName"), home_recent,
                extra_aliases=match_data.get("homeTeamAliases"))
            away_aliases = _resolve_side_aliases(
                away, match_data.get("awayTeamName"), away_recent,
                extra_aliases=match_data.get("awayTeamAliases"))
            parts.append("\n【近期状态客观指标】")
            if home_recent:
                hm = build_form_metrics(home_recent, home_aliases)
                alias_hint = ""
                extra = [a for a in home_aliases if a != home]
                if extra:
                    alias_hint = f"/{'/'.join(extra)}"
                label = f"{home}{alias_hint}(主队{'，本场上盘' if is_home_let else '，本场下盘'})"
                parts.append(_format_form_metrics(hm, label))
            if away_recent:
                am = build_form_metrics(away_recent, away_aliases)
                alias_hint = ""
                extra = [a for a in away_aliases if a != away]
                if extra:
                    alias_hint = f"/{'/'.join(extra)}"
                label = f"{away}{alias_hint}(客队{'，本场下盘' if is_home_let else '，本场上盘'})"
                parts.append(_format_form_metrics(am, label))


        # 近期比赛明细(供AI核对)
        if home_recent:
            parts.append(f"\n{home}近期明细:")
            for r in home_recent[:6]:
                parts.append(f"  {r.get('date','')} {r.get('match','')} {r.get('result','')} 盘口:{r.get('handicap','-')} 亚盘:{r.get('asianResult','-')}")
        if away_recent:
            parts.append(f"\n{away}近期明细:")
            for r in away_recent[:6]:
                parts.append(f"  {r.get('date','')} {r.get('match','')} {r.get('result','')} 盘口:{r.get('handicap','-')} 亚盘:{r.get('asianResult','-')}")

        if h2h:
            import re
            from datetime import datetime, timedelta
            # 过滤当前比赛(日期±1天)
            match_date = match_info.get("match_date", "")
            filtered_h2h = h2h
            if match_date:
                try:
                    md = datetime.strptime(match_date, "%Y-%m-%d")
                    ex_start = (md - timedelta(days=1)).strftime("%Y-%m-%d")
                    ex_end = (md + timedelta(days=1)).strftime("%Y-%m-%d")
                    filtered_h2h = [r for r in h2h if not (ex_start <= r.get("date", "") <= ex_end)]
                except (ValueError, TypeError):
                    pass

            if filtered_h2h:
                parts.append(f"\n{upper_team}与{lower_team}近{len(filtered_h2h)}次交锋(亚盘结果从{upper_team}上盘视角):")
                for r in filtered_h2h[:6]:
                    match_text = re.sub(r'\[\d+\]', '', r.get('match', ''))
                    # 转换asianResult为上盘方视角
                    raw_ar = (r.get('asianResult') or '').strip()
                    if is_home_let:
                        upper_ar = raw_ar  # 页面主队=上盘方，视角一致
                    else:
                        # 页面主队=下盘方，需要翻转
                        flip = {"赢": "输", "赢半": "输半", "输": "赢", "输半": "赢半", "走": "走"}
                        upper_ar = flip.get(raw_ar, raw_ar)
                    parts.append(f"  {r.get('date','')} {match_text} {r.get('result','')} 盘口:{r.get('handicap','?')} {upper_team}{'赢盘' if upper_ar in ('赢','赢半') else '输盘' if upper_ar in ('输','输半') else '走盘'}")

    # 市场热度相关补充
    if match_info.get("market_heat_desc"):
        parts.append(f"\n用户提供的市场热度信息: {match_info['market_heat_desc']}")

    return "\n".join(parts)


def call_deepseek_factors(prompt: str) -> List[Dict[str, Any]]:
    """调用 DeepSeek 获取 F1近期状态/F2交锋历史/F3实力定位 分析（含重试）"""
    client = _get_client()

    logger.info(f"[predict] DeepSeek prompt (前200字): {prompt[:200]}...")

    content = ""
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": AI_FACTORS_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            if content.strip():
                break
        except Exception as e:
            logger.warning(f"[predict] DeepSeek 调用失败(attempt {attempt+1}): {e}")
            if attempt == 1:
                content = ""

    logger.info(f"[predict] DeepSeek 返回: {content[:300]}...")

    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    default_factors = [
        {"name": "近期状态", "score": 5, "direction": "neutral", "reason": "AI分析无结果"},
        {"name": "交锋历史", "score": 5, "direction": "neutral", "reason": "AI分析无结果"},
        {"name": "实力定位", "score": 5, "direction": "neutral", "reason": "AI分析无结果"},
    ]

    if not text:
        logger.warning("[predict] DeepSeek 返回空内容，使用默认值")
        return default_factors

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"[predict] DeepSeek 返回JSON解析失败: {e}, 原文: {text[:200]}")
        # 尝试修复常见问题：末尾多余逗号
        import re
        fixed = re.sub(r',\s*([}\]])', r'\1', text)
        try:
            result = json.loads(fixed)
        except json.JSONDecodeError:
            return default_factors

    factors = result.get("factors", [])

    # 规范化
    for f in factors:
        f["score"] = max(1, min(10, int(f.get("score", 5))))
        if f.get("direction") not in ("upper", "lower", "neutral"):
            f["direction"] = "neutral"

    return factors


# ============================================================
# 综合预测入口
# ============================================================

# 标识"数据缺失型中性"的关键词(区别于"算出来确实中性")
_MISSING_KEYWORDS = ("无", "缺失", "不足", "无结果", "数据不足")


def _is_missing_neutral(factor: Dict[str, Any]) -> bool:
    """判断中性因子是数据缺失导致(应惩罚) 还是 算出来确实中性(不惩罚)"""
    if factor.get("direction") != "neutral":
        return False
    reason = factor.get("reason", "")
    return any(kw in reason for kw in _MISSING_KEYWORDS)


def _effective_dir(factor: Dict[str, Any], reverse_set: set) -> str:
    """获取因子在预测计算中的有效方向(考虑逆向翻转)"""
    d = factor.get("direction", "neutral")
    if factor["name"] in reverse_set and d in ("upper", "lower"):
        return "lower" if d == "upper" else "upper"
    return d


def calc_prediction(factors: List[Dict[str, Any]], custom_weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """综合计算最终预测方向和置信度 - 净方向占比模型

    置信度拆为两个独立维度：
    - 一致性 consistency: 主导方向的权重 / 有方向因子总权重(0.5~1.0)
      反映"方向是否明确"，反向因子越少越高。六因子全同向 = 1.0。
    - 强度 avg_intensity: 主导方向因子的加权平均强度(0~1)
      反映"信号是否强烈"，因子分数越高越强。

    置信度 = base(一致性主导, 50~85) + 强度加成(0~12) - 数据缺失惩罚

    Args:
        factors: 因子列表
        custom_weights: 自定义权重字典(可选，默认用全局FACTOR_WEIGHTS)
    """
    weights = custom_weights or FACTOR_WEIGHTS
    upper_w = 0.0               # 上盘方向加权强度和
    lower_w = 0.0               # 下盘方向加权强度和
    upper_weight = 0.0          # 上盘因子权重和(不乘强度)
    lower_weight = 0.0          # 下盘因子权重和
    upper_count = 0
    lower_count = 0
    neutral_count = 0
    missing_count = 0

    # 市场热度/单关修正的direction表示"哪边热"(事实)，在预测中需逆向解读：热的一边反向
    REVERSE_FACTORS = {"市场热度", "单关修正"}

    # 展示方向统计(界面卡片方向)，用于整体逆向候选
    raw_upper = 0
    raw_lower = 0
    raw_neutral = 0
    for f in factors:
        d = f.get("direction", "neutral")
        if d == "upper":
            raw_upper += 1
        elif d == "lower":
            raw_lower += 1
        else:
            raw_neutral += 1

    # 展示共识候选：几乎全部一致(同向≥n-2，反向≤1)
    total_factors = len(factors)
    reverse_candidate = False
    raw_dom_dir = None
    if total_factors >= 6:
        raw_dom = max(raw_upper, raw_lower)
        raw_opp = min(raw_upper, raw_lower)
        if raw_dom >= (total_factors - 2) and raw_opp <= 1 and raw_dom > 0:
            reverse_candidate = True
            raw_dom_dir = "upper" if raw_upper >= raw_lower else "lower"

    for f in factors:
        name = f["name"]
        w = weights.get(name, 1.0)
        fscore = f.get("score", 5)
        direction = f["direction"]

        # 逆向因子：direction翻转后参与预测计算
        if name in REVERSE_FACTORS and direction in ("upper", "lower"):
            direction = "lower" if direction == "upper" else "upper"

        # 修复重复计权：单关修正同向于市场热度时打5折，避免热度信号被计两次
        if name == "单关修正" and direction != "neutral":
            f5 = next((x for x in factors if x["name"] == "市场热度"), None)
            if f5 and f5.get("direction") == f["direction"]:
                w = w * 0.5

        if direction in ("upper", "lower"):
            intensity = max(0.0, (fscore - 5) / 5.0)  # 0~1
            if direction == "upper":
                upper_w += w * intensity
                upper_weight += w
                upper_count += 1
            else:
                lower_w += w * intensity
                lower_weight += w
                lower_count += 1
        else:
            neutral_count += 1
            if _is_missing_neutral(f):
                missing_count += 1

    active_count = upper_count + lower_count
    total_dir_weight = upper_weight + lower_weight

    # 完全无方向信号(因子全中性)
    if active_count == 0 or total_dir_weight < 1e-6:
        return {"direction": "neutral", "confidence": 35, "score": 0.0,
                "neutral_count": neutral_count, "overall_reverse": False}

    # 加权主导方向(已含因子级逆向)
    if upper_w > lower_w:
        direction = "upper"
        dom_weight, dom_intensity_sum = upper_weight, upper_w
    elif lower_w > upper_w:
        direction = "lower"
        dom_weight, dom_intensity_sum = lower_weight, lower_w
    else:
        # 双向强度相等，方向不明
        return {"direction": "neutral", "confidence": 38, "score": 0.0,
                "neutral_count": neutral_count, "overall_reverse": False}

    # 整体逆向：仅当展示共识一边倒，且加权后仍跟展示共识同向(散户跟风未被热度逆向压住)时翻一次。
    # 避免与市场热度/单关的因子级逆向双重翻转(本已反向又翻回共识)。
    overall_reverse = bool(
        reverse_candidate and raw_dom_dir and direction == raw_dom_dir
    )
    if overall_reverse:
        direction = "lower" if direction == "upper" else "upper"
        dom_weight, dom_intensity_sum = (lower_weight, lower_w) if direction == "lower" else (upper_weight, upper_w)

    # 统计主导方向中score>5的强因子数(真正有信号强度的因子)
    dom_dir = direction
    opp_dir = "lower" if dom_dir == "upper" else "upper"
    # 注意：这里的direction是翻转后的，需要用内部direction来判断
    dom_strong = sum(1 for f in factors
                     if _effective_dir(f, REVERSE_FACTORS) == dom_dir and f.get("score", 5) > 5)
    opp_strong = sum(1 for f in factors
                     if _effective_dir(f, REVERSE_FACTORS) == opp_dir and f.get("score", 5) > 5)
    total_strong = dom_strong + opp_strong

    # 维度1 方向优势：强因子中主导方向的占比
    if total_strong > 0:
        dir_advantage = dom_strong / total_strong
    else:
        dir_advantage = 0.5

    # 维度2 强度：主导方向因子的加权平均强度(0~1)
    avg_score = dom_intensity_sum / dom_weight if dom_weight else 0

    # 维度3 覆盖度：有强信号的因子数占总因子数
    strong_ratio = total_strong / total_factors if total_factors > 0 else 0

    if overall_reverse:
        dir_advantage = 0.65

    # 置信度计算:
    # base: 方向优势 (0.5→40, 0.75→52, 1.0→65)
    base = 40 + (dir_advantage - 0.5) * 50
    # 强度加成: (0→0, 0.4→5, 0.6→8, 1.0→13)
    strength_bonus = avg_score * 13
    # 覆盖度加成: 强因子越多越确定，这是区分度的核心
    # 2/7→0, 3/7→+3, 4/7→+6, 5/7→+10, 6/7→+14
    coverage_bonus = max(0, (strong_ratio - 0.28)) * 24
    # 数据缺失惩罚: 仅对拿不到数据的中性因子(每个-3，最多-9)
    missing_penalty = min(9, missing_count * 3)
    # 逆向触发时置信度适度降低(逆向本身有不确定性)
    reverse_penalty = 8 if overall_reverse else 0

    confidence = int(base + strength_bonus + coverage_bonus - missing_penalty - reverse_penalty)
    confidence = max(35, min(92, confidence))

    return {
        "direction": direction,
        "confidence": confidence,
        "score": round((upper_w - lower_w) / total_dir_weight, 3),
        "neutral_count": neutral_count,
        "dir_advantage": round(dir_advantage, 3),
        "avg_intensity": round(avg_score, 3),
        "strong_ratio": round(strong_ratio, 3),
        "overall_reverse": overall_reverse,
        "consensus_dir": raw_dom_dir if overall_reverse else None,
    }


def generate_analysis(factors: List[Dict], prediction: Dict, match_info: Dict) -> str:
    """生成综合分析文本"""
    home = match_info.get("home_team", "主队")
    away = match_info.get("away_team", "客队")
    handicap = match_info.get("handicap")
    is_home_let = handicap is not None and float(handicap) < 0
    upper_team = home if is_home_let else away
    lower_team = away if is_home_let else home

    conf = prediction["confidence"]
    direction = prediction["direction"]

    upper_factors = [f for f in factors if f["direction"] == "upper" and f["score"] >= 6]
    lower_factors = [f for f in factors if f["direction"] == "lower" and f["score"] >= 6]

    parts = []
    if upper_factors:
        names = "、".join(f["name"] for f in upper_factors)
        parts.append(f"看好上盘的因子: {names}")
    if lower_factors:
        names = "、".join(f["name"] for f in lower_factors)
        parts.append(f"看好下盘的因子: {names}")

    if direction == "neutral":
        parts.append(f"综合{len(factors)}项因子，多数因子中性或方向冲突，无明显倾向，不建议下注，置信度{conf}%。")
    elif prediction.get("overall_reverse"):
        dir_text = "上盘" if direction == "upper" else "下盘"
        consensus = prediction.get("consensus_dir")
        if consensus not in ("upper", "lower"):
            consensus = "lower" if direction == "upper" else "upper"
        consensus_text = "上盘" if consensus == "upper" else "下盘"
        parts.append(
            f"展示方向多数共识偏{consensus_text}，加权后仍跟风，触发整体逆向，"
            f"建议方向: {dir_text}，置信度{conf}%。"
        )
    else:
        dir_text = "上盘" if direction == "upper" else "下盘"
        parts.append(f"综合{len(factors)}项因子，建议方向: {dir_text}（{upper_team}{'赢盘' if direction == 'upper' else '输盘'}），置信度{conf}%。")

    return "。".join(parts)


def _fmt_handicap(v):
    """格式化盘口数值：0显示为0，正数加+号"""
    if v == 0 or v == -0.0:
        return "0"
    return f"+{v}" if v > 0 else str(v)


def calc_factor_jczq_odds(jczq_company: Optional[Dict]) -> Dict[str, Any]:
    """F5 竞彩赔率: 竞彩nspf初盘→终盘的低赔变动方向

    逻辑(与世界杯一致):
    - 找初盘中最低的赔率（低赔 = 热门方向）
    - 低赔↓(降): 市场持续看好热门 → upper, score=7
    - 低赔↑(升): 市场对热门信心减弱 → lower, score=7
    - 不变(±0.02): neutral, score=5
    """
    if not jczq_company:
        return {"name": "竞彩赔率", "score": 5, "direction": "neutral",
                "reason": "无竞彩nspf赔率数据", "details": []}

    initial = jczq_company.get("initial", {})
    current = jczq_company.get("current", {})

    open_win = initial.get("win")
    open_draw = initial.get("draw")
    open_loss = initial.get("lose")
    close_win = current.get("win")
    close_draw = current.get("draw")
    close_loss = current.get("lose")

    if not all([open_win, open_draw, open_loss, close_win, close_draw, close_loss]):
        return {"name": "竞彩赔率", "score": 5, "direction": "neutral",
                "reason": "竞彩nspf赔率数据不完整", "details": []}

    odds_list = [
        ("胜", open_win, close_win),
        ("平", open_draw, close_draw),
        ("负", open_loss, close_loss),
    ]
    low_label, low_open, low_close = min(odds_list, key=lambda x: x[1])
    diff = low_close - low_open

    details = [
        {"name": "初盘", "desc": f"胜{open_win:.2f}/平{open_draw:.2f}/负{open_loss:.2f}"},
        {"name": "终盘", "desc": f"胜{close_win:.2f}/平{close_draw:.2f}/负{close_loss:.2f}"},
        {"name": "低赔位置", "desc": f"{low_label}赔 {low_open:.2f}→{low_close:.2f} ({diff:+.2f})"},
    ]

    if diff < -0.02:
        direction = "upper"
        score = 7
        reason = f"竞彩{low_label}赔(低赔)下降{diff:.2f}，市场持续看好热门→偏上盘"
    elif diff > 0.02:
        direction = "lower"
        score = 7
        reason = f"竞彩{low_label}赔(低赔)上升{diff:+.2f}，市场对热门信心减弱→偏下盘"
    else:
        direction = "neutral"
        score = 5
        reason = f"竞彩{low_label}赔(低赔)变动极小({diff:+.2f})，方向不明"

    return {"name": "竞彩赔率", "score": score, "direction": direction,
            "reason": reason, "details": details}


def _hc_proximity(hist_hc: Optional[float], ah_handicap: Optional[float]) -> float:
    """D4 盘口一致性权重: 线越接近越高; 缺盘口给中性 0.6。"""
    if hist_hc is None or ah_handicap is None:
        return 0.6
    try:
        delta = abs(float(hist_hc) - float(ah_handicap))
    except (TypeError, ValueError):
        return 0.6
    if delta <= 0.25:
        return 1.0
    if delta <= 0.5:
        return 0.7
    if delta <= 1.0:
        return 0.4
    return 0.2


def _time_decay(match_date) -> float:
    """D8 时效: 近3年1.0 / 3–6年0.85 / 更旧0.7。"""
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


def _ah_side_mag(ah_result: Optional[str]) -> Tuple[Optional[str], float]:
    """盘路 → (side upper/lower/push, 全赢1.0/半赢0.5)。无法判定返回 (None, 0)。"""
    if ah_result == "上盘":
        return "upper", 1.0
    if ah_result == "半上":
        return "upper", 0.5
    if ah_result == "下盘":
        return "lower", 1.0
    if ah_result == "半下":
        return "lower", 0.5
    if ah_result == "走水":
        return "push", 0.0
    return None, 0.0


def _calc_similar_ref_score(
    direction: str,
    rows: List[Dict[str, Any]],
    *,
    ah_handicap: Optional[float] = None,
    query_degraded: bool = False,
    total: int = 0,
) -> Tuple[int, Dict[str, int]]:
    """多维同赔参考分 0–100 + 分项 breakdown。

    rows 字段: similarity, same_league, ah_result, handicap(float|None), match_date
    """
    empty_bd = {"edge": 0, "quality": 0, "sample": 0, "decidable": 0}
    if not rows:
        return 0, empty_bd

    support = 0.0
    oppose = 0.0
    wp = 0.0
    sims: List[float] = []
    hcs: List[float] = []
    same_lg = 0
    n_quality = 0
    n_eff = 0.0
    # 中性时先累加两侧,再取优势侧算 edge
    w_upper = 0.0
    w_lower = 0.0

    for r in rows:
        side, mag = _ah_side_mag(r.get("ah_result"))
        if side is None:
            continue
        sim = float(r.get("similarity") or 0) / 100.0
        sim = max(0.0, min(1.0, sim))
        w_lg = 1.15 if r.get("same_league") else 1.0
        w_hc = _hc_proximity(r.get("handicap"), ah_handicap)
        w_time = _time_decay(r.get("match_date"))
        w = sim * w_lg * w_hc * w_time

        n_quality += 1
        sims.append(sim)
        hcs.append(w_hc)
        if r.get("same_league"):
            same_lg += 1

        if side == "push":
            wp += w
            continue

        contrib = mag * w
        n_eff += w
        if side == "upper":
            w_upper += contrib
        else:
            w_lower += contrib

    if n_quality == 0:
        return 0, empty_bd

    # 倾向侧: 明确方向用 direction; 中性取加权更强一侧
    if direction == "upper":
        support, oppose = w_upper, w_lower
    elif direction == "lower":
        support, oppose = w_lower, w_upper
    else:
        if w_upper >= w_lower:
            support, oppose = w_upper, w_lower
        else:
            support, oppose = w_lower, w_upper

    wdec = support + oppose
    if wdec > 0:
        margin = max(0.0, (support - oppose) / wdec)
        s_edge = 100.0 * margin
    else:
        s_edge = 0.0

    avg_sim = sum(sims) / len(sims)
    avg_hc = sum(hcs) / len(hcs)
    same_league_rate = same_lg / n_quality
    s_quality = 100.0 * (0.5 * avg_sim + 0.25 * same_league_rate + 0.25 * avg_hc)

    s_sample = 100.0 * (1.0 - math.exp(-n_eff / 14.0))

    wtot = wdec + wp
    s_decidable = 100.0 * (1.0 - wp / wtot) if wtot > 0 else 0.0

    raw = 0.40 * s_edge + 0.25 * s_quality + 0.20 * s_sample + 0.15 * s_decidable
    if query_degraded:
        raw *= 0.85
    if total < 3:
        raw = min(raw, 20.0)
    if direction == "neutral":
        raw = min(raw, 50.0)

    ref_score = int(max(0, min(100, round(raw))))
    breakdown = {
        "edge": int(max(0, min(100, round(s_edge)))),
        "quality": int(max(0, min(100, round(s_quality)))),
        "sample": int(max(0, min(100, round(s_sample)))),
        "decidable": int(max(0, min(100, round(s_decidable)))),
    }
    return ref_score, breakdown


def _fmt_ah_line(hc) -> str:
    """亚盘展示: 0 / +0.25 / -0.50; None→空串。"""
    if hc is None:
        return ""
    try:
        v = float(hc)
    except (TypeError, ValueError):
        return ""
    if abs(v) < 1e-9:
        return "0"
    return f"{v:+.2f}"


def calc_factor_jczq_similar_odds(jczq_company: Optional[Dict], league: Optional[str] = None,
                                  exclude_match_id: Optional[str] = None,
                                  ah_handicap: Optional[float] = None,
                                  ah_open: Optional[float] = None) -> Dict[str, Any]:
    """F6 历史同赔: 匹配竞彩历史 spf(胜平负)中赔率相近且变动方向一致的比赛

    匹配条件: 初盘低赔±0.03 + 终盘低赔±0.03 + 低赔方同一侧(同为胜/平/负) + 低赔变动方向一致
    ah_handicap=终盘亚盘, ah_open=初盘亚盘(标准负=主让); 均有时相似度并入亚盘路径。
    方向判定(以盘路为准, 与弹窗"盘路"列口径一致, 不用胜平负低赔命中):
    - 匹配 < 3场 或 无盘口: neutral, score=5
    - 盘路上盘命中 > 65%: upper, score=7
    - 盘路上盘命中 < 40%(即下盘频出): lower, score=7
    - 其他: neutral, score=5

    另返回 refScore(0–100 多维证据强度) + refBreakdown, 不并入因子 score。
    """
    _empty_ref = {"refScore": 0, "refBreakdown": {"edge": 0, "quality": 0, "sample": 0, "decidable": 0}}

    if not jczq_company:
        return {"name": "历史同赔", "score": 5, "direction": "neutral",
                "reason": "无竞彩spf赔率，无法匹配历史同赔", "details": [], **_empty_ref}

    initial = jczq_company.get("initial", {})
    current = jczq_company.get("current", {})

    open_win = initial.get("win")
    open_draw = initial.get("draw")
    open_loss = initial.get("lose")
    close_win = current.get("win")
    close_draw = current.get("draw")
    close_loss = current.get("lose")

    if not all([open_win, open_draw, open_loss, close_win, close_draw, close_loss]):
        return {"name": "历史同赔", "score": 5, "direction": "neutral",
                "reason": "竞彩spf赔率不完整，无法匹配", "details": [], **_empty_ref}

    # 预测场仅有1条spf快照(open==current)时, 无真实变动, 方向恒"平"是数据缺失而非真稳定。
    # 此时放弃"变动方向一致"过滤, 仅按初/终盘接近+同侧匹配(方向降级)。
    has_move = initial != current
    query_degraded = not has_move

    try:
        result = find_similar_spf(open_win, open_draw, open_loss, close_win, close_draw, close_loss,
                                  league=league, exclude_match_id=exclude_match_id,
                                  require_direction=has_move,
                                  ah_open=ah_open, ah_close=ah_handicap)
    except Exception as e:
        logger.warning(f"历史同赔查询失败: {e}")
        return {"name": "历史同赔", "score": 5, "direction": "neutral",
                "reason": f"查询异常: {e}", "details": [], **_empty_ref}

    stats = result.get("stats", {})
    matches = result.get("matches", [])
    query = result.get("query", {})
    total = stats.get("total", 0)

    # 详情列表(样本不足时也要返回, 避免 reason 说匹配N场但 matches 为空)
    similar_matches = []
    ref_rows: List[Dict[str, Any]] = []
    for m in matches:
        hs, aws = m.get("home_score", 0), m.get("away_score", 0)
        hc = m.get("handicap")  # close
        oh = m.get("open_handicap")
        out = _ah_outcome(hs, aws, hc, m.get("hist_low_key"))
        ah_result = out[0] if out else None
        similar_matches.append({
            "similarity": m.get("similarity", 0),
            "date": m.get("match_date", ""),
            "league": m.get("league_name", ""),
            "sameLeague": bool(m.get("same_league", False)),
            "isSingle": bool(int(m.get("is_single") or 0)),
            "homeTeam": m.get("home_team_cn", ""),
            "awayTeam": m.get("away_team_cn", ""),
            "score": f"{hs}-{aws}",
            "homeScore": int(hs) if hs is not None else None,
            "awayScore": int(aws) if aws is not None else None,
            "result": {"H": "主胜", "D": "平局", "A": "客胜"}.get(m.get("result"), ""),
            "handicap": _fmt_ah_line(hc),  # 兼容旧字段=终盘
            "handicapOpen": _fmt_ah_line(oh),
            "handicapClose": _fmt_ah_line(hc),
            "ahResult": ah_result,
            "openOdds": f"{m.get('open_win', 0):.2f}/{m.get('open_draw', 0):.2f}/{m.get('open_loss', 0):.2f}",
            "closeOdds": f"{m.get('close_win', 0):.2f}/{m.get('close_draw', 0):.2f}/{m.get('close_loss', 0):.2f}",
        })
        ref_rows.append({
            "similarity": m.get("similarity", 0),
            "same_league": bool(m.get("same_league", False)),
            "ah_result": ah_result,
            "handicap": float(hc) if hc is not None else None,
            "match_date": m.get("match_date"),
        })

    dir_label = query.get("direction", "") if has_move else "不限(无变动)"
    if total < 3:
        ref_score, breakdown = _calc_similar_ref_score(
            "neutral", ref_rows, ah_handicap=ah_handicap,
            query_degraded=query_degraded, total=total)
        return {"name": "历史同赔", "score": 5, "direction": "neutral",
                "reason": f"匹配到{total}场历史比赛，样本不足(需≥3场)",
                "details": [
                    {"name": "匹配条件", "desc": f"低赔初{query.get('low_open', 0):.2f}±{query.get('tolerance', 0.03):.2f} 终{query.get('low_close', 0):.2f}±{query.get('tolerance', 0.03):.2f}({query.get('low_position', '')}) 方向{dir_label}"},
                    {"name": "参考分", "desc": f"{ref_score} (证据强度)"},
                ],
                "matches": similar_matches, "refScore": ref_score, "refBreakdown": breakdown}

    # 方向以盘路(亚盘上盘/下盘)统计为准, 与弹窗"盘路"列口径一致
    ah_total = stats.get("ah_total", 0)
    ah_upper = stats.get("ah_upper", 0)
    ah_lower = stats.get("ah_lower", 0)
    ah_push = stats.get("ah_push", 0)
    ah_upper_pct = stats.get("ah_upper_pct", 0)
    ah_lower_pct = stats.get("ah_lower_pct", 0)
    full_up = stats.get("full_up", 0)
    half_up = stats.get("half_up", 0)
    full_down = stats.get("full_down", 0)
    half_down = stats.get("half_down", 0)

    if ah_total >= 3 and ah_upper_pct > 65:
        direction = "upper"
        score = 7
        reason = f"历史同赔{ah_total}场盘路上盘命中{ah_upper_pct:.0f}%({ah_upper}/{ah_total})，上盘稳定打出→偏上盘"
    elif ah_total >= 3 and ah_upper_pct < 40:
        direction = "lower"
        score = 7
        reason = f"历史同赔{ah_total}场盘路下盘命中{ah_lower_pct:.0f}%({ah_lower}/{ah_total})，下盘频出→偏下盘"
    else:
        direction = "neutral"
        score = 5
        if ah_total >= 3:
            reason = f"历史同赔{ah_total}场盘路上盘{ah_upper_pct:.0f}%/下盘{ah_lower_pct:.0f}%，无明确倾向"
        else:
            reason = f"历史同赔{total}场无盘口数据，无法判定盘路倾向"

    ref_score, breakdown = _calc_similar_ref_score(
        direction, ref_rows, ah_handicap=ah_handicap,
        query_degraded=query_degraded, total=total)

    details = [
        {"name": "匹配条件", "desc": (f"低赔初{query.get('low_open', 0):.2f}±{query.get('tolerance', 0.03):.2f} 终{query.get('low_close', 0):.2f}±{query.get('tolerance', 0.03):.2f}"
                                      f"({query.get('low_position', '')}) | 高赔初{query.get('high_open', 0):.2f}±{query.get('high_tolerance_open', query.get('high_tolerance', 0.1)):.2f} 终{query.get('high_close', 0):.2f}±{query.get('high_tolerance_close', query.get('high_tolerance', 0.1)):.2f}"
                                      f" | 方向{dir_label}")},
        {"name": "匹配场次", "desc": f"{total}场竞彩历史比赛(spf)"},
        {"name": "盘路分布", "desc": f"上盘{ah_upper}(全{full_up}半{half_up}) 下盘{ah_lower}(全{full_down}半{half_down}) 走水{ah_push} (共{ah_total}场)"},
        {"name": "上盘命中", "desc": f"{ah_upper_pct:.0f}% ({ah_upper}/{ah_total})"},
        {"name": "下盘命中", "desc": f"{ah_lower_pct:.0f}% ({ah_lower}/{ah_total})"},
        {"name": "走水", "desc": f"{ah_push}场 ({round(ah_push / ah_total * 100, 0) if ah_total else 0:.0f}%)" if ah_total else "0场"},
        {"name": "参考分", "desc": f"{ref_score} (证据强度 edge{breakdown['edge']}/质{breakdown['quality']}/样{breakdown['sample']}/判{breakdown['decidable']})"},
    ]

    # 添加匹配比赛摘要(前5场)
    for m in matches[:5]:
        score_str = f"{m['home_score']}-{m['away_score']}"
        details.append({
            "name": f"{m.get('match_date', '')} {m.get('league_name', '')}",
            "desc": f"{m.get('home_team_cn', '')} {score_str} {m.get('away_team_cn', '')}"
        })

    return {"name": "历史同赔", "score": score, "direction": direction,
            "reason": reason, "details": details, "matches": similar_matches,
            "refScore": ref_score, "refBreakdown": breakdown}


def predict_match(match_info: Dict[str, Any], match_data: Optional[Dict] = None,
                  asian_data: Optional[List] = None,
                  euro_data: Optional[Dict] = None) -> Dict[str, Any]:
    """完整预测流程

    Args:
        match_info: 比赛基本信息 (league, home_team, away_team, handicap, is_single, etc.)
        match_data: 500.com基本面数据 (h2h, homeRecent, awayRecent)
        asian_data: 500.com亚盘数据列表
        euro_data: 500.com欧赔数据 {"companies": [...], "summary": {...}}

    Returns:
        {"factors": [...], "prediction": {...}}
    """
    handicap = match_info.get("handicap")
    is_home_let = handicap is not None and float(handicap) < 0
    is_single = bool(match_info.get("is_single"))

    # F3 市场信号：初盘+亚盘变动+欧赔变动+亚欧一致性
    f3 = calc_factor4(asian_data or [], is_home_let, euro_data)
    f3["name"] = "市场信号"
    # F4 市场热度：纯量化（多公司水位一致性）+ 用户手动输入优先
    f4 = calc_factor5(asian_data or [], is_home_let, match_info.get("market_heat_desc"))
    f4["name"] = "市场热度"

    # F5 竞彩赔率 & F6 历史同赔: 从 jczq_odds_history 取本场 nspf 初/终盘
    # F5竞彩赔率 & F6历史同赔 均用 spf(胜平负)口径(与世界杯一致, 用户预期)
    _mid = match_info.get("match_id")
    jczq_company_spf = get_match_spf_odds(_mid) if _mid else None
    f5 = calc_factor_jczq_odds(jczq_company_spf)
    f6 = calc_factor_jczq_similar_odds(
        jczq_company_spf, league=match_info.get("league"),
        exclude_match_id=_mid,
        ah_handicap=match_info.get("handicap"),
        ah_open=match_info.get("handicap_open"))

    # F1 近期状态 & F2 实力定位: DeepSeek推理(3次调用取多数，并行加速)
    # 与世界杯一致: 不再投交锋历史票
    prompt = build_ai_prompt(match_info, match_data)

    ai_f1_list = []
    ai_f3_list = []

    from concurrent.futures import ThreadPoolExecutor

    def _safe_call(_prompt):
        try:
            return call_deepseek_factors(_prompt)
        except Exception as e:
            logger.warning(f"[predict] AI调用异常: {e}")
            return []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_safe_call, prompt) for _ in range(3)]
        for future in futures:
            ai_factors = future.result()
            ai_f1 = next((f for f in ai_factors if f["name"] == "近期状态"), None)
            if ai_f1:
                ai_f1_list.append(ai_f1)
            ai_f3 = next((f for f in ai_factors if f["name"] == "实力定位"), None)
            if ai_f3:
                ai_f3_list.append(ai_f3)

    f1 = calc_factor1(match_data, match_info, ai_f1_list or None)
    f2 = calc_factor3(match_info, ai_f3_list or None)
    f2["name"] = "实力定位"

    # F7: 单关修正（基于F4市场热度结果）
    f7 = calc_factor6(is_single, f4["direction"], f4["score"])

    # 组装7因子(与世界杯对齐: F1近期 F2实力 F3市场信号 F4市场热度 F5竞彩赔率 F6历史同赔 F7单关)
    all_factors = [f1, f2, f3, f4, f5, f6, f7]

    # 综合计算(7因子权重, 不使用盘口先验：竞彩整数盘的走水偏差不适用于真实亚盘小数盘口)
    prediction = calc_prediction(all_factors, FACTOR_WEIGHTS)

    # 生成分析文本
    analysis = generate_analysis(all_factors, prediction, match_info)
    prediction["analysis"] = analysis

    return {"factors": all_factors, "prediction": prediction}
