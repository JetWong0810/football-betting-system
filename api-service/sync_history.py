"""
从 world-cup 项目的 jczq.db 同步 2026 年竞彩历史数据到当前项目 MySQL
包含: 比赛基本信息 + 竞彩赔率变动(spf/nspf)
"""

import sqlite3
import pymysql
from datetime import datetime

import settings

JCZQ_DB = "/Users/jetwong/Projects/personal/world-cup/data/jczq.db"


def get_mysql_conn():
    return pymysql.connect(
        **settings.MYSQL_CONFIG,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def get_sqlite_conn():
    conn = sqlite3.connect(JCZQ_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_history_tables(mysql_conn):
    """确保历史赔率变动表存在"""
    with mysql_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jczq_odds_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                match_id VARCHAR(100) NOT NULL,
                odds_type VARCHAR(20) NOT NULL COMMENT 'spf/nspf',
                odds_win DECIMAL(8,2) NOT NULL,
                odds_draw DECIMAL(8,2) NOT NULL,
                odds_loss DECIMAL(8,2) NOT NULL,
                direction_win TINYINT DEFAULT 0,
                direction_draw TINYINT DEFAULT 0,
                direction_loss TINYINT DEFAULT 0,
                change_time DATETIME NOT NULL,
                UNIQUE KEY uk_match_type_time (match_id, odds_type, change_time),
                INDEX idx_match (match_id),
                FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
    mysql_conn.commit()


def sync_matches(sqlite_conn, mysql_conn):
    """同步比赛数据"""
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT id, match_date, match_num, league_name, league_id, kickoff_time,
               home_team, home_team_id, away_team, away_team_id,
               handicap, ft_home_score, ft_away_score,
               spf_result, spf_sp, rqspf_result, rqspf_sp,
               zid, is_single
        FROM jczq_matches
        WHERE match_date >= '2026-01-01'
        ORDER BY match_date, match_num
    """)
    rows = cursor.fetchall()
    print(f"从 jczq.db 读取到 {len(rows)} 场 2026 年比赛")

    inserted = 0
    skipped = 0
    with mysql_conn.cursor() as cur:
        for row in rows:
            match_id = f"jczq_{row['id']}"
            match_date = row["match_date"]
            match_num = row["match_num"] or ""
            kickoff_time = row["kickoff_time"] or ""

            # 解析开赛时间戳
            match_timestamp = None
            if kickoff_time:
                try:
                    # kickoff_time format: "MM-DD HH:MM"
                    year = int(match_date[:4])
                    time_str = f"{year}-{kickoff_time}"
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                    match_timestamp = int(dt.timestamp())
                except Exception:
                    pass
            # kickoff_time 缺失/解析失败时，用 match_date 当天兜底
            # (确保已结束的比赛能正确按时间归类，不会误判为"未开始")
            if match_timestamp is None and match_date:
                try:
                    dt = datetime.strptime(match_date, "%Y-%m-%d")
                    match_timestamp = int(dt.timestamp())
                except Exception:
                    pass

            # 确定比赛状态
            ft_home = row["ft_home_score"]
            ft_away = row["ft_away_score"]
            if ft_home is not None and ft_away is not None:
                match_status = "finished"
            else:
                match_status = "not_started"

            try:
                # match_number 格式为 YYMMDD（从 match_date 取）
                match_number_val = match_date[2:].replace("-", "")

                cur.execute("""
                    INSERT INTO matches
                    (match_id, match_number, match_code, league_id, league_name,
                     match_date, match_time, match_timestamp,
                     home_team_id, home_team_name, away_team_id, away_team_name,
                     home_score, away_score,
                     is_single, match_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        match_status = VALUES(match_status),
                        is_single = VALUES(is_single),
                        home_score = VALUES(home_score),
                        away_score = VALUES(away_score)
                """, (
                    match_id,
                    match_number_val,
                    match_num,
                    str(row["league_id"] or ""),
                    row["league_name"] or "",
                    match_date,
                    kickoff_time.split(" ")[1] if " " in kickoff_time else "00:00",
                    match_timestamp,
                    str(row["home_team_id"] or ""),
                    row["home_team"] or "",
                    str(row["away_team_id"] or ""),
                    row["away_team"] or "",
                    ft_home,
                    ft_away,
                    row["is_single"] or 0,
                    match_status,
                ))
                inserted += 1
            except pymysql.err.IntegrityError:
                skipped += 1
            except Exception as e:
                print(f"  Error inserting match {match_id}: {e}")
                skipped += 1

        # 同步赔率到 odds_win_draw_lose (had=spf, hhad=nspf)
        for row in rows:
            match_id = f"jczq_{row['id']}"
            handicap = row["handicap"] or 0

            # spf (胜平负, had)
            if row["spf_sp"]:
                try:
                    cur.execute("""
                        INSERT INTO odds_win_draw_lose
                        (match_id, odds_type, handicap, win_odds, draw_odds, lose_odds, is_single)
                        VALUES (%s, 'had', 0, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            win_odds = VALUES(win_odds),
                            draw_odds = VALUES(draw_odds),
                            lose_odds = VALUES(lose_odds)
                    """, (match_id, 0, 0, 0, row["is_single"] or 0))
                except Exception:
                    pass

            # nspf (让球胜平负, hhad)
            if row["rqspf_sp"]:
                try:
                    cur.execute("""
                        INSERT INTO odds_win_draw_lose
                        (match_id, odds_type, handicap, win_odds, draw_odds, lose_odds, is_single)
                        VALUES (%s, 'hhad', %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            handicap = VALUES(handicap),
                            win_odds = VALUES(win_odds),
                            draw_odds = VALUES(draw_odds),
                            lose_odds = VALUES(lose_odds)
                    """, (match_id, handicap, 0, 0, 0, row["is_single"] or 0))
                except Exception:
                    pass

    mysql_conn.commit()
    print(f"  同步比赛: 新增/更新 {inserted} 条, 跳过 {skipped} 条")
    return inserted


def sync_odds_movement(sqlite_conn, mysql_conn):
    """同步赔率变动历史"""
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT o.match_id, o.odds_type, o.odds_win, o.odds_draw, o.odds_loss,
               o.direction_win, o.direction_draw, o.direction_loss, o.change_time
        FROM jczq_odds_movement o
        JOIN jczq_matches m ON o.match_id = m.id
        WHERE m.match_date >= '2026-01-01'
        ORDER BY o.match_id, o.odds_type, o.change_time
    """)
    rows = cursor.fetchall()
    print(f"从 jczq.db 读取到 {len(rows)} 条 2026 年赔率变动")

    inserted = 0
    batch = []
    with mysql_conn.cursor() as cur:
        for row in rows:
            match_id = f"jczq_{row['match_id']}"
            odds_type = row["odds_type"] or "nspf"
            change_time = row["change_time"] or ""

            # 补全 change_time 格式
            if len(change_time) == 16:
                change_time += ":00"

            batch.append((
                match_id, odds_type,
                row["odds_win"], row["odds_draw"], row["odds_loss"],
                row["direction_win"] or 0, row["direction_draw"] or 0, row["direction_loss"] or 0,
                change_time,
            ))

            if len(batch) >= 500:
                inserted += _insert_odds_batch(cur, batch)
                batch = []

        if batch:
            inserted += _insert_odds_batch(cur, batch)

    mysql_conn.commit()
    print(f"  同步赔率变动: 新增 {inserted} 条")
    return inserted


def _insert_odds_batch(cur, batch):
    count = 0
    for row in batch:
        try:
            cur.execute("""
                INSERT IGNORE INTO jczq_odds_history
                (match_id, odds_type, odds_win, odds_draw, odds_loss,
                 direction_win, direction_draw, direction_loss, change_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, row)
            count += cur.rowcount
        except Exception:
            pass
    return count


def sync_final_odds(sqlite_conn, mysql_conn):
    """用赔率变动的最新一条更新 odds_win_draw_lose 的终盘赔率"""
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT o.match_id, o.odds_type, o.odds_win, o.odds_draw, o.odds_loss
        FROM jczq_odds_movement o
        JOIN jczq_matches m ON o.match_id = m.id
        WHERE m.match_date >= '2026-01-01'
          AND o.change_time = (
              SELECT MAX(o2.change_time)
              FROM jczq_odds_movement o2
              WHERE o2.match_id = o.match_id AND o2.odds_type = o.odds_type
          )
        ORDER BY o.match_id
    """)
    rows = cursor.fetchall()
    print(f"更新终盘赔率 {len(rows)} 条...")

    updated = 0
    with mysql_conn.cursor() as cur:
        for row in rows:
            match_id = f"jczq_{row['match_id']}"
            odds_type_map = {"spf": "had", "nspf": "hhad"}
            odds_type = odds_type_map.get(row["odds_type"], row["odds_type"])

            try:
                cur.execute("""
                    UPDATE odds_win_draw_lose
                    SET win_odds = %s, draw_odds = %s, lose_odds = %s
                    WHERE match_id = %s AND odds_type = %s
                """, (row["odds_win"], row["odds_draw"], row["odds_loss"],
                      match_id, odds_type))
                if cur.rowcount > 0:
                    updated += 1
            except Exception:
                pass

    mysql_conn.commit()
    print(f"  更新终盘赔率: {updated} 条")
    return updated


def sync_initial_odds(sqlite_conn, mysql_conn):
    """用赔率变动的最早一条写入 odds_win_draw_lose (初盘)"""
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT o.match_id, o.odds_type, o.odds_win, o.odds_draw, o.odds_loss,
               m.handicap, m.is_single
        FROM jczq_odds_movement o
        JOIN jczq_matches m ON o.match_id = m.id
        WHERE m.match_date >= '2026-01-01'
          AND o.change_time = (
              SELECT MIN(o2.change_time)
              FROM jczq_odds_movement o2
              WHERE o2.match_id = o.match_id AND o2.odds_type = o.odds_type
          )
        ORDER BY o.match_id
    """)
    rows = cursor.fetchall()
    print(f"写入初盘/终盘赔率 {len(rows)} 条...")

    inserted = 0
    with mysql_conn.cursor() as cur:
        for row in rows:
            match_id = f"jczq_{row['match_id']}"
            odds_type_map = {"spf": "had", "nspf": "hhad"}
            odds_type = odds_type_map.get(row["odds_type"], row["odds_type"])
            handicap = row["handicap"] if odds_type == "hhad" else 0

            try:
                cur.execute("""
                    INSERT INTO odds_win_draw_lose
                    (match_id, odds_type, handicap, win_odds, draw_odds, lose_odds, is_single)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        win_odds = VALUES(win_odds),
                        draw_odds = VALUES(draw_odds),
                        lose_odds = VALUES(lose_odds),
                        handicap = VALUES(handicap)
                """, (match_id, odds_type, handicap or 0,
                      row["odds_win"], row["odds_draw"], row["odds_loss"],
                      row["is_single"] or 0))
                inserted += cur.rowcount
            except Exception as e:
                pass

    mysql_conn.commit()
    print(f"  写入赔率: {inserted} 条")
    return inserted


def run():
    print("=" * 60)
    print("开始同步 2026 年竞彩历史数据")
    print(f"源: {JCZQ_DB}")
    print(f"目标: MySQL {settings.MYSQL_CONFIG['host']}:{settings.MYSQL_CONFIG['port']}/{settings.MYSQL_CONFIG['database']}")
    print("=" * 60)

    sqlite_conn = get_sqlite_conn()
    mysql_conn = get_mysql_conn()

    try:
        ensure_history_tables(mysql_conn)
        sync_matches(sqlite_conn, mysql_conn)
        sync_initial_odds(sqlite_conn, mysql_conn)
        sync_odds_movement(sqlite_conn, mysql_conn)
        sync_final_odds(sqlite_conn, mysql_conn)

        # 统计最终结果
        with mysql_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM matches WHERE match_id LIKE 'jczq_%'")
            m_count = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM odds_win_draw_lose WHERE match_id LIKE 'jczq_%'")
            o_count = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM jczq_odds_history")
            h_count = cur.fetchone()["cnt"]

        print("\n" + "=" * 60)
        print("同步完成!")
        print(f"  历史比赛: {m_count} 条")
        print(f"  赔率记录: {o_count} 条")
        print(f"  赔率变动历史: {h_count} 条")
        print("=" * 60)

    finally:
        sqlite_conn.close()
        mysql_conn.close()


if __name__ == "__main__":
    run()
