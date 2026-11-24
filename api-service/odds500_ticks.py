"""[与 scraper-service/scraper/odds500_ticks.py 同源副本: API 镜像只包含 api-service/, 改动请两处同步]
500.com 多家公司亚盘/欧赔/大小球逐次变动抓取(odds.500.com, 纯 HTTP, 无需浏览器)。

接口(均返回该公司从初盘到现在的完整历史, 新→旧):
  亚盘  /fenxi1/inc/yazhiajax.php?fid=&id=<cid>     -> ["<tr><td>主水</td><td>盘口</td><td>客水</td><td>MM-DD HH:MM</td></tr>", ...]
  大小球 /fenxi1/inc/daxiaoajax.php?fid=&id=<cid>   -> 同上(中间列为盘口线)
  欧赔  /fenxi1/json/ouzhi.php?fid=&cid=            -> [[胜,平,负,返还率,"YYYY-MM-DD HH:MM:SS"], ...]
  竞彩列表 /yazhi_jczq_<售卖日>.shtml               -> tr[data-fid] -> {match_code: (fid, 开赛时间)}

数据准确性约定:
  - 时间为北京时间。亚盘/大小球只有"月-日 时:分"(无年、无秒), 用开赛时间推断年份;
    欧赔带完整日期时间。
  - 开赛后的记录(滚球)一律丢弃, 赛前盘口路径不被污染。
  - 盘口符号为 500 原值(正=主让, 负=主受让), 与现有 jczq_ah_ticks 同口径, 入库不取反。
  - 空响应(HTTP 200 + 仅换行)在服务端偶发, 重试一次; 仍为空按"无数据"处理, 不当成"无变动"写库。

反爬约定: 单线程、请求间隔 1~2.2 秒带抖动; 遇 567/403/429/5xx 或连续空/非 JSON 即熔断,
退避 5/10/20 分钟(指数, 上限 20 分钟); 熔断期间 allow() 为 False, 调用方应整体跳过(由足彩网兜底)。
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from odds500_service import HANDICAP_MAP

logger = logging.getLogger(__name__)

BASE_URL = "https://odds.500.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 500.com 公司 cid -> 标准公司名(页面公司名被星号脱敏, 只能按 cid 识别)
COMPANIES: Dict[int, str] = {
    3: "Bet365", 280: "皇冠", 5: "澳门", 1055: "Pinnacle", 122: "香港马会",
    293: "威廉希尔", 2: "立博", 6: "伟德", 9: "易胜博", 651: "利记", 140: "明陞",
}
# 核心公司(临近开赛全部抓取) / 远期只抓精简集合
CORE_CIDS: Tuple[int, ...] = (3, 280, 5, 1055, 122, 293, 2)
LITE_CIDS: Tuple[int, ...] = (3, 280, 1055, 122)
KINDS: Tuple[str, ...] = ("asian", "ou", "euro")

GAP_MIN = 1.0
GAP_MAX = 2.2
BACKOFF_STEPS = (300, 600, 1200)


# ---------------------------------------------------------------- 解析(纯函数, 便于测试)

def parse_odds(text: str) -> Optional[float]:
    t = (text or "").strip().replace("↑", "").replace("↓", "").replace("\xa0", "")
    try:
        return float(t)
    except ValueError:
        return None


def _clean(text: str) -> str:
    return (text or "").replace("\xa0", "").replace("升", "").replace("降", "").strip()


def parse_ah_text(text: str) -> Tuple[Optional[float], str]:
    """'受球半' -> (-1.5, '受球半'); '半球' -> (0.5, '半球')。无法识别返回 (None, 原文)。"""
    t = _clean(text)
    if not t:
        return None, ""
    neg = t.startswith("受")
    body = t[1:] if neg else t
    val = HANDICAP_MAP.get(body)
    if val is None:
        try:
            val = float(body)
        except ValueError:
            return None, t
    return (-val if neg else val), t


def parse_ou_line(text: str) -> Optional[float]:
    """'2.5' -> 2.5; '2.5/3' -> 2.75; '3球' 等中文盘口 -> 无法识别返回 None。"""
    t = _clean(text).replace("球", "")
    if not t:
        return None
    if "/" in t:
        try:
            a, b = t.split("/", 1)
            return (float(a) + float(b)) / 2
        except ValueError:
            return None
    try:
        return float(t)
    except ValueError:
        return None


def infer_tick_dt(raw: str, kickoff: datetime) -> Optional[datetime]:
    """把 500 的时间文本转成 datetime(北京时间)。无年份时按开赛时间推断。"""
    t = (raw or "").strip()
    if not t:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            pass
    try:
        d = datetime.strptime(t, "%m-%d %H:%M")
    except ValueError:
        return None
    best: Optional[datetime] = None
    for y in (kickoff.year - 1, kickoff.year, kickoff.year + 1):
        try:
            cand = d.replace(year=y)
        except ValueError:      # 02-29
            continue
        # 赔率变动一定发生在开赛前(最多略晚几分钟的滚球), 且离开赛不会超过一年
        if cand <= kickoff + timedelta(days=2):
            if best is None or cand > best:
                best = cand
    return best


def _rows_from_html_list(data: Any) -> List[List[str]]:
    out: List[List[str]] = []
    if not isinstance(data, list):
        return out
    for s in data:
        tds = BeautifulSoup(s, "html.parser").find_all("td") if isinstance(s, str) else []
        if len(tds) >= 4:
            out.append([td.get_text(strip=True) for td in tds[:4]])
    return out


def parse_asian_history(data: Any, kickoff: datetime) -> List[Dict[str, Any]]:
    res = []
    for home, hc, away, tm in _rows_from_html_list(data):
        val, text = parse_ah_text(hc)
        dt = infer_tick_dt(tm, kickoff)
        if val is None or dt is None:
            continue
        res.append({"time": dt, "home": parse_odds(home), "handicap": val, "handicapText": text,
                    "away": parse_odds(away)})
    return res


def parse_ou_history(data: Any, kickoff: datetime) -> List[Dict[str, Any]]:
    res = []
    for over, line, under, tm in _rows_from_html_list(data):
        ln = parse_ou_line(line)
        dt = infer_tick_dt(tm, kickoff)
        if ln is None or dt is None:
            continue
        res.append({"time": dt, "over": parse_odds(over), "line": ln, "lineText": _clean(line),
                    "under": parse_odds(under)})
    return res


def parse_euro_history(data: Any, kickoff: datetime) -> List[Dict[str, Any]]:
    res = []
    if not isinstance(data, list):
        return res
    for r in data:
        if not isinstance(r, list) or len(r) < 5:
            continue
        dt = infer_tick_dt(str(r[4]), kickoff)
        try:
            w, d, l = float(r[0]), float(r[1]), float(r[2])
        except (TypeError, ValueError):
            continue
        try:
            rr = float(r[3])
        except (TypeError, ValueError):
            rr = None
        if dt is None:
            continue
        res.append({"time": dt, "win": w, "draw": d, "lose": l, "returnRate": rr})
    return res


def drop_after_kickoff(rows: List[Dict[str, Any]], kickoff: datetime, grace_min: int = 0) -> List[Dict[str, Any]]:
    """丢弃开赛之后的记录(滚球盘), 保证赛前路径纯净。"""
    lim = kickoff + timedelta(minutes=grace_min)
    return [r for r in rows if r["time"] <= lim]


def parse_fid_list(html: str, year: int) -> Dict[str, Dict[str, Any]]:
    """竞彩列表页 -> {match_code: {fid, kickoff(datetime|None), home}}。"""
    soup = BeautifulSoup(html, "html.parser")
    out: Dict[str, Dict[str, Any]] = {}
    for tr in soup.find_all("tr", attrs={"data-fid": True}):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        code = tds[0].get_text(strip=True)
        if not code.startswith("周"):
            continue
        ko = None
        m = re.match(r"(\d{2})-(\d{2}) (\d{2}):(\d{2})", tds[3].get_text(strip=True))
        if m:
            mo, d, h, mi = map(int, m.groups())
            ko = datetime(year, mo, d, h, mi)
        out[code] = {"fid": str(tr["data-fid"]), "kickoff": ko, "home": tds[4].get_text(strip=True)}
    return out


# ---------------------------------------------------------------- HTTP 客户端 + 熔断

class Odds500Client:
    def __init__(self, gap_min: float = GAP_MIN, gap_max: float = GAP_MAX):
        self.gap_min, self.gap_max = gap_min, gap_max
        self._last = 0.0
        self.requests = 0
        self._client = httpx.Client(timeout=15, headers=HEADERS)

    # 熔断状态在进程内共享(模块级), 多个客户端实例也一起退避
    def allow(self) -> bool:
        return time.time() >= _STATE["blocked_until"]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Odds500Client":
        return self

    def __exit__(self, *a) -> None:
        self.close()

    def _pace(self) -> None:
        wait = self._last + random.uniform(self.gap_min, self.gap_max) - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def _trip(self, why: str) -> None:
        step = min(_STATE["trips"], len(BACKOFF_STEPS) - 1)
        _STATE["trips"] += 1
        _STATE["blocked_until"] = time.time() + BACKOFF_STEPS[step]
        logger.warning("500.com 熔断 %s, 退避 %ss (第%s次)", why, BACKOFF_STEPS[step], _STATE["trips"])

    def _ok(self) -> None:
        _STATE["trips"] = 0
        _STATE["bad"] = 0

    def _get(self, path: str, params: Dict[str, Any], referer: str, xhr: bool, label: str) -> Optional[bytes]:
        """成功返回响应体(可能为空白); 被拦/异常返回 None 并按需熔断。"""
        if not self.allow():
            return None
        headers = {"Referer": referer}
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"
        for attempt in (0, 1):
            self._pace()
            self.requests += 1
            try:
                r = self._client.get(BASE_URL + path, params=params, headers=headers)
            except httpx.HTTPError as e:
                logger.warning("500.com %s 请求异常: %s", label, type(e).__name__)
                _STATE["bad"] += 1
                if _STATE["bad"] >= 3:
                    self._trip("连续请求异常")
                return None
            if r.status_code in (403, 429, 567) or r.status_code >= 500:
                self._trip(f"HTTP {r.status_code} {label}")
                return None
            if r.status_code != 200:
                logger.warning("500.com %s HTTP %s", label, r.status_code)
                return None
            body = r.content
            if body.strip() or attempt == 1:
                if body.strip():
                    self._ok()
                return body
            time.sleep(2.0)     # 偶发空响应: 重试一次
        return b""

    def _json(self, path, params, referer, xhr, label) -> Optional[list]:
        """None=失败/被拦; []=空(重试后仍空, 视为本次无数据)。"""
        body = self._get(path, params, referer, xhr, label)
        if body is None:
            return None
        if not body.strip():
            return []
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            _STATE["bad"] += 1
            if _STATE["bad"] >= 3 or body.lstrip()[:1] == b"<":     # 返回 HTML 多为盾页
                self._trip(f"非 JSON {label}")
            return None
        return data if isinstance(data, list) else []

    # -------- 对外接口
    def fetch_history(self, kind: str, fid: str, cid: int, kickoff: datetime) -> Optional[List[Dict[str, Any]]]:
        """返回解析后的逐次变动(新→旧, 已剔除开赛后记录); None=失败/被拦(不可当成无变动)。"""
        if kind == "asian":
            data = self._json("/fenxi1/inc/yazhiajax.php", {"fid": fid, "id": cid, "t": int(time.time() * 1000), "r": 1},
                              f"{BASE_URL}/fenxi/yazhi-{fid}.shtml", True, f"asian {fid}/{cid}")
            parse = parse_asian_history
        elif kind == "ou":
            data = self._json("/fenxi1/inc/daxiaoajax.php", {"fid": fid, "id": cid, "t": int(time.time() * 1000), "r": 1},
                              f"{BASE_URL}/fenxi/daxiao-{fid}.shtml", True, f"ou {fid}/{cid}")
            parse = parse_ou_history
        elif kind == "euro":
            data = self._json("/fenxi1/json/ouzhi.php", {"fid": fid, "cid": cid, "r": 1},
                              f"{BASE_URL}/fenxi/ouzhi-{fid}.shtml", True, f"euro {fid}/{cid}")
            parse = parse_euro_history
        else:
            raise ValueError(kind)
        if data is None:
            return None
        return drop_after_kickoff(parse(data, kickoff), kickoff)

    def fetch_fid_list(self, sale_date: str) -> Optional[Dict[str, Dict[str, Any]]]:
        """售卖日列表页 -> {match_code: {fid, kickoff, home}}; None=失败/被拦。"""
        body = self._get(f"/yazhi_jczq_{sale_date}.shtml", {}, BASE_URL + "/", False, f"list {sale_date}")
        if body is None:
            return None
        html = body.decode("gbk", errors="replace")
        if "data-fid" not in html and len(html) < 5000:
            _STATE["bad"] += 1
            if _STATE["bad"] >= 3:
                self._trip(f"列表页异常 {sale_date}")
            return None
        return parse_fid_list(html, int(sale_date[:4]))


_STATE: Dict[str, Any] = {"blocked_until": 0.0, "trips": 0, "bad": 0}


def reset_state() -> None:
    _STATE.update({"blocked_until": 0.0, "trips": 0, "bad": 0})


def breaker_open() -> bool:
    return time.time() < _STATE["blocked_until"]
