"""一次性回采竞彩历史比赛的胜平负(spf)赔率变动 —— 单线程顺序版。

500.com readpl 接口有加速乐(EO_Bot)盾, 并发/突发会触发持续封锁。改单线程一场一场抓,
被挡时指数退避重试同一场(最长10分钟), 盾放行即继续, 0.6s 延速。断点续跑。

用法:
  python3 -u backfill_spf_history.py            # 全量(断点续跑)
  DELAY=1 LIMIT=50 python3 -u backfill_spf_history.py
  ONLY_YEAR=2024 python3 -u backfill_spf_history.py
"""
import os
import json
import time
import sqlite3
from typing import Dict, List, Tuple

import pymysql
from playwright.sync_api import sync_playwright

import settings

JCZQ_DB = os.getenv("JCZQ_DB", "/Users/jetwong/Projects/personal/world-cup/data/jczq.db")
BASE_URL = "https://zx.500.com/jczq/kaijiang.php"
SHIELD_PAGE = "https://zx.500.com/jczq/kaijiang.php?d=2024-01-01"
DELAY = float(os.getenv("DELAY", "0.6"))
LIMIT = int(os.getenv("LIMIT", "0"))
ONLY_YEAR = os.getenv("ONLY_YEAR", "")
INSERT_BATCH = 300
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def fetch_url(zid, date):
    return (f"{BASE_URL}?step=readpl&zxid={zid}&date={date}&wtype=spf&rnd={int(time.time()*1000)}")


def parse_rows(items, match_id: str) -> List[Tuple]:
    if not isinstance(items, list):
        return []
    from datetime import datetime
    rows = []
    for it in items:
        try:
            win = float(it.get("win") or 0); draw = float(it.get("draw") or 0); loss = float(it.get("lost") or 0)
        except (TypeError, ValueError):
            continue
        if win <= 0 and draw <= 0 and loss <= 0:
            continue
        try:
            ct = datetime.strptime(it.get("time", ""), "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        dw = int(it.get("w") or 0); dd = int(it.get("d") or 0); dl = int(it.get("l") or 0)
        rows.append((match_id, "spf", win, draw, loss, dw, dd, dl, ct))
    return rows


def fetch_in_page(page, zid, date):
    """返回 (ok, items): ok=True 表示拿到JSON(可能空数组=该场真无spf变动);
    ok=False 表示被盾挡(非JSON)或网络错, 需重试。"""
    url = fetch_url(zid, date)
    js = """async (url) => {
        try {
            const r = await fetch(url, {headers:{'X-Requested-With':'XMLHttpRequest'}});
            const t = await r.text();
            return {status: r.status, body: t};
        } catch(e) { return {status: 0, body: 'ERR:'+e.message}; }
    }"""
    try:
        res = page.evaluate(js, url)
    except Exception:
        return False, []
    body = res.get("body", "") if isinstance(res, dict) else ""
    if not body:
        return False, []
    try:
        return True, json.loads(body)
    except (ValueError, TypeError):
        return False, []  # 盾页/非json


def get_mysql_conn():
    return pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)


def already_done() -> set:
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT match_id FROM jczq_odds_history WHERE odds_type='spf'")
            return {r["match_id"] for r in cur.fetchall()}
    finally:
        conn.close()


def load_tasks() -> List[Tuple[str, int, str]]:
    conn = sqlite3.connect(JCZQ_DB); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if ONLY_YEAR:
        sql = (f"SELECT id, zid, match_date FROM jczq_matches "
               f"WHERE match_date >= '{ONLY_YEAR}-01-01' AND match_date < '{int(ONLY_YEAR)+1}-01-01' "
               f"AND zid IS NOT NULL AND zid != '' ORDER BY match_date ASC")
    else:
        sql = ("SELECT id, zid, match_date FROM jczq_matches "
               "WHERE match_date >= '2018-01-01' AND zid IS NOT NULL AND zid != '' "
               "ORDER BY match_date ASC")
    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()
    tasks = [(f"jczq_{r['id']}", int(r['zid']), r['match_date']) for r in rows]
    if LIMIT:
        tasks = tasks[:LIMIT]
    return tasks


INSERT_SQL = """INSERT IGNORE INTO jczq_odds_history
    (match_id, odds_type, odds_win, odds_draw, odds_loss,
     direction_win, direction_draw, direction_loss, change_time)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""


def main():
    tasks = load_tasks()
    print(f"待回采候选: {len(tasks)} 场 (来源 {JCZQ_DB})", flush=True)
    done = already_done()
    todo = [t for t in tasks if t[0] not in done]
    print(f"已回采 {len(done)} 场, 本次需抓 {len(todo)} 场, 单线程, 延速 {DELAY}s", flush=True)
    if not todo:
        print("无待回采, 全部完成", flush=True); return

    conn = get_mysql_conn()
    batch: List[Tuple] = []
    written = 0

    def flush():
        nonlocal written
        if not batch:
            return
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, batch)
        conn.commit()
        written += len(batch)
        batch.clear()

    i = 0
    ok_cnt = 0
    empty_cnt = 0
    block_cnt = 0
    backoff = 2.0
    start = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()

        def refresh_shield():
            try:
                page.goto(SHIELD_PAGE, wait_until="load", timeout=30000)
                time.sleep(5)
            except Exception as e:
                print(f"  refresh失败: {e}", flush=True)

        print("过盾中...", flush=True)
        refresh_shield()

        while i < len(todo):
            mid, zid, mdate = todo[i]
            ok, items = fetch_in_page(page, zid, mdate)
            if ok:
                # 拿到JSON(可能空=真无spf变动) -> 正常推进
                rows = parse_rows(items, mid)
                batch.extend(rows)
                if len(batch) >= INSERT_BATCH:
                    flush()
                backoff = max(DELAY, backoff * 0.6)  # 成功, 退避回落
                if rows:
                    ok_cnt += 1
                else:
                    empty_cnt += 1
                i += 1
                if i % 200 == 0:
                    el = time.time() - start
                    rate = i / el if el else 0
                    remain = (len(todo) - i) / rate if rate else 0
                    print(f"  进度 {i}/{len(todo)}  有数据{ok_cnt} 空场{empty_cnt} 被挡{block_cnt}  "
                          f"速率 {rate:.2f}/秒  剩余 ~{remain/60:.1f}分  入库{written}行", flush=True)
                time.sleep(DELAY)
            else:
                # 被盾挡 -> 退避重试同一场
                block_cnt += 1
                backoff = min(backoff * 1.8, 600)
                if block_cnt % 5 == 1:
                    print(f"  被挡(累计{block_cnt}) 退避 {backoff:.0f}s 重试 {mid}", flush=True)
                refresh_shield()
                time.sleep(backoff)

        flush()
        conn.close()
        browser.close()

    el = time.time() - start
    print(f"\n完成: 抓取 {i} 场, 有数据 {ok_cnt}, 真空场 {empty_cnt}, 入库 {written} 行, "
          f"耗时 {el/60:.1f} 分, 被挡 {block_cnt} 次", flush=True)


if __name__ == "__main__":
    main()
