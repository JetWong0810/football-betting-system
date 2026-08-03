"""从体彩赛果 API 回填胜平负(spf)终盘。

在售计算器接口封盘前停更 → jczq_odds_history 末条常不是真终盘
(例: 索尔纳 1.37, 赛果终赔 1.40)。赛果页 h/d/a 为官方终赔。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

RESULT_API_URL = (
    "https://webapi.sporttery.cn/gateway/uniform/football/"
    "getUniformMatchResultV1.qry"
)

# 售卖日 → 上次懒回填 monotonic 秒; 同进程内 30min 内不重复打体彩
_ENSURE_CACHE: Dict[str, float] = {}
_ENSURE_TTL_SEC = 1800.0


def fetch_match_results(begin_date: str, end_date: str) -> List[Dict]:
    """体彩赛果列表。h/d/a = 胜平负终赔。"""
    params = {
        "matchBeginDate": begin_date,
        "matchEndDate": end_date,
        "leagueId": "",
        "pageSize": 100,
        "pageNo": 1,
        "isFix": 0,
        "matchPage": 1,
        "pcOrWap": 1,
    }
    rows: List[Dict] = []
    with httpx.Client(timeout=20, headers={"User-Agent": "football-betting-system/1.0"}) as client:
        while True:
            resp = client.get(RESULT_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                break
            batch = (data.get("value") or {}).get("matchResult") or []
            if not batch:
                break
            rows.extend(batch)
            total = int((data.get("value") or {}).get("total") or 0)
            if len(rows) >= total or len(batch) < params["pageSize"]:
                break
            params["pageNo"] += 1
    return rows


def _apply_closing_spf(
    conn,
    match_id: str,
    win: float,
    draw: float,
    lose: float,
    change_time: Optional[datetime] = None,
) -> bool:
    cur = conn.cursor()
    cur.execute(
        """SELECT odds_win, odds_draw, odds_loss, change_time FROM jczq_odds_history
           WHERE match_id=%s AND odds_type='spf'
           ORDER BY change_time DESC LIMIT 1""",
        (match_id,),
    )
    prev = cur.fetchone()
    if prev:
        pw, pd, pl = float(prev["odds_win"]), float(prev["odds_draw"]), float(prev["odds_loss"])
        if abs(win - pw) < 0.005 and abs(draw - pd) < 0.005 and abs(lose - pl) < 0.005:
            cur.execute(
                """UPDATE odds_win_draw_lose
                   SET win_odds=%s, draw_odds=%s, lose_odds=%s, updated_at=CURRENT_TIMESTAMP
                   WHERE match_id=%s AND odds_type='had'
                     AND (ABS(win_odds-%s)>=0.005 OR ABS(draw_odds-%s)>=0.005
                          OR ABS(lose_odds-%s)>=0.005)""",
                (win, draw, lose, match_id, win, draw, lose),
            )
            return False
        dw = 0 if abs(win - pw) < 0.005 else (1 if win > pw else -1)
        dd = 0 if abs(draw - pd) < 0.005 else (1 if draw > pd else -1)
        dl = 0 if abs(lose - pl) < 0.005 else (1 if lose > pl else -1)
        prev_ct = prev["change_time"]
    else:
        dw = dd = dl = 0
        prev_ct = None

    ct = change_time or datetime.utcnow().replace(microsecond=0)
    if prev_ct is not None and ct <= prev_ct:
        ct = prev_ct + timedelta(seconds=1)

    cur.execute(
        """INSERT IGNORE INTO jczq_odds_history
           (match_id, odds_type, odds_win, odds_draw, odds_loss,
            direction_win, direction_draw, direction_loss, change_time)
           VALUES (%s,'spf',%s,%s,%s,%s,%s,%s,%s)""",
        (match_id, win, draw, lose, dw, dd, dl, ct),
    )
    cur.execute(
        """UPDATE odds_win_draw_lose
           SET win_odds=%s, draw_odds=%s, lose_odds=%s, updated_at=CURRENT_TIMESTAMP
           WHERE match_id=%s AND odds_type='had'""",
        (win, draw, lose, match_id),
    )
    return True


def backfill_closing_odds_for_dates(dates: List[str]) -> int:
    """按比赛日(体彩 matchDate)回填终盘, 返回写入 history 的场次数。"""
    if not dates:
        return 0
    begin, end = min(dates), max(dates)
    try:
        results = fetch_match_results(begin, end)
    except Exception as e:
        logger.warning(f"拉取赛果终赔失败 {begin}~{end}: {e}")
        return 0
    if not results:
        return 0
    want = set(dates)
    from database import get_db

    updated = 0
    with get_db() as conn:
        for m in results:
            md = str(m.get("matchDate") or "")[:10]
            if md not in want:
                continue
            mid = str(m.get("matchId") or "").strip()
            h, d, a = m.get("h"), m.get("d"), m.get("a")
            if not mid or h in (None, "", "-") or d in (None, "", "-") or a in (None, "", "-"):
                continue
            try:
                win, draw, lose = float(h), float(d), float(a)
            except (TypeError, ValueError):
                continue
            cur = conn.cursor()
            cur.execute("SELECT match_timestamp FROM matches WHERE match_id=%s", (mid,))
            row = cur.fetchone()
            if not row:
                continue
            ct = None
            ts = row.get("match_timestamp")
            if ts:
                ct = datetime.utcfromtimestamp(int(ts)).replace(microsecond=0)
            if _apply_closing_spf(conn, mid, win, draw, lose, change_time=ct):
                updated += 1
                logger.info(
                    "终盘回填 %s %s %.2f/%.2f/%.2f %s",
                    mid, m.get("homeTeam"), win, draw, lose, m.get("awayTeam"),
                )
    return updated


def ensure_closing_spf_for_sale_date(sale_date: str) -> int:
    """已结束同赔页懒校正: 售卖日 ±1 天的赛果(跨日场)。"""
    import time as _time

    try:
        base = datetime.strptime(sale_date, "%Y-%m-%d").date()
    except ValueError:
        return 0
    now = _time.monotonic()
    prev = _ENSURE_CACHE.get(sale_date)
    if prev is not None and now - prev < _ENSURE_TTL_SEC:
        return 0
    dates = [
        (base - timedelta(days=1)).isoformat(),
        base.isoformat(),
        (base + timedelta(days=1)).isoformat(),
    ]
    n = backfill_closing_odds_for_dates(dates)
    _ENSURE_CACHE[sale_date] = now
    return n


if __name__ == "__main__":
    import os
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    days = int(os.getenv("DAYS", "3"))
    end = datetime.now().date()
    begin = end - timedelta(days=days - 1)
    dates = []
    d = begin
    while d <= end:
        dates.append(d.isoformat())
        d += timedelta(days=1)
    n = backfill_closing_odds_for_dates(dates)
    print(f"done updated={n} dates={dates[0]}~{dates[-1]}")
    sys.exit(0)
