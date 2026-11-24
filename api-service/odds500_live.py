"""AI 聊天里"抓取本场最新盘口赔率": 实时从 500.com 抓这一场的多家公司亚盘/大小球/欧赔变动并落库。

保护(API 与 scraper 共用服务器出口 IP, 不能把 500.com 打封):
  - 同一时间只允许一个实时抓取(单飞); 忙时直接返回 busy, 走已有数据。
  - 同一场 COOLDOWN_SEC 内重复要求, 复用刚抓到的结果(cached=True)。
  - 全局每小时次数上限; 与定时抓取一样遇 567/403/429 即熔断, 熔断期间返回 blocked。
  - 已开赛的比赛只补抓到开赛为止的记录(滚球剔除); 已完赛超过 3 天的不抓。
失败一律不抛异常, 返回 {"ok": False, "reason": ...}, 调用方用库里已有数据并如实告知。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from database import get_db
from odds500_ticks import COMPANIES, KINDS, Odds500Client, breaker_open

logger = logging.getLogger(__name__)

_BJ = timezone(timedelta(hours=8))
COOLDOWN_SEC = 120
HOURLY_CAP = 40
# 实时抓取的公司顺序: 香港马会优先, 其后 Bet365/皇冠/Pinnacle/澳门 (每家 亚盘+大小球+欧赔 共 3 个请求)
LIVE_CIDS: Tuple[int, ...] = (122, 3, 280, 1055, 5)

_lock = threading.Lock()
_recent: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_calls: List[float] = []
_fid_lists: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_tables_ready = False

_SPEC = {
    "asian": ("odds500_ah_ticks", "home_odds, handicap, handicap_text, away_odds",
              lambda t: (t.get("home"), t.get("handicap"), t.get("handicapText") or "", t.get("away"))),
    "ou": ("odds500_ou_ticks", "over_odds, line, line_text, under_odds",
           lambda t: (t.get("over"), t.get("line"), t.get("lineText") or "", t.get("under"))),
    "euro": ("odds500_euro_ticks", "win_odds, draw_odds, lose_odds, return_rate",
             lambda t: (t.get("win"), t.get("draw"), t.get("lose"), t.get("returnRate"))),
}
_DDL = {
    "asian": "home_odds DECIMAL(8,3) DEFAULT NULL, handicap DECIMAL(6,2) DEFAULT NULL COMMENT '500原值 正=主让', "
             "handicap_text VARCHAR(32) DEFAULT NULL, away_odds DECIMAL(8,3) DEFAULT NULL",
    "ou": "over_odds DECIMAL(8,3) DEFAULT NULL, line DECIMAL(6,2) DEFAULT NULL, "
          "line_text VARCHAR(32) DEFAULT NULL, under_odds DECIMAL(8,3) DEFAULT NULL",
    "euro": "win_odds DECIMAL(8,3) DEFAULT NULL, draw_odds DECIMAL(8,3) DEFAULT NULL, "
            "lose_odds DECIMAL(8,3) DEFAULT NULL, return_rate DECIMAL(5,2) DEFAULT NULL",
}
_SHORT = {"asian": "ah", "ou": "ou", "euro": "euro"}


def ensure_tables() -> None:
    """与 scraper-service/database.py 同 DDL(CREATE IF NOT EXISTS)。"""
    global _tables_ready
    if _tables_ready:
        return
    with get_db() as conn:
        cur = conn.cursor()
        for kind in KINDS:
            s = _SHORT[kind]
            cur.execute(
                f"""CREATE TABLE IF NOT EXISTS odds500_{s}_ticks (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    match_id VARCHAR(100) NOT NULL,
                    company VARCHAR(50) NOT NULL,
                    cid INT NOT NULL,
                    tick_time DATETIME NOT NULL,
                    {_DDL[kind]},
                    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_o500_{s} (match_id, company, tick_time),
                    INDEX idx_o500_{s}_m (match_id, company)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""")
    _tables_ready = True


def _save(kind: str, match_id: str, ticks: List[Dict[str, Any]], company: str, cid: int) -> int:
    table, cols, pick = _SPEC[kind]
    rows = [(match_id, company, int(cid), t["time"].strftime("%Y-%m-%d %H:%M:%S")) + pick(t) for t in ticks]
    if not rows:
        return 0
    upd = ", ".join(f"{c.strip()}=VALUES({c.strip()})" for c in cols.split(","))
    with get_db() as conn:
        cur = conn.cursor()
        cur.executemany(
            f"INSERT INTO {table} (match_id, company, cid, tick_time, {cols}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
            f"ON DUPLICATE KEY UPDATE {upd}", rows)
    return len(rows)


def _sale_date(match_number: Any) -> Optional[str]:
    mn = str(match_number or "").strip()
    if len(mn) >= 6 and mn[:6].isdigit():
        try:
            datetime.strptime(f"20{mn[:2]}-{mn[2:4]}-{mn[4:6]}", "%Y-%m-%d")
            return f"20{mn[:2]}-{mn[2:4]}-{mn[4:6]}"
        except ValueError:
            return None
    return None


def _load_match(match_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT match_id, match_code, match_number, match_timestamp FROM matches WHERE match_id=%s", (match_id,))
        return cur.fetchone()


def _resolve_fid(client: Odds500Client, m: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """返回 (fid, 失败原因)。按售卖日列表页映射, 并用开赛时间校验防错配。"""
    sale = _sale_date(m.get("match_number"))
    code = m.get("match_code")
    if not sale or not code:
        return None, "no_mapping"
    now = time.time()
    hit = _fid_lists.get(sale)
    if hit is None or now - hit[0] > 600:
        data = client.fetch_fid_list(sale)
        if data is None:
            return None, "blocked" if breaker_open() else "list_failed"
        hit = _fid_lists[sale] = (now, data)
    info = hit[1].get(code)
    if not info:
        return None, "not_listed"
    ko, ts = info.get("kickoff"), m.get("match_timestamp")
    if ko is not None and ts and abs(ko.replace(tzinfo=_BJ).timestamp() - float(ts)) > 15 * 60:
        return None, "kickoff_mismatch"
    return info["fid"], None


def refresh_match_odds(match_id: str, force: bool = False) -> Dict[str, Any]:
    """实时抓取一场。返回 {ok, reason, cached, fetchedAt(北京时间), requests, ticks, got, failed}。"""
    now = time.time()
    rec = _recent.get(match_id)
    if rec and not force and now - rec[0] < COOLDOWN_SEC:
        return {**rec[1], "cached": True}
    if breaker_open():
        return {"ok": False, "reason": "blocked"}
    _calls[:] = [t for t in _calls if now - t < 3600]
    if len(_calls) >= HOURLY_CAP:
        return {"ok": False, "reason": "rate_limited"}
    if not _lock.acquire(blocking=False):
        return {"ok": False, "reason": "busy"}
    try:
        m = _load_match(match_id)
        if not m or not m.get("match_timestamp"):
            return {"ok": False, "reason": "no_match"}
        if now - float(m["match_timestamp"]) > 3 * 86400:
            return {"ok": False, "reason": "too_old"}
        try:
            ensure_tables()
        except Exception as e:  # noqa: BLE001
            logger.warning("odds500 建表失败: %s", e)
            return {"ok": False, "reason": "db_error"}
        _calls.append(now)
        kickoff = datetime.fromtimestamp(float(m["match_timestamp"]), _BJ).replace(tzinfo=None)
        got, failed, ticks_n = [], [], 0
        with Odds500Client() as c:
            fid, why = _resolve_fid(c, m)
            if not fid:
                res = {"ok": False, "reason": why or "no_fid", "requests": c.requests}
                return res
            for cid in LIVE_CIDS:
                for kind in KINDS:
                    if not c.allow():
                        failed.append(f"{COMPANIES[cid]}/{kind}")
                        continue
                    rows = c.fetch_history(kind, fid, cid, kickoff)
                    if rows is None:
                        failed.append(f"{COMPANIES[cid]}/{kind}")
                        continue
                    got.append(f"{COMPANIES[cid]}/{kind}")
                    if rows:
                        try:
                            ticks_n += _save(kind, match_id, rows, COMPANIES[cid], cid)
                        except Exception as e:  # noqa: BLE001
                            logger.warning("odds500 落库失败 %s %s/%s: %s", match_id, kind, cid, e)
                            failed.append(f"{COMPANIES[cid]}/{kind}")
            reqs = c.requests
        fetched_at = datetime.now(_BJ).strftime("%Y-%m-%d %H:%M:%S")
        res = {"ok": bool(got), "reason": None if got else "all_failed", "fetchedAt": fetched_at,
               "requests": reqs, "ticks": ticks_n, "got": len(got), "failed": failed}
        if got:
            _recent[match_id] = (time.time(), res)
        logger.info("odds500 实时抓取 %s: 成功%s 失败%s 请求%s 写入%s点", match_id, len(got), len(failed), reqs, ticks_n)
        return res
    finally:
        _lock.release()


REASON_TEXT = {
    "blocked": "500.com 当前处于限流退避期", "busy": "另一个实时抓取正在进行", "rate_limited": "实时抓取次数已达每小时上限",
    "not_listed": "500.com 竞彩列表里没找到这场比赛", "kickoff_mismatch": "500.com 场次与本场开赛时间对不上(为防错配已放弃)",
    "no_mapping": "缺少场次编号,无法映射到 500.com", "list_failed": "500.com 列表页获取失败", "too_old": "比赛已结束较久",
    "no_match": "未找到比赛", "db_error": "数据库暂不可用", "all_failed": "所有请求都失败了",
}
