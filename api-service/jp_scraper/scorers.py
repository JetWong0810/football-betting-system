"""通算得点榜 SFTD08（免费）。"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from bs4 import BeautifulSoup

from .http_client import DATA_BASE, JpHttp
from .schedule import FRAME_COMP


def fetch_top_scorers(http: JpHttp, competition_frame_id: int = 1,
                      year_from: int = 2025, year_to: int = 2025,
                      goals_from: int = 1) -> List[Dict[str, Any]]:
    url = f"{DATA_BASE}/SFTD08/search"
    html = http.get_text(
        url,
        competition_frames=competition_frame_id,
        competition_year_from=year_from,
        competition_year_to=year_to,
        goals_from=goals_from,
    )
    return parse_scorers_html(html)


def parse_scorers_html(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, Any]] = []
    for table in soup.select("table"):
        headers = [th.get_text(strip=True) for th in table.select("tr th")]
        if "得点" not in "".join(headers) and "選手名" not in "".join(headers):
            # 也可能首行全是 td
            first = table.select_one("tr")
            if first:
                headers = [c.get_text(strip=True) for c in first.select("th,td")]
            if "得点" not in "".join(headers):
                continue
        # map columns
        col = {h: i for i, h in enumerate(headers)}
        for tr in table.select("tr")[1:]:
            cells = [td.get_text(" ", strip=True).replace("\u3000", " ") for td in tr.select("td")]
            if len(cells) < 5:
                continue
            try:
                rank = int(cells[col.get("順位", 1)]) if cells[col.get("順位", 1)].isdigit() else None
                name = cells[col.get("選手名", 2)]
                club = cells[col.get("所属(J最終所属)", 3)] if "所属(J最終所属)" in col else cells[3]
                goals = int(re.sub(r"[^\d]", "", cells[col.get("得点", 4)]) or "0")
                apps = None
                if "出場" in col and col["出場"] < len(cells):
                    apps = int(re.sub(r"[^\d]", "", cells[col["出場"]]) or "0")
            except (ValueError, IndexError):
                continue
            if not name or goals <= 0:
                continue
            out.append({
                "rank_no": rank,
                "player_name": name,
                "club_short": club,
                "goals": goals,
                "apps": apps,
            })
        if out:
            break
    return out


def competition_label(frame_id: int) -> str:
    return FRAME_COMP.get(frame_id, f"frame{frame_id}")
