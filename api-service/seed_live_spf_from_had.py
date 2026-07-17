"""一次性: 为缺失 spf 变动的 live 比赛从 odds_win_draw_lose.had 补种一条 spf 快照。

背景: 上次 spf 清理删掉了 live 'spf' 变动行(>=2026-06)。sporttery scraper 只在赔率变化时
追加变动行, 首条快照对部分场次未落库 → 230 场 live 无 spf 变动, 其中 203 场在
odds_win_draw_lose 有 had(=raw 胜平负, 即 spf)当前值。用 had 值补种一条 spf 行
(initial==current), 配合 F6 无变动方向降级逻辑, 让历史同赔有数据可匹配。

27 场无 had(竞彩未开盘胜平负, 只有让球胜平负 hhad) 无法补种, 留空。

幂等: 仅对 jczq_odds_history 无 spf 行的场次补种; 已有则跳过。
"""
import pymysql
import settings

SEED_SQL = """INSERT IGNORE INTO jczq_odds_history
    (match_id, odds_type, odds_win, odds_draw, odds_loss,
     direction_win, direction_draw, direction_loss, change_time)
    VALUES (%s, 'spf', %s, %s, %s, 0, 0, 0, %s)"""

FIND_SQL = """
SELECT m.match_id, m.odds_update_time, o.win_odds, o.draw_odds, o.lose_odds
FROM matches m
JOIN odds_win_draw_lose o ON o.match_id = m.match_id AND o.odds_type = 'had'
WHERE m.match_id NOT LIKE 'jczq_%%' AND m.match_date >= '2026-06-01'
  AND NOT EXISTS (SELECT 1 FROM jczq_odds_history h
                 WHERE h.match_id = m.match_id AND h.odds_type = 'spf')
ORDER BY m.match_date DESC
"""


def main():
    conn = pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(FIND_SQL)
            rows = cur.fetchall()
        print(f"待补种 spf 的 live 场次: {len(rows)}")
        batch = []
        for r in rows:
            win = float(r["win_odds"] or 0)
            draw = float(r["draw_odds"] or 0)
            lose = float(r["lose_odds"] or 0)
            if win <= 0 and draw <= 0 and lose <= 0:
                continue
            ct = r.get("odds_update_time") or "2026-07-17 00:00:00"
            batch.append((r["match_id"], win, draw, lose, ct))
        if not batch:
            print("无场次需补种")
            return
        with conn.cursor() as cur:
            cur.executemany(SEED_SQL, batch)
        conn.commit()
        print(f"已补种 spf 行: {len(batch)} 场")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
