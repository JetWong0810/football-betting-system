"""解析 data.j-league SFMS01 日程/比分表。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from .http_client import DATA_BASE, JpHttp

# competition_frame_id → 内部 competition 标签
FRAME_COMP = {
    1: "J1",
    2: "J2",
    3: "J3",
    11: "联杯",
}


def _parse_match_date(cell: str) -> Optional[str]:
    """'26/08/07(金)' / '25/02/14(金)' → YYYY-MM-DD"""
    m = re.search(r"(\d{2})/(\d{2})/(\d{2})", cell or "")
    if not m:
        return None
    yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    year = 2000 + yy
    return f"{year:04d}-{mm:02d}-{dd:02d}"


def _parse_kickoff(date_str: Optional[str], time_cell: str) -> Optional[datetime]:
    if not date_str:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", time_cell or "")
    if not m:
        return None
    return datetime.strptime(f"{date_str} {int(m.group(1)):02d}:{m.group(2)}:00", "%Y-%m-%d %H:%M:%S")


def _parse_score(cell: str) -> Tuple[Optional[int], Optional[int], str]:
    """返回 (home, away, status). status=finished|scheduled"""
    s = (cell or "").strip()
    if not s or s.lower() == "vs":
        return None, None, "scheduled"
    m = re.search(r"(\d+)\s*[-－]\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2)), "finished"
    return None, None, "scheduled"


def _extract_slug(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    m = re.search(r"/club/([^/]+)/", href)
    return m.group(1) if m else None


def _extract_card_id(href: Optional[str]) -> Optional[int]:
    if not href:
        return None
    if "match_card_id=" in href:
        q = parse_qs(urlparse(href if "://" in href else f"http://x{href}").query)
        vals = q.get("match_card_id") or []
        if vals and vals[0].isdigit():
            return int(vals[0])
    m = re.search(r"match_card_id=(\d+)", href)
    return int(m.group(1)) if m else None


def fetch_schedule(http: JpHttp, competition_frame_id: int, year: int) -> List[Dict[str, Any]]:
    """拉取某联赛某年日程行。"""
    url = f"{DATA_BASE}/SFMS01/search"
    html = http.get_text(url, competition_frame_ids=competition_frame_id, competition_years=year)
    return parse_schedule_html(html, competition_frame_id=competition_frame_id, year=year)


def parse_schedule_html(html: str, competition_frame_id: int, year: int) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table")
    if not tables:
        return []
    # 主表通常是最大的
    table = max(tables, key=lambda t: len(t.select("tr")))
    comp = FRAME_COMP.get(competition_frame_id, f"frame{competition_frame_id}")
    rows_out: List[Dict[str, Any]] = []
    for tr in table.select("tr")[1:]:
        tds = tr.select("td")
        if len(tds) < 8:
            continue
        cells = [td.get_text(" ", strip=True) for td in tds]
        # 期望列: シーズン 大会 節 試合日 K/O ホーム スコア アウェイ スタジアム ...
        season = cells[0]
        round_label = cells[2]
        match_date = _parse_match_date(cells[3])
        kickoff = _parse_kickoff(match_date, cells[4])
        home_short = cells[5]
        hs, aws, status = _parse_score(cells[6])
        away_short = cells[7]
        venue = cells[8] if len(cells) > 8 else ""

        home_slug = away_slug = None
        card_id = None
        for a in tr.select("a[href]"):
            href = a.get("href") or ""
            slug = _extract_slug(href)
            text = a.get_text(strip=True)
            if slug and text == home_short:
                home_slug = slug
            elif slug and text == away_short:
                away_slug = slug
            cid = _extract_card_id(href)
            if cid:
                card_id = cid

        rows_out.append({
            "season": season or str(year),
            "competition": comp,
            "competition_frame_id": competition_frame_id,
            "round_label": round_label,
            "match_date": match_date,
            "kickoff_at": kickoff,
            "home_short": home_short,
            "away_short": away_short,
            "home_slug": home_slug,
            "away_slug": away_slug,
            "home_score": hs,
            "away_score": aws,
            "status": status,
            "venue_short": venue,
            "match_card_id": card_id,
            "source_url": (
                f"{DATA_BASE}/SFMS02/?match_card_id={card_id}" if card_id else
                f"{DATA_BASE}/SFMS01/search?competition_frame_ids={competition_frame_id}&competition_years={year}"
            ),
        })
    return rows_out
