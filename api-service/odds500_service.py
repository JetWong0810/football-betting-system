"""500.com 赔率数据实时抓取服务

按需从 500.com 获取欧赔、亚盘、大小球数据，返回结构化结果。
数据源:
  - 欧赔 JSON API: odds.500.com/fenxi1/json/ouzhi.php?fid={fid}&cid={cid}
  - 欧赔 HTML 页面: odds.500.com/fenxi/ouzhi-{fid}.shtml (全部公司初盘/即时)
  - 亚盘 HTML 页面: odds.500.com/fenxi/yazhi-{fid}.shtml
  - 大小球 HTML 页面: odds.500.com/fenxi/daxiao-{fid}.shtml
  - 竞彩列表页: odds.500.com/yazhi_jczq_{YYYY-MM-DD}.shtml (用于 match_number → fid 映射)
"""

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://odds.500.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

EURO_COMPANIES = {
    3: "Bet365",
    293: "威廉希尔",
    1055: "Pinnacle",
    280: "皇冠",
    5: "澳门",
    122: "香港马会",
}

COMPANY_MAP = {
    "Pi****le": "Pinnacle", "Pi****le平*": "Pinnacle",
    "*冠": "皇冠", "*冠*冠": "皇冠",
    "**t3*5": "Bet365", "**t3*5**t3*5": "Bet365",
    "威**尔": "威廉希尔", "威**尔威**尔": "威廉希尔",
    "易*博": "易胜博", "易*博易*博": "易胜博",
    "*门": "澳门", "*门*门": "澳门",
    "立*": "立博", "立*立*": "立博",
    "利*": "利记", "利*利*": "利记",
    "伟*": "伟德", "伟*伟*": "伟德",
    "I***rw**t*n": "Interwetten",
    "on**": "10BET", "on**on**": "10BET",
    "18**t": "18Bet", "18**t18**t": "18Bet",
    "12**t (壹*博)": "12Bet", "12**t (壹*博)12**t (壹*博)": "12Bet",
    "M****on88 (明*)": "明陞", "M****on88 (明*)M****on88 (明*)": "明陞",
    "W****t (盈*)": "盈禾", "W****t (盈*)W****t (盈*)": "盈禾",
    "香**会": "香港马会", "香**会香**会": "香港马会",
    "竞*官*": "竞彩官方",
    "C***l": "Coral",
    "必*": "必发",
    "1x**t": "1xBet",
}

EURO_COMPANY_MAP = {
    "竞*官*": "竞彩官方",
    "*门": "澳门",
    "**t3*5": "Bet365",
    "*冠": "皇冠",
    "伟*": "伟德",
    "Pi****le": "Pinnacle",
    "香**会": "香港马会",
    "必*": "必发",
    "C***l": "Coral",
    "1x**t": "1xBet",
}

HANDICAP_MAP = {
    "平手": 0, "平/半": 0.25, "平手/半球": 0.25, "半球": 0.5,
    "半/一": 0.75, "半球/一球": 0.75, "一球": 1.0,
    "一/球半": 1.25, "一球/球半": 1.25, "球半": 1.5,
    "球半/两": 1.75, "球半/两球": 1.75, "两球": 2.0,
    "两/两球半": 2.25, "两球/两球半": 2.25, "两球半": 2.5,
    "两球半/三": 2.75, "两球半/三球": 2.75, "三球": 3.0,
}

# FID 缓存: match_number -> fid
_fid_cache: Dict[str, str] = {}


def _identify_company(raw_name: str) -> str:
    if raw_name in COMPANY_MAP:
        return COMPANY_MAP[raw_name]
    if len(raw_name) > 4:
        half = len(raw_name) // 2
        if raw_name[:half] == raw_name[half:]:
            short = raw_name[:half]
            if short in COMPANY_MAP:
                return COMPANY_MAP[short]
            return short
    return raw_name


def _parse_odds(text: str) -> Optional[float]:
    text = text.strip().replace("↑", "").replace("↓", "")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


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


def _clean_handicap(text: str) -> str:
    return text.strip().replace("升", "").replace("降", "")


def get_fid_for_match(match_date: str, match_number: str) -> Optional[str]:
    """通过竞彩列表页获取 500.com fixture ID"""
    cache_key = f"{match_date}:{match_number}"
    if cache_key in _fid_cache:
        return _fid_cache[cache_key]

    try:
        url = f"{BASE_URL}/yazhi_jczq_{match_date}.shtml"
        with httpx.Client(timeout=15, headers=HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                logger.warning(f"获取竞彩列表失败: {resp.status_code}")
                return None

        content = resp.content.decode("gbk", errors="replace")
        soup = BeautifulSoup(content, "html.parser")

        for tr in soup.find_all("tr", attrs={"data-fid": True}):
            tds = tr.find_all("td")
            if len(tds) < 7:
                continue
            num = tds[0].get_text(strip=True)
            fid = tr["data-fid"]
            key = f"{match_date}:{num}"
            _fid_cache[key] = fid

        return _fid_cache.get(cache_key)

    except Exception as e:
        logger.error(f"获取FID失败: {e}")
        return None


def fetch_european_odds(fid: str) -> Dict[str, Any]:
    """获取欧赔数据 - 从百家欧赔页面抓取所有公司初盘/即时盘"""
    url = f"{BASE_URL}/fenxi/ouzhi-{fid}.shtml"
    try:
        with httpx.Client(timeout=15, headers=HEADERS) as client:
            resp = client.get(url)

        html = resp.content.decode("gbk", errors="replace")
        return _parse_european_page(html)
    except Exception as e:
        logger.error(f"获取欧赔失败 fid={fid}: {e}")
        return {"companies": [], "summary": {}}


def _parse_european_page(html: str) -> Dict[str, Any]:
    """解析百家欧赔页面 - tr.tr1 每行27个td"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="datatb")
    if not table:
        return {"companies": [], "summary": {}}

    companies = []
    company_rows = table.find_all("tr", class_="tr1")

    for tr in company_rows:
        cid = tr.get("id", "")
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue

        # 公司名从 title 属性或文本取
        company_td = tds[1]
        raw_name = company_td.get("title", "") or company_td.get_text(strip=True)
        company_name = _identify_company(raw_name)

        # td[3-5] = 初盘(胜/平/负), td[6-8] = 即时(胜/平/负)
        init_w = _parse_odds(tds[3].get_text(strip=True))
        init_d = _parse_odds(tds[4].get_text(strip=True))
        init_l = _parse_odds(tds[5].get_text(strip=True))
        curr_w = _parse_odds(tds[6].get_text(strip=True))
        curr_d = _parse_odds(tds[7].get_text(strip=True))
        curr_l = _parse_odds(tds[8].get_text(strip=True))

        if not all([init_w, init_d, init_l, curr_w, curr_d, curr_l]):
            continue

        # 返还率: td[17]=初盘返还率, td[18]=即时返还率
        return_rate = 0.0
        if len(tds) > 18:
            rate_text = tds[18].get_text(strip=True).replace("%", "")
            try:
                return_rate = float(rate_text)
            except (ValueError, TypeError):
                if curr_w and curr_d and curr_l:
                    return_rate = round(1 / (1/curr_w + 1/curr_d + 1/curr_l) * 100, 2)

        companies.append({
            "bookmaker": company_name,
            "cid": int(cid) if cid.isdigit() else 0,
            "initial": {"win": init_w, "draw": init_d, "lose": init_l},
            "current": {"win": curr_w, "draw": curr_d, "lose": curr_l},
            "returnRate": return_rate,
        })

    summary = _calc_euro_summary(companies)
    return {"companies": companies, "summary": summary}


def _calc_euro_summary(companies: List[Dict]) -> Dict[str, Any]:
    """计算欧赔统计值(最大/最小/平均)"""
    if not companies:
        return {}

    wins_init = [c["initial"]["win"] for c in companies if c["initial"]["win"]]
    draws_init = [c["initial"]["draw"] for c in companies if c["initial"]["draw"]]
    loses_init = [c["initial"]["lose"] for c in companies if c["initial"]["lose"]]
    wins_curr = [c["current"]["win"] for c in companies if c["current"]["win"]]
    draws_curr = [c["current"]["draw"] for c in companies if c["current"]["draw"]]
    loses_curr = [c["current"]["lose"] for c in companies if c["current"]["lose"]]
    returns = [c["returnRate"] for c in companies if c["returnRate"]]

    def safe_max(lst): return round(max(lst), 2) if lst else 0
    def safe_min(lst): return round(min(lst), 2) if lst else 0
    def safe_avg(lst): return round(sum(lst)/len(lst), 2) if lst else 0

    return {
        "max": {
            "initial": {"win": safe_max(wins_init), "draw": safe_max(draws_init), "lose": safe_max(loses_init)},
            "current": {"win": safe_max(wins_curr), "draw": safe_max(draws_curr), "lose": safe_max(loses_curr)},
            "returnRate": safe_max(returns),
        },
        "min": {
            "initial": {"win": safe_min(wins_init), "draw": safe_min(draws_init), "lose": safe_min(loses_init)},
            "current": {"win": safe_min(wins_curr), "draw": safe_min(draws_curr), "lose": safe_min(loses_curr)},
            "returnRate": safe_min(returns),
        },
        "avg": {
            "initial": {"win": safe_avg(wins_init), "draw": safe_avg(draws_init), "lose": safe_avg(loses_init)},
            "current": {"win": safe_avg(wins_curr), "draw": safe_avg(draws_curr), "lose": safe_avg(loses_curr)},
            "returnRate": safe_avg(returns),
        },
    }


def fetch_asian_handicap(fid: str) -> List[Dict[str, Any]]:
    """获取亚盘数据"""
    url = f"{BASE_URL}/fenxi/yazhi-{fid}.shtml"
    try:
        with httpx.Client(timeout=15, headers=HEADERS) as client:
            resp = client.get(url)

        content = resp.content.decode("gbk", errors="replace")
        return _parse_asian_page(content)
    except Exception as e:
        logger.error(f"获取亚盘失败 fid={fid}: {e}")
        return []


def _parse_asian_page(html: str) -> List[Dict[str, Any]]:
    """解析亚盘页面"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="datatb")
    if not table:
        return []

    rows = table.find_all("tr")
    companies = []
    i = 0
    while i < len(rows):
        tr = rows[i]
        tds = tr.find_all("td")
        if len(tds) >= 12 and tds[0].get("class") == ["td_one"]:
            company_raw = tds[1].get_text(strip=True)
            company = _identify_company(company_raw)
            cid = tr.get("id", "")

            latest_home = _parse_odds(tds[3].get_text(strip=True))
            latest_hcap_text = _clean_handicap(tds[4].get_text(strip=True))
            latest_away = _parse_odds(tds[5].get_text(strip=True))
            init_home = _parse_odds(tds[9].get_text(strip=True))
            init_hcap_text = _clean_handicap(tds[10].get_text(strip=True)) if len(tds) > 10 else ""
            init_away = _parse_odds(tds[11].get_text(strip=True)) if len(tds) > 11 else None

            companies.append({
                "bookmaker": company,
                "cid": int(cid) if cid.isdigit() else 0,
                "initial": {
                    "home": init_home,
                    "handicap": _parse_handicap_value(init_hcap_text),
                    "handicapText": init_hcap_text,
                    "away": init_away,
                },
                "current": {
                    "home": latest_home,
                    "handicap": _parse_handicap_value(latest_hcap_text),
                    "handicapText": latest_hcap_text,
                    "away": latest_away,
                },
            })
            i += 3
        else:
            i += 1

    return companies


def fetch_over_under(fid: str) -> List[Dict[str, Any]]:
    """获取大小球数据"""
    url = f"{BASE_URL}/fenxi/daxiao-{fid}.shtml"
    try:
        with httpx.Client(timeout=15, headers=HEADERS) as client:
            resp = client.get(url)

        content = resp.content.decode("gbk", errors="replace")
        return _parse_over_under_page(content)
    except Exception as e:
        logger.error(f"获取大小球失败 fid={fid}: {e}")
        return []


def _parse_over_under_page(html: str) -> List[Dict[str, Any]]:
    """解析大小球页面"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="datatb")
    if not table:
        return []

    rows = table.find_all("tr")
    companies = []
    i = 0
    while i < len(rows):
        tr = rows[i]
        tds = tr.find_all("td")
        if len(tds) >= 12 and tds[0].get("class") == ["td_one"]:
            company_raw = tds[1].get_text(strip=True)
            company = _identify_company(company_raw)
            cid = tr.get("id", "")

            latest_over = _parse_odds(tds[3].get_text(strip=True))
            latest_line_text = tds[4].get_text(strip=True).replace("升", "").replace("降", "")
            latest_under = _parse_odds(tds[5].get_text(strip=True))
            init_over = _parse_odds(tds[9].get_text(strip=True))
            init_line_text = tds[10].get_text(strip=True).replace("升", "").replace("降", "") if len(tds) > 10 else ""
            init_under = _parse_odds(tds[11].get_text(strip=True)) if len(tds) > 11 else None

            latest_line = _parse_odds(latest_line_text)
            init_line = _parse_odds(init_line_text)

            companies.append({
                "bookmaker": company,
                "cid": int(cid) if cid.isdigit() else 0,
                "initial": {
                    "over": init_over,
                    "line": init_line,
                    "under": init_under,
                },
                "current": {
                    "over": latest_over,
                    "line": latest_line,
                    "under": latest_under,
                },
            })
            i += 3
        else:
            i += 1

    return companies


def fetch_all_indices(fid: str) -> Dict[str, Any]:
    """获取完整指数数据(欧赔+亚盘+大小球) - 并发请求"""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=3) as executor:
        euro_future = executor.submit(fetch_european_odds, fid)
        asian_future = executor.submit(fetch_asian_handicap, fid)
        ou_future = executor.submit(fetch_over_under, fid)

        euro_data = euro_future.result()
        asian_data = asian_future.result()
        ou_data = ou_future.result()

    # 欧赔: 组合统计值+公司列表
    euro_list = []
    summary = euro_data.get("summary", {})
    if summary.get("max"):
        euro_list.append({
            "bookmaker": "最大值",
            "initial": summary["max"]["initial"],
            "current": summary["max"]["current"],
            "returnRate": summary["max"]["returnRate"],
        })
    if summary.get("min"):
        euro_list.append({
            "bookmaker": "最小值",
            "initial": summary["min"]["initial"],
            "current": summary["min"]["current"],
            "returnRate": summary["min"]["returnRate"],
        })
    if summary.get("avg"):
        euro_list.append({
            "bookmaker": "平均值",
            "initial": summary["avg"]["initial"],
            "current": summary["avg"]["current"],
            "returnRate": summary["avg"]["returnRate"],
        })

    # 添加主要公司数据
    for company in euro_data.get("companies", []):
        euro_list.append(company)

    return {
        "european": euro_list,
        "asian": asian_data,
        "overUnder": ou_data,
    }


def fetch_euro_history(fid: str, cid: int) -> List[Dict[str, Any]]:
    """获取某公司欧赔变动历史 (JSON API)"""
    url = f"{BASE_URL}/fenxi1/json/ouzhi.php"
    params = {"fid": fid, "cid": cid, "r": 1}
    headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/fenxi/ouzhi-{fid}.shtml",
    }
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, params=params, headers=headers)
        data = resp.json()
        if not isinstance(data, list):
            return []
        return [
            {
                "win": float(r[0]),
                "draw": float(r[1]),
                "lose": float(r[2]),
                "returnRate": float(r[3]),
                "time": r[4],
            }
            for r in data if len(r) >= 5
        ]
    except Exception as e:
        logger.error(f"获取欧赔历史失败 fid={fid} cid={cid}: {e}")
        return []


def fetch_asian_history(fid: str, cid: int) -> List[Dict[str, Any]]:
    """获取某公司亚盘变动历史 (AJAX API)"""
    url = f"{BASE_URL}/fenxi1/inc/yazhiajax.php"
    params = {"fid": fid, "id": cid, "t": int(time.time() * 1000), "r": 1}
    headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/fenxi/yazhi-{fid}.shtml",
    }
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, params=params, headers=headers)
        data = resp.json()
        if not isinstance(data, list):
            return []

        records = []
        for html_str in data:
            soup = BeautifulSoup(html_str, "html.parser")
            tds = soup.find_all("td")
            if len(tds) < 4:
                continue
            records.append({
                "home": _parse_odds(tds[0].get_text(strip=True)),
                "handicap": _parse_handicap_value(_clean_handicap(tds[1].get_text(strip=True))),
                "handicapText": _clean_handicap(tds[1].get_text(strip=True)),
                "away": _parse_odds(tds[2].get_text(strip=True)),
                "time": tds[3].get_text(strip=True),
            })
        return records
    except Exception as e:
        logger.error(f"获取亚盘历史失败 fid={fid} cid={cid}: {e}")
        return []


def fetch_ou_history(fid: str, cid: int) -> List[Dict[str, Any]]:
    """获取某公司大小球变动历史 (AJAX API)"""
    url = f"{BASE_URL}/fenxi1/inc/daxiaoajax.php"
    params = {"fid": fid, "id": cid, "t": int(time.time() * 1000), "r": 1}
    headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/fenxi/daxiao-{fid}.shtml",
    }
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, params=params, headers=headers)
        data = resp.json()
        if not isinstance(data, list):
            return []

        records = []
        for html_str in data:
            soup = BeautifulSoup(html_str, "html.parser")
            tds = soup.find_all("td")
            if len(tds) < 4:
                continue
            records.append({
                "over": _parse_odds(tds[0].get_text(strip=True)),
                "line": _parse_odds(tds[1].get_text(strip=True)),
                "under": _parse_odds(tds[2].get_text(strip=True)),
                "time": tds[3].get_text(strip=True),
            })
        return records
    except Exception as e:
        logger.error(f"获取大小球历史失败 fid={fid} cid={cid}: {e}")
        return []
