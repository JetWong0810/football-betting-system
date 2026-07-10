"""
F1/F2 历史回测 - 用本地重建的基本面数据验证近期状态/交锋因子的方向命中率

样本: 五大联赛国家(英超/英冠/西甲/西乙/意甲/意乙/德甲/德乙/法甲/法乙)竞彩完赛比赛,
      双方队名在 team_history_matches 中可匹配。
数据: build_local_match_data 重建 homeRecent/awayRecent/h2h -> calc_factor1/calc_factor2(AI子因素跳过)
对照: 实际赢盘方向 actual_cover(home_score, away_score, hhad_handicap)
"""

from collections import defaultdict
from typing import Dict, List, Optional

import pymysql

import settings
from local_match_data import build_local_match_data
from predict_service import calc_factor1, calc_factor2

FIVE_LEAGUES = ('英超', '西甲', '意甲', '德甲', '法甲',
                '英冠', '西乙', '意乙', '德乙', '法乙')


def get_conn():
    return pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)


def actual_cover(home_score: int, away_score: int, handicap: float) -> str:
    """实际赢盘方向: upper/lower/push。负盘=主让=主队上盘。"""
    adjusted = (home_score - away_score) + float(handicap)
    if abs(adjusted) < 1e-9:
        return "push"
    if float(handicap) <= 0:
        return "upper" if adjusted > 0 else "lower"
    return "lower" if adjusted > 0 else "upper"


def load_matches(conn) -> List[Dict]:
    """加载五大联赛竞彩完赛比赛 + hhad盘口 + 双方在历史库可匹配"""
    sql = """
        SELECT m.match_id, m.match_date, m.league_name, m.home_team_name, m.away_team_name,
               m.home_score, m.away_score, o.handicap
        FROM matches m
        JOIN odds_win_draw_lose o ON o.match_id = m.match_id AND o.odds_type = 'hhad'
        WHERE m.match_id LIKE 'jczq_%%'
          AND m.league_name IN ('英超','西甲','意甲','德甲','法甲','英冠','西乙','意乙','德乙','法乙')
          AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
          AND o.handicap IS NOT NULL
          AND EXISTS(SELECT 1 FROM team_history_matches t WHERE t.home_team_cn = m.home_team_name
                     OR t.away_team_cn = m.home_team_name)
          AND EXISTS(SELECT 1 FROM team_history_matches t WHERE t.home_team_cn = m.away_team_name
                     OR t.away_team_cn = m.away_team_name)
        ORDER BY m.match_date
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return list(cur.fetchall())


def run():
    conn = get_conn()
    try:
        matches = load_matches(conn)
    finally:
        # 回测期间需要一个独立连接给 build_local_match_data
        pass
    print("=" * 64)
    print(f"回测样本: {len(matches)} 场五大联赛竞彩完赛比赛")
    print("=" * 64)

    data_conn = get_conn()
    stats = {
        "f1": {"hit": 0, "miss": 0, "push": 0, "neutral": 0, "total": 0},
        "f2": {"hit": 0, "miss": 0, "push": 0, "neutral": 0, "total": 0},
    }
    f1_by_hc = defaultdict(lambda: {"hit": 0, "miss": 0, "decided": 0})
    f2_by_hc = defaultdict(lambda: {"hit": 0, "miss": 0, "decided": 0})
    f1_by_lg = defaultdict(lambda: {"hit": 0, "miss": 0, "decided": 0})
    f2_by_lg = defaultdict(lambda: {"hit": 0, "miss": 0, "decided": 0})
    both_agree = {"hit": 0, "miss": 0, "decided": 0}

    try:
        for i, m in enumerate(matches):
            if i % 500 == 0 and i > 0:
                print(f"  进度 {i}/{len(matches)}...")
            match_info = {
                "handicap": float(m["handicap"]),
                "home_team": m["home_team_name"],
                "away_team": m["away_team_name"],
                "match_date": str(m["match_date"]),
            }
            try:
                md = build_local_match_data(m["home_team_name"], m["away_team_name"],
                                            str(m["match_date"]), conn=data_conn)
            except Exception:
                continue

            cover = actual_cover(m["home_score"], m["away_score"], float(m["handicap"]))

            f1 = calc_factor1(md, match_info, ai_f1_list=None)
            f2 = calc_factor2(md, match_info, ai_f2_list=None)

            for name, f, st, by_hc, by_lg in [
                ("f1", f1, stats["f1"], f1_by_hc, f1_by_lg),
                ("f2", f2, stats["f2"], f2_by_hc, f2_by_lg),
            ]:
                st["total"] += 1
                d = f.get("direction", "neutral")
                if d == "neutral":
                    st["neutral"] += 1
                    continue
                if cover == "push":
                    st["push"] += 1
                    continue
                st_decided = st["hit"] + st["miss"]
                if d == cover:
                    st["hit"] += 1
                    by_hc[float(m["handicap"])]["hit"] += 1
                    by_lg[m["league_name"]]["hit"] += 1
                else:
                    st["miss"] += 1
                    by_hc[float(m["handicap"])]["miss"] += 1
                    by_lg[m["league_name"]]["miss"] += 1
                by_hc[float(m["handicap"])]["decided"] += 1
                by_lg[m["league_name"]]["decided"] += 1

            # 两因子同向且命中
            d1, d2 = f1.get("direction", "neutral"), f2.get("direction", "neutral")
            if d1 != "neutral" and d1 == d2 and cover != "push":
                both_agree["decided"] += 1
                if d1 == cover:
                    both_agree["hit"] += 1
                else:
                    both_agree["miss"] += 1
    finally:
        data_conn.close()

    # ============ 输出 ============
    print("\n" + "=" * 64)
    print("回测结果")
    print("=" * 64)

    for name, st in [("F1 近期状态", stats["f1"]), ("F2 交锋历史", stats["f2"])]:
        decided = st["hit"] + st["miss"]
        rate = st["hit"] / decided * 100 if decided else 0
        print(f"\n【{name}】")
        print(f"  总样本 {st['total']} | 有方向 {decided} | 命中 {st['hit']} | 未中 {st['miss']} | "
              f"走水 {st['push']} | 中性 {st['neutral']}")
        print(f"  命中率: {rate:.1f}% (基准50%)")

    print(f"\n【F1+F2 同向(两因子一致)】")
    ba_decided = both_agree["hit"] + both_agree["miss"]
    ba_rate = both_agree["hit"] / ba_decided * 100 if ba_decided else 0
    print(f"  同向场次 {ba_decided} | 命中 {both_agree['hit']} | 命中率 {ba_rate:.1f}%")

    print(f"\n【F2 按盘口分桶(样本≥50)】")
    for hc in sorted(f2_by_hc.keys()):
        d = f2_by_hc[hc]
        if d["decided"] >= 50:
            print(f"  让{hc:+.1f}: {d['hit']}/{d['decided']} = {d['hit']/d['decided']*100:.1f}%")

    print(f"\n【F2 按联赛】")
    for lg in sorted(f2_by_lg.keys(), key=lambda x: -f2_by_lg[x]["decided"]):
        d = f2_by_lg[lg]
        if d["decided"] >= 20:
            print(f"  {lg}: {d['hit']}/{d['decided']} = {d['hit']/d['decided']*100:.1f}%")

    print(f"\n【F1 按联赛】")
    for lg in sorted(f1_by_lg.keys(), key=lambda x: -f1_by_lg[x]["decided"]):
        d = f1_by_lg[lg]
        if d["decided"] >= 20:
            print(f"  {lg}: {d['hit']}/{d['decided']} = {d['hit']/d['decided']*100:.1f}%")


if __name__ == "__main__":
    run()
