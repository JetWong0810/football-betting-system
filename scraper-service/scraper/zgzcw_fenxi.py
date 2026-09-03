"""足彩网 fenxi 分析页: 单 Playwright 上下文串行抓 /ypdb。

company_id=2 显示 36*, 实测对应 Bet365。
ypdb 列序与 500 相反: 初盘(主/盘/客) 在前, 即时在后。
盘口文案与 500 相同(受=主受让), 返回值同 fetch_bet365_line: 500 原值正=主让。
"""
from __future__ import annotations

import logging
import os
import random
import re
import time
from typing import Optional

from bs4 import BeautifulSoup

from scraper.asian_bet365 import _parse_handicap_value, _parse_odds

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

_BLOCK_MARKERS = (
    "Please Enable JavaScript",
    "Access Verification",
    "security_antibot",
    "CloudWAF",
    "确认您是真人",
)


def _clean_hc(text: str) -> str:
    return (text or "").strip().replace("升", "").replace("降", "").replace("↑", "").replace("↓", "")


def is_blocked(html: str, title: str = "") -> bool:
    blob = f"{title}\n{html or ''}"
    return any(m in blob for m in _BLOCK_MARKERS)


_CID_RE = re.compile(r"company_id=(\d+)")


def _link_cid(href: str) -> Optional[int]:
    m = _CID_RE.search(href or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def parse_ypdb_bet365(html: str, cid: int = BET365_CID) -> Optional[dict]:
    """从已渲染的 /ypdb HTML 取 Bet365 初/即时。无则 None。

    cid 必须整段数字相等: company_id=22 不得命中 cid=2。
    """
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if _link_cid(a["href"]) != cid:
            continue
        tr = a.find_parent("tr")
        if not tr:
            continue
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue
        name = tds[1].get_text(strip=True)
        if "微信" in name or "推荐" in name or "北单" in name:
            continue
        # 初盘 tds[2:5], 即时 tds[5:8]
        open_home = _parse_odds(tds[2].get_text(strip=True))
        open_hc = _parse_handicap_value(_clean_hc(tds[3].get_text(strip=True)))
        open_away = _parse_odds(tds[4].get_text(strip=True))
        close_home = _parse_odds(tds[5].get_text(strip=True))
        close_hc = _parse_handicap_value(_clean_hc(tds[6].get_text(strip=True)))
        close_away = _parse_odds(tds[7].get_text(strip=True))
        if close_hc is None:
            continue
        return {
            "open_hc": open_hc,
            "close_hc": close_hc,
            "open_home": open_home,
            "open_away": open_away,
            "close_home": close_home,
            "close_away": close_away,
            "cid": cid,
            "name": name,
        }
    return None


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

    def fetch_ypdb_bet365(self, fid: str) -> Optional[dict]:
        if self.aborted or not fid:
            return None
        if self.opened >= self.budget:
            logger.warning(f"fenxi 达预算 {self.budget}, 停止开页")
            self.aborted = True
            return None
        if not self._page:
            self.aborted = True
            return None
        self._sleep()
        url = YPDB_URL.format(fid=fid)
        self.opened += 1
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=25000)
            self._page.wait_for_selector("table", timeout=8000)
        except Exception as e:
            logger.warning(f"fenxi ypdb 打开失败 fid={fid}: {e}")
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
        line = parse_ypdb_bet365(html)
        if not line:
            logger.info(f"ypdb 无 Bet365(cid={BET365_CID}) fid={fid}")
        return line
