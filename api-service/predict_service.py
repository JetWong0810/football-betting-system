"""预测服务模块 - 6因子亚盘方向预测

因子体系:
  F1 近期状态 (权重1.5) - DeepSeek分析双方近10场
  F2 交锋历史 (权重1.0) - DeepSeek分析近期交锋
  F3 实力定位 (权重2.0) - DeepSeek分析排名+形象认知
  F4 赔率变动 (权重3.0) - 纯量化：亚盘水位升降
  F5 市场热度 (权重2.0) - DeepSeek综合判断/用户手动输入
  F6 单关修正 (权重1.5) - 结合F5的单关逆向规则
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

FACTOR_WEIGHTS = {
    "近期状态": 1.5,
    "交锋历史": 1.0,
    "实力定位": 2.0,
    "赔率变动": 1.5,   # 原3.0，回测显示F4命中率仅52-54%(接近随机)，下调权重
    "市场热度": 2.0,
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
# F4 赔率变动 - 纯量化计算
# ============================================================

def calc_factor4(asian_data: List[Dict], is_home_let: bool) -> Dict[str, Any]:
    """F4: 亚盘水位变动

    上盘升水=不看好上盘, 降水=看好上盘
    """
    if not asian_data:
        return {"name": "赔率变动", "score": 5, "direction": "neutral", "reason": "无亚盘数据"}

    pinnacle = next((c for c in asian_data if c.get("bookmaker") == "Pinnacle"), None)
    if not pinnacle:
        pinnacle = next((c for c in asian_data if c.get("bookmaker") in ("Bet365", "皇冠", "澳门")), None)
    if not pinnacle:
        pinnacle = asian_data[0] if asian_data else None

    if not pinnacle:
        return {"name": "赔率变动", "score": 5, "direction": "neutral", "reason": "无有效公司数据"}

    initial = pinnacle.get("initial", {})
    current = pinnacle.get("current", {})

    init_home = initial.get("home")
    curr_home = current.get("home")
    init_away = initial.get("away")
    curr_away = current.get("away")

    if init_home is None or curr_home is None:
        return {"name": "赔率变动", "score": 5, "direction": "neutral", "reason": "水位数据缺失"}

    # 上盘水位变化(>0升水, <0降水)
    if is_home_let:
        water_change = curr_home - init_home
    else:
        water_change = curr_away - init_away if init_away and curr_away else 0

    # 盘口变化: 500.com正值=主队让球, 绝对值变大=升盘(让球加深)
    init_hcap = initial.get("handicap")
    curr_hcap = current.get("handicap")
    handicap_up = handicap_down = False
    if init_hcap is not None and curr_hcap is not None and init_hcap != curr_hcap:
        # 上盘方让球深度: is_home_let时看主队盘口(500.com正值), 否则客队受让(取反)
        init_depth = abs(init_hcap)
        curr_depth = abs(curr_hcap)
        if curr_depth > init_depth + 1e-9:
            handicap_up = True       # 升盘=让球加深=庄家看好上盘
        elif curr_depth < init_depth - 1e-9:
            handicap_down = True     # 降盘=让球变浅=庄家看淡上盘

    # ===== 综合判断: 盘口变化优先级高于水位 =====
    # 盘口是庄家对实力的真实定价，水位可被用作诱盘
    UP, DOWN, NEU = "upper", "lower", "neutral"

    if handicap_up:
        # 升盘=庄家加深让球, 强烈看好上盘
        if water_change >= 0.05:
            # 升盘+升水: 经典诱盘形态——加深盘口表明真实看好上盘, 升水制造"上盘没人看好"假象诱散户买下盘
            score, direction = 8, UP
            reason = f"升盘(让球加深)+上盘升水{water_change:+.2f}，疑似诱盘，偏看好上盘"
        else:
            score, direction = 8, UP
            reason = f"升盘(让球加深){'＋降水' if water_change<=-0.05 else ''}，庄家看好上盘"
    elif handicap_down:
        # 降盘=庄家减让球, 看淡上盘
        if water_change <= -0.05:
            # 降盘+降水: 反向诱盘——盘口变浅看淡上盘, 降水制造"上盘热"假象
            score, direction = 8, DOWN
            reason = f"降盘(让球变浅)+上盘降水{water_change:+.2f}，疑似诱盘，偏看好下盘"
        else:
            score, direction = 8, DOWN
            reason = f"降盘(让球变浅){'＋升水' if water_change>=0.05 else ''}，庄家看淡上盘"
    else:
        # 盘口未变, 看水位(信号较弱, 单一水位最高7分)
        if water_change <= -0.10:
            score, direction = 7, UP
            reason = f"盘口稳定，上盘大幅降水{water_change:+.2f}，资金流入上盘"
        elif water_change <= -0.05:
            score, direction = 6, UP
            reason = f"盘口稳定，上盘小幅降水{water_change:+.2f}，略偏上盘"
        elif water_change >= 0.10:
            score, direction = 7, DOWN
            reason = f"盘口稳定，上盘大幅升水{water_change:+.2f}，资金流出上盘"
        elif water_change >= 0.05:
            score, direction = 6, DOWN
            reason = f"盘口稳定，上盘小幅升水{water_change:+.2f}，略偏下盘"
        else:
            score, direction = 5, NEU
            reason = f"盘口与水位均稳定({water_change:+.2f})"

    return {"name": "赔率变动", "score": score, "direction": direction, "reason": reason}


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
        return {"name": "市场热度", "score": 7, "direction": "lower",
                "reason": f"手动:上盘过热，逆向偏下盘"}
    if lower_hot and not upper_hot:
        return {"name": "市场热度", "score": 7, "direction": "upper",
                "reason": f"手动:下盘过热，逆向偏上盘"}
    return None


def calc_factor5(asian_data: List[Dict], is_home_let: bool,
                 market_heat_desc: Optional[str] = None) -> Dict[str, Any]:
    """F5 市场热度: 多公司上盘水位一致性(资金流向) + 用户手动输入

    逻辑(逆向): 多数公司上盘方降水 = 资金涌入上盘 = 上盘过热 = 逆向偏下盘。
    多数公司上盘方升水 = 上盘遇冷 = 偏上盘。
    用户手动输入优先级最高。
    """
    # 1. 用户手动输入优先
    manual = _parse_manual_heat(market_heat_desc, is_home_let)
    if manual:
        return manual

    # 2. 多公司水位一致性
    if not asian_data:
        return {"name": "市场热度", "score": 5, "direction": "neutral", "reason": "无亚盘数据，热度不明"}

    mainstream = {"Pinnacle", "Bet365", "皇冠", "威廉希尔", "澳门", "立博", "Crown",
                  "明陞", "iBC", "12bet", "易胜博", "Interwetten", "10BET", "manbetx"}
    drops = rises = 0  # 上盘方降水/升水公司数
    total = 0
    for c in asian_data:
        i = c.get("initial", {})
        cur = c.get("current", {})
        if is_home_let:
            iv, cv = i.get("home"), cur.get("home")
        else:
            iv, cv = i.get("away"), cur.get("away")
        if iv is None or cv is None:
            continue
        # 优先统计主流公司，但全部纳入计数
        wc = cv - iv
        total += 1
        if wc <= -0.03:
            drops += 1
        elif wc >= 0.03:
            rises += 1

    if total < 4:
        return {"name": "市场热度", "score": 5, "direction": "neutral", "reason": "公司样本不足，热度不明"}

    moved = drops + rises
    if moved < 3:
        return {"name": "市场热度", "score": 5, "direction": "neutral",
                "reason": f"仅{moved}家水位变动，热度不明"}

    # 在"发生变动的公司"中看方向占比(未变动的不代表态度)
    drop_ratio = drops / moved
    rise_ratio = rises / moved

    # 降水占多数 = 资金追上盘 = 上盘热 = 逆向看下盘
    if drop_ratio >= 0.75:
        return {"name": "市场热度", "score": 7, "direction": "lower",
                "reason": f"{drops}/{moved}家上盘降水，资金追上盘，逆向偏下盘"}
    elif drop_ratio >= 0.6:
        return {"name": "市场热度", "score": 6, "direction": "lower",
                "reason": f"{drops}/{moved}家上盘降水，上盘略热，偏下盘"}
    elif rise_ratio >= 0.75:
        return {"name": "市场热度", "score": 7, "direction": "upper",
                "reason": f"{rises}/{moved}家上盘升水，上盘遇冷，偏上盘"}
    elif rise_ratio >= 0.6:
        return {"name": "市场热度", "score": 6, "direction": "upper",
                "reason": f"{rises}/{moved}家上盘升水，上盘略冷，偏上盘"}
    else:
        return {"name": "市场热度", "score": 5, "direction": "neutral",
                "reason": f"水位分歧({drops}降/{rises}升)，热度不明"}


# ============================================================
# 近期状态量化指标 - 代码算客观数据，喂给 AI 推理(F1/F3)
# ============================================================

def _team_in_match(team: str, match_text: str) -> Optional[bool]:
    """判断本队在该场是主队还是客队。match格式: '主队比分:比分客队'
    返回 True=主场, False=客场, None=无法判断
    """
    if not team or not match_text:
        return None
    # 去掉比分标记后，队名出现在':'前为主、之后为客
    import re
    # 比分形如 0:3，定位中间的数字:数字
    m = re.search(r"\d+:\d+", match_text)
    if not m:
        # 退化：看队名在文本前半还是后半
        idx = match_text.find(team)
        if idx < 0:
            return None
        return idx < len(match_text) / 2
    before = match_text[:m.start()]
    return team in before


def build_form_metrics(records: List[Dict], team: str) -> Dict[str, Any]:
    """统计近期状态客观指标(供AI推理)

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

    F5的direction已经是逆向后的建议（上盘热→F5看lower，下盘热→F5看upper）。
    单关场次热门方被更多追捧，F6应放大F5的逆向信号。
    """
    if not is_single:
        return {"name": "单关修正", "score": 5, "direction": "neutral", "reason": "非单关，不触发"}

    # F5 direction="lower" 意味着上盘过热，单关放大此信号
    # F5 direction="upper" 意味着下盘过热，单关放大此信号
    if f5_direction == "lower" and f5_score >= 7:
        return {"name": "单关修正", "score": 8, "direction": "lower",
                "reason": "单关+上盘过热，加强逆向看下"}
    elif f5_direction == "upper" and f5_score >= 7:
        return {"name": "单关修正", "score": 8, "direction": "upper",
                "reason": "单关+下盘过热，加强逆向看上"}
    elif f5_direction == "lower" and f5_score >= 6:
        return {"name": "单关修正", "score": 6, "direction": "lower",
                "reason": "单关+上盘略热，偏看下"}
    elif f5_direction == "upper" and f5_score >= 6:
        return {"name": "单关修正", "score": 6, "direction": "upper",
                "reason": "单关+下盘略热，偏看上"}
    else:
        return {"name": "单关修正", "score": 5, "direction": "neutral",
                "reason": "单关但热度中性，不触发"}


# ============================================================
# F1 近期状态 / F2 交锋历史 / F3 实力定位 - DeepSeek 推理
# (代码喂量化指标; F4赔率变动、F5市场热度、F6单关 已纯量化计算)
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

3. **实力定位**：判断当前盘口与实力差距是否匹配。衡量"盘口开得合不合理"，不是"谁更强"。
   - 我提供了上盘方近期"被开出的平均盘口深度"作参考。本场盘口明显深于其历史均值→市场高估上盘方→偏下盘；明显浅于→上盘方被低估→偏上盘；基本匹配→neutral。
   - 关键：实力强 ≠ 上盘，盘口合理时给 neutral。

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
        parts.append(f"{home}排名: {match_info['home_rank']}")
    if match_info.get("away_rank"):
        parts.append(f"{away}排名: {match_info['away_rank']}")

    # 近期战绩数据
    if match_data:
        home_recent = match_data.get("homeRecent", [])[:10]
        away_recent = match_data.get("awayRecent", [])[:10]
        h2h = match_data.get("h2h", [])[:10]

        # 代码算好的客观指标(供F1近期状态推理)
        if home_recent or away_recent:
            parts.append("\n【近期状态客观指标】")
            if home_recent:
                hm = build_form_metrics(home_recent, home)
                label = f"{home}(主队{'，本场上盘' if is_home_let else '，本场下盘'})"
                parts.append(_format_form_metrics(hm, label))
            if away_recent:
                am = build_form_metrics(away_recent, away)
                label = f"{away}(客队{'，本场下盘' if is_home_let else '，本场上盘'})"
                parts.append(_format_form_metrics(am, label))

        # 上盘方近期平均盘口深度(供F3实力定位参考)
        upper_recent = home_recent if is_home_let else away_recent
        avg_h = _avg_abs_handicap(upper_recent)
        if avg_h is not None and handicap is not None:
            parts.append(f"\n【实力定位参考】{upper_team}近期被开出的平均让球深度约{avg_h:.2f}球，"
                         f"本场让{abs(float(handicap)):.2f}球")

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
            parts.append(f"\n双方近{len(h2h)}次交锋:")
            for r in h2h[:6]:
                import re
                match_text = re.sub(r'\[\d+\]', '', r.get('match', ''))
                parts.append(f"  {r.get('date','')} {match_text} {r.get('result','')} 盘口:{r.get('handicap','?')} 亚盘:{r.get('asianResult','')}")

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


def calc_prediction(factors: List[Dict[str, Any]]) -> Dict[str, Any]:
    """综合计算最终预测方向和置信度 - 净方向占比模型

    置信度拆为两个独立维度：
    - 一致性 consistency: 主导方向的权重 / 有方向因子总权重(0.5~1.0)
      反映"方向是否明确"，反向因子越少越高。六因子全同向 = 1.0。
    - 强度 avg_intensity: 主导方向因子的加权平均强度(0~1)
      反映"信号是否强烈"，因子分数越高越强。

    置信度 = base(一致性主导, 50~85) + 强度加成(0~12) - 数据缺失惩罚

    Args:
        factors: 6因子列表
    """
    upper_w = 0.0               # 上盘方向加权强度和
    lower_w = 0.0               # 下盘方向加权强度和
    upper_weight = 0.0          # 上盘因子权重和(不乘强度)
    lower_weight = 0.0          # 下盘因子权重和
    upper_count = 0
    lower_count = 0
    neutral_count = 0
    missing_count = 0

    for f in factors:
        name = f["name"]
        w = FACTOR_WEIGHTS.get(name, 1.0)
        fscore = f.get("score", 5)
        direction = f["direction"]

        # 修复F5/F6重复计权：F6同向于F5时打5折，避免市场热度信号被计两次
        if name == "单关修正" and direction != "neutral":
            f5 = next((x for x in factors if x["name"] == "市场热度"), None)
            if f5 and f5.get("direction") == direction:
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
                "neutral_count": neutral_count}

    # 确定主导方向
    if upper_w > lower_w:
        direction = "upper"
        dom_weight, dom_intensity_sum = upper_weight, upper_w
    elif lower_w > upper_w:
        direction = "lower"
        dom_weight, dom_intensity_sum = lower_weight, lower_w
    else:
        # 双向强度相等，方向不明
        return {"direction": "neutral", "confidence": 38, "score": 0.0,
                "neutral_count": neutral_count}

    # 维度1 一致性：主导方向权重占有方向因子总权重的比例(0.5~1.0)
    consistency = dom_weight / total_dir_weight

    # 维度2 强度：主导方向因子的加权平均强度(0~1)
    avg_intensity = dom_intensity_sum / dom_weight if dom_weight else 0

    # 维度3 参与度：有方向因子权重占全部因子总权重的比例(防止少数因子定高分)
    all_weight = sum(FACTOR_WEIGHTS.values())
    participation = min(1.0, total_dir_weight / all_weight)  # 0~1

    # base: 一致性映射到 50~85 (一致性0.5→50, 1.0→85)
    base = 50 + (consistency - 0.5) * 70
    # 强度加成: 0~12
    strength = avg_intensity * 12
    # 参与度惩罚: 参与判断的因子越少越降分。
    # participation>=0.6(约4因子)不罚；越少罚越多，最多-15
    participation_penalty = max(0.0, (0.6 - participation)) / 0.6 * 15
    # 数据缺失惩罚: 仅对拿不到数据的中性因子(每个-4，最多-10)
    missing_penalty = min(10, missing_count * 4)

    confidence = int(base + strength - participation_penalty - missing_penalty)
    confidence = max(35, min(95, confidence))

    return {
        "direction": direction,
        "confidence": confidence,
        "score": round((upper_w - lower_w) / total_dir_weight, 3),
        "neutral_count": neutral_count,
        "consistency": round(consistency, 3),
        "avg_intensity": round(avg_intensity, 3),
        "participation": round(participation, 3),
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
    else:
        dir_text = "上盘" if direction == "upper" else "下盘"
        parts.append(f"综合{len(factors)}项因子，建议方向: {dir_text}（{upper_team}{'赢盘' if direction == 'upper' else '输盘'}），置信度{conf}%。")

    return "。".join(parts)


def predict_match(match_info: Dict[str, Any], match_data: Optional[Dict] = None,
                  asian_data: Optional[List] = None) -> Dict[str, Any]:
    """完整预测流程

    Args:
        match_info: 比赛基本信息 (league, home_team, away_team, handicap, is_single, etc.)
        match_data: 500.com基本面数据 (h2h, homeRecent, awayRecent)
        asian_data: 500.com亚盘数据列表

    Returns:
        {"factors": [...], "prediction": {...}}
    """
    handicap = match_info.get("handicap")
    is_home_let = handicap is not None and float(handicap) < 0
    is_single = bool(match_info.get("is_single"))

    # F4 赔率变动：纯量化（盘口+水位综合）
    f4 = calc_factor4(asian_data or [], is_home_let)
    # F5 市场热度：纯量化（多公司水位一致性）+ 用户手动输入优先
    f5 = calc_factor5(asian_data or [], is_home_let, match_info.get("market_heat_desc"))

    # F1近期状态/F2交锋历史/F3实力定位：DeepSeek 推理
    # (代码已在 prompt 中提供近期积分、主客场、不败、赢盘率、平均盘口深度等客观指标)
    prompt = build_ai_prompt(match_info, match_data)
    ai_factors = call_deepseek_factors(prompt)

    f1 = next((f for f in ai_factors if f["name"] == "近期状态"), {"name": "近期状态", "score": 5, "direction": "neutral", "reason": "数据不足"})
    f2 = next((f for f in ai_factors if f["name"] == "交锋历史"), {"name": "交锋历史", "score": 5, "direction": "neutral", "reason": "数据不足"})
    f3 = next((f for f in ai_factors if f["name"] == "实力定位"), {"name": "实力定位", "score": 5, "direction": "neutral", "reason": "数据不足"})

    # F6: 单关修正（基于F5结果）
    f6 = calc_factor6(is_single, f5["direction"], f5["score"])

    # 组装所有因子(保持原顺序: F1近期状态 F2交锋 F3实力 F4赔率 F5热度 F6单关)
    all_factors = [f1, f2, f3, f4, f5, f6]

    # 综合计算(不使用盘口先验：竞彩整数盘的走水偏差不适用于真实亚盘小数盘口，
    # 会对每场比赛施加固定下盘推力，导致系统性偏向下盘)
    prediction = calc_prediction(all_factors)

    # 生成分析文本
    analysis = generate_analysis(all_factors, prediction, match_info)
    prediction["analysis"] = analysis

    return {"factors": all_factors, "prediction": prediction}
