"""针对 spf 池缺亚盘的场次补洞(500.com Bet365)。

优先用 matches.fid_500; 否则 get_fid_for_match(售卖日, match_code) 反查。
复用 backfill_ah_500.pick_open_close / INSERT 口径。

用法:
  python3 -u backfill_ah_missing.py
  DELAY=0.8 LIMIT=50 python3 -u backfill_ah_missing.py
  # 有 fid、缺 Bet365(含仅有澳门), 排除俄超:
  TARGET=has_fid_no_bet365 EXCLUDE_LEAGUE=俄超 python3 -u backfill_ah_missing.py
"""
from __future__ import annotations

import os
import time
from typing import List, Optional

import pymysql

import settings
from backfill_ah_500 import INSERT_SQL, pick_open_close
from odds500_service import fetch_asian_history, get_fid_for_match

DELAY = float(os.getenv("DELAY", "0.8"))
LIMIT = int(os.getenv("LIMIT", "0"))
CID_BET365 = 3
# missing: 任意公司都没有亚盘行(旧默认)
# has_fid_no_bet365: 有 fid_500 且无 Bet365 终盘(可覆盖澳门行)
TARGET = os.getenv("TARGET", "missing").strip() or "missing"
EXCLUDE_LEAGUE = os.getenv("EXCLUDE_LEAGUE", "").strip()


def get_conn():
    return pymysql.connect(**settings.MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)


def sale_date_of(row) -> Optional[str]:
    mn = str(row.get("match_number") or "").strip()
    if len(mn) >= 6 and mn[:6].isdigit():
        return f"20{mn[:2]}-{mn[2:4]}-{mn[4:6]}"
    md = row.get("match_date")
    return str(md)[:10] if md else None


def load_missing() -> List[dict]:
    if TARGET == "has_fid_no_bet365":
        sql = """
          SELECT m.match_id, m.match_date, m.match_number, m.match_code,
                 m.league_name, m.fid_500, m.home_team_name, m.away_team_name
          FROM (
            SELECT match_id, COUNT(*) AS cnt
            FROM jczq_odds_history
            WHERE odds_type='spf'
            GROUP BY match_id
            HAVING cnt >= 2
          ) t
          JOIN matches m ON m.match_id = t.match_id
          LEFT JOIN jczq_ah_history ah
            ON ah.match_id = t.match_id AND ah.company LIKE %s
          WHERE m.home_score IS NOT NULL AND m.away_score IS NOT NULL
            AND ah.close_handicap IS NULL
            AND m.fid_500 IS NOT NULL AND TRIM(m.fid_500) <> ''
        """
        params: list = ["Bet365%"]
        if EXCLUDE_LEAGUE:
            sql += " AND COALESCE(m.league_name,'') <> %s"
            params.append(EXCLUDE_LEAGUE)
        sql += " ORDER BY m.match_date ASC"
    else:
        sql = """
          SELECT m.match_id, m.match_date, m.match_number, m.match_code,
                 m.league_name, m.fid_500, m.home_team_name, m.away_team_name
          FROM (
            SELECT DISTINCT match_id FROM jczq_odds_history WHERE odds_type='spf'
          ) s
          JOIN matches m ON m.match_id = s.match_id
          LEFT JOIN jczq_ah_history a ON a.match_id = s.match_id
          WHERE a.match_id IS NULL AND m.home_score IS NOT NULL
          ORDER BY m.match_date ASC
        """
        params = []
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = list(cur.fetchall())
    finally:
        conn.close()
    if LIMIT:
        rows = rows[:LIMIT]
    return rows


def resolve_fid(row) -> Optional[str]:
    fid = row.get("fid_500")
    if fid:
        return str(fid)
    sale = sale_date_of(row)
    code = row.get("match_code")
    if not sale or not code:
        return None
    try:
        return get_fid_for_match(sale, str(code).strip())
    except Exception as e:
        print(f"  fid反查失败 {row['match_id']}: {e}", flush=True)
        return None


def main():
    rows = load_missing()
    print(
        f"缺亚盘: {len(rows)} 场 TARGET={TARGET} EXCLUDE_LEAGUE={EXCLUDE_LEAGUE or '-'} "
        f"(LIMIT={LIMIT or 'all'})",
        flush=True,
    )
    conn = get_conn()
    batch = []
    stats = {"ok": 0, "no_fid": 0, "no_hist": 0, "err": 0, "fid_saved": 0}

    for i, row in enumerate(rows, 1):
        mid = row["match_id"]
        md = str(row["match_date"])[:10]
        fid = resolve_fid(row)
        if not fid:
            stats["no_fid"] += 1
            if i % 50 == 0 or stats["no_fid"] <= 5:
                print(f"  [{i}/{len(rows)}] 无fid {mid} {md} {row['league_name']} "
                      f"{row['home_team_name']}", flush=True)
            continue

        # 缓存 fid
        if not row.get("fid_500"):
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE matches SET fid_500=%s WHERE match_id=%s AND "
                        "(fid_500 IS NULL OR fid_500='')",
                        (fid, mid),
                    )
                conn.commit()
                stats["fid_saved"] += 1
            except Exception:
                pass

        try:
            records = fetch_asian_history(fid, CID_BET365)
        except Exception as e:
            stats["err"] += 1
            print(f"  fetch失败 {mid} fid={fid}: {e}", flush=True)
            time.sleep(DELAY)
            continue

        if not records:
            stats["no_hist"] += 1
            time.sleep(DELAY)
            continue

        rec = pick_open_close(records, md)
        if not rec:
            stats["no_hist"] += 1
            time.sleep(DELAY)
            continue

        batch.append((mid, *rec, "Bet365-500"))
        stats["ok"] += 1
        print(
            f"  + {mid} {md} {row['league_name']} {row['home_team_name']} "
            f"初{rec[0]:+.2f} 终{rec[3]:+.2f}",
            flush=True,
        )
        if len(batch) >= 50:
            with conn.cursor() as cur:
                cur.executemany(INSERT_SQL, batch)
            conn.commit()
            batch.clear()
            print(f"  -- flush ok={stats['ok']}", flush=True)
        time.sleep(DELAY)

        if i % 50 == 0:
            print(
                f"进度 {i}/{len(rows)} ok={stats['ok']} no_fid={stats['no_fid']} "
                f"no_hist={stats['no_hist']} err={stats['err']}",
                flush=True,
            )

    if batch:
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, batch)
        conn.commit()
    conn.close()
    print(
        f"\n完成: ok={stats['ok']} no_fid={stats['no_fid']} "
        f"no_hist={stats['no_hist']} err={stats['err']} fid_saved={stats['fid_saved']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
