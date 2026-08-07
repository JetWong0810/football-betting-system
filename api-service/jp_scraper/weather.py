"""Open-Meteo 赛前天气预报。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import httpx

# 常用场馆坐标（可后续扩充 jp_venues）
VENUE_COORDS = {
    "MUFG国立": (35.6779, 139.7145),
    "パナスタ": (34.8031, 135.4761),
    "日産ス": (35.4697, 139.6211),
    "味スタ": (35.6644, 139.5272),
    "豊田ス": (35.0844, 137.1194),
    "Ｅピース": (34.4394, 132.3947),
    "三協Ｆ柏": (35.8722, 139.9764),
}


def forecast_at(lat: float, lon: float, kickoff: datetime) -> Optional[Dict[str, Any]]:
    hour = kickoff.replace(minute=0, second=0, microsecond=0)
    end = hour
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation_probability,windspeed_10m",
        "start_hour": hour.strftime("%Y-%m-%dT%H:%M"),
        "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
        "timezone": "Asia/Tokyo",
    }
    r = httpx.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    hourly = data.get("hourly") or {}
    temps = hourly.get("temperature_2m") or []
    precips = hourly.get("precipitation_probability") or []
    winds = hourly.get("windspeed_10m") or []
    if not temps:
        return None
    return {
        "temp_c": temps[0],
        "precip_prob": precips[0] if precips else None,
        "wind_ms": round((winds[0] or 0) / 3.6, 2) if winds else None,  # km/h → m/s approx
    }


def forecast_for_venue(venue_short: str, kickoff: datetime) -> Optional[Dict[str, Any]]:
    coords = VENUE_COORDS.get(venue_short)
    if not coords:
        return None
    return forecast_at(coords[0], coords[1], kickoff)
