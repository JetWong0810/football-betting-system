"""ゲキサカ临场スタメン発表抓取。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .http_client import GEKI_BASE, JpHttp
from .formation_util import resolve_formation, extract_formation_from_text


LIST_URL = f"{GEKI_BASE}/news/jleague/"


def list_stamen_articles(http: JpHttp) -> List[Dict[str, str]]:
    """列表页中带「スタメン発表」的新闻。"""
    html = http.get_text(LIST_URL)
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for a in soup.select("a[href]"):
        title = a.get_text(strip=True)
        href = a.get("href") or ""
        if "スタメン発表" not in title:
            continue
        if href.startswith("//"):
            url = "https:" + href
        elif href.startswith("http"):
            url = href
        else:
            url = urljoin(LIST_URL, href)
        if url in seen:
            continue
        seen.add(url)
        home, away = _parse_title_teams(title)
        out.append({"title": title, "url": url, "home_hint": home or "", "away_hint": away or ""})
    return out


def _parse_title_teams(title: str) -> Tuple[Optional[str], Optional[str]]:
    m = re.match(r"^(.+?)vs(.+?)\s*スタメン", title)
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip()


def fetch_stamen_article(http: JpHttp, url: str) -> Dict[str, Any]:
    html = http.get_text(url)
    data = parse_stamen_html(html)
    data["source_url"] = url
    return data


def parse_stamen_html(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "")
    home_hint, away_hint = _parse_title_teams(title.replace(" | ゲキサカ", ""))

    article = soup.select_one("article") or soup
    text = article.get_text("\n", strip=True).replace("\u3000", " ")

    blocks = _split_team_blocks(text)
    # 全文/分队正文里的明文阵型（少见）
    global_form = extract_formation_from_text(text)
    lineups = []
    for i, block in enumerate(blocks[:2]):
        starters, bench = _extract_xi_and_bench(block["body"])
        if len(starters) < 8:
            continue
        form_info = resolve_formation(starters, text=block["body"])
        if not form_info.get("formation") and global_form:
            form_info = {"formation": global_form, "formationEstimated": False}
        lineups.append({
            "team_hint": block["name"],
            "side": "home" if i == 0 else "away",
            "players": starters[:11],
            "bench": bench,
            "formation": form_info.get("formation"),
            "formationEstimated": form_info.get("formationEstimated", False),
        })

    return {
        "title": title,
        "home_hint": home_hint,
        "away_hint": away_hint,
        "lineups": lineups,
    }


def _split_team_blocks(text: str) -> List[Dict[str, str]]:
    # 允许换行: [\n横浜F・マリノス\n]
    parts = re.split(r"[【\[]\s*([^\n】\]]{2,40}?)\s*[】\]]", text)
    blocks = []
    if len(parts) >= 3:
        for i in range(1, len(parts) - 1, 2):
            name = parts[i].strip()
            body = parts[i + 1]
            if "先発" in body or re.search(r"\bGK\b", body):
                # 跳过导航噪声
                if name in ("J1", "J2", "J3") or "一覧" in name or re.match(r"^\d", name):
                    continue
                blocks.append({"name": name, "body": body})
    return blocks


def _extract_xi_and_bench(body: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    # 先発 ... 控え ...
    start_part = body
    bench_part = ""
    m = re.search(r"先発([\s\S]*?)(?:控え|ベンチ|監督)", body)
    if m:
        start_part = m.group(1)
    m2 = re.search(r"控え([\s\S]*?)(?:監督|$)", body)
    if m2:
        bench_part = m2.group(1)

    # 多行格式: GK 36\nルベン・ブランコ
    starters = _extract_players_multiline(start_part)
    bench = _extract_players_multiline(bench_part) if bench_part else []
    if len(starters) < 8:
        starters = _extract_players_inline(start_part)
    return starters, bench


def _extract_players_multiline(body: str) -> List[Dict[str, str]]:
    players = []
    # GK 36\nName  or GK 36 Name
    for m in re.finditer(
        r"\b(GK|DF|MF|FW)\s+(\d{1,2})\s*\n\s*([^\n【\[\d]{2,40})",
        body,
    ):
        name = re.sub(r"\s+", " ", m.group(3)).strip(" 　・·#")
        if len(name) < 2:
            continue
        players.append({"pos": m.group(1), "num": m.group(2), "name": name})
    if len(players) >= 8:
        return players
    return _extract_players_inline(body)


def _extract_players_inline(body: str) -> List[Dict[str, str]]:
    players = []
    for m in re.finditer(
        r"\b(GK|DF|MF|FW)\s+(\d{1,2})\s+([^\n]{2,40}?)(?=(?:\b(?:GK|DF|MF|FW)\s+\d)|$)",
        body,
    ):
        name = re.sub(r"\s+", " ", m.group(3)).strip()
        players.append({"pos": m.group(1), "num": m.group(2), "name": name})
    return players
