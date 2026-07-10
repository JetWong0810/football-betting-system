"""
从 world-cup 项目的 team_matches.db 导入五大联赛国家历史比赛到 MySQL

数据源: ~/Projects/personal/world-cup/data/team_matches.db (football-data.co.uk)
覆盖: England/Spain/Italy/Germany/France 五国(含英超/英冠/西甲/西乙/意甲/意乙/德甲/德乙/法甲/法乙)
含: 比分+半场比分+亚盘(closing)+欧赔(b365/avg/max)+角球/射门/射正/犯规/黄红牌
导入时套用 team_name_mapping 把英文队名映射成竞彩中文名(存 home_team_cn/away_team_cn)

用途: 作为 F1/F2 历史回测的本地基本面数据源(local_match_data.py 查询此表)。
性能: executemany 批量 + 关 FK 校验,参照 sync_history.py。
"""

import sqlite3
import pymysql
from typing import Dict, Optional

import settings

TEAM_DB = "/Users/jetwong/Projects/personal/world-cup/data/team_matches.db"

FIVE_COUNTRIES = ("England", "Spain", "Italy", "Germany", "France")
BATCH_SIZE = 2000


def get_mysql_conn():
    return pymysql.connect(
        **settings.MYSQL_CONFIG,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def get_sqlite_conn():
    conn = sqlite3.connect(TEAM_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _bulk_preamble(cur):
    cur.execute("SET unique_checks=0")
    cur.execute("SET foreign_key_checks=0")


def _bulk_epilogue(cur):
    cur.execute("SET unique_checks=1")
    cur.execute("SET foreign_key_checks=1")


def ensure_tables(mysql_conn):
    with mysql_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS team_name_mapping (
                id INT AUTO_INCREMENT PRIMARY KEY,
                fd_name VARCHAR(200) NOT NULL,
                jczq_name VARCHAR(200) NOT NULL,
                league_code VARCHAR(20),
                UNIQUE KEY uk_fd_league (fd_name, league_code),
                INDEX idx_jczq_name (jczq_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS team_history_matches (
                id INT AUTO_INCREMENT PRIMARY KEY,
                match_date DATE NOT NULL,
                league_code VARCHAR(20),
                league_name VARCHAR(50),
                jczq_league VARCHAR(50),
                season VARCHAR(10),
                home_team_en VARCHAR(200) NOT NULL,
                home_team_cn VARCHAR(200),
                away_team_en VARCHAR(200) NOT NULL,
                away_team_cn VARCHAR(200),
                ft_home_goals TINYINT,
                ft_away_goals TINYINT,
                ht_home_goals TINYINT,
                ht_away_goals TINYINT,
                asian_handicap DECIMAL(5,2) COMMENT '负=主让(football-data约定,与500.com recent一致)',
                avg_ah_home DECIMAL(6,3),
                avg_ah_away DECIMAL(6,3),
                b365_home DECIMAL(6,3),
                b365_draw DECIMAL(6,3),
                b365_away DECIMAL(6,3),
                avg_home DECIMAL(6,3),
                avg_draw DECIMAL(6,3),
                avg_away DECIMAL(6,3),
                max_home DECIMAL(6,3),
                max_draw DECIMAL(6,3),
                max_away DECIMAL(6,3),
                home_corners TINYINT,
                away_corners TINYINT,
                home_shots TINYINT,
                away_shots TINYINT,
                home_shots_target TINYINT,
                away_shots_target TINYINT,
                home_fouls TINYINT,
                away_fouls TINYINT,
                home_yellow TINYINT,
                away_yellow TINYINT,
                home_red TINYINT,
                away_red TINYINT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uk_match (league_code, match_date, home_team_en, away_team_en),
                INDEX idx_date (match_date),
                INDEX idx_home_cn (home_team_cn),
                INDEX idx_away_cn (away_team_cn)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
    mysql_conn.commit()


def load_name_mapping(sqlite_conn) -> Dict[str, Dict[str, str]]:
    """加载 team_name_mapping: {(league_code, fd_name): jczq_name}
    同名不同联赛用 league_code 消歧;兜底再存 (None, fd_name)。"""
    mapping: Dict[str, Dict[str, str]] = {}
    by_code: Dict[str, Dict[str, str]] = {}
    by_name: Dict[str, str] = {}
    for r in sqlite_conn.execute("SELECT fd_name, jczq_name, league_code FROM team_name_mapping"):
        fd, jczq, lc = r["fd_name"], r["jczq_name"], r["league_code"]
        by_code.setdefault(lc or "", {})[fd] = jczq
        by_name.setdefault(fd, jczq)  # 无联赛兜底(后写覆盖,影响小)
    mapping["by_code"] = by_code
    mapping["by_name"] = by_name
    return mapping


def sync_name_mapping(sqlite_conn, mysql_conn):
    rows = [dict(r) for r in sqlite_conn.execute(
        "SELECT fd_name, jczq_name, league_code FROM team_name_mapping")]
    sql = """INSERT INTO team_name_mapping (fd_name, jczq_name, league_code)
             VALUES (%s, %s, %s)
             ON DUPLICATE KEY UPDATE jczq_name=VALUES(jczq_name)"""
    with mysql_conn.cursor() as cur:
        _bulk_preamble(cur)
        for i in range(0, len(rows), BATCH_SIZE):
            cur.executemany(sql, [(r["fd_name"], r["jczq_name"], r["league_code"]) for r in rows[i:i + BATCH_SIZE]])
        _bulk_epilogue(cur)
    mysql_conn.commit()
    print(f"  队名映射: {len(rows)} 条")
    return len(rows)


def sync_team_matches(sqlite_conn, mysql_conn, mapping):
    placeholders = ",".join(["%s"] * 37)
    sql = f"""INSERT INTO team_history_matches
        (match_date, league_code, league_name, jczq_league, season,
         home_team_en, home_team_cn, away_team_en, away_team_cn,
         ft_home_goals, ft_away_goals, ht_home_goals, ht_away_goals,
         asian_handicap, avg_ah_home, avg_ah_away,
         b365_home, b365_draw, b365_away, avg_home, avg_draw, avg_away,
         max_home, max_draw, max_away,
         home_corners, away_corners, home_shots, away_shots,
         home_shots_target, away_shots_target, home_fouls, away_fouls,
         home_yellow, away_yellow, home_red, away_red)
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE
            home_team_cn=VALUES(home_team_cn), away_team_cn=VALUES(away_team_cn),
            asian_handicap=VALUES(asian_handicap), ft_home_goals=VALUES(ft_home_goals),
            ft_away_goals=VALUES(ft_away_goals)"""

    by_code = mapping["by_code"]
    by_name = mapping["by_name"]

    rows = sqlite_conn.execute("""
        SELECT match_date, league_code, league_name, jczq_league, season,
               home_team, away_team, ft_home_goals, ft_away_goals,
               ht_home_goals, ht_away_goals,
               asian_handicap, avg_ah_home, avg_ah_away,
               b365_home, b365_draw, b365_away, avg_home, avg_draw, avg_away,
               max_home, max_draw, max_away,
               home_corners, away_corners, home_shots, away_shots,
               home_shots_target, away_shots_target, home_fouls, away_fouls,
               home_yellow, away_yellow, home_red, away_red
        FROM team_matches
        WHERE league_name IN ('England','Spain','Italy','Germany','France')
        ORDER BY match_date
    """).fetchall()

    print(f"从 team_matches.db 读取到 {len(rows)} 场五大联赛国家比赛")

    def map_cn(team_en: str, league_code: Optional[str]) -> Optional[str]:
        if not team_en:
            return None
        if league_code and team_en in by_code.get(league_code, {}):
            return by_code[league_code][team_en]
        return by_name.get(team_en)

    batch = []
    cn_hit = 0
    with mysql_conn.cursor() as cur:
        _bulk_preamble(cur)
        for r in rows:
            r = dict(r)
            lc = r["league_code"]
            home_cn = map_cn(r["home_team"], lc)
            away_cn = map_cn(r["away_team"], lc)
            if home_cn:
                cn_hit += 1
            if away_cn:
                cn_hit += 1
            batch.append((
                r["match_date"], lc, r["league_name"], r["jczq_league"], r["season"],
                r["home_team"], home_cn, r["away_team"], away_cn,
                r["ft_home_goals"], r["ft_away_goals"], r["ht_home_goals"], r["ht_away_goals"],
                r["asian_handicap"], r["avg_ah_home"], r["avg_ah_away"],
                r["b365_home"], r["b365_draw"], r["b365_away"], r["avg_home"], r["avg_draw"], r["avg_away"],
                r["max_home"], r["max_draw"], r["max_away"],
                r["home_corners"], r["away_corners"], r["home_shots"], r["away_shots"],
                r["home_shots_target"], r["away_shots_target"], r["home_fouls"], r["away_fouls"],
                r["home_yellow"], r["away_yellow"], r["home_red"], r["away_red"],
            ))
            if len(batch) >= BATCH_SIZE:
                cur.executemany(sql, batch)
                batch = []
        if batch:
            cur.executemany(sql, batch)
        _bulk_epilogue(cur)
    mysql_conn.commit()
    print(f"  导入完成: {len(rows)} 场, 中文名命中 {cn_hit}/{len(rows)*2} ({cn_hit/(len(rows)*2)*100:.1f}%)")
    return len(rows)


def run():
    print("=" * 60)
    print("导入五大联赛国家历史比赛 (team_matches.db -> MySQL)")
    print(f"源: {TEAM_DB}")
    print(f"目标: {settings.MYSQL_CONFIG['host']}:{settings.MYSQL_CONFIG['port']}/{settings.MYSQL_CONFIG['database']}")
    print("=" * 60)

    sqlite_conn = get_sqlite_conn()
    mysql_conn = get_mysql_conn()
    try:
        ensure_tables(mysql_conn)
        mapping = load_name_mapping(sqlite_conn)
        print(f"加载队名映射: {len(mapping['by_name'])} 个队名")
        sync_name_mapping(sqlite_conn, mysql_conn)
        sync_team_matches(sqlite_conn, mysql_conn, mapping)

        with mysql_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) c FROM team_history_matches")
            m = cur.fetchone()["c"]
            cur.execute("SELECT SUM(home_team_cn IS NOT NULL) h, SUM(away_team_cn IS NOT NULL) a, SUM(asian_handicap IS NOT NULL) ah FROM team_history_matches")
            cov = cur.fetchone()
        print("\n" + "=" * 60)
        print("导入完成!")
        print(f"  总场次: {m}")
        print(f"  主队中文名: {cov['h']} | 客队中文名: {cov['a']}")
        print(f"  有亚盘: {cov['ah']}")
        print("=" * 60)
    finally:
        sqlite_conn.close()
        mysql_conn.close()


if __name__ == "__main__":
    run()
