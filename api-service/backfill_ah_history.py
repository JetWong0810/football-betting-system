"""一次性回填竞彩历史比赛的亚盘让球(Bet365 初盘+终盘) —— football-data.co.uk CSV 版。

数据源: football-data.co.uk 静态CSV(无反爬, 直接httpx下载), 每联赛每赛季一文件。
覆盖: 18个国内联赛(英超/英冠/西甲/西乙/意甲/意乙/德甲/德乙/法甲/法乙/荷甲/葡超/比甲/
      挪超/瑞典超/日职/巴甲/美职联), 赛季1819~2526(2018-2026)。
映射:
  1) team_name_mapping(fd_name->jczq_name) 按(日期,主队,客队)命中 —— 优先、可覆盖已有行
  2) 可选比分回退: 仅当(日期,联赛,比分)在 matches 中唯一,且该场尚未被队名命中占用
     (旧版 LIMIT 1 会把同日同比分场次的盘写串, 如阿森纳被伯恩茅斯盘覆盖)

符号约定: football-data 亚盘标准(正=主受让/主underdog, 负=主让/主favorite), 原样存入。

用法:
  python3 -u backfill_ah_history.py            # 全量
  LEAGUES=E0,E1 LIMIT=10 python3 -u backfill_ah_history.py
  DRY_RUN=1 python3 -u backfill_ah_history.py  # 只统计不写库
  SCORE_FALLBACK=0 python3 -u backfill_ah_history.py  # 禁用比分回退(默认开启唯一比分回退)
"""
import os
import csv
import io
import time
from collections import defaultdict
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
    """{league_code: {fd_name: jczq_name}}"""
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


def load_match_indexes(league_names: List[str]) -> Tuple[
    Dict[Tuple[str, str, str], str],
    Dict[Tuple[str, str, int, int], List[str]],
]:
    """预加载 matches 索引, 避免逐行查库。

    Returns:
      by_teams: (date, home, away) -> match_id
      by_score: (date, league, hs, as) -> [match_id, ...]
    """
    conn = get_conn()
    by_teams: Dict[Tuple[str, str, str], str] = {}
    by_score: Dict[Tuple[str, str, int, int], List[str]] = defaultdict(list)
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(league_names))
            cur.execute(
                f"""
                SELECT match_id, match_date, league_name, home_team_name, away_team_name,
                       home_score, away_score
                FROM matches
                WHERE league_name IN ({placeholders})
                  AND match_date >= '2018-01-01'
                """,
                league_names,
            )
            for r in cur.fetchall():
                d = str(r["match_date"])[:10]
                mid = r["match_id"]
                by_teams[(d, r["home_team_name"], r["away_team_name"])] = mid
                if r["home_score"] is not None and r["away_score"] is not None:
                    key = (d, r["league_name"], int(r["home_score"]), int(r["away_score"]))
                    by_score[key].append(mid)
        return by_teams, dict(by_score)
    finally:
        conn.close()


def fetch_csv(season: str, code: str) -> List[Dict]:
    url = f"{BASE}/{season}/{code}.csv"
    try:
        resp = httpx.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
        if resp.status_code != 200 or not resp.content:
            return []
        text = resp.content.decode("utf-8", errors="replace")
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
    # 仅有开盘时用开盘填收盘, 避免 close NULL
    if close_h is None:
        close_h = open_h
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
    dry_run = os.getenv("DRY_RUN", "0") == "1"
    score_fallback = os.getenv("SCORE_FALLBACK", "1") != "0"

    team_map = load_team_map()
    league_names = [LEAGUE_NAMES[c] for c in codes if c in LEAGUE_NAMES]
    print(
        f"联赛 {len(codes)} 个, 赛季 {len(seasons)} 个, 队名映射覆盖 {len(team_map)} 联赛, "
        f"SCORE_FALLBACK={int(score_fallback)}, DRY_RUN={int(dry_run)}",
        flush=True,
    )
    print("预加载 matches 索引...", flush=True)
    by_teams, by_score = load_match_indexes(league_names)
    print(f"  队名索引 {len(by_teams)}, 比分索引 {len(by_score)}", flush=True)

    # 两遍: 先队名占坑, 再唯一比分补洞(不覆盖已占)
    pending_score: List[Tuple[str, Dict, str]] = []  # (league_code, csv_row, date)
    claimed: Dict[str, str] = {}  # match_id -> source (team|score)
    batch: List[Tuple] = []
    written = 0
    csv_matches = 0
    stats = defaultdict(int)

    conn = None if dry_run else get_conn()

    def flush():
        nonlocal written
        if dry_run or not batch:
            if batch:
                written += len(batch)
                batch.clear()
            return
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, batch)
        conn.commit()
        written += len(batch)
        batch.clear()

    def try_append(mid: str, r: Dict, source: str) -> bool:
        if mid in claimed:
            stats[f"skip_claimed_by_{claimed[mid]}"] += 1
            return False
        rec = _to_row(mid, r)
        if not rec:
            stats["skip_no_ah"] += 1
            return False
        claimed[mid] = source
        batch.append(rec)
        stats[f"hit_{source}"] += 1
        if len(batch) >= 200:
            flush()
        return True

    # ---- Pass 1: 队名映射 ----
    for code in codes:
        league_name = LEAGUE_NAMES.get(code, "")
        if not league_name:
            continue
        tmap = team_map.get(code, {})
        league_team = 0
        for season in seasons:
            rows = fetch_csv(season, code)
            if not rows:
                continue
            time.sleep(DELAY)
            for r in rows:
                csv_matches += 1
                date = _norm_date(r.get("Date", ""))
                if not date:
                    stats["skip_bad_date"] += 1
                    continue
                ht = (r.get("HomeTeam") or "").strip()
                at = (r.get("AwayTeam") or "").strip()
                mid = None
                if ht in tmap and at in tmap:
                    mid = by_teams.get((date, tmap[ht], tmap[at]))
                if mid:
                    if try_append(mid, r, "team"):
                        league_team += 1
                else:
                    # 留给 pass2
                    pending_score.append((code, r, date))
            if limit and written >= limit:
                break
        print(f"  {code} {league_name}: 队名命中 {league_team}", flush=True)
        if limit and written >= limit:
            break

    # ---- Pass 2: 唯一比分回退 ----
    score_hits_by_league: Dict[str, int] = defaultdict(int)
    if score_fallback and not (limit and written >= limit):
        for code, r, date in pending_score:
            if limit and written >= limit:
                break
            league_name = LEAGUE_NAMES.get(code, "")
            hs = _i(r.get("FTHG"))
            as_ = _i(r.get("FTAG"))
            if hs is None or as_ is None:
                stats["score_skip_no_ft"] += 1
                continue
            cands = by_score.get((date, league_name, hs, as_), [])
            if len(cands) == 0:
                stats["score_skip_none"] += 1
                continue
            if len(cands) > 1:
                stats["score_skip_ambiguous"] += 1
                continue
            mid = cands[0]
            if try_append(mid, r, "score"):
                score_hits_by_league[code] += 1

    flush()
    if conn:
        conn.close()

    print("\n比分回退命中(按联赛):", dict(score_hits_by_league) or "{}", flush=True)
    print(
        f"完成: CSV={csv_matches}, 入库={written}, "
        f"team={stats['hit_team']}, score={stats['hit_score']}, "
        f"比分歧义跳过={stats['score_skip_ambiguous']}, "
        f"已被队名占用跳过={stats['skip_claimed_by_team']}, "
        f"DRY_RUN={int(dry_run)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
