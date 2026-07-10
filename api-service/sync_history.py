"""
从 world-cup 项目的 jczq.db 同步竞彩历史数据到当前项目 MySQL
全量同步 2018 起的比赛 + 比分 + 竞彩赔率变动(spf/nspf) + okooo亚盘

注: okooo_asian_handicap 表仅 2026 年有数据，2018-2025 亚盘历史需另找数据源。

性能: 全程使用 executemany(单条多值语句) + bulk load 期间关闭 FK/唯一索引校验，
把逐行网络往返(17.9万次)压缩到几百次批量提交。
"""

import sqlite3
import pymysql
from datetime import datetime

import settings

JCZQ_DB = "/Users/jetwong/Projects/personal/world-cup/data/jczq.db"

# 批量插入的批次大小
BATCH_SIZE = 2000


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


def _bulk_preamble(cur):
    """bulk load 期间关闭 FK/唯一索引自检，大幅加速 InnoDB 插入"""
    cur.execute("SET unique_checks=0")
    cur.execute("SET foreign_key_checks=0")


def _bulk_epilogue(cur):
    cur.execute("SET unique_checks=1")
    cur.execute("SET foreign_key_checks=1")


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
    """同步比赛数据 + 竞彩赔率占位行(spf=had, rqspf=hhad)"""
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT id, match_date, match_num, league_name, league_id, kickoff_time,
               home_team, home_team_id, away_team, away_team_id,
               handicap, ft_home_score, ft_away_score,
               spf_result, spf_sp, rqspf_result, rqspf_sp,
               zid, is_single
        FROM jczq_matches
        WHERE match_date >= '2018-01-01'
        ORDER BY match_date, match_num
    """)
    rows = cursor.fetchall()
    print(f"从 jczq.db 读取到 {len(rows)} 场 2018 起比赛")

    match_rows = []
    wdl_rows = []
    for row in rows:
        match_id = f"jczq_{row['id']}"
        match_date = row["match_date"]
        match_num = row["match_num"] or ""
        kickoff_time = row["kickoff_time"] or ""

        # 解析开赛时间戳
        match_timestamp = None
        if kickoff_time:
            try:
                year = int(match_date[:4])
                time_str = f"{year}-{kickoff_time}"
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                match_timestamp = int(dt.timestamp())
            except Exception:
                pass
        if match_timestamp is None and match_date:
            try:
                dt = datetime.strptime(match_date, "%Y-%m-%d")
                match_timestamp = int(dt.timestamp())
            except Exception:
                pass

        ft_home = row["ft_home_score"]
        ft_away = row["ft_away_score"]
        match_status = "finished" if (ft_home is not None and ft_away is not None) else "not_started"

        match_number_val = match_date[2:].replace("-", "")
        match_rows.append((
            match_id, match_number_val, match_num,
            str(row["league_id"] or ""), row["league_name"] or "",
            match_date,
            kickoff_time.split(" ")[1] if " " in kickoff_time else "00:00",
            match_timestamp,
            str(row["home_team_id"] or ""), row["home_team"] or "",
            str(row["away_team_id"] or ""), row["away_team"] or "",
            ft_home, ft_away, row["is_single"] or 0, match_status,
        ))

        # 竞彩赔率占位行(真实赔率由 sync_initial_odds/sync_final_odds 回填)
        is_single = row["is_single"] or 0
        if row["spf_sp"]:
            wdl_rows.append((match_id, "had", 0, 0, 0, 0, is_single))
        if row["rqspf_sp"]:
            wdl_rows.append((match_id, "hhad", row["handicap"] or 0, 0, 0, 0, is_single))

    match_sql = """
        INSERT INTO matches
        (match_id, match_number, match_code, league_id, league_name,
         match_date, match_time, match_timestamp,
         home_team_id, home_team_name, away_team_id, away_team_name,
         home_score, away_score, is_single, match_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            match_status = VALUES(match_status),
            is_single = VALUES(is_single),
            home_score = VALUES(home_score),
            away_score = VALUES(away_score)
    """
    wdl_sql = """
        INSERT INTO odds_win_draw_lose
        (match_id, odds_type, handicap, win_odds, draw_odds, lose_odds, is_single)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            handicap = VALUES(handicap),
            is_single = IF(VALUES(is_single)=1,1,is_single)
    """

    with mysql_conn.cursor() as cur:
        _bulk_preamble(cur)
        for i in range(0, len(match_rows), BATCH_SIZE):
            cur.executemany(match_sql, match_rows[i:i + BATCH_SIZE])
        for i in range(0, len(wdl_rows), BATCH_SIZE):
            cur.executemany(wdl_sql, wdl_rows[i:i + BATCH_SIZE])
        _bulk_epilogue(cur)
    mysql_conn.commit()
    print(f"  同步比赛: {len(match_rows)} 场, 赔率占位行 {len(wdl_rows)} 条")
    return len(match_rows)


def sync_odds_movement(sqlite_conn, mysql_conn):
    """同步赔率变动历史(单条多值批量插入)"""
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT o.match_id, o.odds_type, o.odds_win, o.odds_draw, o.odds_loss,
               o.direction_win, o.direction_draw, o.direction_loss, o.change_time
        FROM jczq_odds_movement o
        JOIN jczq_matches m ON o.match_id = m.id
        WHERE m.match_date >= '2018-01-01'
        ORDER BY o.match_id, o.odds_type, o.change_time
    """)
    rows = cursor.fetchall()
    print(f"从 jczq.db 读取到 {len(rows)} 条 2018 起赔率变动")

    sql = """
        INSERT IGNORE INTO jczq_odds_history
        (match_id, odds_type, odds_win, odds_draw, odds_loss,
         direction_win, direction_draw, direction_loss, change_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    inserted = 0
    batch = []
    with mysql_conn.cursor() as cur:
        _bulk_preamble(cur)
        for row in rows:
            change_time = row["change_time"] or ""
            # 跳过非日期脏值(如 "初盘"/"终盘" 文本)，避免插成零日期
            if not change_time or not change_time[:4].isdigit():
                continue
            if len(change_time) == 16:
                change_time += ":00"
            batch.append((
                f"jczq_{row['match_id']}", row["odds_type"] or "nspf",
                row["odds_win"], row["odds_draw"], row["odds_loss"],
                row["direction_win"] or 0, row["direction_draw"] or 0, row["direction_loss"] or 0,
                change_time,
            ))
            if len(batch) >= BATCH_SIZE:
                cur.executemany(sql, batch)
                inserted += cur.rowcount
                batch = []
        if batch:
            cur.executemany(sql, batch)
            inserted += cur.rowcount
        _bulk_epilogue(cur)
    mysql_conn.commit()
    print(f"  同步赔率变动: 新增 {inserted} 条")
    return inserted


def sync_final_odds(sqlite_conn, mysql_conn):
    """用赔率变动的最新一条更新 odds_win_draw_lose 的终盘赔率(多值 ON DUPLICATE)"""
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT o.match_id, o.odds_type, o.odds_win, o.odds_draw, o.odds_loss
        FROM jczq_odds_movement o
        JOIN jczq_matches m ON o.match_id = m.id
        WHERE m.match_date >= '2018-01-01'
          AND o.change_time = (
              SELECT MAX(o2.change_time)
              FROM jczq_odds_movement o2
              WHERE o2.match_id = o.match_id AND o2.odds_type = o.odds_type
          )
        ORDER BY o.match_id
    """)
    rows = cursor.fetchall()
    print(f"更新终盘赔率 {len(rows)} 条...")

    sql = """
        INSERT INTO odds_win_draw_lose
        (match_id, odds_type, win_odds, draw_odds, lose_odds)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            win_odds = VALUES(win_odds),
            draw_odds = VALUES(draw_odds),
            lose_odds = VALUES(lose_odds)
    """
    odds_type_map = {"spf": "had", "nspf": "hhad"}
    batch = []
    with mysql_conn.cursor() as cur:
        for row in rows:
            odds_type = odds_type_map.get(row["odds_type"], row["odds_type"])
            batch.append((f"jczq_{row['match_id']}", odds_type,
                          row["odds_win"], row["odds_draw"], row["odds_loss"]))
            if len(batch) >= BATCH_SIZE:
                cur.executemany(sql, batch)
                batch = []
        if batch:
            cur.executemany(sql, batch)
    mysql_conn.commit()
    print(f"  更新终盘赔率: {len(rows)} 条")
    return len(rows)


def sync_initial_odds(sqlite_conn, mysql_conn):
    """用赔率变动的最早一条写入 odds_win_draw_lose (初盘, 多值 ON DUPLICATE)"""
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT o.match_id, o.odds_type, o.odds_win, o.odds_draw, o.odds_loss,
               m.handicap, m.is_single
        FROM jczq_odds_movement o
        JOIN jczq_matches m ON o.match_id = m.id
        WHERE m.match_date >= '2018-01-01'
          AND o.change_time = (
              SELECT MIN(o2.change_time)
              FROM jczq_odds_movement o2
              WHERE o2.match_id = o.match_id AND o2.odds_type = o.odds_type
          )
        ORDER BY o.match_id
    """)
    rows = cursor.fetchall()
    print(f"写入初盘/终盘赔率 {len(rows)} 条...")

    sql = """
        INSERT INTO odds_win_draw_lose
        (match_id, odds_type, handicap, win_odds, draw_odds, lose_odds, is_single)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            win_odds = VALUES(win_odds),
            draw_odds = VALUES(draw_odds),
            lose_odds = VALUES(lose_odds),
            handicap = VALUES(handicap)
    """
    odds_type_map = {"spf": "had", "nspf": "hhad"}
    batch = []
    with mysql_conn.cursor() as cur:
        for row in rows:
            odds_type = odds_type_map.get(row["odds_type"], row["odds_type"])
            handicap = row["handicap"] if odds_type == "hhad" else 0
            batch.append((f"jczq_{row['match_id']}", odds_type, handicap or 0,
                          row["odds_win"], row["odds_draw"], row["odds_loss"],
                          row["is_single"] or 0))
            if len(batch) >= BATCH_SIZE:
                cur.executemany(sql, batch)
                batch = []
        if batch:
            cur.executemany(sql, batch)
    mysql_conn.commit()
    print(f"  写入赔率: {len(rows)} 条")
    return len(rows)


def ensure_asian_table(mysql_conn):
    """确保亚盘数据表存在"""
    with mysql_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS okooo_asian_odds (
                id INT AUTO_INCREMENT PRIMARY KEY,
                match_id VARCHAR(100) NOT NULL,
                company VARCHAR(50) NOT NULL,
                initial_home_odds DECIMAL(6,3),
                initial_handicap DECIMAL(6,3) COMMENT '正=主让,负=客让(与500.com一致)',
                initial_away_odds DECIMAL(6,3),
                latest_home_odds DECIMAL(6,3),
                latest_handicap DECIMAL(6,3),
                latest_away_odds DECIMAL(6,3),
                UNIQUE KEY uk_match_company (match_id, company),
                INDEX idx_match (match_id),
                FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
    mysql_conn.commit()


def sync_okooo_asian(sqlite_conn, mysql_conn):
    """同步okooo亚盘数据(初盘+终盘)到MySQL(多值 ON DUPLICATE)"""
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT m.id as jczq_id, o.company,
               o.initial_home_odds, o.initial_handicap_value, o.initial_away_odds,
               o.latest_home_odds, o.latest_handicap_value, o.latest_away_odds
        FROM okooo_asian_handicap o
        JOIN jczq_matches m ON o.match_num = m.match_num AND o.scrape_date = m.match_date
        WHERE m.match_date >= '2018-01-01'
          AND o.initial_home_odds IS NOT NULL
          AND o.latest_home_odds IS NOT NULL
          AND o.initial_handicap_value IS NOT NULL
        ORDER BY m.id, o.company
    """)
    rows = cursor.fetchall()
    print(f"从 jczq.db 读取到 {len(rows)} 条 okooo 亚盘数据")

    sql = """
        INSERT INTO okooo_asian_odds
        (match_id, company, initial_home_odds, initial_handicap,
         initial_away_odds, latest_home_odds, latest_handicap, latest_away_odds)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            initial_home_odds = VALUES(initial_home_odds),
            initial_handicap = VALUES(initial_handicap),
            initial_away_odds = VALUES(initial_away_odds),
            latest_home_odds = VALUES(latest_home_odds),
            latest_handicap = VALUES(latest_handicap),
            latest_away_odds = VALUES(latest_away_odds)
    """
    batch = []
    with mysql_conn.cursor() as cur:
        _bulk_preamble(cur)
        for row in rows:
            batch.append((
                f"jczq_{row['jczq_id']}", _normalize_company(row["company"]),
                row["initial_home_odds"], row["initial_handicap_value"], row["initial_away_odds"],
                row["latest_home_odds"], row["latest_handicap_value"], row["latest_away_odds"],
            ))
            if len(batch) >= BATCH_SIZE:
                cur.executemany(sql, batch)
                batch = []
        if batch:
            cur.executemany(sql, batch)
        _bulk_epilogue(cur)
    mysql_conn.commit()
    print(f"  同步亚盘: {len(rows)} 条")
    return len(rows)


def _normalize_company(name: str) -> str:
    """统一公司名(与500.com抓取的名称对齐)"""
    mapping = {
        "澳门彩票": "澳门",
        "威廉.希尔": "威廉希尔",
        "伟德国际": "伟德",
        "利记菲律宾": "利记",
        "12bet.com": "12Bet",
        "12bet.com菲律宾": "12Bet",
    }
    return mapping.get(name, name)


def run():
    print("=" * 60)
    print("开始同步 2018 起竞彩历史数据")
    print(f"源: {JCZQ_DB}")
    print(f"目标: MySQL {settings.MYSQL_CONFIG['host']}:{settings.MYSQL_CONFIG['port']}/{settings.MYSQL_CONFIG['database']}")
    print("=" * 60)

    sqlite_conn = get_sqlite_conn()
    mysql_conn = get_mysql_conn()

    try:
        ensure_history_tables(mysql_conn)
        ensure_asian_table(mysql_conn)
        sync_matches(sqlite_conn, mysql_conn)
        sync_initial_odds(sqlite_conn, mysql_conn)
        sync_odds_movement(sqlite_conn, mysql_conn)
        sync_final_odds(sqlite_conn, mysql_conn)
        sync_okooo_asian(sqlite_conn, mysql_conn)

        # 统计最终结果
        with mysql_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM matches WHERE match_id LIKE 'jczq_%'")
            m_count = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM odds_win_draw_lose WHERE match_id LIKE 'jczq_%'")
            o_count = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM jczq_odds_history")
            h_count = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM okooo_asian_odds")
            a_count = cur.fetchone()["cnt"]

        print("\n" + "=" * 60)
        print("同步完成!")
        print(f"  历史比赛: {m_count} 条")
        print(f"  竞彩赔率记录: {o_count} 条")
        print(f"  竞彩赔率变动: {h_count} 条")
        print(f"  亚盘数据: {a_count} 条")
        print("=" * 60)

    finally:
        sqlite_conn.close()
        mysql_conn.close()


if __name__ == "__main__":
    run()
