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
    "B*****": "Bet365", "B*****B*****": "Bet365",
    "威**尔": "威廉希尔", "威**尔威**尔": "威廉希尔",
    "威***": "威廉希尔", "威***威***": "威廉希尔",
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
    if raw_name in EURO_COMPANY_MAP:
        return EURO_COMPANY_MAP[raw_name]
    if len(raw_name) > 4:
        half = len(raw_name) // 2
        if raw_name[:half] == raw_name[half:]:
            short = raw_name[:half]
            if short in COMPANY_MAP:
                return COMPANY_MAP[short]
            if short in EURO_COMPANY_MAP:
                return EURO_COMPANY_MAP[short]
            return short
    return raw_name


def _identify_asian_company(raw_name: str, cid: str = "") -> str:
    """亚盘行识别: 优先 cid(Bet365=3), 再走脱敏名映射。"""
    if cid and str(cid).isdigit() and int(cid) == 3:
        return "Bet365"
    return _identify_company(raw_name)

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


# 竞彩列表页比分缓存: {match_date:match_number} -> (home_score, away_score) 或 None
_score_cache: Dict[str, Optional[tuple]] = {}


def clear_score_cache() -> None:
    """清空比分缓存，确保下次 fetch_match_score 重新拉取最新数据"""
    _score_cache.clear()
    try:
        from score_sporttery import clear_score_cache as _clear_st
        _clear_st()
    except Exception:
        pass


def _load_jczq_list(match_date: str) -> None:
    """抓取竞彩亚盘列表页，缓存该日所有比赛的 fid 和比分"""
    url = f"{BASE_URL}/yazhi_jczq_{match_date}.shtml"
    with httpx.Client(timeout=15, headers=HEADERS) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            logger.warning(f"获取竞彩列表失败: {resp.status_code}")
            return

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

        # 比分在 td[5]，格式 "1:2"；未开赛为空或"-"
        score_text = tds[5].get_text(strip=True)
        score = _parse_score(score_text)
        _score_cache[key] = score


def _parse_score(text: str) -> Optional[tuple]:
    """解析比分文本 '1:2' -> (1, 2)，无效返回 None。

    时间格式如"18:00"会被误解析为(18,0)，过滤掉任一侧>15的不合理比分。
    """
    if not text or ":" not in text:
        return None
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        h = int(parts[0].strip())
        a = int(parts[1].strip())
        # 过滤时间格式（如"18:00"）等非比分数据
        if h > 15 or a > 15:
            return None
        return (h, a)
    except (ValueError, TypeError):
        return None


def fetch_live_score_from_fid(fid: str) -> Optional[tuple]:
    """从500.com比赛详情页抓取实时比分。

    比赛详情页(yazhi-{fid}.shtml)顶部有 <p class="odds_hd_bf">比分</p>，
    比分格式为 "1:2"。该页面比分在比赛进行中就会更新，不同于列表页只显示赛后比分。
    """
    url = f"{BASE_URL}/fenxi/yazhi-{fid}.shtml"
    try:
        with httpx.Client(timeout=15, headers=HEADERS) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            logger.warning(f"获取比赛详情页失败 fid={fid}: HTTP {resp.status_code}")
            return None
        content = resp.content.decode("gbk", errors="replace")
        soup = BeautifulSoup(content, "html.parser")
        p = soup.find("p", class_="odds_hd_bf")
        if p:
            score_text = p.get_text(strip=True)
            score = _parse_score(score_text)
            if score:
                return score
        # 兜底：从 odds_hd_cont 中提取比分
        div = soup.find("div", class_="odds_hd_cont")
        if div:
            text = div.get_text(strip=True)
            # 格式: "主队名...比赛时间...比分...客队名"
            import re
            for m in re.finditer(r'(\d+):(\d+)', text):
                score = _parse_score(m.group(0))
                if score:
                    return score
        return None
    except Exception as e:
        logger.warning(f"获取实时比分失败 fid={fid}: {e}")
        return None


def get_fid_for_match(match_date: str, match_number: str) -> Optional[str]:
    """通过竞彩列表页获取 500.com fixture ID

    500.com 按售卖窗口起始日期组织列表页，一个窗口可能包含未来数天的比赛，
    因此售卖日期和比赛实际日期可能差数天。找不到时向前搜索最多5天。
    """
    cache_key = f"{match_date}:{match_number}"
    if cache_key in _fid_cache:
        return _fid_cache[cache_key]

    try:
        _load_jczq_list(match_date)
        if cache_key in _fid_cache:
            return _fid_cache[cache_key]

        from datetime import datetime, timedelta
        base = datetime.strptime(match_date, "%Y-%m-%d")
        for delta in [-1, -2, -3, -4, -5, 1, 2]:
            alt_date = (base + timedelta(days=delta)).strftime("%Y-%m-%d")
            alt_key = f"{alt_date}:{match_number}"
            if alt_key in _fid_cache:
                return _fid_cache[alt_key]
            _load_jczq_list(alt_date)
            if alt_key in _fid_cache:
                return _fid_cache[alt_key]

        return None
    except Exception as e:
        logger.error(f"获取FID失败: {e}")
        return None


def fetch_match_score(match_date: str, match_number: str, match_id: Optional[str] = None) -> Optional[tuple]:
    """获取比赛最终比分 (home_score, away_score)，未结束或无数据返回 None。

    优先体彩赛果 API；500.com 列表页仅作兜底（当前会被乐盾拦截）。
    """
    try:
        from score_sporttery import fetch_match_score as _st_score
        got = _st_score(match_date, match_number, match_id=match_id)
        if got:
            return got
    except Exception as e:
        logger.warning(f"体彩赛果比分失败: {e}")

    cache_key = f"{match_date}:{match_number}"
    if cache_key in _score_cache:
        return _score_cache[cache_key]

    try:
        _load_jczq_list(match_date)
        if cache_key in _score_cache:
            return _score_cache[cache_key]

        from datetime import datetime, timedelta
        base = datetime.strptime(match_date, "%Y-%m-%d")
        for delta in [1, -1]:
            alt_date = (base + timedelta(days=delta)).strftime("%Y-%m-%d")
            alt_key = f"{alt_date}:{match_number}"
            if alt_key in _score_cache:
                return _score_cache[alt_key]
            _load_jczq_list(alt_date)
            if alt_key in _score_cache:
                return _score_cache[alt_key]

        return None
    except Exception as e:
        logger.error(f"获取比分失败: {e}")
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
    for tr in table.find_all("tr"):
        classes = tr.get("class") or []
        if not any(c in ("tr1", "tr2") for c in classes):
            continue
        cid = tr.get("id", "")
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue

        # 公司名从 title 属性或文本取
        company_td = tds[1]
        raw_name = company_td.get("title", "") or company_td.get_text(strip=True)
        company_name = _identify_company(raw_name)
        if cid and str(cid).isdigit():
            mapped = EURO_COMPANIES.get(int(cid))
            if mapped:
                company_name = mapped

        # td[3-5] = 初盘(胜/平/负), td[6-8] = 即时(胜/平/负)
        init_w = _parse_odds(tds[3].get_text(strip=True))
        init_d = _parse_odds(tds[4].get_text(strip=True))
        init_l = _parse_odds(tds[5].get_text(strip=True))
        curr_w = _parse_odds(tds[6].get_text(strip=True))
        curr_d = _parse_odds(tds[7].get_text(strip=True))
        curr_l = _parse_odds(tds[8].get_text(strip=True))

        if not company_name or company_name in ("最大值", "最小值", "平均值"):
            continue
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
            cid = tr.get("id", "")
            company = _identify_asian_company(company_raw, cid)

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


def fetch_match_data(fid: str) -> Dict[str, Any]:
    """获取基本面数据：交锋历史、近期战绩、未来赛程"""
    from concurrent.futures import ThreadPoolExecutor

    def _fetch_shuju_page() -> str:
        """获取数据页面 HTML"""
        url = f"{BASE_URL}/fenxi/shuju-{fid}.shtml"
        with httpx.Client(timeout=15, headers=HEADERS) as client:
            resp = client.get(url)
        return resp.content.decode("gbk", errors="replace")

    def _fetch_recent(hoa: int) -> str:
        """POST 获取近期战绩 HTML (hoa=1 主队, hoa=0 客队)"""
        url = f"{BASE_URL}/fenxi1/inc/shuju_zhanji.php"
        data = {
            "id": fid,
            "limit": "15",
            "hoa": str(hoa),
            "bhbc": "0",
            "callback": "ajax",
            "r": "1",
        }
        headers = {
            **HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/fenxi/shuju-{fid}.shtml",
        }
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, data=data, headers=headers)
        return resp.content.decode("utf-8", errors="replace")

    def _parse_h2h(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """解析交锋历史表格
        列结构: [赛事, 日期, 对阵, 半场, 结果, 欧赔, 亚盘信息, 亚指结果, 大小结果, ?]
        支持两种来源: 页面内div#team_jiaozhan 或 POST接口直接返回的table
        """
        records = []
        div = soup.find("div", id="team_jiaozhan")
        if div:
            table = div.find("table")
        else:
            table = soup.find("table")
        if not table:
            return records
        rows = table.find_all("tr")
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 9:
                continue
            competition = tds[0].get_text(strip=True)
            date = tds[1].get_text(strip=True)
            match = tds[2].get_text(strip=True)
            half_score = tds[3].get_text(strip=True)
            result = tds[4].get_text(strip=True)
            # tds[5] = 欧赔 (跳过)
            # tds[6] = 亚盘信息 "0.78半球1.02" -> 提取盘口
            asian_raw = tds[6].get_text(strip=True)
            asian_result = tds[7].get_text(strip=True) if len(tds) > 7 else ""
            ou_result = tds[8].get_text(strip=True) if len(tds) > 8 else ""

            # 从亚盘信息提取盘口并转为数值，格式如 "0.78半球1.02" or "0.78受平手/半球0.97"
            handicap = ""
            hc_match = re.search(r'[\d.]+(受?[^\d.]+)[\d.]+', asian_raw)
            if hc_match:
                hc_text = hc_match.group(1)
                hc_val = _parse_handicap_value(hc_text)
                if hc_val is not None:
                    handicap = str(hc_val)

            records.append({
                "competition": competition,
                "date": date,
                "match": match,
                "halfScore": half_score,
                "result": result,
                "handicap": handicap,
                "asianResult": asian_result,
                "ouResult": ou_result,
            })
        return records

    def _parse_recent(html: str) -> List[Dict[str, Any]]:
        """解析近期战绩 POST 响应"""
        records = []
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 8:
                continue
            competition = tds[0].get_text(strip=True)
            # 跳过汇总行
            if competition.startswith("最近"):
                continue
            date = tds[1].get_text(strip=True)
            match = tds[2].get_text(strip=True)
            handicap = tds[3].get_text(strip=True)
            half_score = tds[4].get_text(strip=True)
            # 跳过未完赛（第5列为 VS）
            if half_score == "VS":
                continue
            result = tds[5].get_text(strip=True)
            asian_result = tds[6].get_text(strip=True)
            ou_result = tds[7].get_text(strip=True)
            records.append({
                "competition": competition,
                "date": date,
                "match": match,
                "handicap": handicap,
                "halfScore": half_score,
                "result": result,
                "asianResult": asian_result,
                "ouResult": ou_result,
            })
        return records

    def _parse_future(soup: BeautifulSoup) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """解析未来赛程（主队、客队）"""
        home_future: List[Dict[str, Any]] = []
        away_future: List[Dict[str, Any]] = []

        # 找到 h4 包含 "未来赛事" 的标签，取其后续兄弟 .M_content
        h4_tags = soup.find_all("h4")
        target_h4 = None
        for h4 in h4_tags:
            if "未来赛事" in h4.get_text():
                target_h4 = h4
                break

        if not target_h4:
            return home_future, away_future

        # h4 在 .M_title div 内，需要取其父级的下一个兄弟 .M_content
        title_div = target_h4.parent
        content_div = title_div.find_next_sibling(class_="M_content") if title_div else None
        if not content_div:
            return home_future, away_future

        tables = content_div.find_all("table")

        def _parse_future_table(table) -> List[Dict[str, Any]]:
            results = []
            rows = table.find_all("tr")
            for tr in rows:
                tds = tr.find_all("td")
                if len(tds) < 4:
                    continue
                competition = tds[0].get_text(strip=True)
                date = tds[1].get_text(strip=True)
                match = tds[2].get_text(strip=True)
                interval = tds[3].get_text(strip=True)
                results.append({
                    "competition": competition,
                    "date": date,
                    "match": match,
                    "interval": interval,
                })
            return results

        if len(tables) >= 1:
            home_future = _parse_future_table(tables[0])
        if len(tables) >= 2:
            away_future = _parse_future_table(tables[1])

        return home_future, away_future

    def _fetch_h2h_post() -> str:
        """POST 获取完整交锋历史"""
        url = f"{BASE_URL}/fenxi1/inc/shuju_jiaozhan.php"
        data = {"id": fid, "limit": "30", "bhbc": "0", "r": "1"}
        h = {
            **HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/fenxi/shuju-{fid}.shtml",
        }
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, data=data, headers=h)
        return resp.content.decode("gbk", errors="replace")

    # 并发请求：页面 HTML + 主队近期 + 客队近期 + 交锋历史
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            page_future = executor.submit(_fetch_shuju_page)
            home_recent_future = executor.submit(_fetch_recent, 1)
            away_recent_future = executor.submit(_fetch_recent, 0)
            h2h_future = executor.submit(_fetch_h2h_post)

            page_html = page_future.result()
            home_recent_html = home_recent_future.result()
            away_recent_html = away_recent_future.result()
            h2h_html = h2h_future.result()
    except Exception as e:
        logger.error(f"获取基本面数据失败 fid={fid}: {e}")
        return {
            "h2h": [],
            "homeRecent": [],
            "awayRecent": [],
            "homeFuture": [],
            "awayFuture": [],
        }

    # 解析页面
    soup = BeautifulSoup(page_html, "html.parser")
    # 优先使用POST接口的完整交锋(最多30条)，回退到页面内嵌的6条
    h2h_soup = BeautifulSoup(h2h_html, "html.parser") if h2h_html else None
    h2h = _parse_h2h(h2h_soup) if h2h_soup else []
    if not h2h:
        h2h = _parse_h2h(soup)
    home_future, away_future = _parse_future(soup)
    home_recent = _parse_recent(home_recent_html)
    away_recent = _parse_recent(away_recent_html)

    # 抓取队名+排名: <div class="team_name">曼城[英超2]</div> / <h3 class="lslayout1_stit">西班牙[世2]</h3>
    home_rank = None
    away_rank = None
    home_team_name = None
    away_team_name = None

    def _split_team_label(raw: str):
        """'凯拉特[欧冠]' / '曼城[英超2]' → (队名, 排名orNone)"""
        text = (raw or "").strip()
        if not text:
            return None, None
        m = re.match(r"^(.+?)\[(.+)\]$", text)
        if not m:
            return text, None
        name = m.group(1).strip() or None
        rank = None
        rm = re.search(r"(\d+)", m.group(2))
        if rm:
            rank = int(rm.group(1))
        return name, rank

    team_name_divs = soup.find_all("div", class_="team_name")
    if len(team_name_divs) >= 2:
        home_team_name, hr = _split_team_label(team_name_divs[0].get_text(strip=True))
        away_team_name, ar = _split_team_label(team_name_divs[1].get_text(strip=True))
        if hr is not None:
            home_rank = hr
        if ar is not None:
            away_rank = ar
    if home_rank is None or away_rank is None or not home_team_name or not away_team_name:
        h3_tags = soup.find_all("h3", class_="lslayout1_stit")
        if len(h3_tags) >= 2:
            hn, hr = _split_team_label(h3_tags[0].get_text(strip=True))
            an, ar = _split_team_label(h3_tags[1].get_text(strip=True))
            if not home_team_name:
                home_team_name = hn
            if not away_team_name:
                away_team_name = an
            if home_rank is None and hr is not None:
                home_rank = hr
            if away_rank is None and ar is not None:
                away_rank = ar

    # 500 球队稳定 ID + 页面别名（页头 odds_hd_team；同页链接可出现全称/简称）
    home_team_id, away_team_id, home_aliases, away_aliases = _extract_team_identity(
        soup, home_team_name, away_team_name
    )
    if not home_team_name and home_aliases:
        home_team_name = min(home_aliases, key=len)
    if not away_team_name and away_aliases:
        away_team_name = min(away_aliases, key=len)

    return {
        "h2h": h2h,
        "homeRecent": home_recent,
        "awayRecent": away_recent,
        "homeFuture": home_future,
        "awayFuture": away_future,
        "homeRank": home_rank,
        "awayRank": away_rank,
        "homeTeamName": home_team_name,
        "awayTeamName": away_team_name,
        "homeTeamId": home_team_id,
        "awayTeamId": away_team_id,
        "homeTeamAliases": home_aliases,
        "awayTeamAliases": away_aliases,
    }


def _extract_team_identity(
    soup: BeautifulSoup,
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> Tuple[Optional[str], Optional[str], List[str], List[str]]:
    """从 shuju 页提取主客 500 team_id 及别名。

    页头: <a class="odds_hd_team" href="https://liansai.500.com/team/2814/">
          <a href=".../team/2814/">阿拉木图凯拉特</a>
    战绩区同 id 可能再出现简称「凯拉特」。
    """
    def _tid_from_href(href: str) -> Optional[str]:
        m = re.search(r"/team/(\d+)/?", href or "")
        return m.group(1) if m else None

    home_id: Optional[str] = None
    away_id: Optional[str] = None

    # 1) 页头主客图链（顺序=主→客）
    hd_ids: List[str] = []
    for a in soup.select("a.odds_hd_team"):
        tid = _tid_from_href(a.get("href", ""))
        if tid and tid not in hd_ids:
            hd_ids.append(tid)
    if len(hd_ids) >= 1:
        home_id = hd_ids[0]
    if len(hd_ids) >= 2:
        away_id = hd_ids[1]

    # 2) 回退：odds_hd_list 里带队名的 /team/ 链接
    if not home_id or not away_id:
        list_ids: List[str] = []
        for a in soup.select(".odds_hd_list a[href*='/team/']"):
            tid = _tid_from_href(a.get("href", ""))
            name = (a.get_text(strip=True) or "").strip()
            if tid and name and tid not in list_ids:
                list_ids.append(tid)
        if not home_id and len(list_ids) >= 1:
            home_id = list_ids[0]
        if not away_id and len(list_ids) >= 2:
            away_id = list_ids[1]

    alias_map: Dict[str, List[str]] = {}
    if home_id:
        alias_map[home_id] = []
    if away_id:
        alias_map[away_id] = []

    def _add_alias(tid: Optional[str], name: Optional[str]) -> None:
        if not tid or tid not in alias_map or not name:
            return
        n = name.strip()
        if n and n not in alias_map[tid]:
            alias_map[tid].append(n)

    _add_alias(home_id, home_team_name)
    _add_alias(away_id, away_team_name)

    for a in soup.select("a[href*='/team/']"):
        tid = _tid_from_href(a.get("href", ""))
        if tid not in alias_map:
            continue
        _add_alias(tid, a.get_text(strip=True))

    home_aliases = sorted(alias_map.get(home_id, []), key=len, reverse=True) if home_id else []
    away_aliases = sorted(alias_map.get(away_id, []), key=len, reverse=True) if away_id else []

    return home_id, away_id, home_aliases, away_aliases


# ============================================================
# 竞彩对阵球队身价 (zx.500.com/jczq/worth)
# ============================================================

_WORTH_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}
_WORTH_CACHE_TS: Dict[str, float] = {}
_WORTH_CACHE_TTL = 600  # 10min


def _parse_worth_euro_wan(text: str) -> Optional[float]:
    """解析 '€  1260万' / '€1.2亿' → 万欧元数值。"""
    if not text:
        return None
    s = re.sub(r"\s+", "", str(text))
    m = re.search(r"([\d.]+)\s*亿", s)
    if m:
        try:
            return float(m.group(1)) * 10000.0  # 亿→万
        except ValueError:
            return None
    m = re.search(r"([\d.]+)\s*万", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    m = re.search(r"([\d.]+)", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _fmt_worth_wan(v: Optional[float]) -> str:
    if v is None:
        return "-"
    if v >= 10000:
        return f"€{v / 10000:.2f}亿".rstrip("0").rstrip(".")
    if v == int(v):
        return f"€{int(v)}万"
    return f"€{v:.1f}万"


def fetch_jczq_squad_worth(sale_date: str) -> Dict[str, Dict[str, Any]]:
    """抓取竞彩对阵球队身价，按 match_code(如周三001) 索引。

    Returns:
        {
          "周三001": {
            "match_code": "周三001",
            "league": "欧冠",
            "home_team": "凯拉特",
            "away_team": "奥莫尼亚",
            "home_worth": 1260.0,   # 万欧元
            "away_worth": 1507.0,
            "home_worth_text": "€1260万",
            "away_worth_text": "€1507万",
            "ratio": "1/1.2",
          },
          ...
        }
    """
    if not sale_date:
        return {}
    now = time.time()
    cached = _WORTH_CACHE.get(sale_date)
    if cached is not None and now - _WORTH_CACHE_TS.get(sale_date, 0) < _WORTH_CACHE_TTL:
        return cached

    url = f"https://zx.500.com/jczq/worth/?d={sale_date}"
    try:
        with httpx.Client(timeout=15, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.content.decode("gbk", errors="replace")
    except Exception as e:
        logger.warning(f"抓取竞彩身价失败 date={sale_date}: {e}")
        return cached or {}

    # 校验标题日期，避免参数被忽略时误用今日数据
    title_m = re.search(r"<title>\s*(\d{4}-\d{2}-\d{2})日", html)
    if title_m and title_m.group(1) != sale_date:
        logger.warning(
            f"竞彩身价日期不匹配 request={sale_date} got={title_m.group(1)}，丢弃"
        )
        return {}

    soup = BeautifulSoup(html, "html.parser")
    result: Dict[str, Dict[str, Any]] = {}
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "主队身价" not in headers or "客队身价" not in headers:
            continue
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 8:
                continue
            code = tds[0].get_text(strip=True)
            if not re.match(r"周[一二三四五六日]\d{3}$", code):
                continue
            league = tds[1].get_text(strip=True)
            home_worth_raw = tds[3].get_text(strip=True)
            home_team = tds[4].get_text(strip=True)
            away_team = tds[6].get_text(strip=True)
            away_worth_raw = tds[7].get_text(strip=True)
            ratio = tds[8].get_text(strip=True) if len(tds) > 8 else ""
            hw = _parse_worth_euro_wan(home_worth_raw)
            aw = _parse_worth_euro_wan(away_worth_raw)
            result[code] = {
                "match_code": code,
                "league": league,
                "home_team": home_team,
                "away_team": away_team,
                "home_worth": hw,
                "away_worth": aw,
                "home_worth_text": _fmt_worth_wan(hw) if hw is not None else home_worth_raw,
                "away_worth_text": _fmt_worth_wan(aw) if aw is not None else away_worth_raw,
                "ratio": ratio,
            }
        break

    _WORTH_CACHE[sale_date] = result
    _WORTH_CACHE_TS[sale_date] = now
    logger.info(f"竞彩身价 date={sale_date} 抓取 {len(result)} 场")
    return result


def get_match_squad_worth(
    sale_date: Optional[str],
    match_code: Optional[str],
) -> Optional[Dict[str, Any]]:
    """按售卖日+场次号取单场身价。"""
    if not sale_date or not match_code:
        return None
    return fetch_jczq_squad_worth(sale_date).get(str(match_code).strip()) or None

