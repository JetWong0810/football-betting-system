#!/usr/bin/env python3
"""近一年竞彩同赔回测: 筛选组合命中率 + 每日推荐候选。

只读 DB。用法:
  python3 backtest_similar_filters.py
  START=2025-07-20 END=2026-07-20 python3 backtest_similar_filters.py
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import pymysql

from jczq_similar_odds import (
    _ah_outcome,
    _get_low_odds_info,
    get_match_spf_odds,
)
from predict_service import calc_factor_jczq_similar_odds


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
    """售卖期 YYYY-MM-DD(match_number 前6位 YYMMDD)。"""
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


def _low_move(spf: Dict) -> Optional[str]:
    ini, cur = spf.get("initial") or {}, spf.get("current") or {}
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


def _parse_ah_pct(f6: Dict) -> Tuple[float, float, int, int, int, int]:
    """从 details 解析上/下盘命中%; 缺则从 matches 重算。"""
    up_n = lo_n = push = total = 0
    for d in f6.get("details") or []:
        name, desc = d.get("name"), str(d.get("desc") or "")
        if name == "上盘命中":
            # 31% (9/29)
            import re
            m = re.search(r"(\d+(?:\.\d+)?)%\s*\((\d+)/(\d+)\)", desc)
            if m:
                up_n, total = int(m.group(2)), int(m.group(3))
        elif name == "下盘命中":
            import re
            m = re.search(r"(\d+(?:\.\d+)?)%\s*\((\d+)/(\d+)\)", desc)
            if m:
                lo_n = int(m.group(2))
                total = total or int(m.group(3))
        elif name == "走水":
            import re
            m = re.search(r"^(\d+)", desc)
            if m:
                push = int(m.group(1))
    if total <= 0:
        # fallback matches
        for m in f6.get("matches") or []:
            ah = m.get("ahResult")
            if ah in ("上盘", "半上"):
                up_n += 1
                total += 1
            elif ah in ("下盘", "半下"):
                lo_n += 1
                total += 1
            elif ah == "走水":
                push += 1
                total += 1
    up_pct = round(up_n / total * 100) if total else 0
    lo_pct = round(lo_n / total * 100) if total else 0
    return up_pct, lo_pct, up_n, lo_n, push, total


def _focus_hit_pct(direction: str, up_pct: float, lo_pct: float) -> float:
    if direction == "upper":
        return up_pct
    if direction == "lower":
        return lo_pct
    return max(up_pct, lo_pct)


def load_matches(start: str, end: str) -> List[Dict]:
    sql = """
        SELECT m.match_id, m.match_number, m.match_date, m.match_time, m.league_name,
               m.home_team_name, m.away_team_name, m.home_score, m.away_score,
               m.asian_handicap, ah.close_handicap
        FROM matches m
        LEFT JOIN jczq_ah_history ah ON ah.match_id = m.match_id
        WHERE m.match_date >= %s AND m.match_date <= %s
          AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
        ORDER BY m.match_date ASC, m.match_time ASC
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (start, end))
            rows = cur.fetchall()
    out = []
    for r in rows:
        ahc = None
        if r.get("close_handicap") is not None:
            ahc = float(r["close_handicap"])
        elif r.get("asian_handicap") is not None:
            try:
                ahc = -float(r["asian_handicap"])
            except (TypeError, ValueError):
                ahc = None
        out.append({
            "match_id": r["match_id"],
            "sale_date": _sale_date(r.get("match_number"), r.get("match_date")),
            "match_date": str(r["match_date"])[:10] if r.get("match_date") else None,
            "league": r.get("league_name") or "",
            "home": r.get("home_team_name") or "",
            "away": r.get("away_team_name") or "",
            "home_score": int(r["home_score"]),
            "away_score": int(r["away_score"]),
            "ahc": ahc,
        })
    return out


def run_backtest(start: str, end: str) -> Dict[str, Any]:
    rows = load_matches(start, end)
    print(f"loaded {len(rows)} finished matches {start}~{end}", flush=True)

    # warm pool once
    from jczq_similar_odds import get_spf_pool
    t0 = time.time()
    pool_n = len(get_spf_pool())
    print(f"spf pool {pool_n} in {time.time()-t0:.1f}s", flush=True)

    records: List[Dict] = []
    skipped = defaultdict(int)
    t1 = time.time()
    for i, row in enumerate(rows, 1):
        if i % 200 == 0:
            print(f"  progress {i}/{len(rows)} records={len(records)} {time.time()-t1:.0f}s", flush=True)
        mid = row["match_id"]
        spf = get_match_spf_odds(mid)
        if not spf:
            skipped["no_spf"] += 1
            continue
        if row["ahc"] is None:
            skipped["no_ah"] += 1
            continue
        f6 = calc_factor_jczq_similar_odds(
            spf, league=row["league"], exclude_match_id=mid, ah_handicap=row["ahc"])
        direction = f6.get("direction") or "neutral"
        sample_n = len(f6.get("matches") or [])
        up_pct, lo_pct, up_n, lo_n, push, ah_total = _parse_ah_pct(f6)
        focus_pct = _focus_hit_pct(direction, up_pct, lo_pct)
        ref = int(f6.get("refScore") or 0)
        move = _low_move(spf)

        low_key = _get_low_odds_info(
            spf["initial"]["win"], spf["initial"]["draw"], spf["initial"]["lose"],
            spf["current"]["win"], spf["current"]["draw"], spf["current"]["lose"],
        )[0]
        out = _ah_outcome(row["home_score"], row["away_score"], row["ahc"], low_key)
        actual_label = out[0] if out else None
        actual_dir = _ah_to_dir(actual_label)

        hit = None
        if direction in ("upper", "lower") and actual_dir in ("upper", "lower"):
            hit = actual_dir == direction

        records.append({
            "match_id": mid,
            "sale_date": row["sale_date"],
            "league": row["league"],
            "home": row["home"],
            "away": row["away"],
            "direction": direction,
            "sample": sample_n,
            "ah_total": ah_total,
            "up_pct": up_pct,
            "lo_pct": lo_pct,
            "focus_pct": focus_pct,
            "refScore": ref,
            "move": move,
            "actual": actual_label,
            "actual_dir": actual_dir,
            "hit": hit,
        })

    print(f"done records={len(records)} skipped={dict(skipped)} in {time.time()-t1:.0f}s", flush=True)
    return {"records": records, "skipped": dict(skipped), "start": start, "end": end}


def _rate(hits: int, n: int) -> Optional[float]:
    if n <= 0:
        return None
    return round(hits * 100.0 / n, 1)


def evaluate_combos(records: List[Dict]) -> List[Dict]:
    """评估筛选组合(仅统计有方向且可判命中的场)。"""
    flags = {
        "dir_ul": lambda r: r["direction"] in ("upper", "lower"),
        "sample>=5": lambda r: r["sample"] >= 5,
        "ah_total>=5": lambda r: r["ah_total"] >= 5,
        "focus>=65": lambda r: r["focus_pct"] >= 65,
        "ref>=60": lambda r: r["refScore"] >= 60,
        "ref>=50": lambda r: r["refScore"] >= 50,
        "move_up": lambda r: r["move"] == "up",
        "move_down": lambda r: r["move"] == "down",
        "move_flat": lambda r: r["move"] == "flat",
        "dir_upper": lambda r: r["direction"] == "upper",
        "dir_lower": lambda r: r["direction"] == "lower",
    }

    # 核心组合(与 UI 对齐) + 若干扩展
    combo_defs = [
        ("全部有方向", ["dir_ul"]),
        ("同赔≥5", ["dir_ul", "sample>=5"]),
        ("盘路样本≥5", ["dir_ul", "ah_total>=5"]),
        ("命中≥65%", ["dir_ul", "focus>=65"]),
        ("分数≥60", ["dir_ul", "ref>=60"]),
        ("分数≥50", ["dir_ul", "ref>=50"]),
        ("同赔≥5 + 命中≥65%", ["dir_ul", "sample>=5", "focus>=65"]),
        ("同赔≥5 + 分数≥60", ["dir_ul", "sample>=5", "ref>=60"]),
        ("命中≥65% + 分数≥60", ["dir_ul", "focus>=65", "ref>=60"]),
        ("同赔≥5 + 命中≥65% + 分数≥60", ["dir_ul", "sample>=5", "focus>=65", "ref>=60"]),
        ("盘路≥5 + 命中≥65% + 分数≥60", ["dir_ul", "ah_total>=5", "focus>=65", "ref>=60"]),
        ("上盘 + 同赔≥5 + 命中≥65%", ["dir_upper", "sample>=5", "focus>=65"]),
        ("下盘 + 同赔≥5 + 命中≥65%", ["dir_lower", "sample>=5", "focus>=65"]),
        ("上盘 + 三条件", ["dir_upper", "sample>=5", "focus>=65", "ref>=60"]),
        ("下盘 + 三条件", ["dir_lower", "sample>=5", "focus>=65", "ref>=60"]),
        ("上升 + 三条件", ["dir_ul", "sample>=5", "focus>=65", "ref>=60", "move_up"]),
        ("下降 + 三条件", ["dir_ul", "sample>=5", "focus>=65", "ref>=60", "move_down"]),
        ("不变 + 三条件", ["dir_ul", "sample>=5", "focus>=65", "ref>=60", "move_flat"]),
        ("同赔≥10 + 命中≥70% + 分数≥65", ["dir_ul", "sample>=5", "focus>=65", "ref>=60"]),  # placeholder replaced below
    ]

    # 额外高门槛
    def sample10(r): return r["sample"] >= 10
    def focus70(r): return r["focus_pct"] >= 70
    def ref65(r): return r["refScore"] >= 65
    flags["sample>=10"] = sample10
    flags["focus>=70"] = focus70
    flags["ref>=65"] = ref65
    combo_defs[-1] = ("同赔≥10 + 命中≥70% + 分数≥65", ["dir_ul", "sample>=10", "focus>=70", "ref>=65"])

    results = []
    for name, keys in combo_defs:
        preds = [flags[k] for k in keys]
        subset = [r for r in records if r["hit"] is not None and all(p(r) for p in preds)]
        n = len(subset)
        hits = sum(1 for r in subset if r["hit"])
        results.append({
            "name": name,
            "n": n,
            "hits": hits,
            "hit_rate": _rate(hits, n),
            "keys": keys,
        })
    results.sort(key=lambda x: (-(x["hit_rate"] or 0), -x["n"]))
    return results


def daily_top(records: List[Dict], sale_date: str, k: int = 3) -> List[Dict]:
    """某售卖日推荐: 有方向 + 同赔≥5 + 命中≥65%, 优先分数再命中率。"""
    cands = [
        r for r in records
        if r.get("sale_date") == sale_date
        and r["direction"] in ("upper", "lower")
        and r["sample"] >= 5
        and r["focus_pct"] >= 65
    ]
    cands.sort(key=lambda r: (-r["refScore"], -r["focus_pct"], -r["sample"]))
    return cands[:k]


def main():
    start = os.getenv("START", "2025-07-20")
    end = os.getenv("END", "2026-07-20")
    out_path = Path(__file__).resolve().parent.parent / "logs" / f"similar_backtest_{start}_{end}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = run_backtest(start, end)
    records = data["records"]
    combos = evaluate_combos(records)

    # 按售卖日汇总(三条件)
    by_day = defaultdict(list)
    for r in records:
        if r["sale_date"]:
            by_day[r["sale_date"]].append(r)

    day_stats = []
    for d, rs in sorted(by_day.items()):
        tops = daily_top(rs if False else records, d, 3)  # noqa — use all records filter by date inside
        tops = daily_top(records, d, 3)
        # day hit rate under best combo
        subset = [
            r for r in rs
            if r["hit"] is not None
            and r["direction"] in ("upper", "lower")
            and r["sample"] >= 5
            and r["focus_pct"] >= 65
            and r["refScore"] >= 60
        ]
        n = len(subset)
        hits = sum(1 for r in subset if r["hit"])
        day_stats.append({
            "sale_date": d,
            "n_triple": n,
            "hit_rate": _rate(hits, n),
            "tops": [
                {
                    "match_id": t["match_id"],
                    "league": t["league"],
                    "home": t["home"],
                    "away": t["away"],
                    "direction": t["direction"],
                    "focus_pct": t["focus_pct"],
                    "refScore": t["refScore"],
                    "sample": t["sample"],
                    "hit": t["hit"],
                    "actual": t["actual"],
                }
                for t in tops
            ],
        })

    # 最近 14 个有三条件样本的日子
    recent_days = [x for x in day_stats if (x["n_triple"] or 0) > 0][-14:]

    directional = [r for r in records if r["hit"] is not None]
    summary = {
        "range": [start, end],
        "n_records": len(records),
        "n_directional_judgable": len(directional),
        "baseline_hit_rate": _rate(sum(1 for r in directional if r["hit"]), len(directional)),
        "skipped": data["skipped"],
        "combos": combos,
        "recent_days": recent_days,
        "best_combo": next((c for c in combos if c["n"] >= 30), combos[0] if combos else None),
    }

    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    # also dump slim records for further analysis
    rec_path = out_path.with_name(out_path.stem + "_records.jsonl")
    with rec_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("\n===== COMBOS (n>=1) =====")
    for c in combos:
        if c["n"] <= 0:
            continue
        print(f"{c['hit_rate']:>5}%  n={c['n']:<5}  {c['name']}")

    print(f"\nwrote {out_path}")
    print(f"wrote {rec_path}")


if __name__ == "__main__":
    main()
