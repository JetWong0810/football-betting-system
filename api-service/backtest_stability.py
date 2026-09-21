#!/usr/bin/env python3
"""近两个月稳度回测: 对齐 frontend/src/utils/stabilityScore.js + 今日稳推荐。

只读 DB。用法:
  python3 backtest_stability.py
  START=2026-07-21 END=2026-09-20 python3 backtest_stability.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import pymysql

from jczq_similar_odds import (
    _ah_outcome,
    _get_low_odds_info,
    get_match_nspf_odds,
    get_match_spf_odds,
)
from predict_service import calc_factor_jczq_similar_odds

SAMPLE_REC_MIN = 8
STABLE_REC_MAX = 2
STABLE_REC_GAP = 3


def _conn():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "10.130.130.139"),
        port=int(os.getenv("MYSQL_PORT", 3321)),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE", "football_betting"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _sale_date(match_number: Optional[str], match_date) -> Optional[str]:
    mn = str(match_number or "").strip()
    if len(mn) >= 6 and mn[:6].isdigit():
        yy, mo, dd = int(mn[:2]), int(mn[2:4]), int(mn[4:6])
        try:
            return date(2000 + yy, mo, dd).isoformat()
        except ValueError:
            pass
    if match_date:
        return str(match_date)[:10]
    return None


def _low_move(odds: Optional[Dict]) -> Optional[str]:
    if not odds:
        return None
    ini, cur = odds.get("initial") or {}, odds.get("current") or {}
    key, lo, lc, _ = _get_low_odds_info(
        ini.get("win"), ini.get("draw"), ini.get("lose"),
        cur.get("win"), cur.get("draw"), cur.get("lose"),
    )
    if key is None or lo is None or lc is None:
        return None
    if lc < lo - 0.005:
        return "down"
    if lc > lo + 0.005:
        return "up"
    return "flat"


def _ah_to_dir(label: Optional[str]) -> Optional[str]:
    if label in ("上盘", "半上"):
        return "upper"
    if label in ("下盘", "半下"):
        return "lower"
    return None


def _focus_hit_pct(f6: Dict) -> Tuple[float, int]:
    up = lo = push = 0
    for m in f6.get("matches") or []:
        ah = m.get("ahResult") or m.get("ah_result")
        if ah in ("上盘", "半上"):
            up += 1
        elif ah in ("下盘", "半下"):
            lo += 1
        elif ah == "走水":
            push += 1
    total = up + lo + push
    direction = f6.get("direction")
    if not total:
        return 0.0, 0
    if direction == "upper":
        return round(up / total * 100, 1), total
    if direction == "lower":
        return round(lo / total * 100, 1), total
    return round(max(up, lo) / total * 100, 1), total


def is_dir_move_paired(direction: str, move: Optional[str]) -> bool:
    return (direction == "lower" and move == "down") or (
        direction == "upper" and move == "up"
    )


def calc_stability(
    *,
    direction: Optional[str],
    move: Optional[str],
    handicap: Optional[float],
    is_single: bool,
    sample: int,
    hit_pct: float,
    ref_score: Optional[float],
    odds_kind: str,
) -> Dict[str, Any]:
    dir_ = direction if direction in ("upper", "lower") else "neutral"
    nspf = odds_kind == "nspf"
    n = int(sample or 0)
    paired = is_dir_move_paired(dir_, move)
    thick = (not nspf) and n >= SAMPLE_REC_MIN
    reasons: List[str] = []
    score = 0
    if dir_ == "lower":
        score += 3
        reasons.append("下盘")
    elif dir_ == "upper":
        score += 1
        reasons.append("上盘")
    else:
        return {
            "score": 0, "paired": False, "recommendable": False,
            "reasons": [], "dir": dir_, "nspf": nspf, "shallowUpper": False,
        }

    hc = None if handicap is None else abs(float(handicap))
    shallow = hc is not None and hc <= 0.5 + 1e-9
    deep = hc is not None and hc + 1e-9 >= 0.5
    shallow_upper = dir_ == "upper" and shallow
    if shallow_upper:
        score += 2
        reasons.append("浅盘上盘")
    elif deep:
        score += 2
        reasons.append("深盘")
    if is_single:
        score += 2
        reasons.append("单关")
    if not nspf and n >= SAMPLE_REC_MIN:
        score += 3
        reasons.append("同赔≥8")
    elif not nspf and n >= 5:
        score += 1
        reasons.append("同赔≥5")
    ref = -1 if ref_score is None else float(ref_score)
    if thick and (hit_pct or 0) >= 65:
        score += 2
        reasons.append("赢盘≥65")
    if thick and ref >= 48:
        score += 1
        reasons.append("分数≥48")
    if thick and ref >= 60:
        score += 1
        reasons.append("分数≥60")
    return {
        "score": score,
        "paired": paired,
        "recommendable": paired and thick,
        "reasons": reasons,
        "dir": dir_,
        "nspf": nspf,
        "shallowUpper": shallow_upper,
    }


def cmp_stability(a: Dict, b: Dict) -> int:
    for ka, kb in (
        (b["score"], a["score"]),
        (b["sample"], a["sample"]),
        (b["hitPct"], a["hitPct"]),
        (b["refScore"], a["refScore"]),
    ):
        if kb != ka:
            return 1 if ka > kb else -1
    return 0


def pick_stable_recs(ranked: List[Dict]) -> List[Dict]:
    pool = [x for x in ranked if x.get("recommendable")]
    if not pool:
        return []
    if len(pool) == 1:
        return pool[:1]
    if (pool[0]["score"] - pool[1]["score"]) >= STABLE_REC_GAP and not pool[1].get("shallowUpper"):
        return pool[:1]
    return pool[:STABLE_REC_MAX]


def _rate(hits: int, n: int) -> Optional[float]:
    if n <= 0:
        return None
    return round(hits * 100.0 / n, 1)


def summarize(rows: List[Dict], label: str) -> Dict[str, Any]:
    decidable = [r for r in rows if r.get("hit") is not None]
    pushes = [r for r in rows if r.get("actual_dir") is None and r.get("hit") is None and r.get("actual")]
    # actual 走水: actual_dir None, hit None
    push_n = sum(1 for r in rows if r.get("actual_label") in ("走水",))
    hits = sum(1 for r in decidable if r["hit"])
    n = len(decidable)
    return {
        "label": label,
        "n_all": len(rows),
        "n": n,
        "hits": hits,
        "misses": n - hits,
        "push": push_n,
        "hit_rate": _rate(hits, n),
    }


def load_matches(start: str, end: str) -> List[Dict]:
    start_yy = start[2:].replace("-", "")
    end_yy = end[2:].replace("-", "")
    sql = """
        SELECT m.match_id, m.match_number, m.match_date, m.match_time, m.league_name,
               m.home_team_name, m.away_team_name, m.home_score, m.away_score,
               m.is_single, ah.close_handicap
        FROM matches m
        LEFT JOIN (
            SELECT match_id, MAX(close_handicap) AS close_handicap
            FROM jczq_ah_history
            WHERE company LIKE 'Bet365%%'
            GROUP BY match_id
        ) ah ON ah.match_id = m.match_id
        WHERE m.home_score IS NOT NULL AND m.away_score IS NOT NULL
          AND LEFT(m.match_number, 6) >= %s AND LEFT(m.match_number, 6) <= %s
        ORDER BY LEFT(m.match_number, 6) ASC, m.match_time ASC
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (start_yy, end_yy))
            rows = cur.fetchall()
    out = []
    for r in rows:
        ahc = float(r["close_handicap"]) if r.get("close_handicap") is not None else None
        out.append({
            "match_id": r["match_id"],
            "sale_date": _sale_date(r.get("match_number"), r.get("match_date")),
            "league": r.get("league_name") or "",
            "home": r.get("home_team_name") or "",
            "away": r.get("away_team_name") or "",
            "home_score": int(r["home_score"]),
            "away_score": int(r["away_score"]),
            "is_single": bool(r.get("is_single")),
            "ahc": ahc,
        })
    return out


def load_wdl_singles(match_ids: List[str]) -> Dict[str, bool]:
    if not match_ids:
        return {}
    out: Dict[str, bool] = {}
    with _conn() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(match_ids), 400):
                chunk = match_ids[i:i + 400]
                ph = ",".join(["%s"] * len(chunk))
                cur.execute(
                    f"SELECT match_id, is_single FROM odds_win_draw_lose "
                    f"WHERE match_id IN ({ph}) AND odds_type='had'",
                    chunk,
                )
                for r in cur.fetchall():
                    out[r["match_id"]] = int(r.get("is_single") or 0) == 1
    return out


def run(start: str, end: str) -> Dict[str, Any]:
    rows = load_matches(start, end)
    print(f"loaded {len(rows)} finished {start}~{end}", flush=True)
    had_single = load_wdl_singles([r["match_id"] for r in rows])

    from jczq_similar_odds import get_spf_pool
    t0 = time.time()
    print(f"spf pool {len(get_spf_pool())} in {time.time()-t0:.1f}s", flush=True)

    records: List[Dict] = []
    skipped = defaultdict(int)
    t1 = time.time()
    for i, row in enumerate(rows, 1):
        if i % 100 == 0:
            print(f"  {i}/{len(rows)} rec={len(records)} {time.time()-t1:.0f}s", flush=True)
        mid = row["match_id"]
        spf = get_match_spf_odds(mid)
        nspf = None
        odds_kind = "spf"
        odds = spf
        if not spf:
            nspf = get_match_nspf_odds(mid)
            odds_kind = "nspf"
            odds = nspf
        if not odds:
            skipped["no_odds"] += 1
            continue
        if row["ahc"] is None:
            skipped["no_ah"] += 1
            continue
        is_single = bool(row["is_single"] or had_single.get(mid))
        extra = {}
        if odds_kind == "nspf":
            extra = {"odds_kind": "nspf"}
        f6 = calc_factor_jczq_similar_odds(
            odds, league=row["league"], exclude_match_id=mid,
            ah_handicap=row["ahc"], is_single=is_single, **extra)
        direction = f6.get("direction") or "neutral"
        sample = len(f6.get("matches") or [])
        hit_pct, ah_total = _focus_hit_pct(f6)
        ref = int(f6.get("refScore") or 0)
        move = _low_move(odds)
        st = calc_stability(
            direction=direction, move=move, handicap=row["ahc"],
            is_single=is_single, sample=sample, hit_pct=hit_pct,
            ref_score=ref, odds_kind=odds_kind,
        )
        low_key = _get_low_odds_info(
            odds["initial"]["win"], odds["initial"]["draw"], odds["initial"]["lose"],
            odds["current"]["win"], odds["current"]["draw"], odds["current"]["lose"],
        )[0]
        out = _ah_outcome(row["home_score"], row["away_score"], row["ahc"], low_key)
        actual_label = out[0] if out else None
        actual_dir = _ah_to_dir(actual_label)
        hit = None
        if direction in ("upper", "lower") and actual_dir in ("upper", "lower"):
            hit = actual_dir == direction
        rec = {
            **row,
            "direction": direction,
            "move": move,
            "sample": sample,
            "ah_total": ah_total,
            "hitPct": hit_pct,
            "refScore": ref,
            "oddsKind": odds_kind,
            "score": st["score"],
            "paired": st["paired"],
            "recommendable": st["recommendable"],
            "shallowUpper": st["shallowUpper"],
            "reasons": st["reasons"],
            "actual_label": actual_label,
            "actual_dir": actual_dir,
            "hit": hit,
        }
        records.append(rec)

    print(f"done records={len(records)} skipped={dict(skipped)} {time.time()-t1:.0f}s", flush=True)

    recable = [r for r in records if r["recommendable"]]
    paired = [r for r in records if r["paired"] and r["oddsKind"] != "nspf"]
    directional = [r for r in records if r["direction"] in ("upper", "lower") and r["oddsKind"] != "nspf"]

    by_day: Dict[str, List[Dict]] = defaultdict(list)
    for r in recable:
        if r.get("sale_date"):
            by_day[r["sale_date"]].append(r)

    daily_picks: List[Dict] = []
    daily_first: List[Dict] = []
    empty_days = 0
    for d, rs in sorted(by_day.items()):
        ranked = sorted(rs, key=lambda x: (-x["score"], -x["sample"], -x["hitPct"], -x["refScore"]))
        picks = pick_stable_recs(ranked)
        if not picks:
            empty_days += 1
            continue
        daily_picks.extend(picks)
        daily_first.append(picks[0])

    buckets = {
        "all_dir": directional,
        "paired": paired,
        "recommendable": recable,
        "daily_top1": daily_first,
        "daily_top12": daily_picks,
        "rec_lower": [r for r in recable if r["direction"] == "lower"],
        "rec_upper": [r for r in recable if r["direction"] == "upper"],
        "rec_shallow_upper": [r for r in recable if r.get("shallowUpper")],
        "rec_deep_lower": [r for r in recable if r["direction"] == "lower" and "深盘" in (r.get("reasons") or [])],
        "rec_single": [r for r in recable if "单关" in (r.get("reasons") or [])],
        "rec_score11+": [r for r in recable if r["score"] >= 11],
        "rec_score9+": [r for r in recable if r["score"] >= 9],
        "pick_lower": [r for r in daily_picks if r["direction"] == "lower"],
        "pick_upper": [r for r in daily_picks if r["direction"] == "upper"],
        "pick_shallow_upper": [r for r in daily_picks if r.get("shallowUpper")],
    }
    labels = {
        "all_dir": "有方向(spf)",
        "paired": "方向-变动配对",
        "recommendable": "今日稳池(配对+同赔≥8+非nspf)",
        "daily_top1": "每日稳1",
        "daily_top12": "每日稳1+稳2",
        "rec_lower": "今日稳·下盘",
        "rec_upper": "今日稳·上盘",
        "rec_shallow_upper": "今日稳·浅盘上盘",
        "rec_deep_lower": "今日稳·深盘下盘",
        "rec_single": "今日稳·单关",
        "rec_score11+": "今日稳·稳度≥11",
        "rec_score9+": "今日稳·稳度≥9",
        "pick_lower": "稳1+2·下盘",
        "pick_upper": "稳1+2·上盘",
        "pick_shallow_upper": "稳1+2·浅盘上盘",
    }
    stats = [summarize(buckets[k], labels[k]) for k in buckets]

    # recent days with picks
    day_rows = []
    for d, rs in sorted(by_day.items()):
        ranked = sorted(rs, key=lambda x: (-x["score"], -x["sample"], -x["hitPct"], -x["refScore"]))
        picks = pick_stable_recs(ranked)
        dec = [p for p in picks if p.get("hit") is not None]
        hits = sum(1 for p in dec if p["hit"])
        day_rows.append({
            "sale_date": d,
            "pool": len(rs),
            "picks": [
                {
                    "league": p["league"], "home": p["home"], "away": p["away"],
                    "dir": p["direction"], "score": p["score"], "sample": p["sample"],
                    "hitPct": p["hitPct"], "hit": p["hit"], "actual": p["actual_label"],
                    "shallowUpper": p.get("shallowUpper"),
                }
                for p in picks
            ],
            "n": len(dec),
            "hits": hits,
            "hit_rate": _rate(hits, len(dec)),
        })

    return {
        "range": [start, end],
        "n_loaded": len(rows),
        "n_records": len(records),
        "skipped": dict(skipped),
        "n_days_with_pool": len(by_day),
        "n_days_empty_pick": empty_days,
        "stats": stats,
        "recent_days": day_rows[-21:],
        "all_days": day_rows,
    }


def main():
    end = os.getenv("END") or (date.today() - timedelta(days=1)).isoformat()
    start = os.getenv("START") or (date.today() - timedelta(days=61)).isoformat()
    data = run(start, end)
    out_path = Path(__file__).resolve().parent.parent / "logs" / f"stability_backtest_{start}_{end}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n===== HIT RATES =====")
    for s in data["stats"]:
        hr = "--" if s["hit_rate"] is None else f"{s['hit_rate']}%"
        print(f"{hr:>7}  n={s['n']:<4} hit={s['hits']}/{s['n']}  push={s['push']}  {s['label']}")
    print(f"\ndays with pool={data['n_days_with_pool']} wrote {out_path}")


if __name__ == "__main__":
    main()
