"""一次性回填竞彩历史比赛的亚盘让球(Bet365 初盘+终盘) —— football-data.co.uk CSV 版。

数据源: football-data.co.uk 静态CSV(无反爬, 直接httpx下载), 每联赛每赛季一文件。
覆盖: 18个国内联赛(英超/英冠/西甲/西乙/意甲/意乙/德甲/德乙/法甲/法乙/荷甲/葡超/比甲/
      挪超/瑞典超/日职/巴甲/美职联), 赛季1819~2526(2018-2026)。
映射: team_name_mapping(fd_name->jczq_name) 按(日期,主队,客队)命中matches表;
      未映射队按(日期,联赛,比分)回退(借此覆盖SP2/I2等无队名映射的联赛)。
符号约定: football-data 亚盘标准(正=主受让/主underdog, 负=主让/主favorite), 原样存入。

用法:
  python3 -u backfill_ah_history.py            # 全量
  LEAGUES=E0,E1 LIMIT=10 python3 -u backfill_ah_history.py
"""
import os
import csv
import io
import time
from typing import Dict, List, Optional, Tuple

import httpx
import pymysql

import settings

BASE = "https://www.football-data.co.uk/mmz4281"
SEASONS = ["1819", "1920", "2021", "2122", "2223", "2324", "2425", "2526"]

# league_code -> jczq league_name
LEAGUE_NAMES: Dict[str, str] = {
    "E0": "英超", "E1": "英冠", "SP1": "西甲", "SP2": "西乙",
    "I1": "意甲", "I2": "意乙", "D1": "德甲", "D2": "德乙",
    "F1": "法甲", "F2": "法乙", "N1": "荷甲", "P1": "葡超",
    "B1": "比甲", "NOR": "挪超", "SWE": "瑞典超", "JPN": "日职",
    "BRA": "巴甲", "USA": "美职联",
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DELAY = 0.3


def _f(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _norm_date(s: str) -> Optional[str]:
    """football-data DD/MM/YYYY(或YY) -> YYYY-MM-DD"""
    if not s or "/" not in s:
        return None
    parts = s.split("/")
    if len(parts) != 3:
        return None
    dd, mm, yy = parts
    if len(yy) == 2:
        yy = "20" + yy
    try:
        return f"{int(yy):04d}-{int(mm):02d}-{int(dd):02d}"
    except ValueError:
        return None


def get_conn():
    return pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)


def load_team_map() -> Dict[str, Dict[str, str]]:
    """{league_code: {fd_home_name: jczq_home_name}} — 双向按队名同时映射主客"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT fd_name, jczq_name, league_code FROM team_name_mapping")
            mp: Dict[str, Dict[str, str]] = {}
            for r in cur.fetchall():
                mp.setdefault(r["league_code"], {})[r["fd_name"]] = r["jczq_name"]
            return mp
    finally:
        conn.close()


def fetch_csv(season: str, code: str) -> List[Dict]:
    url = f"{BASE}/{season}/{code}.csv"
    try:
        resp = httpx.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
        if resp.status_code != 200 or not resp.content:
            return []
        text = resp.content.decode("utf-8", errors="replace")
        # 去BOM
        if text and text[0] == "﻿":
            text = text[1:]
        return list(csv.DictReader(io.StringIO(text)))
    except Exception as e:
        print(f"  下载失败 {code}/{season}: {e}", flush=True)
        return []


def _to_row(match_id: str, r: Dict) -> Optional[Tuple]:
    open_h = _f(r.get("AHh"))
    close_h = _f(r.get("AHCh"))
    # 至少有收盘线(盘路用)才入库; 开盘线可缺
    if open_h is None and close_h is None:
        return None
    open_home = _f(r.get("B365AHH"))
    open_away = _f(r.get("B365AHA"))
    close_home = _f(r.get("B365CAHH"))
    close_away = _f(r.get("B365CAHA"))
    return (match_id, open_h, open_home, open_away, close_h, close_home, close_away, "Bet365")


INSERT_SQL = """INSERT INTO jczq_ah_history
    (match_id, open_handicap, open_home_odds, open_away_odds,
     close_handicap, close_home_odds, close_away_odds, company)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      open_handicap=VALUES(open_handicap), open_home_odds=VALUES(open_home_odds),
      open_away_odds=VALUES(open_away_odds), close_handicap=VALUES(close_handicap),
      close_home_odds=VALUES(close_home_odds), close_away_odds=VALUES(close_away_odds),
      company=VALUES(company)"""


def main():
    codes = [c.strip() for c in os.getenv("LEAGUES", "").split(",") if c.strip()] or list(LEAGUE_NAMES.keys())
    seasons = [s.strip() for s in os.getenv("SEASONS", "").split(",") if s.strip()] or SEASONS
    limit = int(os.getenv("LIMIT", "0"))

    team_map = load_team_map()
    print(f"联赛 {len(codes)} 个, 赛季 {len(seasons)} 个, 队名映射覆盖 {len(team_map)} 联赛", flush=True)

    conn = get_conn()
    batch: List[Tuple] = []
    written = 0
    csv_matches = 0

    def flush():
        nonlocal written
        if not batch:
            return
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, batch)
        conn.commit()
        written += len(batch)
        batch.clear()

    for code in codes:
        league_name = LEAGUE_NAMES.get(code, "")
        if not league_name:
            continue
        tmap = team_map.get(code, {})  # 该联赛 fd_name->jczq_name
        league_hit = 0
        for season in seasons:
            rows = fetch_csv(season, code)
            if not rows:
                continue
            time.sleep(DELAY)
            for r in rows:
                csv_matches += 1
                date = _norm_date(r.get("Date", ""))
                if not date:
                    continue
                ht = r.get("HomeTeam", "").strip()
                at = r.get("AwayTeam", "").strip()
                mid = None
                # 1) 队名映射命中
                if ht in tmap and at in tmap:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT match_id FROM matches WHERE match_date=%s AND home_team_name=%s AND away_team_name=%s",
                            (date, tmap[ht], tmap[at]),
                        )
                        row = cur.fetchone()
                        if row:
                            mid = row["match_id"]
                # 2) 回退: 日期+联赛+比分
                if not mid:
                    hs = _i(r.get("FTHG"))
                    as_ = _i(r.get("FTAG"))
                    if hs is not None and as_ is not None:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT match_id FROM matches WHERE match_date=%s AND league_name=%s "
                                "AND home_score=%s AND away_score=%s LIMIT 1",
                                (date, league_name, hs, as_),
                            )
                            row = cur.fetchone()
                            if row:
                                mid = row["match_id"]
                if not mid:
                    continue
                rec = _to_row(mid, r)
                if rec:
                    batch.append(rec)
                    league_hit += 1
                    if len(batch) >= 200:
                        flush()
                if limit and written >= limit:
                    break
            if limit and written >= limit:
                break
        print(f"  {code} {league_name}: 入库 {league_hit} 场", flush=True)
        if limit and written >= limit:
            break

    flush()
    conn.close()
    print(f"\n完成: 扫描CSV {csv_matches} 行, 入库 {written} 场", flush=True)


if __name__ == "__main__":
    main()
