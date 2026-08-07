"""解析 SFMS02 官网公式记录：首发 / 替补 / 天气。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from .http_client import DATA_BASE, JpHttp

POS = {"GK", "DF", "MF", "FW"}


def fetch_match_card(http: JpHttp, match_card_id: int) -> Dict[str, Any]:
    url = f"{DATA_BASE}/SFMS02/?match_card_id={match_card_id}"
    html = http.get_text(url)
    data = parse_match_card(html)
    data["match_card_id"] = match_card_id
    data["source_url"] = url
    return data


def parse_match_card(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    weather = _parse_weather(soup)
    lineups = _parse_lineups(soup)
    return {"weather": weather, "lineups": lineups}


def _parse_weather(soup: BeautifulSoup) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for table in soup.select("table"):
        rows = table.select("tr")
        if len(rows) < 2:
            continue
        headers = [c.get_text(" ", strip=True) for c in rows[0].select("th,td")]
        if "天候" not in headers or "気温" not in headers:
            continue
        vals = [c.get_text(" ", strip=True) for c in rows[1].select("th,td")]
        if len(vals) < len(headers):
            continue
        mapping = dict(zip(headers, vals))
        if mapping.get("天候"):
            out["weather_text"] = mapping["天候"]
        if mapping.get("気温"):
            try:
                out["temp_c"] = float(re.sub(r"[^\d.]", "", mapping["気温"]))
            except ValueError:
                pass
        if mapping.get("湿度"):
            try:
                out["humidity"] = int(re.sub(r"[^\d]", "", mapping["湿度"]) or "0")
            except ValueError:
                pass
        break
    return out


def _is_player_row(cells: List[str]) -> bool:
    if len(cells) < 3:
        return False
    return cells[0] in POS and bool(re.match(r"^\d+$", cells[1] or ""))


def _parse_lineups(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """尽力从公式记录页抽出两队首发。

    SFMS02 结构多变：按「连续 GK/DF/MF/FW 行」切段，前两段视为主/客首发。
    """
    blocks: List[List[Dict[str, str]]] = []
    current: List[Dict[str, str]] = []

    for tr in soup.select("table tr"):
        cells = [c.get_text(" ", strip=True).replace("\u3000", " ") for c in tr.select("th,td")]
        if _is_player_row(cells):
            current.append({
                "pos": cells[0],
                "num": cells[1],
                "name": re.sub(r"\s+", " ", cells[2]).strip(),
            })
        else:
            if len(current) >= 8:  # 接近一队首发
                blocks.append(current)
            current = []
    if len(current) >= 8:
        blocks.append(current)

    # 取前两个满员块(优先 11 人)
    starters = []
    for b in blocks:
        if len(b) >= 11:
            starters.append(b[:11])
        elif len(b) >= 8:
            starters.append(b)
        if len(starters) >= 2:
            break

    out = []
    for i, players in enumerate(starters[:2]):
        out.append({
            "side": "home" if i == 0 else "away",
            "players": players,
            "bench": [],
        })
    return out
