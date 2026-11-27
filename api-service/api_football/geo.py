"""球场城市地理编码(Open-Meteo, 免费)与客场旅途距离/时差。AF 的球场没有经纬度, 这里按城市补。
对不上的城市只记录"已尝试"(geocoded_at), 不反复重试; 距离计算遇到没有坐标就不输出。"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from database import get_db

from .hist import haversine_km

logger = logging.getLogger(__name__)
URL = "https://geocoding-api.open-meteo.com/v1/search"


_ALIAS = {"usa": "united states", "uae": "united arab emirates", "czech republic": "czechia", "bosnia": "bosnia and herzegovina",
          "ivory coast": "cote d'ivoire", "faroe islands": "faroe islands", "turkey": "turkey", "south korea": "south korea"}
_UK = {"england", "scotland", "wales", "northern ireland"}


def norm_country(c: Optional[str]) -> str:
    c = (c or "").replace("-", " ").strip().lower()
    if c in _UK:
        return "united kingdom"
    return _ALIAS.get(c, c)


def pick_result(results: list, country: Optional[str], region_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """从候选里取国家一致的(AF 与 Open-Meteo 的国家写法先做规范化); 有州/郡提示时优先匹配 admin1。
    国家对不上宁可返回 None(这个球场就没有旅途信息), 也不退回第一个结果去猜, 否则会把"Chester, Pennsylvania"编码成英国。"""
    if not results:
        return None
    c = norm_country(country)
    pool = [r for r in results if not c or norm_country(r.get("country")) == c or c in (r.get("country") or "").lower()]
    if not pool:
        return None
    if region_hint:
        h = region_hint.strip().lower()
        for r in pool:
            if h and h in ((r.get("admin1") or "").lower()):
                return r
    return pool[0]


def region_of(city: str) -> Optional[str]:
    parts = [x.strip() for x in (city or "").split(",")]
    return parts[1] if len(parts) > 1 and parts[1] else None


def query_candidates(city: str) -> list:
    """AF 的城市常带郡名("Bournemouth, Dorset"), 先用逗号前的城市名查, 查不到再用完整字符串。"""
    head = (city or "").split(",")[0].strip()
    out = [head] if head else []
    if city and city.strip() != head:
        out.append(city.strip())
    return out


def geocode_pending(limit: int = 200, pause: float = 0.25) -> int:
    n = 0
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT af_venue_id, city, country FROM af_venue WHERE geocoded_at IS NULL AND city IS NOT NULL AND city<>'' LIMIT %s", (limit,))
        rows = cur.fetchall()
    with httpx.Client(timeout=15) as h:
        for r in rows:
            lat = lon = tz = None
            failed = False
            for q in query_candidates(r["city"]):
                try:
                    res = h.get(URL, params={"name": q, "count": 5, "language": "en"}).json().get("results") or []
                except Exception as e:  # noqa: BLE001
                    logger.warning("地理编码失败 %s: %s", q, e)
                    failed = True                            # 网络类失败不标记已尝试, 下次重试
                    break
                pr = pick_result(res, r.get("country"), region_of(r["city"]))
                if pr:
                    lat, lon, tz = pr["latitude"], pr["longitude"], pr.get("timezone")
                    break
            if failed:
                continue
            with get_db() as conn:
                conn.cursor().execute("UPDATE af_venue SET lat=%s, lon=%s, tz=%s, geocoded_at=CURRENT_TIMESTAMP WHERE af_venue_id=%s", (lat, lon, tz, r["af_venue_id"]))
            n += 1
            time.sleep(pause)
    return n


def tz_offset_hours(tz: Optional[str], when: datetime) -> Optional[float]:
    if not tz:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz).utcoffset(when).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        return None


def travel(away_team_id: int, match_venue_id: Optional[int], when: datetime, home_team_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """客队从自己主场城市到比赛球场: 直线距离(km)和时差(小时)。任一端没有坐标返回 None。
    比赛没有球场 id 时(约 1/3 的比赛如此, 美职/巴甲/欧战居多)用主队的主场球场兜底; 中立场(决赛等)会有偏差。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT v.lat, v.lon, v.tz, v.city FROM af_team t JOIN af_venue v ON v.af_venue_id=t.venue_id WHERE t.af_team_id=%s", (away_team_id,))
        a = cur.fetchone()
        b = None
        if match_venue_id:
            cur.execute("SELECT lat, lon, tz, city FROM af_venue WHERE af_venue_id=%s", (match_venue_id,))
            b = cur.fetchone()
        if (not b or b["lat"] is None) and home_team_id:
            cur.execute("SELECT v.lat, v.lon, v.tz, v.city FROM af_team t JOIN af_venue v ON v.af_venue_id=t.venue_id WHERE t.af_team_id=%s", (home_team_id,))
            b = cur.fetchone()
    if not a or not b or a["lat"] is None or b["lat"] is None:
        return None
    d = haversine_km(float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"]))
    ta, tb = tz_offset_hours(a["tz"], when), tz_offset_hours(b["tz"], when)
    return {"km": round(d), "tz_diff": (round(tb - ta, 1) if ta is not None and tb is not None else None), "from": a["city"], "to": b["city"]}
