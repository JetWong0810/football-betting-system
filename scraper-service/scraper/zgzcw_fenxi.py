"""足彩网 fenxi 分析页: 单 Playwright 上下文串行抓 /ypdb /bjop /bsls /dxdb /ypdb/zhishu。

company_id 必须整段数字相等: 22 不得命中 2。
ypdb 列序与 500 相反: 初盘(主/盘/客) 在前, 即时在后。
盘口文案与 500 相同(受=主受让), 亚盘数值为 500 原值正=主让。
入库公司名用规范名(Bet365), 不存 36*。
大小球与亚盘 ticks 只给指数页, 不进 7 因子。
"""
from __future__ import annotations

import logging
import os
import random
import re
import time
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from scraper.asian_bet365 import HANDICAP_MAP, _parse_handicap_value, _parse_odds

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
BET365_CID = int(os.getenv("ZGZCW_BET365_CID", "2"))
FENXI_BUDGET = int(os.getenv("ZGZCW_FENXI_BUDGET", "25"))
SLEEP_MIN = float(os.getenv("ZGZCW_FENXI_SLEEP_MIN", "1.5"))
SLEEP_MAX = float(os.getenv("ZGZCW_FENXI_SLEEP_MAX", "3.0"))
YPDB_URL = "https://fenxi.zgzcw.com/{fid}/ypdb"
BJOP_URL = "https://fenxi.zgzcw.com/{fid}/bjop"
BSLS_URL = "https://fenxi.zgzcw.com/{fid}/bsls"
DXDB_URL = "https://fenxi.zgzcw.com/{fid}/dxdb"
YPDB_ZHISHU_URL = "https://fenxi.zgzcw.com/{fid}/ypdb/zhishu?company_id={cid}"

# cid → 规范名。禁止子串匹配。
# cid=3 沙巴(ＳＢ/SBOBET)按皇冠计入 F3; cid=11 是韦德, 不是伟德, 只进热度。
ASIAN_CID_BOOK = {
    2: "Bet365",
    22: "Pinnacle",
    9: "威廉希尔",
    7: "澳门",
    5: "立博",
    3: "皇冠",
    11: "韦德",
}
EURO_CID_BOOK = {
    2: "Bet365",
    22: "Pinnacle",
    9: "威廉希尔",
    7: "澳门",
    5: "立博",
    3: "皇冠",
    11: "韦德",
}

_BLOCK_MARKERS = (
    "Please Enable JavaScript",
    "Access Verification",
    "security_antibot",
    "CloudWAF",
    "确认您是真人",
)

_CID_RE = re.compile(r"company_id=(\d+)")
_HC_ALT = "|".join(
    re.escape(n) for n in sorted(HANDICAP_MAP.keys(), key=len, reverse=True)
)
_AH_BLOB_RE = re.compile(
    rf"(?P<w1>[\d.]+)?(?P<hc>受?(?:{_HC_ALT}))(?P<w2>[\d.]+)?(?P<res>赢半|输半|赢|输|走)?"
)
_SCORE_RE = re.compile(r"^(\d+):(\d+)$")
_DATE_RE = re.compile(r"^(\d{2,4})-(\d{1,2})-(\d{1,2})$")
_DT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)")
_DT_SHORT_RE = re.compile(r"^(\d{1,2}-\d{1,2}[ T]\d{2}:\d{2}(?::\d{2})?)")
_FLIP_AH = {"赢": "输", "赢半": "输半", "输": "赢", "输半": "赢半", "走": "走"}
DXDB_CID_BOOK = {**EURO_CID_BOOK, **ASIAN_CID_BOOK}


def _clean_hc(text: str) -> str:
    return (text or "").strip().replace("升", "").replace("降", "").replace("↑", "").replace("↓", "")


def is_blocked(html: str, title: str = "") -> bool:
    blob = f"{title}\n{html or ''}"
    return any(m in blob for m in _BLOCK_MARKERS)


def _link_cid(href: str) -> Optional[int]:
    m = _CID_RE.search(href or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _is_ad(name: str) -> bool:
    return any(k in (name or "") for k in ("微信", "推荐", "北单"))


def _ypdb_from_tds(tds, cid: int, name: str) -> Optional[dict]:
    if len(tds) < 8:
        return None
    open_hc_text = _clean_hc(tds[3].get_text(strip=True))
    close_hc_text = _clean_hc(tds[6].get_text(strip=True))
    open_home = _parse_odds(tds[2].get_text(strip=True))
    open_hc = _parse_handicap_value(open_hc_text)
    open_away = _parse_odds(tds[4].get_text(strip=True))
    close_home = _parse_odds(tds[5].get_text(strip=True))
    close_hc = _parse_handicap_value(close_hc_text)
    close_away = _parse_odds(tds[7].get_text(strip=True))
    if close_hc is None:
        return None
    return {
        "open_hc": open_hc,
        "close_hc": close_hc,
        "open_hc_text": open_hc_text,
        "close_hc_text": close_hc_text,
        "open_home": open_home,
        "open_away": open_away,
        "close_home": close_home,
        "close_away": close_away,
        "cid": cid,
        "name": name,
    }


def parse_ypdb_bet365(html: str, cid: int = BET365_CID) -> Optional[dict]:
    """从已渲染的 /ypdb HTML 取 Bet365 初/即时。无则 None。"""
    for row in parse_ypdb_mainstream(html):
        if row.get("cid") == cid:
            ini = row.get("initial") or {}
            cur = row.get("current") or {}
            return {
                "open_hc": ini.get("handicap"),
                "close_hc": cur.get("handicap"),
                "open_home": ini.get("home"),
                "open_away": ini.get("away"),
                "close_home": cur.get("home"),
                "close_away": cur.get("away"),
                "cid": cid,
                "name": row.get("raw_name") or "36*",
            }
    return None


def parse_ypdb_mainstream(html: str) -> List[dict]:
    """ypdb 主流公司, bookmaker 为规范名。handicap=500 原值正=主让。"""
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    out: List[dict] = []
    for a in soup.find_all("a", href=True):
        cid = _link_cid(a["href"])
        book = ASIAN_CID_BOOK.get(cid) if cid is not None else None
        if not book or cid in seen:
            continue
        tr = a.find_parent("tr")
        if not tr:
            continue
        tds = tr.find_all("td")
        name = tds[1].get_text(strip=True) if len(tds) > 1 else ""
        if _is_ad(name):
            continue
        line = _ypdb_from_tds(tds, cid, name)
        if not line:
            continue
        seen.add(cid)
        out.append({
            "bookmaker": book,
            "cid": cid,
            "raw_name": name,
            "initial": {
                "home": line["open_home"],
                "handicap": line["open_hc"],
                "handicapText": line.get("open_hc_text") or "",
                "away": line["open_away"],
            },
            "current": {
                "home": line["close_home"],
                "handicap": line["close_hc"],
                "handicapText": line.get("close_hc_text") or "",
                "away": line["close_away"],
            },
        })
    return out


def parse_bjop(html: str) -> Dict:
    """百家欧赔 → fetch_european_odds 同构 {companies, summary}。凯利同页解析但不进因子。"""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue
        name = tds[1].get_text(strip=True)
        if _is_ad(name) or name in ("公司", "平均值", "最大值", "最小值"):
            continue
        if "平均" in name:
            continue
        a = tds[1].find("a", href=True) or tr.find("a", href=True)
        cid = _link_cid(a["href"]) if a else None
        book = None
        if cid is not None:
            book = EURO_CID_BOOK.get(cid)
        if not book and "官方" in name:
            book = "竞彩官方"
            cid = cid or 0
        if not book:
            continue
        key = book if book == "竞彩官方" else cid
        if key in seen:
            continue
        init_w = _parse_odds(tds[2].get_text(strip=True))
        init_d = _parse_odds(tds[3].get_text(strip=True))
        init_l = _parse_odds(tds[4].get_text(strip=True))
        curr_w = _parse_odds(tds[5].get_text(strip=True))
        curr_d = _parse_odds(tds[6].get_text(strip=True))
        curr_l = _parse_odds(tds[7].get_text(strip=True))
        if not all([init_w, init_d, init_l, curr_w, curr_d, curr_l]):
            continue
        return_rate = 0.0
        if len(tds) > 15:
            raw = _parse_odds(tds[15].get_text(strip=True))
            if raw is not None:
                return_rate = round(raw * 100, 2) if raw <= 1.5 else round(raw, 2)
        kelly = None
        if len(tds) > 14:
            kelly = {
                "win": _parse_odds(tds[12].get_text(strip=True)),
                "draw": _parse_odds(tds[13].get_text(strip=True)),
                "lose": _parse_odds(tds[14].get_text(strip=True)),
            }
        implied = None
        if len(tds) > 11:
            implied = {
                "win": _parse_odds(tds[9].get_text(strip=True)),
                "draw": _parse_odds(tds[10].get_text(strip=True)),
                "lose": _parse_odds(tds[11].get_text(strip=True)),
            }
        seen.add(key)
        companies.append({
            "bookmaker": book,
            "cid": int(cid or 0),
            "initial": {"win": init_w, "draw": init_d, "lose": init_l},
            "current": {"win": curr_w, "draw": curr_d, "lose": curr_l},
            "returnRate": return_rate,
            "kelly": kelly,
            "implied": implied,
        })
    return {"companies": companies, "summary": {}}


def _parse_ou_line(text: str) -> Optional[float]:
    """大小球盘口: 2.5球 / 2/2.5球 → 2.5 / 2.25。"""
    raw = _clean_hc(text).replace("球", "").replace(" ", "")
    if not raw:
        return None
    if "/" in raw:
        left, right = raw.split("/", 1)
        a = _parse_odds(left)
        b = _parse_odds(right)
        if a is None or b is None:
            return None
        return round((a + b) / 2, 2)
    return _parse_odds(raw)


def parse_dxdb(html: str) -> List[dict]:
    """大小球 → 与 500 fetch_over_under 同构。不进 7 因子。"""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue
        name = tds[1].get_text(strip=True)
        if _is_ad(name) or name in ("公司", "平均值", "最大值", "最小值"):
            continue
        if "平均" in name:
            continue
        a = tds[1].find("a", href=True) or tr.find("a", href=True)
        cid = _link_cid(a["href"]) if a else None
        book = DXDB_CID_BOOK.get(cid) if cid is not None else None
        if not book or cid in seen:
            continue
        init_over = _parse_odds(tds[2].get_text(strip=True))
        init_line = _parse_ou_line(tds[3].get_text(strip=True))
        init_under = _parse_odds(tds[4].get_text(strip=True))
        curr_over = _parse_odds(tds[5].get_text(strip=True))
        curr_line = _parse_ou_line(tds[6].get_text(strip=True))
        curr_under = _parse_odds(tds[7].get_text(strip=True))
        if curr_line is None or curr_over is None or curr_under is None:
            continue
        seen.add(cid)
        companies.append({
            "bookmaker": book,
            "cid": int(cid),
            "initial": {
                "over": init_over,
                "line": init_line,
                "under": init_under,
            },
            "current": {
                "over": curr_over,
                "line": curr_line,
                "under": curr_under,
            },
        })
    return companies


def _zhishu_time(cells: List[str]) -> Optional[tuple]:
    for i, c in enumerate(cells):
        t = (c or "").strip()
        if _DT_RE.match(t) or _DT_SHORT_RE.match(t):
            return i, t
    return None


def _zhishu_triple(cells: List[str]) -> Optional[tuple]:
    """从时间后的格子里找 主水/盘口/客水。"""
    for i in range(len(cells) - 2):
        home = _parse_odds(cells[i])
        hc_text = _clean_hc(cells[i + 1])
        away = _parse_odds(cells[i + 2])
        hc = _parse_handicap_value(hc_text)
        if home is not None and away is not None and hc is not None:
            return home, hc, hc_text, away
    return None


def parse_ypdb_zhishu(html: str) -> List[dict]:
    """Bet365 亚盘变动轴, 页面新在前。handicap=500 原值正=主让。"""
    soup = BeautifulSoup(html, "html.parser")
    out: List[dict] = []
    seen = set()
    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 4:
            continue
        found = _zhishu_time(cells)
        if not found:
            continue
        time_i, time_s = found
        triple = _zhishu_triple(cells[time_i + 1:])
        if not triple:
            continue
        if time_s in seen:
            continue
        seen.add(time_s)
        home, hc, hc_text, away = triple
        out.append({
            "home": home,
            "handicap": hc,
            "handicapText": hc_text,
            "away": away,
            "time": time_s,
        })
    return out


def _norm_date(text: str) -> str:
    m = _DATE_RE.match((text or "").strip())
    if not m:
        return (text or "").strip()
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _flip_ah(res: str) -> str:
    return _FLIP_AH.get(res, res)


def _parse_ah_blob(blob: str) -> tuple[Optional[float], str]:
    """从『1.09平/半0.80输』解析盘口(正=主让)和主队视角盘路。"""
    m = _AH_BLOB_RE.search(_clean_hc(blob or ""))
    if not m:
        return None, ""
    hc = _parse_handicap_value(m.group("hc") or "")
    res = (m.group("res") or "").strip()
    return hc, res


def _parse_form_row(tds, focus_name: str, *, h2h_home: Optional[str] = None) -> Optional[dict]:
    """bsls 战绩行。focus_name=列表所属队; h2h 时 asianResult 换到当前主队视角。"""
    if len(tds) < 7:
        return None
    cells = [td.get_text(" ", strip=True) for td in tds]
    competition = cells[0]
    if competition in ("联赛",) or competition.startswith("最近"):
        return None
    date = _norm_date(cells[2])
    home = cells[3]
    score = cells[4].replace(" ", "")
    away = cells[5]
    if score.upper() == "VS" or not home or not away:
        return None
    sm = _SCORE_RE.match(score)
    if not sm:
        return None
    hs, aws = int(sm.group(1)), int(sm.group(2))
    half = cells[6] if len(cells) > 6 else ""
    blob = "".join(cells[7:])
    hc_raw, home_ar = _parse_ah_blob(blob)
    focus_is_home = home == focus_name
    if h2h_home:
        ar_focus = home_ar if home == h2h_home else _flip_ah(home_ar)
    else:
        ar_focus = home_ar if focus_is_home else _flip_ah(home_ar)
    if hs == aws:
        result = "平"
    elif focus_is_home:
        result = "胜" if hs > aws else "负"
    else:
        result = "胜" if aws > hs else "负"
    # recent: 负=主让; h2h: 正=主让(与 500 契约一致)
    if h2h_home is not None:
        handicap = "" if hc_raw is None else str(hc_raw)
    else:
        handicap = "" if hc_raw is None else str(-hc_raw)
    return {
        "competition": competition,
        "date": date,
        "match": f"{home}{hs}:{aws}{away}",
        "handicap": handicap,
        "halfScore": half,
        "result": result,
        "asianResult": ar_focus,
        "ouResult": "",
    }


def _parse_future_row(tds) -> Optional[dict]:
    if len(tds) < 6:
        return None
    cells = [td.get_text(" ", strip=True) for td in tds]
    if cells[0] in ("联赛",) or cells[4].upper() != "VS":
        return None
    return {
        "competition": cells[0],
        "date": _norm_date(cells[2]),
        "match": f"{cells[3]} VS {cells[5]}",
        "interval": "",
    }


def _bsls_tables(soup: BeautifulSoup):
    tables = soup.find_all("table")
    scored = []
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) < 2:
            continue
        head = " ".join(td.get_text(strip=True) for td in rows[0].find_all(["th", "td"]))
        scored.append((t, head, rows))
    return scored


def parse_bsls(html: str) -> Dict:
    """基本面 → fetch_match_data 同构。队名用页面名, 不伪造 500 team id。

    页内表序: 主队近期、客队近期、交锋、主队未来、客队未来。
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = _bsls_tables(soup)
    home_recent: List[dict] = []
    away_recent: List[dict] = []
    h2h: List[dict] = []
    home_future: List[dict] = []
    away_future: List[dict] = []
    home_name = away_name = None

    form_tables = []
    future_tables = []
    for t, head, rows in tables:
        first_data = rows[1] if len(rows) > 1 else None
        cells = [td.get_text(strip=True) for td in first_data.find_all("td")] if first_data else []
        is_future = bool(cells and len(cells) >= 6 and cells[4].upper() == "VS" and "盘路" not in head)
        if is_future:
            future_tables.append(rows)
            continue
        if "盘路" in head or "终盘" in head:
            form_tables.append(rows)

    if len(form_tables) < 3:
        used = set(id(r) for r in form_tables)
        for t, head, rows in tables:
            if id(rows) in used:
                continue
            if len(rows) > 8:
                form_tables.append(rows)
            if len(form_tables) >= 3:
                break

    if form_tables:
        for tr in form_tables[0][1:4]:
            tds = tr.find_all("td")
            if len(tds) >= 6 and tds[4].get_text(strip=True).upper() == "VS":
                home_name = tds[3].get_text(strip=True)
                away_name = tds[5].get_text(strip=True)
                break

    def _collect(rows, focus: str, limit: int, h2h_home=None) -> List[dict]:
        out: List[dict] = []
        if not focus:
            return out
        for tr in rows[1:]:
            rec = _parse_form_row(tr.find_all("td"), focus, h2h_home=h2h_home)
            if rec:
                out.append(rec)
            if len(out) >= limit:
                break
        return out

    if form_tables and home_name:
        home_recent = _collect(form_tables[0], home_name, 15)
    if len(form_tables) > 1 and away_name:
        away_recent = _collect(form_tables[1], away_name, 15)
    if len(form_tables) > 2 and home_name:
        h2h = _collect(form_tables[2], home_name, 30, h2h_home=home_name)

    if future_tables:
        for tr in future_tables[0][1:]:
            rec = _parse_future_row(tr.find_all("td"))
            if rec:
                home_future.append(rec)
    if len(future_tables) > 1:
        for tr in future_tables[1][1:]:
            rec = _parse_future_row(tr.find_all("td"))
            if rec:
                away_future.append(rec)

    return {
        "h2h": h2h,
        "homeRecent": home_recent,
        "awayRecent": away_recent,
        "homeFuture": home_future,
        "awayFuture": away_future,
        "homeRank": None,
        "awayRank": None,
        "homeTeamName": home_name,
        "awayTeamName": away_name,
    }


class FenxiSession:
    """一轮 scraper 共用一个浏览器上下文。二次验证则 aborted, 调用方应停本轮。"""

    def __init__(
        self,
        budget: int = FENXI_BUDGET,
        sleep_min: float = SLEEP_MIN,
        sleep_max: float = SLEEP_MAX,
    ):
        self.budget = max(1, budget)
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max
        self.opened = 0
        self.skipped = 0
        self.aborted = False
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._first = True

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.opened)

    def __enter__(self) -> "FenxiSession":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("未安装 playwright, 无法抓 fenxi")
            self.aborted = True
            return self
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        self._ctx = self._browser.new_context(user_agent=UA, locale="zh-CN")
        self._page = self._ctx.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for closer in (self._page, self._ctx, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
        logger.info(
            f"fenxi 本轮 opened={self.opened} skipped={self.skipped} "
            f"aborted={self.aborted} budget={self.budget}"
        )

    def _sleep(self) -> None:
        if self._first:
            self._first = False
            return
        lo, hi = self.sleep_min, self.sleep_max
        if hi < lo:
            lo, hi = hi, lo
        time.sleep(random.uniform(lo, hi))

    def _open(self, url: str, label: str) -> Optional[str]:
        if self.aborted or not url:
            return None
        if self.opened >= self.budget:
            logger.warning(f"fenxi 达预算 {self.budget}, 停止开页")
            self.aborted = True
            return None
        if not self._page:
            self.aborted = True
            return None
        self._sleep()
        self.opened += 1
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=25000)
            self._page.wait_for_selector("table", timeout=8000)
        except Exception as e:
            logger.warning(f"fenxi {label} 打开失败: {e}")
            html = ""
            try:
                html = self._page.content()
            except Exception:
                pass
            if is_blocked(html):
                self.aborted = True
                logger.warning("fenxi 二次验证, 中止本轮")
            return None
        html = self._page.content()
        title = ""
        try:
            title = self._page.title() or ""
        except Exception:
            pass
        if is_blocked(html, title):
            self.aborted = True
            logger.warning("fenxi 二次验证, 中止本轮")
            return None
        return html

    def fetch_ypdb(self, fid: str) -> Optional[dict]:
        html = self._open(YPDB_URL.format(fid=fid), f"ypdb fid={fid}")
        if not html:
            return None
        companies = parse_ypdb_mainstream(html)
        bet365 = parse_ypdb_bet365(html)
        if not bet365:
            logger.info(f"ypdb 无 Bet365(cid={BET365_CID}) fid={fid}")
        return {"bet365": bet365, "companies": companies}

    def fetch_ypdb_bet365(self, fid: str) -> Optional[dict]:
        pack = self.fetch_ypdb(fid)
        return (pack or {}).get("bet365")

    def fetch_bjop(self, fid: str) -> Optional[dict]:
        html = self._open(BJOP_URL.format(fid=fid), f"bjop fid={fid}")
        if not html:
            return None
        data = parse_bjop(html)
        if not data.get("companies"):
            logger.info(f"bjop 无主流欧赔 fid={fid}")
        return data

    def fetch_bsls(self, fid: str) -> Optional[dict]:
        html = self._open(BSLS_URL.format(fid=fid), f"bsls fid={fid}")
        if not html:
            return None
        data = parse_bsls(html)
        if not data.get("homeRecent") and not data.get("awayRecent"):
            logger.info(f"bsls 无近期 fid={fid}")
        return data

    def fetch_dxdb(self, fid: str) -> Optional[dict]:
        html = self._open(DXDB_URL.format(fid=fid), f"dxdb fid={fid}")
        if not html:
            return None
        companies = parse_dxdb(html)
        if not companies:
            logger.info(f"dxdb 无主流大小球 fid={fid}")
        return {"companies": companies}

    def fetch_ypdb_zhishu(self, fid: str, cid: int = BET365_CID) -> Optional[list]:
        html = self._open(
            YPDB_ZHISHU_URL.format(fid=fid, cid=cid),
            f"ypdb/zhishu fid={fid} cid={cid}",
        )
        if not html:
            return None
        ticks = parse_ypdb_zhishu(html)
        if not ticks:
            logger.info(f"ypdb/zhishu 无 ticks fid={fid} cid={cid}")
        return ticks
