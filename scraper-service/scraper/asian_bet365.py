"""在售场 Bet365 亚盘定时抓取(500.com)。

列表页 yazhi_jczq_{date}.shtml → match_code→fid;
详情页 yazhi-{fid}.shtml → 仅取 Bet365 初盘+即时盘。
500.com 原值正=主让; 调用方入库前取反成标准负=主让。
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://odds.500.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 500.com 亚盘页公司名常脱敏; Bet365 稳定 cid=3(与 odds500 EURO_COMPANIES 一致)
BET365_CID = 3
_BET365_ALIASES = frozenset({
    "Bet365", "**t3*5", "**t3*5**t3*5",
    "B*****", "B*****B*****",
})


HANDICAP_MAP = {
    "平手": 0, "平/半": 0.25, "平手/半球": 0.25, "半球": 0.5,
    "半/一": 0.75, "半球/一球": 0.75, "一球": 1.0,
    "一/球半": 1.25, "一球/球半": 1.25, "球半": 1.5,
    "球半/两": 1.75, "球半/两球": 1.75, "两球": 2.0,
    "两/两球半": 2.25, "两球/两球半": 2.25, "两球半": 2.5,
    "两球半/三": 2.75, "两球半/三球": 2.75, "三球": 3.0,
}

# sale_date → {match_code: fid}
_fid_cache: Dict[str, Dict[str, str]] = {}


def clear_fid_cache() -> None:
    _fid_cache.clear()


def _is_bet365(raw_name: str, cid: str) -> bool:
    if cid and str(cid).isdigit() and int(cid) == BET365_CID:
        return True
    name = (raw_name or "").strip()
    if name in _BET365_ALIASES:
        return True
    if "**t3*5" in name or "Bet365" in name.lower() or "t365" in name.lower():
        return True
    if len(name) > 4:
        half = len(name) // 2
        if name[:half] == name[half:] and name[:half] in _BET365_ALIASES:
            return True
    return False


def _parse_odds(text: str) -> Optional[float]:
    text = (text or "").strip().replace("↑", "").replace("↓", "")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _clean_handicap(text: str) -> str:
    return (text or "").strip().replace("升", "").replace("降", "")


def _parse_handicap_value(text: str) -> Optional[float]:
    if not text:
        return None
    text = text.strip().replace("升", "").replace("降", "")
    negative = False
    if text.startswith("受"):
        negative = True
        text = text[1:]
    val = HANDICAP_MAP.get(text)
    if val is None:
        try:
            val = float(text)
        except (ValueError, TypeError):
            return None
    return -val if negative else val


def load_fid_map(sale_date: str, timeout: int = 15) -> Dict[str, str]:
    """抓取售卖日列表页, 返回 {match_code: fid}。同日缓存。"""
    if sale_date in _fid_cache:
        return _fid_cache[sale_date]
    url = f"{BASE_URL}/yazhi_jczq_{sale_date}.shtml"
    result: Dict[str, str] = {}
    try:
        with httpx.Client(timeout=timeout, headers=HEADERS) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            logger.warning(f"亚盘列表失败 {sale_date}: HTTP {resp.status_code}")
            _fid_cache[sale_date] = result
            return result
        content = resp.content.decode("gbk", errors="replace")
        soup = BeautifulSoup(content, "html.parser")
        for tr in soup.find_all("tr", attrs={"data-fid": True}):
            tds = tr.find_all("td")
            if len(tds) < 1:
                continue
            code = tds[0].get_text(strip=True)
            fid = tr.get("data-fid")
            if code and fid:
                result[code] = str(fid)
    except Exception as e:
        logger.warning(f"亚盘列表异常 {sale_date}: {e}")
    _fid_cache[sale_date] = result
    return result


def get_fid(sale_date: str, match_code: str) -> Optional[str]:
    if not sale_date or not match_code:
        return None
    m = load_fid_map(sale_date)
    if match_code in m:
        return m[match_code]
    # 售卖日与列表页偶有 ±1 天错位
    from datetime import datetime, timedelta
    try:
        base = datetime.strptime(sale_date, "%Y-%m-%d")
    except ValueError:
        return None
    for delta in (-1, 1, -2, 2):
        alt = (base + timedelta(days=delta)).strftime("%Y-%m-%d")
        hit = load_fid_map(alt).get(match_code)
        if hit:
            return hit
    return None


def fetch_bet365_line(fid: str, timeout: int = 15) -> Optional[Dict]:
    """抓 Bet365 亚盘初/即时。返回 500 原值(正=主让)字段, 无则 None。

    优先用 tr id(cid)=3 识别 Bet365(脱敏名 B***** / **t3*5 不稳定)。
    dict keys: open_hc, close_hc, open_home, open_away, close_home, close_away
    """
    if not fid:
        return None
    url = f"{BASE_URL}/fenxi/yazhi-{fid}.shtml"
    try:
        with httpx.Client(timeout=timeout, headers=HEADERS) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            logger.warning(f"亚盘详情失败 fid={fid}: HTTP {resp.status_code}")
            return None
        content = resp.content.decode("gbk", errors="replace")
    except Exception as e:
        logger.warning(f"亚盘详情异常 fid={fid}: {e}")
        return None

    soup = BeautifulSoup(content, "html.parser")
    table = soup.find("table", id="datatb")
    if not table:
        return None

    rows = table.find_all("tr")
    i = 0
    while i < len(rows):
        tr = rows[i]
        tds = tr.find_all("td")
        if len(tds) >= 12 and tds[0].get("class") == ["td_one"]:
            raw = tds[1].get_text(strip=True)
            cid = tr.get("id", "")
            if _is_bet365(raw, cid):
                close_home = _parse_odds(tds[3].get_text(strip=True))
                close_hc = _parse_handicap_value(_clean_handicap(tds[4].get_text(strip=True)))
                close_away = _parse_odds(tds[5].get_text(strip=True))
                open_home = _parse_odds(tds[9].get_text(strip=True))
                open_hc = _parse_handicap_value(
                    _clean_handicap(tds[10].get_text(strip=True)) if len(tds) > 10 else ""
                )
                open_away = _parse_odds(tds[11].get_text(strip=True)) if len(tds) > 11 else None
                if close_hc is None:
                    return None
                return {
                    "open_hc": open_hc,
                    "close_hc": close_hc,
                    "open_home": open_home,
                    "open_away": open_away,
                    "close_home": close_home,
                    "close_away": close_away,
                }
            i += 3
        else:
            i += 1
    return None


def to_std_line(raw_hc: Optional[float]) -> Optional[float]:
    """500 原值(正=主让) → 标准(负=主让)。"""
    if raw_hc is None:
        return None
    try:
        return -float(raw_hc)
    except (TypeError, ValueError):
        return None
