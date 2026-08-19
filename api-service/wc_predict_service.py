"""世界杯专属预测服务 - 6因子体系

因子体系:
  F1 近期状态 (权重1.5) - 复用现有calc_factor1
  F2 实力定位 (权重1.0) - 复用现有calc_factor3
  F3 市场信号 (权重2.0) - 复用现有calc_factor4 (亚盘+欧赔变动)
  F4 市场热度 (权重2.0) - 复用现有calc_factor5 (水位一致性)
  F5 竞彩赔率 (权重1.5) - 竞彩官方初盘→终盘低赔变动方向
  F6 历史同赔 (权重1.5) - 匹配历史世界杯同赔率比赛结果分布
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from predict_service import (
    calc_factor1,
    calc_factor3,
    calc_factor4,
    calc_factor5,
    calc_factor6,
    calc_prediction,
    generate_analysis,
    build_ai_prompt,
    call_deepseek_factors,
    calc_factor_jczq_odds,
    _home_is_upper,
)
from wc_similar_odds import find_similar

logger = logging.getLogger(__name__)


def _fmt_handicap(v):
    """格式化盘口数值：0显示为0，正数加+号"""
    if v == 0 or v == -0.0:
        return "0"
    return f"+{v}" if v > 0 else str(v)

WC_FACTOR_WEIGHTS = {
    "近期状态": 1.5,
    "实力定位": 1.0,
    "市场信号": 2.0,
    "市场热度": 2.0,
    "竞彩赔率": 1.5,
    "历史同赔": 1.5,
    "单关修正": 1.5,
}


def calc_factor_similar_odds(jczq_company: Optional[Dict]) -> Dict[str, Any]:
    """F6 历史同赔: 匹配历史世界杯中赔率相近且变动方向一致的比赛

    匹配条件: 初盘低赔±0.05 + 低赔变动方向一致
    判定:
    - 匹配 < 3场: neutral, score=5
    - 低赔命中率 > 65%: upper, score=7
    - 低赔命中率 < 40%: lower, score=7
    - 其他: neutral, score=5
    """
    if not jczq_company:
        return {"name": "历史同赔", "score": 5, "direction": "neutral",
                "reason": "无竞彩赔率，无法匹配历史同赔", "details": []}

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
                "reason": "竞彩赔率不完整，无法匹配", "details": []}

    try:
        result = find_similar(open_win, open_draw, open_loss, close_win, close_draw, close_loss)
    except Exception as e:
        logger.warning(f"历史同赔查询失败: {e}")
        return {"name": "历史同赔", "score": 5, "direction": "neutral",
                "reason": f"查询异常: {e}", "details": []}

    stats = result.get("stats", {})
    matches = result.get("matches", [])
    query = result.get("query", {})
    total = stats.get("total", 0)

    if total < 3:
        return {"name": "历史同赔", "score": 5, "direction": "neutral",
                "reason": f"匹配到{total}场历史比赛，样本不足(需≥3场)",
                "details": [{"name": "匹配条件", "desc": f"低赔{query.get('low_open', 0):.2f}±0.05 方向{query.get('direction', '')}"}]}

    low_hit_pct = stats.get("low_hit_pct", 50)

    details = [
        {"name": "匹配条件", "desc": f"低赔{query.get('low_open', 0):.2f}({query.get('low_position', '')})±0.05 方向{query.get('direction', '')}"},
        {"name": "匹配场次", "desc": f"{total}场历史世界杯比赛"},
        {"name": "低赔命中", "desc": f"{stats.get('low_hit', 0)}/{total} ({low_hit_pct:.0f}%)"},
        {"name": "胜平负分布", "desc": f"主胜{stats.get('wins', 0)} 平{stats.get('draws', 0)} 客胜{stats.get('losses', 0)}"},
    ]

    if stats.get("ah_total", 0) > 0:
        details.append({"name": "亚盘分布", "desc": f"上盘{stats.get('ah_upper', 0)} 下盘{stats.get('ah_lower', 0)} (共{stats['ah_total']}场)"})
    if stats.get("ou_total", 0) > 0:
        details.append({"name": "大小球", "desc": f"大球{stats.get('ou_over', 0)} 小球{stats.get('ou_under', 0)} (共{stats['ou_total']}场)"})

    # 添加匹配比赛摘要(前5场)
    for m in matches[:5]:
        score_str = f"{m['home_score']}-{m['away_score']}"
        ah_str = f" 亚盘:{m.get('ah_close_handicap', '')}" if m.get('ah_company') else ""
        details.append({
            "name": f"{m['year']} {m['stage_cn']}",
            "desc": f"{m['home_team_cn']} {score_str} {m['away_team_cn']}{ah_str}"
        })

    if low_hit_pct > 65:
        direction = "upper"
        score = 7
        reason = f"历史同赔{total}场中低赔命中{low_hit_pct:.0f}%，热门稳定打出→偏上盘"
    elif low_hit_pct < 40:
        direction = "lower"
        score = 7
        reason = f"历史同赔{total}场中低赔命中仅{low_hit_pct:.0f}%，冷门频出→偏下盘"
    else:
        direction = "neutral"
        score = 5
        reason = f"历史同赔{total}场低赔命中{low_hit_pct:.0f}%，无明确倾向"

    # 构建详细比赛列表(用于前端弹窗展示)
    similar_matches = []
    for m in matches:
        hs, aws = m.get("home_score", 0), m.get("away_score", 0)
        # 判断亚盘结果: 主队让球值为正数，主队净胜 - 让球数 > 0 则上盘赢
        ah_result = None
        if m.get("ah_close_value") is not None:
            adjusted = (hs - aws) - m["ah_close_value"]
            if abs(adjusted) < 0.01:
                ah_result = "走水"
            elif adjusted > 0:
                ah_result = "上盘"
            else:
                ah_result = "下盘"
        # 判断大小球结果
        ou_result = None
        if m.get("ou_close_value") is not None:
            diff = (hs + aws) - m["ou_close_value"]
            if abs(diff) < 0.01:
                ou_result = "走水"
            elif diff > 0:
                ou_result = "大球"
            else:
                ou_result = "小球"
        # 比赛结果
        result_map = {"H": "主胜", "D": "平局", "A": "客胜"}
        similar_matches.append({
            "similarity": m.get("similarity", 0),
            "year": m.get("year"),
            "stage": m.get("stage_cn", ""),
            "homeTeam": m.get("home_team_cn", ""),
            "awayTeam": m.get("away_team_cn", ""),
            "score": f"{hs}-{aws}",
            "result": result_map.get(m.get("result"), ""),
            "openOdds": f"{m.get('open_win', 0):.2f}/{m.get('open_draw', 0):.2f}/{m.get('open_loss', 0):.2f}",
            "closeOdds": f"{m.get('close_win', 0):.2f}/{m.get('close_draw', 0):.2f}/{m.get('close_loss', 0):.2f}",
            "ahInitial": _fmt_handicap(-m["ah_initial_value"]) if m.get("ah_initial_value") is not None else "",
            "ahInitialOdds": f"{m.get('ah_initial_home', '')}/{m.get('ah_initial_away', '')}" if m.get("ah_initial_home") else "",
            "ahClose": _fmt_handicap(-m["ah_close_value"]) if m.get("ah_close_value") is not None else "",
            "ahCloseOdds": f"{m.get('ah_close_home', '')}/{m.get('ah_close_away', '')}" if m.get("ah_close_home") else "",
            "ahResult": ah_result,
            "ouInitialLine": m.get("ou_initial_line", ""),
            "ouInitialOdds": f"{m.get('ou_initial_over', '')}/{m.get('ou_initial_under', '')}" if m.get("ou_initial_over") else "",
            "ouCloseLine": m.get("ou_close_line", ""),
            "ouCloseOdds": f"{m.get('ou_close_over', '')}/{m.get('ou_close_under', '')}" if m.get("ou_close_over") else "",
            "ouResult": ou_result,
        })

    return {"name": "历史同赔", "score": score, "direction": direction,
            "reason": reason, "details": details, "matches": similar_matches}


def predict_wc_match(match_info: Dict[str, Any],
                     match_data: Optional[Dict] = None,
                     asian_data: Optional[List] = None,
                     euro_data: Optional[Dict] = None) -> Dict[str, Any]:
    """世界杯预测主流程"""
    handicap = match_info.get("handicap")
    is_home_let = _home_is_upper(match_info)

    # F3 市场信号 & F4 市场热度: 纯量化，不需要AI
    f3 = calc_factor4(asian_data or [], is_home_let, euro_data)
    f3["name"] = "市场信号"
    f4 = calc_factor5(asian_data or [], is_home_let, match_info.get("market_heat_desc"),
                     match_info.get("handicap"))
    f4["name"] = "市场热度"

    # F5 竞彩赔率 & F6 历史同赔: 从euro_data中提取竞彩官方数据
    jczq_company = None
    if euro_data and euro_data.get("companies"):
        jczq_company = next(
            (c for c in euro_data["companies"] if "竞彩" in c.get("bookmaker", "")),
            None
        )
    f5 = calc_factor_jczq_odds(jczq_company, home_is_upper=is_home_let)
    f6 = calc_factor_similar_odds(jczq_company)

    # F1 近期状态 & F2 实力定位: 需要AI辅助
    prompt = build_ai_prompt(match_info, match_data)
    ai_f1_list = []
    ai_f3_list = []

    def _safe_call(_prompt):
        try:
            return call_deepseek_factors(_prompt)
        except Exception as e:
            logger.warning(f"[wc_predict] AI调用异常: {e}")
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

    # F7 单关修正: 基于市场热度(f4)的结果
    is_single = bool(match_info.get("is_single"))
    f7 = calc_factor6(is_single, f4["direction"], f4["score"])

    all_factors = [f1, f2, f3, f4, f5, f6, f7]

    # 使用世界杯专用权重计算预测
    prediction = calc_prediction(all_factors, WC_FACTOR_WEIGHTS)
    analysis = generate_analysis(all_factors, prediction, match_info)
    prediction["analysis"] = analysis

    return {"factors": all_factors, "prediction": prediction}
