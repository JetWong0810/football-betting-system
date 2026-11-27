"""裁判历史档案: API-Football 没有按裁判查询的接口, 但每场比赛都带裁判名字(往届赛季基本 100% 填写)。
做法: 扫描该裁判可能执法的赛事(本联赛+次级联赛+国内杯赛+欧战/亚冠)近 3 个赛季的比赛列表(每个联赛赛季 1 次请求, 并行),
本地按名字筛出他执法的场次, 再只对这些场次取详情(每次 20 场)统计牌和点球, 最后与基线比较。按需查询, 结果缓存 24 小时,
缓存里只存"每场精简记录", 不存球员数据, 不做跨赛季批量入库。

名字匹配: AF 里同一人有多种写法("A. Madley"/"Andrew Madley"/"Andy Madley, England"/"Bobby Madley"=Robert), 还有同姓不同人
(英超 Andrew Madley 与英冠 Bobby Madley 是兄弟)。这里用"规范化首字母(昵称先还原) + 姓的词集合包含"判定同一人,
并把同姓但首字母不同的统计为"已排除"透明告知。
"""
from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from database import get_db

from .client import AfClient
from .hist import FINISHED, parse_detail

logger = logging.getLogger(__name__)

SEASONS_BACK = 3
TTL = 24 * 3600
MIN_BASELINE_N = 80
# 全体基线(本系统 30 个联赛本赛季 5091 场, 2026-11): 联赛自己的基线样本不足时退回它
POOLED = {"yellow": 3.86, "red": 0.178, "pens": 0.267, "goals": 2.95}

NICK = {"bobby": "robert", "rob": "robert", "robbie": "robert", "bob": "robert", "andy": "andrew", "drew": "andrew", "alex": "alexander",
        "mike": "michael", "mick": "michael", "tom": "thomas", "tommy": "thomas", "jim": "james", "jimmy": "james", "bill": "william",
        "will": "william", "dave": "david", "steve": "stephen", "steven": "stephen", "chris": "christopher", "nick": "nicholas",
        "joe": "joseph", "matt": "matthew", "dan": "daniel", "danny": "daniel", "ben": "benjamin", "tony": "anthony", "pete": "peter",
        "sam": "samuel", "rich": "richard", "rick": "richard", "ed": "edward", "ted": "edward", "ian": "ian"}

_EUROPE = {39, 40, 41, 45, 48, 140, 141, 143, 135, 136, 137, 78, 79, 81, 61, 62, 66, 88, 89, 90, 94, 96, 113, 244, 103, 179, 181, 185, 2, 3, 848}
_ASIA = {292, 98, 99, 307, 17, 18, 169, 188}
FAMILY: Dict[int, List[int]] = {
    39: [40, 45, 48], 40: [39, 41, 45, 48], 41: [40, 45, 48], 140: [141, 143], 141: [140, 143], 135: [136, 137], 136: [135, 137],
    78: [79, 81], 79: [78, 81], 61: [62, 66], 62: [61, 66], 88: [89, 90], 89: [88, 90], 94: [96], 179: [181, 185],
}
UEFA = [2, 3, 848]
AFC = [17, 18]


def competitions(league_id: int) -> List[int]:
    comps = [league_id] + FAMILY.get(league_id, [])
    if league_id in _EUROPE:
        comps += UEFA
    elif league_id in _ASIA:
        comps += AFC
    out: List[int] = []
    for c in comps:
        if c not in out:
            out.append(c)
    return out


# ---------------------------------------------------------------- 名字匹配
def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def parse_name(raw: Optional[str]) -> Optional[Tuple[str, FrozenSet[str]]]:
    """-> (规范化首字母, 姓的词集合); 单个词(无名字)首字母为空。"""
    if not raw or not str(raw).strip():
        return None
    s = re.sub(r"\s*,\s*[A-Za-z .\-']+$", "", str(raw).strip())       # 去掉 ", England" 这类国家后缀
    toks = [t for t in re.split(r"\s+", _ascii(s).replace(".", " ").strip()) if t]
    if not toks:
        return None
    if len(toks) == 1:
        return "", frozenset(toks)
    first = NICK.get(toks[0], toks[0])
    return first[0], frozenset(toks[1:])


def same_person(a: Optional[Tuple[str, FrozenSet[str]]], b: Optional[Tuple[str, FrozenSet[str]]]) -> bool:
    if not a or not b:
        return False
    if a[0] and b[0] and a[0] != b[0]:
        return False
    return a[1] <= b[1] or b[1] <= a[1]


def same_surname_other_person(a: Tuple[str, FrozenSet[str]], b: Optional[Tuple[str, FrozenSet[str]]]) -> bool:
    return bool(b) and (a[1] <= b[1] or b[1] <= a[1]) and bool(a[0]) and bool(b[0]) and a[0] != b[0]


def ref_key(raw: Optional[str]) -> Optional[str]:
    p = parse_name(raw)
    return f"{p[0]}:{' '.join(sorted(p[1]))}" if p else None


# ---------------------------------------------------------------- 统计(纯函数)
def is_shootout_event(status: str, minute: int, extra: int) -> bool:
    """点球大战的每一脚在 AF 里是"分钟=120、补时>=1"的 Goal(Penalty)/Missed Penalty 事件, 不是裁判判罚的点球, 必须排除。
    只在比赛以点球大战决胜(状态 PEN)时才这样判定; 加时赛(AET)里 120 分钟补时的点球是真判罚。"""
    return status == "PEN" and minute >= 120 and extra > 0


def match_record(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """parse_detail 的结果 -> 精简记录: 双方黄牌/红牌/点球判罚(含罚丢)、比分。"""
    m = parsed["match"]
    hid, aid = m["home_id"], m["away_id"]
    rec = {"fid": m["fixture_id"], "d": datetime.utcfromtimestamp(m["ts"]).strftime("%Y-%m-%d"), "lg": m["league_id"], "s": m["season"],
           "h": hid, "a": aid, "hg": m["hg"], "ag": m["ag"], "yh": 0, "ya": 0, "rh": 0, "ra": 0, "ph": 0, "pa": 0}
    for e in parsed["events"]:
        side = "h" if e["team_id"] == hid else "a" if e["team_id"] == aid else None
        if not side:
            continue
        if e["type"] == "Card" and e["detail"] == "Yellow Card":
            rec["y" + side] += 1
        elif e["type"] == "Card" and e["detail"] == "Red Card":
            rec["r" + side] += 1
        elif e["type"] == "Goal" and e["detail"] in ("Penalty", "Missed Penalty") and not is_shootout_event(m["status"], e["minute"], e["extra"]):
            rec["p" + side] += 1
    return rec


def aggregate(recs: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(recs)
    if not n:
        return {"n": 0}
    tot = lambda a, b: sum(r[a] + r[b] for r in recs)
    out = {"n": n, "yellow": tot("yh", "ya") / n, "red": tot("rh", "ra") / n, "pens": tot("ph", "pa") / n,
           "goals": sum((r["hg"] or 0) + (r["ag"] or 0) for r in recs) / n,
           "home_win": sum(1 for r in recs if (r["hg"] or 0) > (r["ag"] or 0)) / n,
           "draw": sum(1 for r in recs if (r["hg"] or 0) == (r["ag"] or 0)) / n,
           "away_win": sum(1 for r in recs if (r["hg"] or 0) < (r["ag"] or 0)) / n}
    y_all = tot("yh", "ya")
    p_all = tot("ph", "pa")
    out["yellow_home_share"] = sum(r["yh"] for r in recs) / y_all if y_all else None
    out["pens_home_share"] = sum(r["ph"] for r in recs) / p_all if p_all else None
    return out


def team_record(recs: List[Dict[str, Any]], team_id: int) -> Dict[str, Any]:
    mine = [r for r in recs if team_id in (r["h"], r["a"])]
    w = d = l = yf = ya = pf = pa = rf = ra = 0
    for r in mine:
        home = r["h"] == team_id
        gf, ga = (r["hg"], r["ag"]) if home else (r["ag"], r["hg"])
        gf, ga = gf or 0, ga or 0
        w += gf > ga
        d += gf == ga
        l += gf < ga
        yf += r["yh"] if home else r["ya"]
        ya += r["ya"] if home else r["yh"]
        pf += r["ph"] if home else r["pa"]
        pa += r["pa"] if home else r["ph"]
        rf += r["rh"] if home else r["ra"]
        ra += r["ra"] if home else r["rh"]
    return {"n": len(mine), "w": w, "d": d, "l": l, "y_for": yf, "y_against": ya, "p_for": pf, "p_against": pa, "r_for": rf, "r_against": ra}


def zscore(mean: float, base: float, n: int, base_n: Optional[int] = None) -> float:
    """相对基线的偏离。标准误同时包含裁判样本(n 场)和基线样本(base_n 场)的噪音, 泊松近似;
    base_n 为空表示基线是近似精确值(如大样本合并基线)。"""
    if not n or base <= 0:
        return 0.0
    var = base / n + (base / base_n if base_n else 0.0)
    return (mean - base) / math.sqrt(var)


def verdict(z: float) -> str:
    return "普通波动" if abs(z) < 1.5 else ("明显偏高" if z > 0 else "明显偏低")


def league_baseline(league_id: int, season: int) -> Dict[str, Tuple[float, int, str]]:
    """每项指标的基线 -> {指标: (值, 样本场数, 来源)}。
    黄牌、总进球: 联赛差异真实存在, 用该联赛本赛季(场数>=80), 否则退回合并基线;
    红牌、点球判罚: 低频事件, 联赛本赛季的估计太吵(例如英超 110 场只有 22 个点球), 一律用 30 个联赛合并的大样本。"""
    pooled = {k: (v, 5091, "30 个联赛合并") for k, v in POOLED.items()}
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT COUNT(*) n, SUM(m.home_goals+m.away_goals) g,
                SUM((SELECT COUNT(*) FROM af_match_event e WHERE e.af_fixture_id=m.af_fixture_id AND e.type='Card' AND e.detail='Yellow Card')) y
                FROM af_match m WHERE m.league_id=%s AND m.season=%s AND m.status IN ('FT','AET','PEN') AND m.home_goals IS NOT NULL""", (league_id, season))
            r = cur.fetchone()
        n = int(r["n"] or 0)
        if n >= MIN_BASELINE_N:
            out = dict(pooled)
            out["yellow"] = (float(r["y"]) / n, n, "该联赛本赛季")
            out["goals"] = (float(r["g"]) / n, n, "该联赛本赛季")
            return out
    except Exception:  # noqa: BLE001
        logger.exception("联赛基线计算失败")
    return pooled


# ---------------------------------------------------------------- 抓取
def scan_matches(c: AfClient, name: str, league_id: int, season: int) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """扫描赛事×赛季的比赛列表, 返回 (该裁判执法的已完赛场次列表, 名字写法, 已排除的同姓他人写法)。"""
    target = parse_name(name)
    if not target:
        return [], [], []
    jobs = [(lid, s) for lid in competitions(league_id) for s in range(season, season - SEASONS_BACK, -1)]

    def one(job):
        lid, s = job
        try:
            return c.get("/fixtures", {"league": lid, "season": s}).get("response", [])
        except Exception as e:  # noqa: BLE001  某个赛事没有该赛季(如杯赛)很正常
            logger.info("裁判扫描跳过 league=%s season=%s: %s", lid, s, e)
            return []

    with ThreadPoolExecutor(max_workers=5) as ex:
        lists = list(ex.map(one, jobs))
    hits: List[Dict[str, Any]] = []
    variants: Dict[str, int] = {}
    excluded: Dict[str, int] = {}
    for fx in lists:
        for f in fx:
            raw = f["fixture"].get("referee")
            if not raw or f["fixture"]["status"]["short"] not in FINISHED:
                continue
            p = parse_name(raw)
            if same_person(target, p):
                hits.append(f)
                variants[raw] = variants.get(raw, 0) + 1
            elif same_surname_other_person(target, p):
                excluded[raw] = excluded.get(raw, 0) + 1
    return hits, [f"{k}×{v}" for k, v in sorted(variants.items(), key=lambda kv: -kv[1])], [f"{k}×{v}" for k, v in sorted(excluded.items(), key=lambda kv: -kv[1])]


def build(c: AfClient, name: str, league_id: int, season: int) -> Dict[str, Any]:
    hits, variants, excluded = scan_matches(c, name, league_id, season)
    ids = [int(f["fixture"]["id"]) for f in hits]
    recs: List[Dict[str, Any]] = []
    for i in range(0, len(ids), 20):
        for d in c.get("/fixtures", {"ids": "-".join(str(x) for x in ids[i:i + 20])}).get("response", []):
            if d["fixture"]["status"]["short"] in FINISHED:
                recs.append(match_record(parse_detail(d)))
    return {"records": recs, "variants": variants, "excluded": excluded, "comps": competitions(league_id), "built": datetime.utcnow().isoformat()}


def load_cached(key: str, league_id: int, season: int) -> Optional[Dict[str, Any]]:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT payload_json, fetched_at FROM af_referee_profile WHERE ref_key=%s AND league_id=%s AND season=%s", (key, league_id, season))
            r = cur.fetchone()
    except Exception as e:  # noqa: BLE001
        if e.args and e.args[0] == 1146:
            return None
        raise
    if not r or not r.get("payload_json"):
        return None
    return {"data": json.loads(r["payload_json"]), "fetchedAt": r["fetched_at"]}


def fetch(match_id: str, name: str, force: bool = False, client: Optional[AfClient] = None) -> Dict[str, Any]:
    from .injuries import _mapping
    mp = _mapping(match_id)
    key = ref_key(name)
    if not mp or not key or not mp.get("af_league_id") or not mp.get("af_season"):
        return {"ok": False, "reason": "no_mapping"}
    lid, season = int(mp["af_league_id"]), int(mp["af_season"])
    cached = load_cached(key, lid, season)
    if cached and not force and (datetime.utcnow() - cached["fetchedAt"]).total_seconds() < TTL:
        return {"ok": True, "cached": True, "n": len(cached["data"]["records"])}
    own = client is None
    c = client or AfClient()
    try:
        data = build(c, name, lid, season)
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO af_referee_profile (ref_key, league_id, season, payload_json) VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json), fetched_at=CURRENT_TIMESTAMP",
                (key, lid, season, json.dumps(data, ensure_ascii=False)))
        return {"ok": True, "cached": False, "n": len(data["records"]), "requests": c.requests}
    except Exception as e:  # noqa: BLE001
        logger.warning("裁判档案统计失败 %s: %s", name, e)
        return {"ok": False, "reason": "error"}
    finally:
        if own:
            c.close()


# ---------------------------------------------------------------- 渲染
def _pct(x: Optional[float]) -> str:
    return "-" if x is None else f"{x * 100:.0f}%"


def render_profile(data: Dict[str, Any], name: str, home: str, away: str, home_id: Optional[int], away_id: Optional[int],
                   base: Dict[str, Tuple[float, int, str]], season: int) -> str:
    recs = data.get("records") or []
    if not recs:
        return (f"\n【裁判档案】{name}: API-Football 在扫描的赛事(近 {SEASONS_BACK} 个赛季)里没有找到他执法的已完赛场次"
                f"(可能是名字写法不同或他主要在别的赛事执法);请联网补充,查不到就明说。")
    ag = aggregate(recs)
    by_s: Dict[int, int] = {}
    for r in recs:
        by_s[r["s"]] = by_s.get(r["s"], 0) + 1
    seasons = " / ".join(f"{s}:{n}场" for s, n in sorted(by_s.items(), reverse=True))
    n = ag["n"]
    L = [f"\n【裁判档案】{name}(来源 API-Football 自行统计,近 {SEASONS_BACK} 个赛季,共 {n} 场;分赛季 {seasons};"
         f"名字写法 {', '.join(data.get('variants') or [])}"
         + (f";已排除同姓不同人 {', '.join(data['excluded'])}" if data.get("excluded") else "") + ")"]

    def item(label, key, fmt="{:.2f}"):
        b, bn, src = base[key]
        z = zscore(ag[key], b, n, bn)
        return f"{label} {fmt.format(ag[key])}(基线 {fmt.format(b)}[{src}{bn}场],{verdict(z)})"
    L.append("均值对比基线(偏离按 1.5 个标准误判断,标准误已含基线自身的噪音;点球已排除点球大战): "
             + "; ".join([item("黄牌/场", "yellow"), item("红牌/场", "red", "{:.3f}"), item("点球判罚/场(含罚丢)", "pens", "{:.3f}"), item("总进球/场", "goals")]))
    L.append("注意: 他执法的赛事混有联赛、杯赛和欧战,各赛事的牌和点球水平本来就不同,所以和单一基线比只能作粗略参考。")
    L.append(f"结果分布: 主胜 {_pct(ag['home_win'])} / 平 {_pct(ag['draw'])} / 客胜 {_pct(ag['away_win'])};"
             f"黄牌里主队占 {_pct(ag['yellow_home_share'])}(客队 {_pct(None if ag['yellow_home_share'] is None else 1 - ag['yellow_home_share'])});"
             f"点球判给主队占 {_pct(ag['pens_home_share'])}(共 {round(ag['pens'] * n)} 个)")
    for lab, nm, tid in (("主队", home, home_id), ("客队", away, away_id)):
        if not tid:
            continue
        t = team_record(recs, int(tid))
        if t["n"]:
            L.append(f"执法过{lab}{nm}: {t['n']} 场 {t['w']}胜{t['d']}平{t['l']}负;该队被出示黄牌 {t['y_for']} 张、对手 {t['y_against']} 张;"
                     f"点球判给该队 {t['p_for']} 个、判给对手 {t['p_against']} 个;红牌该队 {t['r_for']}、对手 {t['r_against']}")
        else:
            L.append(f"执法过{lab}{nm}: 扫描范围内 0 场")
    L.append("说明: 这是 API-Football 自己统计的数据,口径统一,优先于联网查到的第三方数字(第三方常口径不同);联网只补争议判罚、执法尺度、媒体评价。"
             "单项在 30 场以内的偏差不可靠;红牌和点球没有个人稳定性,黄牌倾向有一定稳定性;和两队的小样本(几场)不能说明\"偏向\"。")
    return "\n".join(L)


def render(match_id: str, name: str, home: str, away: str) -> str:
    from .injuries import _mapping
    mp = _mapping(match_id)
    key = ref_key(name)
    if not mp or not key or not mp.get("af_league_id"):
        return ""
    lid, season = int(mp["af_league_id"]), int(mp["af_season"])
    c = load_cached(key, lid, season)
    if not c:
        return ""
    return render_profile(c["data"], name, home, away, mp.get("af_home_id"), mp.get("af_away_id"), league_baseline(lid, season), season)
