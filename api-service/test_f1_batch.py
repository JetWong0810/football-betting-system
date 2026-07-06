"""F1近期状态因子批量测试

对历史比赛批量运行F1因子，评估：
1. 量化子因素（3个）的方向分布和稳定性
2. 含AI的完整F1（3次调用取多数）的稳定性
3. F1预测方向 vs 实际赢盘结果的命中率
"""

import sys
import time
import pymysql
import settings

sys.path.insert(0, ".")
from predict_service import calc_factor1, _build_role_cover_metrics, _weighted_ppg, _team_in_match
from odds500_service import fetch_match_data


def get_matches(limit=30):
    conn = pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as c:
        c.execute('''
            SELECT m.match_id, m.home_team_name, m.away_team_name, m.league_name, m.fid_500,
                   m.home_score, m.away_score, o.handicap
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
    adjusted = (home_score - away_score) + float(handicap)
    if abs(adjusted) < 1e-9:
        return "push"
    if float(handicap) <= 0:
        return "upper" if adjusted > 0 else "lower"
    else:
        return "lower" if adjusted > 0 else "upper"


def run_test(matches, with_ai=False, ai_rounds=1):
    """对每场比赛运行F1因子

    Args:
        with_ai: 是否调用AI
        ai_rounds: 调用AI时重复几轮（用于测试稳定性）
    """
    from predict_service import build_ai_prompt, _get_client, DEEPSEEK_MODEL
    import json

    results = []
    total = len(matches)

    for idx, m in enumerate(matches):
        fid = m["fid_500"]
        home = m["home_team_name"]
        away = m["away_team_name"]
        handicap = float(m["handicap"])
        home_score = m["home_score"]
        away_score = m["away_score"]
        actual = actual_cover(home_score, away_score, m["handicap"])

        print(f"\n[{idx+1}/{total}] {home} vs {away} (fid={fid}, 盘口={handicap:+.1f}, 比分={home_score}:{away_score}, 实际={actual})")

        # 抓取基本面数据
        try:
            match_data = fetch_match_data(fid)
            time.sleep(0.5)
        except Exception as e:
            print(f"  ❌ 抓取失败: {e}")
            results.append({"match": f"{home} vs {away}", "error": str(e)})
            continue

        match_info = {
            "home_team": home,
            "away_team": away,
            "handicap": m["handicap"],
            "league": m["league_name"],
        }

        if not with_ai:
            # 只测量化部分（不调用AI）
            f1 = calc_factor1(match_data, match_info, ai_f1_list=None)
            print(f"  F1: score={f1['score']} dir={f1['direction']} reason={f1['reason']}")
            if f1.get("details"):
                for d in f1["details"]:
                    print(f"    {d['name']}: {d['direction']} - {d['desc']}")
            results.append({
                "match": f"{home} vs {away}",
                "handicap": handicap,
                "actual": actual,
                "f1_dir": f1["direction"],
                "f1_score": f1["score"],
                "f1_reason": f1["reason"],
                "details": f1.get("details", []),
            })
        else:
            # 含AI，重复ai_rounds轮
            round_results = []
            for rnd in range(ai_rounds):
                ai_f1_list = []
                try:
                    client = _get_client()
                    prompt = build_ai_prompt(match_info, match_data)
                    for call_i in range(3):
                        resp = client.chat.completions.create(
                            model=DEEPSEEK_MODEL,
                            messages=[
                                {"role": "system", "content": "你是一个专业的足球亚盘分析师。"},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0.3,
                        )
                        text = resp.choices[0].message.content.strip()
                        if text.startswith("```"):
                            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                        data = json.loads(text)
                        factors = data.get("factors", [])
                        ai_f1 = next((f for f in factors if f["name"] == "近期状态"), None)
                        if ai_f1:
                            ai_f1_list.append(ai_f1)
                        time.sleep(0.3)
                except Exception as e:
                    print(f"  ⚠️ AI调用失败(轮{rnd+1}): {e}")

                f1 = calc_factor1(match_data, match_info, ai_f1_list or None)
                round_results.append(f1)
                if ai_rounds > 1:
                    print(f"  轮{rnd+1}: score={f1['score']} dir={f1['direction']}")

            # 检查稳定性
            dirs = [r["direction"] for r in round_results]
            stable = len(set(dirs)) == 1
            final = round_results[0]
            print(f"  F1最终: score={final['score']} dir={final['direction']} 稳定={stable} dirs={dirs}")

            results.append({
                "match": f"{home} vs {away}",
                "handicap": handicap,
                "actual": actual,
                "f1_dir": final["direction"],
                "f1_score": final["score"],
                "stable": stable,
                "all_dirs": dirs,
            })

    return results


def analyze_results(results, with_ai=False):
    """分析测试结果"""
    valid = [r for r in results if "error" not in r]
    print("\n" + "=" * 70)
    print(f"测试结果汇总 (共{len(valid)}场有效)")
    print("=" * 70)

    # 方向分布
    dir_counts = {"upper": 0, "lower": 0, "neutral": 0}
    for r in valid:
        dir_counts[r["f1_dir"]] += 1
    print(f"\nF1方向分布: 上盘={dir_counts['upper']} 下盘={dir_counts['lower']} 中性={dir_counts['neutral']}")

    # 命中率（排除neutral和走水）
    hit = miss = 0
    neutral_count = 0
    push_count = 0
    for r in valid:
        if r["f1_dir"] == "neutral":
            neutral_count += 1
            continue
        if r["actual"] == "push":
            push_count += 1
            continue
        if r["f1_dir"] == r["actual"]:
            hit += 1
        else:
            miss += 1

    decided = hit + miss
    if decided:
        print(f"\n命中率: {hit}/{decided} = {hit/decided*100:.1f}% (中性{neutral_count}场, 走水{push_count}场)")
    else:
        print("\n无有效预测（全部中性或走水）")

    # 按分数段分析命中率
    print("\n按F1 score分段:")
    for score_range, label in [(range(7, 11), "7-10(强信号)"), (range(5, 7), "5-6(弱/中性)")]:
        sub = [r for r in valid if r["f1_score"] in score_range and r["f1_dir"] != "neutral" and r["actual"] != "push"]
        if sub:
            sub_hit = sum(1 for r in sub if r["f1_dir"] == r["actual"])
            print(f"  {label}: {sub_hit}/{len(sub)} = {sub_hit/len(sub)*100:.1f}%")

    # 子因素分析（仅量化模式）
    if not with_ai and valid and "details" in valid[0]:
        print("\n各子因素方向分布:")
        sub_names = ["加权场均分", "角色赢盘率", "主客场匹配", "AI综合"]
        for sn in sub_names:
            counts = {"upper": 0, "lower": 0, "neutral": 0}
            hits = misses = 0
            for r in valid:
                detail = next((d for d in r.get("details", []) if d["name"] == sn), None)
                if detail:
                    counts[detail["direction"]] += 1
                    if detail["direction"] != "neutral" and r["actual"] != "push":
                        if detail["direction"] == r["actual"]:
                            hits += 1
                        else:
                            misses += 1
            dec = hits + misses
            hit_rate = f"{hits/dec*100:.1f}%" if dec else "N/A"
            print(f"  {sn}: ↑{counts['upper']} ↓{counts['lower']} ={counts['neutral']} | 命中率={hit_rate} ({hits}/{dec})")

    # 稳定性（AI模式）
    if with_ai:
        stable_count = sum(1 for r in valid if r.get("stable", True))
        print(f"\n稳定性: {stable_count}/{len(valid)} = {stable_count/len(valid)*100:.0f}%")

    # 错误的高分预测（重点关注）
    print("\n⚠️ 高分错误（score>=7但方向错误）:")
    for r in valid:
        if r["f1_score"] >= 7 and r["f1_dir"] != "neutral" and r["actual"] != "push" and r["f1_dir"] != r["actual"]:
            print(f"  {r['match']} 盘口={r['handicap']:+.1f} | F1={r['f1_dir']}(score={r['f1_score']}) 实际={r['actual']}")
            if "details" in r:
                for d in r["details"]:
                    if d["direction"] != "neutral":
                        print(f"    {d['name']}: {d['direction']} - {d['desc']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30, help="测试比赛数量")
    parser.add_argument("--ai", action="store_true", help="包含AI子因素")
    parser.add_argument("--rounds", type=int, default=1, help="AI模式重复轮数(测稳定性)")
    args = parser.parse_args()

    print(f"F1因子批量测试 - {'含AI' if args.ai else '仅量化'} - {args.limit}场比赛")
    if args.ai:
        print(f"  AI重复轮数: {args.rounds}")
    print()

    matches = get_matches(args.limit)
    print(f"获取到 {len(matches)} 场历史比赛")

    results = run_test(matches, with_ai=args.ai, ai_rounds=args.rounds)
    analyze_results(results, with_ai=args.ai)
