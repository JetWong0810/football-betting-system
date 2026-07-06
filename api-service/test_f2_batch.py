"""F2交锋历史因子批量测试

对历史比赛批量运行F2因子（仅量化，不含AI），评估：
1. 有效性分布：多少比赛有足够交锋数据
2. 方向分布：upper/lower/neutral的比例
3. 命中率：F2预测方向 vs 实际赢盘结果
4. 各子因素独立命中率
5. 盘口变化分析的可靠性
"""

import sys
import time
import json
import pymysql
import settings

sys.path.insert(0, ".")
from predict_service import calc_factor2
from odds500_service import fetch_match_data, fetch_asian_handicap


def get_matches(limit=50):
    conn = pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as c:
        c.execute('''
            SELECT m.match_id, m.home_team_name, m.away_team_name, m.league_name,
                   m.fid_500, m.home_score, m.away_score, m.match_time,
                   o.handicap
            FROM matches m
            JOIN odds_win_draw_lose o ON o.match_id = m.match_id AND o.odds_type = 'hhad'
            WHERE m.fid_500 IS NOT NULL
              AND m.home_score IS NOT NULL
              AND m.away_score IS NOT NULL
            ORDER BY m.match_time DESC
            LIMIT %s
        ''', (limit,))
        rows = c.fetchall()
    conn.close()
    return rows


def actual_cover(home_score, away_score, handicap):
    """判断实际赢盘方向"""
    adjusted = (home_score - away_score) + float(handicap)
    if abs(adjusted) < 1e-9:
        return "push"
    if float(handicap) <= 0:
        return "upper" if adjusted > 0 else "lower"
    else:
        return "lower" if adjusted > 0 else "upper"


MAINSTREAM_BOOKS = ["Pinnacle", "Bet365", "皇冠", "威廉希尔", "澳门", "立博"]


def get_real_handicap(fid: str) -> float:
    """从500.com亚盘取主流公司即时盘口中位数（系统内: 负值=主队让）"""
    try:
        asian_data = fetch_asian_handicap(fid)
    except Exception:
        return None
    curr_handicaps = []
    for c in asian_data:
        if c.get("bookmaker") in MAINSTREAM_BOOKS:
            h = c.get("current", {}).get("handicap")
            if h is not None:
                curr_handicaps.append(float(h))
    if not curr_handicaps:
        all_h = [float(c.get("current", {}).get("handicap", 0))
                 for c in asian_data if c.get("current", {}).get("handicap") is not None]
        if all_h:
            all_h.sort()
            return -all_h[len(all_h) // 2]
        return None
    curr_handicaps.sort()
    return -curr_handicaps[len(curr_handicaps) // 2]


def run_test(matches):
    results = []
    total = len(matches)

    for idx, m in enumerate(matches):
        fid = m["fid_500"]
        home = m["home_team_name"]
        away = m["away_team_name"]
        home_score = m["home_score"]
        away_score = m["away_score"]

        # 获取真实亚盘盘口
        real_hcap = get_real_handicap(fid)
        if real_hcap is None:
            real_hcap = float(m["handicap"])
            hcap_source = "竞彩"
        else:
            hcap_source = "亚盘"

        actual = actual_cover(home_score, away_score, real_hcap)

        print(f"[{idx+1}/{total}] {home} vs {away} (盘口={real_hcap:+.2f}[{hcap_source}], "
              f"比分={home_score}:{away_score}, 实际={actual})")

        try:
            match_data = fetch_match_data(fid)
            time.sleep(0.3)
        except Exception as e:
            print(f"  ❌ 抓取失败: {e}")
            results.append({"match": f"{home} vs {away}", "error": str(e)})
            continue

        match_info = {
            "home_team": home,
            "away_team": away,
            "handicap": str(real_hcap),
            "league": m["league_name"],
        }

        f2 = calc_factor2(match_data, match_info, None)
        print(f"  F2: score={f2['score']} dir={f2['direction']} reason={f2['reason']}")
        if f2.get("details"):
            for d in f2["details"]:
                print(f"    {d['name']}: {d['direction']} - {d['desc']}")

        results.append({
            "match": f"{home} vs {away}",
            "handicap": real_hcap,
            "actual": actual,
            "f2_dir": f2["direction"],
            "f2_score": f2["score"],
            "f2_reason": f2["reason"],
            "details": f2.get("details", []),
            "h2h_count": len(match_data.get("h2h", [])),
        })

    return results


def analyze_results(results):
    valid = [r for r in results if "error" not in r]
    print("\n" + "=" * 70)
    print(f"F2交锋历史因子测试结果 (共{len(valid)}场有效)")
    print("=" * 70)

    # 1. 有效性分布
    has_h2h = [r for r in valid if r["h2h_count"] > 0]
    no_h2h = [r for r in valid if r["h2h_count"] == 0]
    print(f"\n[有效性] 有交锋记录: {len(has_h2h)}场, 无交锋: {len(no_h2h)}场")
    if has_h2h:
        avg_h2h = sum(r["h2h_count"] for r in has_h2h) / len(has_h2h)
        print(f"  平均交锋场次: {avg_h2h:.1f}")

    # 2. 方向分布
    dir_counts = {"upper": 0, "lower": 0, "neutral": 0}
    for r in valid:
        dir_counts[r["f2_dir"]] += 1
    print(f"\n[方向分布] 上盘={dir_counts['upper']} 下盘={dir_counts['lower']} 中性={dir_counts['neutral']}")
    total_decided = dir_counts['upper'] + dir_counts['lower']
    if total_decided:
        print(f"  有方向占比: {total_decided}/{len(valid)} = {total_decided/len(valid)*100:.0f}%")

    # 3. 总体命中率
    hit = miss = 0
    neutral_count = push_count = 0
    for r in valid:
        if r["f2_dir"] == "neutral":
            neutral_count += 1
            continue
        if r["actual"] == "push":
            push_count += 1
            continue
        if r["f2_dir"] == r["actual"]:
            hit += 1
        else:
            miss += 1

    decided = hit + miss
    if decided:
        print(f"\n[总体命中率] {hit}/{decided} = {hit/decided*100:.1f}%"
              f" (中性{neutral_count}场, 走水{push_count}场)")
    else:
        print("\n[总体命中率] 无有效预测")

    # 4. 按score分段命中率
    print("\n[按score分段]")
    for lo, hi, label in [(7, 10, "7-10(强信号)"), (5, 6, "5-6(弱/中性)")]:
        sub = [r for r in valid if lo <= r["f2_score"] <= hi
               and r["f2_dir"] != "neutral" and r["actual"] != "push"]
        if sub:
            sub_hit = sum(1 for r in sub if r["f2_dir"] == r["actual"])
            print(f"  {label}: {sub_hit}/{len(sub)} = {sub_hit/len(sub)*100:.1f}%")
        else:
            print(f"  {label}: 无样本")

    # 5. 各子因素独立命中率
    print("\n[子因素独立命中率]")
    sub_names = ["加权赢盘率", "盘口变化", "AI辅助"]
    for sn in sub_names:
        hits = misses = neutrals = 0
        for r in valid:
            if r["actual"] == "push":
                continue
            detail = next((d for d in r.get("details", []) if d["name"] == sn), None)
            if not detail:
                continue
            if detail["direction"] == "neutral":
                neutrals += 1
                continue
            if detail["direction"] == r["actual"]:
                hits += 1
            else:
                misses += 1
        dec = hits + misses
        rate = f"{hits/dec*100:.1f}%" if dec else "N/A"
        print(f"  {sn}: 命中{hits}/{dec}={rate} (中性{neutrals}场)")

    # 6. 有效性level vs 命中率
    print("\n[有效性等级 vs 命中率]")
    for level_desc, score_range in [("高有效(score>=7)", range(7, 11)),
                                     ("低有效(score=5-6)", range(5, 7))]:
        sub = [r for r in valid if r["f2_score"] in score_range
               and r["f2_dir"] != "neutral" and r["actual"] != "push"]
        if sub:
            sub_hit = sum(1 for r in sub if r["f2_dir"] == r["actual"])
            print(f"  {level_desc}: {sub_hit}/{len(sub)} = {sub_hit/len(sub)*100:.1f}%")

    # 7. 错误案例分析
    print("\n[⚠️ 方向错误的案例]")
    errors = [r for r in valid if r["f2_dir"] != "neutral"
              and r["actual"] != "push" and r["f2_dir"] != r["actual"]]
    for r in errors:
        print(f"  {r['match']} 盘口={r['handicap']:+.2f} | "
              f"F2={r['f2_dir']}(score={r['f2_score']}) 实际={r['actual']}")
        for d in r.get("details", []):
            if d["direction"] != "neutral":
                print(f"    {d['name']}: {d['direction']} - {d['desc']}")

    # 8. 正确案例
    print("\n[✓ 方向正确的案例]")
    corrects = [r for r in valid if r["f2_dir"] != "neutral"
                and r["actual"] != "push" and r["f2_dir"] == r["actual"]]
    for r in corrects[:10]:
        print(f"  {r['match']} 盘口={r['handicap']:+.2f} | "
              f"F2={r['f2_dir']}(score={r['f2_score']}) ✓")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50, help="测试比赛数量")
    args = parser.parse_args()

    print(f"F2交锋历史因子批量测试 (仅量化，不含AI) - {args.limit}场比赛")
    print()

    matches = get_matches(args.limit)
    print(f"获取到 {len(matches)} 场历史比赛\n")

    results = run_test(matches)
    analyze_results(results)
