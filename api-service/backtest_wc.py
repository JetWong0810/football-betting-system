"""2018/2022世界杯回测脚本

回测逻辑:
- 使用纯量化因子(F3市场信号 + F4市场热度 + F5竞彩赔率 + F6历史同赔)
- F1近期状态和F2实力定位因依赖AI和近期数据无法回放，设为neutral
- 以亚盘终盘盘口为基准判定实际上下盘结果
- 对比预测方向与实际结果，统计命中率
"""

import sqlite3
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

from predict_service import calc_factor4, calc_factor5, calc_factor6, calc_prediction
from wc_predict_service import (
    calc_factor_jczq_odds, calc_factor_similar_odds, WC_FACTOR_WEIGHTS
)

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "worldcup_odds.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_matches(years: List[int]) -> List[Dict]:
    conn = get_conn()
    placeholders = ",".join("?" * len(years))
    rows = conn.execute(f"""
        SELECT id, year, stage, match_date, home_team, away_team,
               home_score, away_score, result
        FROM matches
        WHERE year IN ({placeholders})
          AND home_score IS NOT NULL
        ORDER BY year, match_date
    """, years).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_asian_data(match_id: int) -> List[Dict]:
    """加载亚盘数据，转换为 calc_factor4/calc_factor5 所需格式"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT company, initial_home_odds, initial_handicap, initial_handicap_value,
               initial_away_odds, close_home_odds, close_handicap, close_handicap_value,
               close_away_odds
        FROM wc_asian_handicap
        WHERE match_id = ?
    """, (match_id,)).fetchall()
    conn.close()

    result = []
    for r in rows:
        r = dict(r)
        result.append({
            "bookmaker": r["company"],
            "initial": {
                "handicap": r["initial_handicap_value"],
                "home": r["initial_home_odds"],
                "away": r["initial_away_odds"],
            },
            "current": {
                "handicap": r["close_handicap_value"],
                "home": r["close_home_odds"],
                "away": r["close_away_odds"],
            },
        })
    return result


def load_euro_data(match_id: int) -> Dict:
    """加载欧赔数据，转换为 calc_factor4 所需格式"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT company_name, odds_home_open, odds_draw_open, odds_away_open,
               odds_home_close, odds_draw_close, odds_away_close
        FROM odds_snapshot
        WHERE match_id = ?
    """, (match_id,)).fetchall()
    conn.close()

    companies = []
    for r in rows:
        r = dict(r)
        companies.append({
            "bookmaker": r["company_name"],
            "initial": {
                "win": r["odds_home_open"],
                "draw": r["odds_draw_open"],
                "lose": r["odds_away_open"],
            },
            "current": {
                "win": r["odds_home_close"],
                "draw": r["odds_draw_close"],
                "lose": r["odds_away_close"],
            },
        })
    return {"companies": companies}


def get_close_handicap(match_id: int) -> Optional[float]:
    """获取终盘亚盘盘口值(取香港马会或第一家)"""
    conn = get_conn()
    row = conn.execute("""
        SELECT close_handicap_value FROM wc_asian_handicap
        WHERE match_id = ?
        ORDER BY CASE company
            WHEN '香港马会' THEN 1
            WHEN 'Pinnacle' THEN 2
            WHEN 'Bet365' THEN 3
            WHEN '澳门' THEN 4
            ELSE 5 END
        LIMIT 1
    """, (match_id,)).fetchone()
    conn.close()
    return row["close_handicap_value"] if row else None


def actual_cover(home_score: int, away_score: int, handicap: float) -> str:
    """判定实际盘路: handicap_value是主队让球值(负=主让)"""
    adjusted = (home_score - away_score) + handicap
    if abs(adjusted) < 0.01:
        return "push"
    elif adjusted > 0:
        return "upper"
    else:
        return "lower"


def run_backtest(years: List[int], verbose: bool = False):
    matches = load_matches(years)
    print(f"\n{'='*70}")
    print(f"世界杯回测: {years}")
    print(f"{'='*70}")
    print(f"总比赛数: {len(matches)}")

    results = []
    skipped = 0

    for m in matches:
        match_id = m["id"]
        handicap_val = get_close_handicap(match_id)
        if handicap_val is None:
            skipped += 1
            continue

        asian_data = load_asian_data(match_id)
        euro_data = load_euro_data(match_id)

        if not asian_data:
            skipped += 1
            continue

        # 判定上下盘: handicap_value 负值=主队让球
        is_home_let = handicap_val < 0

        # --- 计算各因子 ---
        # F1 近期状态: 无法回测，设neutral
        f1 = {"name": "近期状态", "score": 5, "direction": "neutral", "reason": "回测跳过"}
        # F2 实力定位: 无法回测，设neutral
        f2 = {"name": "实力定位", "score": 5, "direction": "neutral", "reason": "回测跳过"}

        # F3 市场信号 (= predict_service.calc_factor4)
        f3 = calc_factor4(asian_data, is_home_let, euro_data)
        f3["name"] = "市场信号"

        # F4 市场热度 (= predict_service.calc_factor5)
        f4 = calc_factor5(asian_data, is_home_let, match_hc=handicap_val)
        f4["name"] = "市场热度"

        # F5 竞彩赔率
        jczq_company = None
        if euro_data and euro_data.get("companies"):
            jczq_company = next(
                (c for c in euro_data["companies"] if "竞彩" in c.get("bookmaker", "")),
                None
            )
        f5 = calc_factor_jczq_odds(jczq_company)

        # F6 历史同赔 (用当场之前的历史数据匹配)
        f6 = calc_factor_similar_odds(jczq_company)

        # F7 单关修正: 世界杯默认非单关
        f7 = calc_factor6(False, f4["direction"], f4["score"])

        all_factors = [f1, f2, f3, f4, f5, f6, f7]

        # 计算预测
        prediction = calc_prediction(all_factors, WC_FACTOR_WEIGHTS)
        pred_dir = prediction["direction"]
        confidence = prediction["confidence"]

        # 实际结果
        actual = actual_cover(m["home_score"], m["away_score"], handicap_val)

        results.append({
            "match_id": match_id,
            "year": m["year"],
            "stage": m["stage"],
            "home": m["home_team"],
            "away": m["away_team"],
            "score": f"{m['home_score']}-{m['away_score']}",
            "handicap": handicap_val,
            "actual": actual,
            "predicted": pred_dir,
            "confidence": confidence,
            "hit": pred_dir == actual if pred_dir != "neutral" and actual != "push" else None,
            "f3_dir": f3["direction"],
            "f3_score": f3["score"],
            "f4_dir": f4["direction"],
            "f4_score": f4["score"],
            "f5_dir": f5["direction"],
            "f5_score": f5["score"],
            "f6_dir": f6["direction"],
            "f6_score": f6["score"],
            "overall_reverse": prediction.get("overall_reverse", False),
        })

    # --- 统计 ---
    print(f"有效比赛(有亚盘): {len(results)}, 跳过: {skipped}")
    print()

    # 总体命中率(排除neutral预测和push实际)
    valid = [r for r in results if r["hit"] is not None]
    hits = [r for r in valid if r["hit"]]
    misses = [r for r in valid if not r["hit"]]
    neutral_pred = [r for r in results if r["predicted"] == "neutral"]
    push_actual = [r for r in results if r["actual"] == "push"]

    print(f"--- 总体统计 ---")
    print(f"给出方向: {len(valid)}场 (neutral跳过{len(neutral_pred)}场, 走水{len(push_actual)}场)")
    if valid:
        print(f"命中: {len(hits)}场, 未中: {len(misses)}场")
        print(f"命中率: {len(hits)/len(valid)*100:.1f}%")
    print()

    # 按年份
    for year in sorted(set(r["year"] for r in results)):
        yr = [r for r in valid if r["year"] == year]
        yr_hits = [r for r in yr if r["hit"]]
        yr_neutral = [r for r in results if r["year"] == year and r["predicted"] == "neutral"]
        print(f"  {year}: {len(yr_hits)}/{len(yr)}命中 ({len(yr_hits)/len(yr)*100:.1f}%) "
              f"[neutral {len(yr_neutral)}场]" if yr else f"  {year}: 无有效数据")

    print()

    # 按置信度分层
    print(f"--- 按置信度分层 ---")
    conf_bins = [(60, 100, ">=60%"), (50, 59, "50-59%"), (40, 49, "40-49%"), (35, 39, "35-39%")]
    for lo, hi, label in conf_bins:
        bin_matches = [r for r in valid if lo <= r["confidence"] <= hi]
        bin_hits = [r for r in bin_matches if r["hit"]]
        if bin_matches:
            print(f"  置信度{label}: {len(bin_hits)}/{len(bin_matches)} "
                  f"({len(bin_hits)/len(bin_matches)*100:.1f}%)")
        else:
            print(f"  置信度{label}: 0场")

    print()

    # 按阶段
    print(f"--- 按阶段 ---")
    stages = {"group": "小组赛", "round_of_16": "1/8决赛", "quarter": "1/4决赛",
              "semi": "半决赛", "third": "三四名", "final": "决赛"}
    for stage_key, stage_name in stages.items():
        st = [r for r in valid if r["stage"] == stage_key]
        st_hits = [r for r in st if r["hit"]]
        if st:
            print(f"  {stage_name}: {len(st_hits)}/{len(st)} ({len(st_hits)/len(st)*100:.1f}%)")

    print()

    # 各因子单独命中率
    # 注意: F4市场热度是逆向因子, direction表示哪边热, 预测时反向
    REVERSE_FACTOR_KEYS = {"f4"}
    print(f"--- 各因子单独信号命中率 ---")
    for factor_key, factor_name in [("f3", "F3市场信号"), ("f4", "F4市场热度(逆向)"),
                                     ("f5", "F5竞彩赔率"), ("f6", "F6历史同赔*")]:
        dir_key = f"{factor_key}_dir"
        f_valid = [r for r in results if r[dir_key] != "neutral" and r["actual"] != "push"]
        if factor_key in REVERSE_FACTOR_KEYS:
            # 逆向因子: direction=upper表示上盘热, 预测应为lower
            f_hits = [r for r in f_valid if r[dir_key] != r["actual"]]
        else:
            f_hits = [r for r in f_valid if r[dir_key] == r["actual"]]
        if f_valid:
            print(f"  {factor_name}: {len(f_hits)}/{len(f_valid)} "
                  f"({len(f_hits)/len(f_valid)*100:.1f}%) [有信号{len(f_valid)}场]")
        else:
            print(f"  {factor_name}: 无有效信号")

        # 高分因子(score >= 7)的命中率
        score_key = f"{factor_key}_score"
        f_strong = [r for r in results if r[score_key] >= 7 and r[dir_key] != "neutral" and r["actual"] != "push"]
        if factor_key in REVERSE_FACTOR_KEYS:
            f_strong_hits = [r for r in f_strong if r[dir_key] != r["actual"]]
        else:
            f_strong_hits = [r for r in f_strong if r[dir_key] == r["actual"]]
        if f_strong:
            print(f"    └ score>=7: {len(f_strong_hits)}/{len(f_strong)} "
                  f"({len(f_strong_hits)/len(f_strong)*100:.1f}%)")

    print()

    # 逆向触发统计
    reversed_matches = [r for r in results if r["overall_reverse"]]
    if reversed_matches:
        rev_valid = [r for r in reversed_matches if r["hit"] is not None]
        rev_hits = [r for r in rev_valid if r["hit"]]
        print(f"--- 整体逆向触发 ---")
        print(f"  触发{len(reversed_matches)}场, 有效{len(rev_valid)}场, "
              f"命中{len(rev_hits)}场 ({len(rev_hits)/len(rev_valid)*100:.1f}%)" if rev_valid else
              f"  触发{len(reversed_matches)}场, 无有效判定")
        print()

    # 逐场详情(verbose)
    if verbose:
        print(f"\n{'='*70}")
        print(f"逐场详情")
        print(f"{'='*70}")
        for r in results:
            hit_mark = "V" if r["hit"] else ("X" if r["hit"] is False else "-")
            handicap_str = f"{r['handicap']:+.2f}" if r["handicap"] else "0"
            factors_str = (f"F3:{r['f3_dir'][0]}{r['f3_score']} "
                          f"F4:{r['f4_dir'][0]}{r['f4_score']} "
                          f"F5:{r['f5_dir'][0]}{r['f5_score']} "
                          f"F6:{r['f6_dir'][0]}{r['f6_score']}")
            rev_str = " [REV]" if r["overall_reverse"] else ""
            print(f"[{hit_mark}] {r['year']} {r['home']:15s} {r['score']} {r['away']:15s} "
                  f"盘口{handicap_str} 实际:{r['actual']:5s} "
                  f"预测:{r['predicted']:7s}({r['confidence']}%) "
                  f"{factors_str}{rev_str}")

    return results


def run_backtest_no_f6(years: List[int]):
    """不含F6的回测(消除历史同赔的数据泄露问题)"""
    matches = load_matches(years)
    print(f"\n{'='*70}")
    print(f"纯净回测(不含F6历史同赔): {years}")
    print(f"说明: F6使用全量历史池(含2018/2022自身数据)存在数据泄露")
    print(f"{'='*70}")

    results = []
    skipped = 0

    for m in matches:
        match_id = m["id"]
        handicap_val = get_close_handicap(match_id)
        if handicap_val is None:
            skipped += 1
            continue

        asian_data = load_asian_data(match_id)
        euro_data = load_euro_data(match_id)

        if not asian_data:
            skipped += 1
            continue

        is_home_let = handicap_val < 0

        f1 = {"name": "近期状态", "score": 5, "direction": "neutral", "reason": "回测跳过"}
        f2 = {"name": "实力定位", "score": 5, "direction": "neutral", "reason": "回测跳过"}

        f3 = calc_factor4(asian_data, is_home_let, euro_data)
        f3["name"] = "市场信号"
        f4 = calc_factor5(asian_data, is_home_let, match_hc=handicap_val)
        f4["name"] = "市场热度"

        jczq_company = None
        if euro_data and euro_data.get("companies"):
            jczq_company = next(
                (c for c in euro_data["companies"] if "竞彩" in c.get("bookmaker", "")),
                None
            )
        f5 = calc_factor_jczq_odds(jczq_company)

        # 不使用F6
        f6 = {"name": "历史同赔", "score": 5, "direction": "neutral", "reason": "回测排除"}
        f7 = calc_factor6(False, f4["direction"], f4["score"])

        all_factors = [f1, f2, f3, f4, f5, f6, f7]
        prediction = calc_prediction(all_factors, WC_FACTOR_WEIGHTS)
        pred_dir = prediction["direction"]
        confidence = prediction["confidence"]

        actual = actual_cover(m["home_score"], m["away_score"], handicap_val)
        results.append({
            "year": m["year"],
            "actual": actual,
            "predicted": pred_dir,
            "confidence": confidence,
            "hit": pred_dir == actual if pred_dir != "neutral" and actual != "push" else None,
        })

    valid = [r for r in results if r["hit"] is not None]
    hits = [r for r in valid if r["hit"]]
    neutral_pred = [r for r in results if r["predicted"] == "neutral"]

    print(f"有效比赛: {len(results)}场")
    print(f"给出方向: {len(valid)}场 (neutral跳过{len(neutral_pred)}场)")
    if valid:
        print(f"命中: {len(hits)}/{len(valid)} = {len(hits)/len(valid)*100:.1f}%")
    print()

    # 按置信度分层
    print(f"按置信度:")
    conf_bins = [(60, 100, ">=60%"), (50, 59, "50-59%"), (40, 49, "40-49%"), (35, 39, "35-39%")]
    for lo, hi, label in conf_bins:
        bin_matches = [r for r in valid if lo <= r["confidence"] <= hi]
        bin_hits = [r for r in bin_matches if r["hit"]]
        if bin_matches:
            print(f"  置信度{label}: {len(bin_hits)}/{len(bin_matches)} "
                  f"({len(bin_hits)/len(bin_matches)*100:.1f}%)")

    # 按年份
    for year in sorted(set(r["year"] for r in results)):
        yr = [r for r in valid if r["year"] == year]
        yr_hits = [r for r in yr if r["hit"]]
        if yr:
            print(f"  {year}: {len(yr_hits)}/{len(yr)} ({len(yr_hits)/len(yr)*100:.1f}%)")


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    all_results = run_backtest([2018, 2022], verbose=verbose)
    run_backtest_no_f6([2018, 2022])
