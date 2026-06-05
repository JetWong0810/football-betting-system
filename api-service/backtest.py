"""
最小回测脚本 - 量化预测因子的真实命中率

用 2026 年历史比赛(有比分 + 竞彩让球赔率变动)回测核心量化信号。
目标：在投入更多因子前，先用数据验证"量化信号 vs 随机"到底有没有优势。

回测的信号：
  1. 盘口先验：每个盘口区间的上盘历史赢盘率(作为 baseline 概率)
  2. F4 赔率变动：竞彩让球主胜赔率(nspf win)的初末变化方向
     - 赔率下降(降水) = 资金看好该方向 = 看好上盘
     - 赔率上升(升水) = 不看好上盘

赢盘判定（系统内盘口约定：负值=主队让球）：
  adjusted = (home_score - away_score) + handicap
  handicap <= 0(主队让球, 主队=上盘): adjusted>0 上盘赢, <0 下盘赢, =0 走水
  handicap >  0(客队让球, 客队=上盘): adjusted>0 下盘赢, <0 上盘赢, =0 走水
"""

import pymysql
import settings


def get_conn():
    return pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)


def actual_cover(home_score, away_score, handicap):
    """返回实际赢盘方向: 'upper'/'lower'/'push'(走水)"""
    adjusted = (home_score - away_score) + float(handicap)
    if abs(adjusted) < 1e-9:
        return "push"
    if float(handicap) <= 0:
        # 主队让球, 主队=上盘
        return "upper" if adjusted > 0 else "lower"
    else:
        # 客队让球, 客队=上盘
        return "lower" if adjusted > 0 else "upper"


def load_matches(conn):
    """加载有比分+hhad盘口的历史比赛"""
    with conn.cursor() as c:
        c.execute("""
            SELECT m.match_id, m.home_score, m.away_score, m.league_name,
                   o.handicap
            FROM matches m
            JOIN odds_win_draw_lose o
              ON o.match_id = m.match_id AND o.odds_type = 'hhad'
            WHERE m.match_id LIKE 'jczq_%'
              AND m.home_score IS NOT NULL
              AND m.away_score IS NOT NULL
        """)
        return c.fetchall()


def load_odds_movement(conn):
    """加载每场比赛的让球主胜赔率(nspf win)初末值"""
    with conn.cursor() as c:
        c.execute("""
            SELECT h.match_id,
                   SUBSTRING_INDEX(GROUP_CONCAT(h.odds_win ORDER BY h.change_time ASC), ',', 1) AS first_win,
                   SUBSTRING_INDEX(GROUP_CONCAT(h.odds_win ORDER BY h.change_time DESC), ',', 1) AS last_win
            FROM jczq_odds_history h
            WHERE h.odds_type = 'nspf'
            GROUP BY h.match_id
        """)
        result = {}
        for r in c.fetchall():
            try:
                result[r["match_id"]] = {
                    "first": float(r["first_win"]),
                    "last": float(r["last_win"]),
                }
            except (ValueError, TypeError):
                pass
        return result


def run():
    conn = get_conn()
    matches = load_matches(conn)
    movements = load_odds_movement(conn)
    conn.close()

    print("=" * 64)
    print(f"回测样本: {len(matches)} 场 (有比分+盘口)")
    print(f"有赔率变动: {len(movements)} 场")
    print("=" * 64)

    # ============ 信号1: 盘口先验(整体上盘赢盘率) ============
    total = {"upper": 0, "lower": 0, "push": 0}
    by_handicap = {}  # handicap -> {upper,lower,push}

    for m in matches:
        cover = actual_cover(m["home_score"], m["away_score"], m["handicap"])
        total[cover] += 1
        hc = float(m["handicap"])
        by_handicap.setdefault(hc, {"upper": 0, "lower": 0, "push": 0})
        by_handicap[hc][cover] += 1

    decided = total["upper"] + total["lower"]
    print("\n【信号1: 盘口先验 - 整体赢盘分布】")
    print(f"  上盘赢: {total['upper']} ({total['upper']/len(matches)*100:.1f}%)")
    print(f"  下盘赢: {total['lower']} ({total['lower']/len(matches)*100:.1f}%)")
    print(f"  走水:   {total['push']} ({total['push']/len(matches)*100:.1f}%)")
    if decided:
        print(f"  非走水中上盘占比: {total['upper']/decided*100:.1f}%")

    print("\n  按盘口分桶上盘赢盘率:")
    for hc in sorted(by_handicap.keys()):
        d = by_handicap[hc]
        dec = d["upper"] + d["lower"]
        if dec >= 20:  # 样本足够才显示
            print(f"    让{hc:+.1f}: 上盘{d['upper']}/下盘{d['lower']}/走水{d['push']} "
                  f"-> 上盘赢盘率 {d['upper']/dec*100:.1f}% (n={dec})")

    # ============ 信号2: F4赔率变动(让球主胜赔率初末变化) ============
    # 赔率下降=降水=看好上盘; 上升=升水=不看好上盘
    # 注意: nspf主胜赔率对应的是"竞彩让球后主队赢", 需结合让球方向判断上盘
    print("\n【信号2: F4赔率变动命中率】")

    thresholds = [0.02, 0.05, 0.10]
    for th in thresholds:
        hit = 0
        miss = 0
        push = 0
        signal_count = 0

        for m in matches:
            mv = movements.get(m["match_id"])
            if not mv:
                continue
            delta = mv["last"] - mv["first"]  # 让球主胜赔率变化
            if abs(delta) < th:
                continue  # 信号太弱，跳过

            hc = float(m["handicap"])
            # nspf主胜赔率 = 让球后主队赢的赔率
            # 赔率下降(delta<0) = 看好"让球后主队赢"
            #   若主队让球(hc<=0, 主队=上盘): 看好上盘
            #   若客队让球(hc>0, 主队=下盘): 看好下盘
            if delta < 0:
                pred = "upper" if hc <= 0 else "lower"
            else:
                pred = "lower" if hc <= 0 else "upper"

            signal_count += 1
            cover = actual_cover(m["home_score"], m["away_score"], m["handicap"])
            if cover == "push":
                push += 1
            elif cover == pred:
                hit += 1
            else:
                miss += 1

        decided_sig = hit + miss
        if decided_sig:
            print(f"  阈值≥{th}: 触发{signal_count}场, 命中{hit}/{decided_sig} "
                  f"= {hit/decided_sig*100:.1f}% (走水{push})")
        else:
            print(f"  阈值≥{th}: 无有效信号")

    print("\n" + "=" * 64)
    print("解读:")
    print("  - 信号1是'纯买上盘'的基准命中率(先验)")
    print("  - 信号2命中率若明显高于信号1, 说明赔率变动有预测价值")
    print("  - 命中率≈50% 说明该信号接近随机, 不应高权重")
    print("=" * 64)


if __name__ == "__main__":
    run()
