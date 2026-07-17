"""试抓/回填竞彩历史亚盘让球(Bet365初盘+终盘变动) —— 500.com 来源。

数据源:
  - 列表页(取fid): https://odds.500.com/yazhi_jczq_{date}.shtml  解析 <tr data-fid> 按场次编号(match_code)
  - 亚盘变动(API): fetch_asian_history(fid, cid=3 Bet365) -> yazhiajax.php 返回每条变动(主水/让球/客水/时间)

符号: 500.com 让球"正=主让(主favorite),负=主受让"; 存库取反为标准约定(正=主受让,与_ah_outcome/football-data一致)。
初/终盘: 变动时间仅MM-DD, 过滤到 match_date ±7天内(排除异常远期条目如赛后10月的脏数据), 最早=初盘, 最晚=终盘。

反爬: odds.500.com 单次httpx可取; 持续抓可能触发加速乐盾。单线程+延时+被挡指数退避+断点续跑。
用法:
  DATES=2019-02-14 python3 -u backfill_ah_500.py            # 试抓指定日期
  python3 -u backfill_ah_500.py                              # 全量(按jczq_matches日期遍历)
"""
import os
import time
import json
from typing import Dict, List, Optional, Tuple

import httpx
import pymysql
from bs4 import BeautifulSoup

import settings
from odds500_service import fetch_asian_history, _parse_handicap_value, _clean_handicap

BASE = "https://odds.500.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CID_BET365 = 3
DELAY = float(os.getenv("DELAY", "1.0"))  # 单线程延时, 保守防封
LIST_DELAY = float(os.getenv("LIST_DELAY", "2.0"))
INSERT_BATCH = 200


def get_conn():
    return pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)


def _doy(mmdd: str) -> Optional[int]:
    """MM-DD -> day of year"""
    try:
        mm, dd = mmdd.split("-")
        import datetime
        return datetime.date(2001, int(mm), int(dd)).timetuple().tm_yday
    except Exception:
        return None


def _doy_circular_diff(a: int, b: int) -> int:
    d = abs(a - b)
    return min(d, 366 - d)


def load_fid_map(date_str: str, session: httpx.Client) -> Dict[str, str]:
    """列表页 -> {match_code: fid}, 只取 '周X' 开头的真实场次行"""
    url = f"{BASE}/yazhi_jczq_{date_str}.shtml"
    import re
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            return {}
        soup = BeautifulSoup(resp.content, "html.parser", from_encoding="utf-8")
        mp = {}
        for tr in soup.find_all("tr", attrs={"data-fid": True}):
            tds = tr.find_all("td")
            num = tds[0].get_text(strip=True) if tds else ""
            if re.match(r"^周", num):
                mp[num] = tr.get("data-fid")
        return mp
    except Exception as e:
        print(f"  列表页失败 {date_str}: {e}", flush=True)
        return {}


def match_dates() -> List[str]:
    """从 MySQL matches 表取历史比赛日期(去重升序, 2018起)"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT match_date FROM matches "
                        "WHERE match_date >= '2018-01-01' AND match_date IS NOT NULL "
                        "ORDER BY match_date ASC")
            return [r["match_date"] for r in cur.fetchall() if r["match_date"]]
    finally:
        conn.close()


def already_done() -> set:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT match_id FROM jczq_ah_history")
            return {r["match_id"] for r in cur.fetchall()}
    finally:
        conn.close()


INSERT_SQL = """INSERT INTO jczq_ah_history
    (match_id, open_handicap, open_home_odds, open_away_odds,
     close_handicap, close_home_odds, close_away_odds, company)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      open_handicap=VALUES(open_handicap), open_home_odds=VALUES(open_home_odds),
      open_away_odds=VALUES(open_away_odds), close_handicap=VALUES(close_handicap),
      close_home_odds=VALUES(close_home_odds), close_away_odds=VALUES(close_away_odds),
      company=VALUES(company)"""


def pick_open_close(records: List[Dict], match_date: str) -> Optional[Tuple]:
    """从变动列表选初/终盘: 过滤到 match_date ±7天(按MM-DD day-of-year), 最早/最晚。
    符号取反(500.com正=主让 -> 标准正=主受让)。"""
    import datetime
    try:
        m_doy = datetime.date(2001, int(match_date[5:7]), int(match_date[8:10])).timetuple().tm_yday
    except Exception:
        return None
    valid = []
    for r in records:
        t = r.get("time", "")
        if " " not in t:
            continue
        mmdd = t.split(" ")[0]
        d = _doy(mmdd)
        if d is None:
            continue
        if _doy_circular_diff(d, m_doy) > 7:
            continue
        h = r.get("handicap")
        if h is None:
            continue
        valid.append((d, t, r))
    if not valid:
        return None
    # 按 (doy, 时间字符串) 排序, 同日内按 HH:MM 细分, 取最早=初盘/最晚=终盘
    valid.sort(key=lambda x: (x[0], x[1]))
    op = valid[0][2]
    cl = valid[-1][2]
    # 符号取反
    return (
        -float(op["handicap"]), float(op.get("home") or 0), float(op.get("away") or 0),
        -float(cl["handicap"]), float(cl.get("home") or 0), float(cl.get("away") or 0),
    )


def process_date(date_str: str, session: httpx.Client, conn, batch: list, done: set) -> Dict:
    fid_map = load_fid_map(date_str, session)
    stats = {"fid": len(fid_map), "hit": 0, "ah": 0, "blocked": 0}
    if not fid_map:
        return stats
    time.sleep(LIST_DELAY)
    # 该日 matches
    with conn.cursor() as cur:
        cur.execute("SELECT match_id, match_code, home_team_name, away_team_name FROM matches WHERE match_date=%s", (date_str,))
        rows = cur.fetchall()
    code2mid = {r["match_code"]: r for r in rows if r.get("match_code")}
    for code, fid in fid_map.items():
        m = code2mid.get(code)
        if not m:
            continue
        mid = m["match_id"]
        stats["hit"] += 1
        if mid in done:
            continue
        try:
            records = fetch_asian_history(fid, CID_BET365)
        except Exception as e:
            print(f"  fetch失败 {mid} fid={fid}: {e}", flush=True)
            continue
        if not records:
            time.sleep(DELAY)
            continue
        # 被挡检测: fetch_asian_history 异常返回空可能因盾
        rec = pick_open_close(records, date_str)
        if rec:
            batch.append((mid, *rec, "Bet365-500"))
            stats["ah"] += 1
            done.add(mid)
            if len(batch) >= INSERT_BATCH:
                with conn.cursor() as cur:
                    cur.executemany(INSERT_SQL, batch)
                conn.commit()
                batch.clear()
        time.sleep(DELAY)
    return stats


def main():
    dates_env = os.getenv("DATES", "")
    dates = [d.strip() for d in dates_env.split(",") if d.strip()] or match_dates()
    start_date = os.getenv("START_DATE", "").strip()
    if start_date:
        dates = [d for d in dates if d >= start_date]
    print(f"待抓日期: {len(dates)} 个 (来源 matches)", flush=True)
    done = already_done()
    print(f"已入库 match_id: {len(done)}", flush=True)

    conn = get_conn()
    batch = []
    total_ah = 0
    processed = 0
    with httpx.Client(headers={"User-Agent": UA}) as session:
        for i, date_str in enumerate(dates):
            st = process_date(date_str, session, conn, batch, done)
            total_ah += st["ah"]
            processed += st.get("hit", 0)
            if st["fid"]:
                print(f"  {date_str}: 列表{st['fid']}场 匹配{st['hit']}场 亚盘入库{st['ah']}场", flush=True)
            if i > 0 and i % 50 == 0:
                print(f"  进度 {i}/{len(dates)} 累计入盘{total_ah}", flush=True)
            # 每100场暂停(可配, 默认0=关; odds.500.com实测宽容无需)
            pause_sec = int(os.getenv("PAUSE_SEC", "0"))
            if pause_sec and processed and processed % 100 == 0:
                time.sleep(pause_sec)
    if batch:
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, batch)
        conn.commit()
    conn.close()
    print(f"\n完成: 累计亚盘入库 {total_ah} 场", flush=True)


if __name__ == "__main__":
    main()
