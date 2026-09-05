"""足彩网 fid 映射: 竞彩场次号 + 投注页队ID × 全量直播页。

live.zgzcw.com 首页只列进行中/刚完赛的竞彩编号场, 未开赛周六场经常不在上面。
全量页 /qb/ 有 fid 但没有「周六001」; 投注页有体彩 match_id 和 saishi 队ID。
用队ID把投注页接到 /qb/, 不依赖中文队名是否完全一致。
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

LIVE_URL = "https://live.zgzcw.com/"
QB_URL = "https://live.zgzcw.com/qb/"
BET_URL = (
    "https://cp.zgzcw.com/lottery/jchtplayvsForJsp.action"
    "?lotteryId=47&type=jcmini"
)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
_CODE_RE = re.compile(r"^周[一二三四五六日]\d{3}$")
_RANK_RE = re.compile(r"\[(\d+)\]")
_TEAM_ID_RE = re.compile(r"/soccer/team/\d+/(\d+)")
_KICK_RE = re.compile(r"比赛时间:(\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
_SHOW_RE = re.compile(r"^show_(\d+)$")


def _headers() -> dict:
    return {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def _blocked(html: str) -> bool:
    return "CloudWAF" in html or "Please Enable JavaScript" in html


def _norm_team(name: Optional[str]) -> str:
    s = (name or "").strip()
    s = re.sub(r"\[\d+\]", "", s)
    s = re.sub(r"[（(][^）)]*[）)]", "", s)
    return re.sub(r"[\s\u3000·・]", "", s)


def _rank_from(text: str) -> Optional[str]:
    m = _RANK_RE.search(text or "")
    return m.group(1) if m else None


def _kickoff_date(raw) -> str:
    if raw is None:
        return ""
    if hasattr(raw, "strftime"):
        return raw.strftime("%Y-%m-%d")
    return str(raw).strip()[:10]


def _http_get(client: httpx.Client, url: str, label: str) -> str:
    try:
        resp = client.get(url)
    except Exception as e:
        logger.warning(f"zgzcw {label} 异常: {e}")
        return ""
    if resp.status_code != 200:
        logger.warning(f"zgzcw {label} HTTP {resp.status_code}")
        return ""
    html = resp.content.decode("utf-8", errors="replace")
    if _blocked(html):
        logger.warning(f"zgzcw {label} 被盾")
        return ""
    return html


def parse_live_code_map(html: str) -> Dict[str, Dict[str, Optional[str]]]:
    """首页: {match_code: {fid, home_rank, away_rank}}。"""
    result: Dict[str, Dict[str, Optional[str]]] = {}
    if not html:
        return result
    soup = BeautifulSoup(html, "html.parser")
    trs = soup.select("tr.matchTr") or soup.find_all("tr", attrs={"matchid": True})
    for tr in trs:
        fid = (tr.get("matchid") or "").strip()
        tds = tr.find_all("td")
        if not fid or not tds:
            continue
        code = tds[0].get_text(strip=True)
        if not _CODE_RE.match(code):
            continue
        home_rank = away_rank = None
        if len(tds) > 5:
            home_rank = _rank_from(tds[5].get_text(" ", strip=True))
        if len(tds) > 7:
            away_rank = _rank_from(tds[7].get_text(" ", strip=True))
        result[code] = {"fid": fid, "home_rank": home_rank, "away_rank": away_rank}
    return result


def parse_qb_fixtures(html: str) -> List[Dict[str, Any]]:
    """全量直播页: fid + saishi 队ID + 开赛时间。"""
    rows: List[Dict[str, Any]] = []
    if not html:
        return rows
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.select("tr.matchTr") or soup.find_all("tr", attrs={"matchid": True}):
        fid = (tr.get("matchid") or "").strip()
        if not fid:
            continue
        date_td = tr.select_one("td.matchDate")
        kick = ((date_td.get("date") if date_td else "") or "").strip()
        links = tr.select("a[href*='/soccer/team/']")
        tids: List[str] = []
        names: List[str] = []
        for a in links[:2]:
            m = _TEAM_ID_RE.search(a.get("href") or "")
            if not m:
                continue
            tids.append(m.group(1))
            names.append(a.get_text(strip=True))
        if len(tids) < 2:
            continue
        rank_tags = tr.select("em.paim")
        home_rank = _rank_from(rank_tags[0].get_text()) if rank_tags else None
        away_rank = _rank_from(rank_tags[1].get_text()) if len(rank_tags) > 1 else None
        rows.append({
            "fid": fid,
            "home_tid": tids[0],
            "away_tid": tids[1],
            "home": names[0] if names else "",
            "away": names[1] if len(names) > 1 else "",
            "kickoff": kick[:19],
            "home_rank": home_rank,
            "away_rank": away_rank,
        })
    return rows


def parse_betting_matches(html: str) -> Dict[str, Dict[str, Any]]:
    """投注页: {sporttery_match_id: {home_tid, away_tid, match_code}}。"""
    result: Dict[str, Dict[str, Any]] = {}
    if not html:
        return result
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.find_all("tr"):
        show = tr.find("a", id=_SHOW_RE)
        if not show:
            continue
        m = _SHOW_RE.match(show.get("id") or "")
        if not m:
            continue
        mid = m.group(1)
        tids = _TEAM_ID_RE.findall(str(tr))
        if len(tids) < 2:
            continue
        code_el = show.find("code")
        i_el = show.find("i")
        mcode = ""
        if code_el and i_el:
            mcode = f"{code_el.get_text(strip=True)}{i_el.get_text(strip=True)}"
        kick = ""
        for sp in tr.find_all("span"):
            km = _KICK_RE.search(sp.get("title") or "")
            if km:
                kick = km.group(1)
                break
        ranks = [_rank_from(em.get_text()) for em in tr.select("em.pm")]
        ranks = [r for r in ranks if r]
        result[mid] = {
            "home_tid": tids[0],
            "away_tid": tids[1],
            "match_code": mcode,
            "kickoff": kick,
            "home_rank": ranks[0] if ranks else None,
            "away_rank": ranks[1] if len(ranks) > 1 else None,
        }
    return result


def _info(fid: str, home_rank=None, away_rank=None, source: str = "") -> Dict[str, Optional[str]]:
    return {
        "fid": str(fid),
        "home_rank": home_rank,
        "away_rank": away_rank,
        "source": source,
    }


def _pick_qb_by_tids(
    home_tid: str,
    away_tid: str,
    qb_index: Dict[tuple, List[Dict]],
    want_date: str,
) -> Optional[Dict[str, Any]]:
    cands = qb_index.get((home_tid, away_tid)) or []
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    if want_date:
        same = [r for r in cands if (r.get("kickoff") or "").startswith(want_date)]
        if len(same) == 1:
            return same[0]
        if same:
            cands = same
        cands = sorted(cands, key=lambda r: r.get("kickoff") or "")
    return cands[0] if len(cands) == 1 else None


def match_zgzcw_fids(
    live: List[Dict[str, Any]],
    code_map: Dict[str, Dict[str, Optional[str]]],
    bet_map: Dict[str, Dict[str, Any]],
    qb_rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Optional[str]]]:
    """{match_id: {fid, home_rank, away_rank, source}}。场次号 > 队ID > 队名日期。"""
    qb_index: Dict[tuple, List[Dict]] = defaultdict(list)
    qb_names: Dict[tuple, List[Dict]] = defaultdict(list)
    for row in qb_rows:
        qb_index[(row["home_tid"], row["away_tid"])].append(row)
        qb_names[(
            (row.get("kickoff") or "")[:10],
            _norm_team(row.get("home")),
            _norm_team(row.get("away")),
        )].append(row)

    result: Dict[str, Dict[str, Optional[str]]] = {}
    for m in live:
        mid = str(m.get("match_id") or "")
        if not mid:
            continue
        if m.get("fid_zgzcw"):
            result[mid] = _info(m["fid_zgzcw"], source="db")

        code = (m.get("match_code") or "").strip()
        by_code = code_map.get(code) if code else None
        if by_code and by_code.get("fid"):
            result[mid] = _info(
                by_code["fid"], by_code.get("home_rank"), by_code.get("away_rank"), "live",
            )
            continue

        want_date = _kickoff_date(m.get("match_date"))
        bet = bet_map.get(mid)
        if bet:
            hit = _pick_qb_by_tids(bet["home_tid"], bet["away_tid"], qb_index, want_date)
            if hit:
                result[mid] = _info(
                    hit["fid"],
                    hit.get("home_rank") or bet.get("home_rank"),
                    hit.get("away_rank") or bet.get("away_rank"),
                    "qb",
                )
                continue

        key = (want_date, _norm_team(m.get("home_team_name")), _norm_team(m.get("away_team_name")))
        named = qb_names.get(key) or []
        if len(named) == 1:
            hit = named[0]
            result[mid] = _info(hit["fid"], hit.get("home_rank"), hit.get("away_rank"), "name")
    return result


def resolve_zgzcw_fids(
    live: List[Dict[str, Any]],
    timeout: int = 20,
) -> Dict[str, Dict[str, Optional[str]]]:
    """给在售场补 fid。首页场次号优先, 否则投注页队ID对全量页。"""
    if not live:
        return {}
    with httpx.Client(timeout=timeout, headers=_headers(), follow_redirects=True) as client:
        live_html = _http_get(client, LIVE_URL, "live")
        bet_html = _http_get(client, BET_URL, "bet")
        qb_html = _http_get(client, QB_URL, "qb")
    code_map = parse_live_code_map(live_html)
    bet_map = parse_betting_matches(bet_html)
    qb_rows = parse_qb_fixtures(qb_html)
    mapped = match_zgzcw_fids(live, code_map, bet_map, qb_rows)
    n_new = sum(1 for v in mapped.values() if v.get("source") != "db")
    logger.info(
        f"zgzcw 映射 {len(mapped)}/{len(live)} "
        f"(live场次{len(code_map)} 投注{len(bet_map)} qb{len(qb_rows)} 新匹配{n_new})"
    )
    return mapped


def fetch_jczq_live_map(timeout: int = 20) -> Dict[str, Dict[str, Optional[str]]]:
    """兼容旧调用: 仅首页场次号。新路径请用 resolve_zgzcw_fids。"""
    with httpx.Client(timeout=timeout, headers=_headers(), follow_redirects=True) as client:
        html = _http_get(client, LIVE_URL, "live")
    result = parse_live_code_map(html)
    logger.info(f"zgzcw live 映射 {len(result)} 场")
    return result
