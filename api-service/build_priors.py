"""
计算并落库盘口先验 - handicap_priors 表

基于 2026 年历史比赛(有比分+竞彩让球盘口)统计每个盘口的赢盘分布。
先验用于 calc_prediction 作为方向基准偏移。

口径说明：
  - 先验按竞彩整数盘口分桶（本地历史数据只有整数盘）
  - decided_upper_rate = 上盘赢 / (上盘赢 + 下盘赢)，排除走水
  - 实际预测用的是真实亚盘小数盘口，应用时按符号+深度映射到最近的盘口桶
  - 小样本(decided < 50)的桶不可靠，应用时回退到全局先验
"""

import pymysql
import settings


def actual_cover(home_score, away_score, handicap):
    """返回实际赢盘方向: upper/lower/push"""
    adjusted = (home_score - away_score) + float(handicap)
    if abs(adjusted) < 1e-9:
        return "push"
    if float(handicap) <= 0:
        return "upper" if adjusted > 0 else "lower"
    else:
        return "lower" if adjusted > 0 else "upper"


def ensure_table(conn):
    with conn.cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS handicap_priors (
                handicap DECIMAL(4,1) PRIMARY KEY COMMENT '竞彩让球盘口',
                upper_count INT NOT NULL COMMENT '上盘赢场次',
                lower_count INT NOT NULL COMMENT '下盘赢场次',
                push_count INT NOT NULL COMMENT '走水场次',
                total_count INT NOT NULL COMMENT '总场次',
                decided_upper_rate DECIMAL(5,4) COMMENT '排除走水后上盘赢盘率',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
    conn.commit()


def run():
    conn = pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    ensure_table(conn)

    with conn.cursor() as c:
        c.execute("""
            SELECT m.home_score hs, m.away_score aws, o.handicap hc
            FROM matches m
            JOIN odds_win_draw_lose o ON o.match_id = m.match_id AND o.odds_type = 'hhad'
            WHERE m.match_id LIKE 'jczq_%' AND m.home_score IS NOT NULL
        """)
        rows = c.fetchall()

    by_hc = {}
    overall = {"upper": 0, "lower": 0, "push": 0}
    for r in rows:
        hc = float(r["hc"])
        cover = actual_cover(r["hs"], r["aws"], hc)
        by_hc.setdefault(hc, {"upper": 0, "lower": 0, "push": 0})
        by_hc[hc][cover] += 1
        overall[cover] += 1

    # 写入每个盘口
    with conn.cursor() as c:
        for hc in sorted(by_hc.keys()):
            d = by_hc[hc]
            total = d["upper"] + d["lower"] + d["push"]
            decided = d["upper"] + d["lower"]
            rate = round(d["upper"] / decided, 4) if decided else None
            c.execute("""
                INSERT INTO handicap_priors
                (handicap, upper_count, lower_count, push_count, total_count, decided_upper_rate)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    upper_count=VALUES(upper_count), lower_count=VALUES(lower_count),
                    push_count=VALUES(push_count), total_count=VALUES(total_count),
                    decided_upper_rate=VALUES(decided_upper_rate)
            """, (hc, d["upper"], d["lower"], d["push"], total, rate))

        # 全局先验存为 handicap=0 (作为回退基准)
        g_decided = overall["upper"] + overall["lower"]
        g_rate = round(overall["upper"] / g_decided, 4) if g_decided else None
        g_total = sum(overall.values())
        c.execute("""
            INSERT INTO handicap_priors
            (handicap, upper_count, lower_count, push_count, total_count, decided_upper_rate)
            VALUES (0, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                upper_count=VALUES(upper_count), lower_count=VALUES(lower_count),
                push_count=VALUES(push_count), total_count=VALUES(total_count),
                decided_upper_rate=VALUES(decided_upper_rate)
        """, (overall["upper"], overall["lower"], overall["push"], g_total, g_rate))

    conn.commit()

    # 输出确认
    with conn.cursor() as c:
        c.execute("SELECT * FROM handicap_priors ORDER BY handicap")
        print("=" * 60)
        print("盘口先验已落库 (handicap_priors):")
        for r in c.fetchall():
            tag = " [全局基准]" if float(r["handicap"]) == 0 else ""
            print(f"  让{float(r['handicap']):+.1f}: 上盘{r['upper_count']}/下盘{r['lower_count']}/"
                  f"走水{r['push_count']} 上盘赢盘率={r['decided_upper_rate']}{tag}")
        print("=" * 60)

    conn.close()


if __name__ == "__main__":
    run()
