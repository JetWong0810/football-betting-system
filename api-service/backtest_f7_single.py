"""F7 单关 / 历史同赔 回测（基于已回填的 matches.is_single）。

不依赖 500 实时亚盘热度（历史无多公司水位），聚焦：
  1) F6 历史同赔：单关 vs 非单关 命中率对比
  2) 反向粗检：单关场若「跟 F6」vs「反 F6」谁更好
  3) 按年分桶

用法:
  cd api-service
  python3 -u backtest_f7_single.py
  ONLY_YEAR=2024 python3 -u backtest_f7_single.py
  LIMIT=500 python3 -u backtest_f7_single.py
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import pymysql

import settings
from jczq_similar_odds import (
    _ah_outcome,
    _get_low_odds_info,
    get_match_spf_odds,
)
from predict_service import calc_factor_jczq_similar_odds

ONLY_YEAR = os.getenv("ONLY_YEAR", "")
LIMIT = int(os.getenv("LIMIT", "0"))
MIN_SAMPLE = int(os.getenv("MIN_SAMPLE", "3"))  # F6 至少 N 场才计入命中统计


def _conn():
    return pymysql.connect(
        **settings.MYSQL_CONFIG,
        cursorclass=pymysql.cursors.DictCursor,
    )


def load_candidates() -> List[Dict]:
    """有比分 + 有亚盘终盘 + 有 spf 的已完赛场。"""
    where = ["m.home_score IS NOT NULL", "m.away_score IS NOT NULL", "ah.close_handicap IS NOT NULL"]
    args: list = []
    if ONLY_YEAR:
        where.append("m.match_date LIKE %s")
        args.append(f"{ONLY_YEAR}%")
    sql = f"""
        SELECT m.match_id, m.match_date, m.league_name, m.is_single,
               m.home_team_name, m.away_team_name,
               m.home_score, m.away_score,
               ah.open_handicap, ah.close_handicap
        FROM matches m
        JOIN jczq_ah_history ah ON ah.match_id = m.match_id
        WHERE {' AND '.join(where)}
        ORDER BY m.match_date
    """
    if LIMIT:
        sql += f" LIMIT {int(LIMIT)}"
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())
    finally:
        conn.close()


def actual_dir(hs: int, aws: int, hc: float, low_key: Optional[str]) -> Optional[str]:
    out = _ah_outcome(hs, aws, hc, low_key)
    if not out:
        return None
    label = out[0]
    if label in ("上盘", "半上"):
        return "upper"
    if label in ("下盘", "半下"):
        return "lower"
    return None  # 走水不计


def pct(n: int, d: int) -> float:
    return round(n * 100 / d, 1) if d else 0.0


def main():
    rows = load_candidates()
    print(f"[load] candidates={len(rows)} year={ONLY_YEAR or 'all'} limit={LIMIT or '-'}")

    # buckets: key -> {decidable, hit, follow_hit, reverse_hit, f6_upper, f6_lower}
    buckets = defaultdict(lambda: {
        "n": 0, "decidable": 0, "hit": 0,
        "f6_upper": 0, "f6_lower": 0, "f6_neutral": 0,
        "follow_ok": 0, "reverse_ok": 0,  # 仅单关+有方向时
    })

    skipped_no_spf = 0
    skipped_push = 0
    processed = 0

    for i, r in enumerate(rows, 1):
        mid = r["match_id"]
        spf = get_match_spf_odds(mid)
        if not spf:
            skipped_no_spf += 1
            continue

        ah_open = float(r["open_handicap"]) if r.get("open_handicap") is not None else None
        ah_close = float(r["close_handicap"])
        f6 = calc_factor_jczq_similar_odds(
            spf,
            league=r.get("league_name"),
            exclude_match_id=mid,
            ah_handicap=ah_close,
            ah_open=ah_open,
        )
        matches = f6.get("matches") or []
        if len(matches) < MIN_SAMPLE:
            # 仍计入样本不足桶，但不做命中
            year = str(r["match_date"])[:4]
            is_s = 1 if int(r.get("is_single") or 0) == 1 else 0
            for key in ("all", f"year:{year}", f"single:{is_s}", f"year:{year}|single:{is_s}"):
                buckets[key]["n"] += 1
                buckets[key]["f6_neutral"] += 1
            processed += 1
            continue

        low_key = None
        lk = _get_low_odds_info(
            spf["initial"]["win"], spf["initial"]["draw"], spf["initial"]["lose"],
            spf["current"]["win"], spf["current"]["draw"], spf["current"]["lose"],
        )
        low_key = lk[0]

        act = actual_dir(int(r["home_score"]), int(r["away_score"]), ah_close, low_key)
        if act is None:
            skipped_push += 1
            continue

        direction = f6.get("direction") or "neutral"
        is_s = 1 if int(r.get("is_single") or 0) == 1 else 0
        year = str(r["match_date"])[:4]
        hit = direction in ("upper", "lower") and direction == act

        keys = ["all", f"year:{year}", f"single:{is_s}", f"year:{year}|single:{is_s}"]
        for key in keys:
            b = buckets[key]
            b["n"] += 1
            if direction == "upper":
                b["f6_upper"] += 1
            elif direction == "lower":
                b["f6_lower"] += 1
            else:
                b["f6_neutral"] += 1
            if direction in ("upper", "lower"):
                b["decidable"] += 1
                if hit:
                    b["hit"] += 1

        # 单关有方向：跟 F6 vs 反 F6
        if is_s and direction in ("upper", "lower"):
            b = buckets["single_dir"]
            b["n"] += 1
            b["decidable"] += 1
            if hit:
                b["hit"] += 1
                b["follow_ok"] += 1
            else:
                b["reverse_ok"] += 1

        processed += 1
        if i % 500 == 0:
            print(f"  … {i}/{len(rows)}")

    print(f"\n[done] processed={processed} no_spf={skipped_no_spf} push/skip={skipped_push}")

    def show(title: str, key: str):
        b = buckets.get(key)
        if not b or not b["n"]:
            print(f"{title}: (empty)")
            return
        print(
            f"{title}: n={b['n']} decidable={b['decidable']} "
            f"hit={b['hit']}/{b['decidable']}={pct(b['hit'], b['decidable'])}% "
            f"U/L/N={b['f6_upper']}/{b['f6_lower']}/{b['f6_neutral']}"
        )

    print("\n=== F6 命中：总体 / 单关 / 非单关 ===")
    show("ALL", "all")
    show("单关", "single:1")
    show("非单", "single:0")

    print("\n=== 按年 × 单关 ===")
    years = sorted({k.split("|")[0][5:] for k in buckets if k.startswith("year:") and "|single:" in k})
    for y in years:
        show(f"{y} 单关", f"year:{y}|single:1")
        show(f"{y} 非单", f"year:{y}|single:0")

    print("\n=== 单关有方向：跟 F6 vs 反 F6（reverse_ok=实际与 F6 相反） ===")
    b = buckets.get("single_dir")
    if b and b["decidable"]:
        print(
            f"单关有方向 n={b['decidable']}: "
            f"跟对 {b['follow_ok']} ({pct(b['follow_ok'], b['decidable'])}%) / "
            f"反面对 {b['reverse_ok']} ({pct(b['reverse_ok'], b['decidable'])}%)"
        )
        if b["reverse_ok"] > b["follow_ok"]:
            print("  → 粗信号：单关场「反向 F6」略优（仅粗检，非完整反向因子）")
        elif b["follow_ok"] > b["reverse_ok"]:
            print("  → 粗信号：单关场仍宜「跟随 F6」")
        else:
            print("  → 打平")
    else:
        print("(无单关有方向样本)")

    print("\n注: 本脚本不回放 F4 市场热度/F7 放大逻辑（缺历史多公司水位）；")
    print("    完整反向因子仍需 had 赔率迎合快照，见 reverse-factors-pending。")


if __name__ == "__main__":
    main()
