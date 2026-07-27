"""从体彩官网 API 回填历史单关标记 + sporttery_match_id（P0/P1）。

数据源:
  P0 列表: getUniformMatchResultV1.qry → bettingSingle + matchId
  P1 详情: getFixedBonusV1.qry → singleList(分玩法 HAD/HHAD)

安全原则（默认绝不改坏已有数据）:
  1. 默认 --dry-run，只有显式 --apply 才写库
  2. is_single 只升不降（0→1），从不把 1 改回 0
  3. sporttery_match_id 仅在空时写入；冲突则跳过并记日志
  4. 不改比分、不改赔率数值、不删行
  5. 匹配必须高置信：match_code + 日期±1 + 队名/比分校验；歧义一律丢弃
  6. FixedBonus 仅更新 odds_win_draw_lose.is_single（HAD/HHAD），不碰赔率

用法:
  cd api-service
  python3 -u backfill_single_sporttery.py --dry-run --month 2024-02
  python3 -u backfill_single_sporttery.py --dry-run                 # 全量对账
  python3 -u backfill_single_sporttery.py --apply                   # P0 写库
  python3 -u backfill_single_sporttery.py --apply --with-fixed-bonus # P0+P1
  ONLY_YEAR=2024 python3 -u backfill_single_sporttery.py --dry-run
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pymysql

import settings

RESULT_API = (
    "https://webapi.sporttery.cn/gateway/uniform/football/"
    "getUniformMatchResultV1.qry"
)
FIXED_BONUS_API = (
    "https://webapi.sporttery.cn/gateway/uniform/football/getFixedBonusV1.qry"
)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.lottery.gov.cn/jc/zqsgkj/",
    "Accept": "application/json,text/plain,*/*",
}

DELAY = float(os.getenv("DELAY", "0.25"))
FIXED_DELAY = float(os.getenv("FIXED_DELAY", "0.35"))
PAGE_SIZE = 100
DATE_PAD_DAYS = 2  # API 开赛日 vs 库销售日常见差 0~2 天
MIN_MATCH_SCORE = 70  # 接受阈值阈值
LOG_DIR = Path(settings.DATA_DIR) / "backfill_single"
POOL_TO_ODDS_TYPE = {"HAD": "had", "HHAD": "hhad"}

# 常见队名异体 → 统一形（体彩缩写 ↔ 库内常用名）
TEAM_ALIASES = {
    "南安普顿": "南安普敦",
    "纽卡斯尔联": "纽卡斯尔",
    "曼彻斯特联": "曼联",
    "曼彻斯特城": "曼城",
    "托特纳姆热刺": "热刺",
    "莱斯特城": "莱斯特",
    "布莱顿海鸥": "布莱顿",
    "布赖顿": "布莱顿",
    "巴黎圣日耳曼": "巴黎圣日耳曼",
    "巴黎圣曼": "巴黎圣日耳曼",
    "巴黎": "巴黎圣日耳曼",
    "国际米兰": "国米",
    "国际米兰队": "国米",
    "亚特兰大队": "亚特兰大",
    "拜仁慕尼黑": "拜仁",
    "多特蒙德": "多特",
    "门兴格拉德巴赫": "门兴",
    "莱比锡红牛": "莱红牛",
    "莱红牛": "RB莱比锡",
    "RB莱比锡": "RB莱比锡",
    "毕尔巴鄂竞技": "毕尔巴鄂",
    "马德里竞技": "马竞",
    "马德里竞技队": "马竞",
    "皇家马德里": "皇马",
    "巴塞罗那": "巴萨",
    "马洛卡": "马略卡",
    "马略卡": "马略卡",
    "赫塔费": "赫塔菲",
    "巴伦西亚": "瓦伦西亚",
    "阿布艾因": "艾因",
    "利雅新月": "利雅得新月",
    "利雅胜利": "利雅得胜利",
    "里斯本": "葡萄牙体育",
}


def norm_team(name: Optional[str]) -> str:
    if not name:
        return ""
    s = str(name).strip()
    s = s.replace("　", "").replace(" ", "")
    s = TEAM_ALIASES.get(s, s)
    # 去常见后缀噪声
    for suf in ("足球俱乐部", "足球队", "队", "FC", "fc"):
        if s.endswith(suf) and len(s) > len(suf) + 1:
            s = s[: -len(suf)]
    return s


def team_sim(a: str, b: str) -> int:
    """简易队名相似度 0-100。"""
    na, nb = norm_team(a), norm_team(b)
    if not na or not nb:
        return 0
    if na == nb:
        return 100
    # 别名后再比一次
    na2 = TEAM_ALIASES.get(na, na)
    nb2 = TEAM_ALIASES.get(nb, nb)
    if na2 == nb2:
        return 100
    if na in nb or nb in na:
        shorter = min(len(na), len(nb))
        longer = max(len(na), len(nb))
        return int(85 + 10 * shorter / longer)
    # 字符重叠
    sa, sb = set(na), set(nb)
    inter = len(sa & sb)
    union = len(sa | sb) or 1
    ratio = inter / union
    if ratio >= 0.7 and inter >= 2:
        return int(60 + 40 * ratio)
    return int(ratio * 50)


def parse_score(text: Optional[str]) -> Optional[Tuple[int, int]]:
    if not text:
        return None
    m = re.match(r"^\s*(\d+)\s*[:：\-]\s*(\d+)\s*$", str(text))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def month_range(year: int, month: int) -> Tuple[str, str]:
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def iter_months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def ensure_columns(conn) -> None:
    """幂等加列：sporttery_match_id。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME='matches' AND COLUMN_NAME='sporttery_match_id'
            """
        )
        row = cur.fetchone()
        cnt = row["cnt"] if isinstance(row, dict) else row[0]
        if not cnt:
            cur.execute(
                """
                ALTER TABLE matches
                ADD COLUMN sporttery_match_id VARCHAR(32) DEFAULT NULL
                  COMMENT '体彩官网 matchId' AFTER fid_500,
                ADD UNIQUE INDEX uk_sporttery_match_id (sporttery_match_id)
                """
            )
            print("[schema] added matches.sporttery_match_id")
        else:
            # 确保唯一索引存在
            cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME='matches' AND INDEX_NAME='uk_sporttery_match_id'
                """
            )
            row = cur.fetchone()
            cnt = row["cnt"] if isinstance(row, dict) else row[0]
            if not cnt:
                # 先清重复再加索引（dry-run/apply 前）
                cur.execute(
                    """
                    SELECT sporttery_match_id, COUNT(*) c FROM matches
                    WHERE sporttery_match_id IS NOT NULL AND sporttery_match_id != ''
                    GROUP BY sporttery_match_id HAVING c > 1 LIMIT 1
                    """
                )
                dup = cur.fetchone()
                if dup:
                    raise RuntimeError(
                        f"sporttery_match_id 已有重复值，拒绝加唯一索引: {dup}"
                    )
                cur.execute(
                    "ALTER TABLE matches ADD UNIQUE INDEX uk_sporttery_match_id (sporttery_match_id)"
                )
                print("[schema] added uk_sporttery_match_id")
    conn.commit()


def fetch_json(client: httpx.Client, url: str, params: Dict[str, Any]) -> Dict:
    last_err = None
    for attempt in range(5):
        try:
            r = client.get(url, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            if not data.get("success"):
                msg = data.get("errorMessage") or data.get("errorCode") or "unknown"
                # 范围过大等业务错不重试
                if "范围过大" in str(msg):
                    raise RuntimeError(msg)
                last_err = RuntimeError(msg)
                time.sleep(1.5 * (attempt + 1))
                continue
            return data
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed {url} {params}: {last_err}")


def fetch_month_results(
    client: httpx.Client, begin: str, end: str
) -> List[Dict[str, Any]]:
    """拉一个月全部赛果（分页）。"""
    out: List[Dict[str, Any]] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        data = fetch_json(
            client,
            RESULT_API,
            {
                "matchBeginDate": begin,
                "matchEndDate": end,
                "leagueId": "",
                "pageSize": PAGE_SIZE,
                "pageNo": page,
                "isFix": 0,
                "matchPage": 1,
                "pcOrWap": 1,
            },
        )
        value = data.get("value") or {}
        total_pages = int(value.get("pages") or 1)
        rows = value.get("matchResult") or []
        out.extend(rows)
        if not rows:
            break
        page += 1
        time.sleep(DELAY)
    return out


def fetch_fixed_bonus(client: httpx.Client, sporttery_match_id: str) -> Optional[Dict]:
    data = fetch_json(
        client,
        FIXED_BONUS_API,
        {"clientCode": "3001", "matchId": sporttery_match_id},
    )
    return data.get("value")


def load_db_matches(conn, d0: str, d1: str) -> List[Dict]:
    """加载日期窗口内比赛（含两侧 padding）。"""
    start = (
        datetime.strptime(d0, "%Y-%m-%d").date() - timedelta(days=DATE_PAD_DAYS)
    ).isoformat()
    end = (
        datetime.strptime(d1, "%Y-%m-%d").date() + timedelta(days=DATE_PAD_DAYS)
    ).isoformat()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute(
            """
            SELECT match_id, match_date, match_code, match_number,
                   home_team_name, away_team_name,
                   home_score, away_score, is_single, sporttery_match_id
            FROM matches
            WHERE match_date BETWEEN %s AND %s
            """,
            (start, end),
        )
        return list(cur.fetchall())


def score_candidate(api: Dict, db: Dict) -> Tuple[int, str]:
    """返回 (score, reason)。score<MIN 视为不匹配。"""
    api_code = (api.get("matchNumStr") or "").strip()
    db_code = (db.get("match_code") or "").strip()
    if not api_code or not db_code or api_code != db_code:
        return 0, "code_mismatch"

    try:
        ad = datetime.strptime(api["matchDate"], "%Y-%m-%d").date()
        dd = datetime.strptime(db["match_date"], "%Y-%m-%d").date()
    except Exception:
        return 0, "bad_date"
    date_delta = abs((ad - dd).days)
    if date_delta > DATE_PAD_DAYS:
        return 0, f"date_delta={date_delta}"

    home_s = team_sim(api.get("homeTeam") or api.get("allHomeTeam"), db.get("home_team_name"))
    away_s = team_sim(api.get("awayTeam") or api.get("allAwayTeam"), db.get("away_team_name"))

    api_score = parse_score(api.get("sectionsNo999"))
    db_hs, db_as = db.get("home_score"), db.get("away_score")
    db_has_score = db_hs is not None and db_as is not None

    # 比分冲突：直接否决（防串场）
    if api_score and db_has_score and api_score != (int(db_hs), int(db_as)):
        return 0, f"score_conflict {api_score}!={(db_hs, db_as)}"

    # 强证据：场次号一致 + 日期窗口内 + 比分一致 → 即使队名缩写差异大也可信
    if api_score and db_has_score and api_score == (int(db_hs), int(db_as)):
        total = 90 + (5 if date_delta == 0 else 0) + min(home_s, away_s) // 20
        return min(total, 100), f"code+score home={home_s} away={away_s}"

    # API 无效/取消场次：必须队名够像，避免误配
    api_raw_score = str(api.get("sectionsNo999") or "")
    if (not api_score) and (
        "无效" in api_raw_score or "取消" in api_raw_score or not api_raw_score.strip()
    ):
        if home_s >= 75 and away_s >= 60:
            return 80, f"void_score_team_ok home={home_s} away={away_s}"
        return 0, f"void_score_team_low home={home_s} away={away_s}"

    # 无比分时靠队名
    if home_s < 55 or away_s < 55:
        return 0, f"team_low home={home_s} away={away_s}"

    total = int(0.5 * home_s + 0.5 * away_s) + (10 if date_delta == 0 else 0)
    if home_s >= 90 and away_s >= 90:
        total = max(total, 88)
    return total, f"teams home={home_s} away={away_s}"


def match_api_to_db(
    api_rows: List[Dict], db_rows: List[Dict]
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """一对一匹配。返回 (matched, unmatched_api, ambiguous)。

    优先：match_code + 日期±1 窗口内唯一候选，且比分一致 → 高置信接受。
    多候选：必须比分精确唯一命中，且综合分过线。
    """
    by_code: Dict[str, List[Dict]] = defaultdict(list)
    for r in db_rows:
        code = (r.get("match_code") or "").strip()
        if code:
            by_code[code].append(r)

    used_db_ids = set()
    matched = []
    unmatched = []
    ambiguous = []

    for api in api_rows:
        code = (api.get("matchNumStr") or "").strip()
        try:
            ad = datetime.strptime(api["matchDate"], "%Y-%m-%d").date()
        except Exception:
            unmatched.append(api)
            continue

        # 窗口内同 code 候选
        window_cands = []
        for db in by_code.get(code, []):
            if db["match_id"] in used_db_ids:
                continue
            try:
                dd = datetime.strptime(db["match_date"], "%Y-%m-%d").date()
            except Exception:
                continue
            if abs((ad - dd).days) <= DATE_PAD_DAYS:
                window_cands.append(db)

        scored = []
        for db in window_cands:
            sc, reason = score_candidate(api, db)
            if sc >= MIN_MATCH_SCORE:
                scored.append((sc, reason, db))
        scored.sort(key=lambda x: -x[0])

        # 唯一窗口候选且过线 → 直接接受
        if len(window_cands) == 1 and scored:
            sc, reason, db = scored[0]
            used_db_ids.add(db["match_id"])
            matched.append(
                {
                    "api": api,
                    "db": db,
                    "score": sc,
                    "reason": reason + "|unique_window",
                    "sporttery_match_id": str(api.get("matchId")),
                    "betting_single": 1 if int(api.get("bettingSingle") or 0) == 1 else 0,
                }
            )
            continue

        if not scored:
            unmatched.append(api)
            continue

        # 多候选：顶尖必须明显领先
        if len(scored) >= 2 and scored[0][0] - scored[1][0] < 8:
            ambiguous.append(
                {
                    "api": _api_brief(api),
                    "cands": [
                        {
                            "score": s,
                            "reason": r,
                            "match_id": d["match_id"],
                            "date": d["match_date"],
                            "home": d["home_team_name"],
                            "away": d["away_team_name"],
                        }
                        for s, r, d in scored[:3]
                    ],
                }
            )
            continue

        sc, reason, db = scored[0]
        used_db_ids.add(db["match_id"])
        matched.append(
            {
                "api": api,
                "db": db,
                "score": sc,
                "reason": reason,
                "sporttery_match_id": str(api.get("matchId")),
                "betting_single": 1 if int(api.get("bettingSingle") or 0) == 1 else 0,
            }
        )

    return matched, unmatched, ambiguous


def _api_brief(api: Dict) -> Dict:
    return {
        "matchId": api.get("matchId"),
        "matchDate": api.get("matchDate"),
        "matchNumStr": api.get("matchNumStr"),
        "home": api.get("homeTeam"),
        "away": api.get("awayTeam"),
        "score": api.get("sectionsNo999"),
        "bettingSingle": api.get("bettingSingle"),
    }


def preview_p0_stats(matched: List[Dict]) -> Dict[str, int]:
    """dry-run 统计，不碰库。"""
    stats = {
        "sporttery_id_set": 0,
        "sporttery_id_skip_conflict": 0,
        "sporttery_id_skip_filled": 0,
        "match_single_up": 0,
        "had_single_up": 0,
        "already_single": 0,
        "non_single": 0,
    }
    for m in matched:
        db = m["db"]
        sid = m["sporttery_match_id"]
        single = m["betting_single"]
        existing_sid = db.get("sporttery_match_id")
        if existing_sid and str(existing_sid) != sid:
            stats["sporttery_id_skip_conflict"] += 1
        elif existing_sid:
            stats["sporttery_id_skip_filled"] += 1
        else:
            stats["sporttery_id_set"] += 1
        if single == 1 and not int(db.get("is_single") or 0):
            stats["match_single_up"] += 1
            stats["had_single_up"] += 1  # 预估：有 had 行才会真升
        elif single == 1:
            stats["already_single"] += 1
        else:
            stats["non_single"] += 1
    return stats


def apply_p0_updates(conn, matched: List[Dict], batch_size: int = 500) -> Dict[str, int]:
    """写 sporttery_match_id + matches.is_single + had.is_single（只升不降）。

    分批 commit：整段已通过匹配率门槛，且更新幂等，中断可重跑。
    """
    stats = {
        "sporttery_id_set": 0,
        "sporttery_id_skip_conflict": 0,
        "sporttery_id_skip_filled": 0,
        "match_single_up": 0,
        "had_single_up": 0,
        "already_single": 0,
        "non_single": 0,
    }

    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        for i, m in enumerate(matched, 1):
            db = m["db"]
            mid = db["match_id"]
            sid = m["sporttery_match_id"]
            single = m["betting_single"]

            cur.execute(
                "SELECT is_single, sporttery_match_id FROM matches WHERE match_id=%s",
                (mid,),
            )
            row = cur.fetchone()
            if not row:
                continue

            existing_sid = row.get("sporttery_match_id")
            if existing_sid and str(existing_sid) != sid:
                stats["sporttery_id_skip_conflict"] += 1
            elif existing_sid:
                stats["sporttery_id_skip_filled"] += 1
            else:
                cur.execute(
                    "SELECT match_id FROM matches WHERE sporttery_match_id=%s AND match_id<>%s LIMIT 1",
                    (sid, mid),
                )
                taken = cur.fetchone()
                if taken:
                    stats["sporttery_id_skip_conflict"] += 1
                else:
                    cur.execute(
                        "UPDATE matches SET sporttery_match_id=%s WHERE match_id=%s AND sporttery_match_id IS NULL",
                        (sid, mid),
                    )
                    if cur.rowcount:
                        stats["sporttery_id_set"] += 1

            if single == 1:
                if not int(row.get("is_single") or 0):
                    cur.execute(
                        "UPDATE matches SET is_single=1 WHERE match_id=%s AND is_single=0",
                        (mid,),
                    )
                    if cur.rowcount:
                        stats["match_single_up"] += 1
                else:
                    stats["already_single"] += 1
                cur.execute(
                    """
                    UPDATE odds_win_draw_lose
                    SET is_single=1
                    WHERE match_id=%s AND odds_type='had' AND is_single=0
                    """,
                    (mid,),
                )
                if cur.rowcount:
                    stats["had_single_up"] += 1
            else:
                stats["non_single"] += 1

            if i % batch_size == 0:
                conn.commit()
                print(f"  [P0] committed {i}/{len(matched)}")

    conn.commit()
    return stats


def apply_p1_fixed_bonus(
    conn,
    client: httpx.Client,
    matched: List[Dict],
    dry_run: bool,
    checkpoint_path: Path,
    mode: str = "singles",
) -> Dict[str, int]:
    """对已匹配场拉 FixedBonus.singleList，只更新 had/hhad.is_single。"""
    stats = {
        "fetched": 0,
        "had_up": 0,
        "hhad_up": 0,
        "skip_cached": 0,
        "fetch_fail": 0,
        "no_single_list": 0,
        "had_mismatch_list": 0,
    }
    done = set()
    if checkpoint_path.exists():
        try:
            done = set(json.loads(checkpoint_path.read_text()).get("done", []))
        except Exception:
            done = set()

    targets = []
    for m in matched:
        sid = m["sporttery_match_id"]
        mid = m["db"]["match_id"]
        if not sid:
            continue
        if mode == "singles" and m["betting_single"] != 1:
            continue
        if sid in done:
            stats["skip_cached"] += 1
            continue
        targets.append((mid, sid, m["betting_single"]))

    print(
        f"[P1] FixedBonus mode={mode} targets={len(targets)} "
        f"(skip_cached={stats['skip_cached']})"
    )

    for i, (mid, sid, list_single) in enumerate(targets, 1):
        try:
            value = fetch_fixed_bonus(client, sid)
            stats["fetched"] += 1
        except Exception as e:
            stats["fetch_fail"] += 1
            print(f"  [P1] fail mid={mid} sid={sid}: {e}")
            time.sleep(FIXED_DELAY * 2)
            continue

        oh = (value or {}).get("oddsHistory") or {}
        sl = oh.get("singleList") or []
        if not sl:
            stats["no_single_list"] += 1
            done.add(sid)
        else:
            flags = {}
            for item in sl:
                pool = str(item.get("poolCode") or "").upper()
                odds_type = POOL_TO_ODDS_TYPE.get(pool)
                if not odds_type:
                    continue
                flags[odds_type] = 1 if int(item.get("single") or 0) == 1 else 0

            # 交叉校验：列表 bettingSingle 应与 HAD.single 一致
            if "had" in flags and flags["had"] != list_single:
                stats["had_mismatch_list"] += 1
                print(
                    f"  [P1] WARN HAD mismatch mid={mid} sid={sid} "
                    f"list={list_single} fixed={flags['had']}"
                )

            if dry_run:
                with conn.cursor(pymysql.cursors.DictCursor) as cur:
                    for ot, flag in flags.items():
                        if flag != 1:
                            continue
                        cur.execute(
                            "SELECT is_single FROM odds_win_draw_lose WHERE match_id=%s AND odds_type=%s",
                            (mid, ot),
                        )
                        row = cur.fetchone()
                        if row and not int(row.get("is_single") or 0):
                            if ot == "had":
                                stats["had_up"] += 1
                            else:
                                stats["hhad_up"] += 1
            else:
                with conn.cursor() as cur:
                    for ot, flag in flags.items():
                        if flag != 1:
                            continue  # 只升不降
                        cur.execute(
                            """
                            UPDATE odds_win_draw_lose
                            SET is_single=1
                            WHERE match_id=%s AND odds_type=%s AND is_single=0
                            """,
                            (mid, ot),
                        )
                        if cur.rowcount:
                            if ot == "had":
                                stats["had_up"] += 1
                            else:
                                stats["hhad_up"] += 1
                    if flags.get("had") == 1:
                        cur.execute(
                            "UPDATE matches SET is_single=1 WHERE match_id=%s AND is_single=0",
                            (mid,),
                        )
                conn.commit()
            done.add(sid)

        if i % 50 == 0 or i == len(targets):
            checkpoint_path.write_text(
                json.dumps(
                    {"done": sorted(done), "updated_at": datetime.now().isoformat()},
                    ensure_ascii=False,
                )
            )
            print(f"  [P1] progress {i}/{len(targets)} stats={stats}")
        time.sleep(FIXED_DELAY)

    checkpoint_path.write_text(
        json.dumps(
            {"done": sorted(done), "updated_at": datetime.now().isoformat()},
            ensure_ascii=False,
        )
    )
    return stats


def resolve_range(args) -> Tuple[date, date]:
    if args.month:
        y, m = args.month.split("-")
        y, m = int(y), int(m)
        last = calendar.monthrange(y, m)[1]
        return date(y, m, 1), date(y, m, last)
    only_year = os.getenv("ONLY_YEAR") or args.year
    if only_year:
        y = int(only_year)
        return date(y, 1, 1), date(y, 12, 31)
    # 默认覆盖库内 jczq 范围
    return date(2018, 1, 1), date(2026, 5, 31)


def main():
    parser = argparse.ArgumentParser(description="回填体彩单关标记")
    parser.add_argument("--dry-run", action="store_true", help="只对账不写库（默认）")
    parser.add_argument("--apply", action="store_true", help="写库")
    parser.add_argument("--month", type=str, help="仅处理 YYYY-MM")
    parser.add_argument("--year", type=str, help="仅处理某年")
    parser.add_argument(
        "--with-fixed-bonus",
        action="store_true",
        help="P1: 拉 FixedBonus 更新分玩法 is_single",
    )
    parser.add_argument(
        "--fixed-bonus-mode",
        choices=["singles", "all"],
        default="singles",
        help="FixedBonus 范围: singles=仅列表单关场(默认,约4.7k); all=全部已匹配场",
    )
    parser.add_argument(
        "--min-match-rate",
        type=float,
        default=0.95,
        help="--apply 时匹配率低于此值则中止（默认 0.95）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略匹配率门槛（危险）",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    if args.apply and args.dry_run:
        print("不能同时 --apply 与 --dry-run")
        sys.exit(2)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "dryrun" if dry_run else "apply"
    report_path = LOG_DIR / f"report_{mode}_{stamp}.json"

    start_d, end_d = resolve_range(args)
    print(
        f"[start] mode={'DRY-RUN' if dry_run else 'APPLY'} "
        f"range={start_d}~{end_d} fixed_bonus={args.with_fixed_bonus}"
    )

    conn = pymysql.connect(
        **settings.MYSQL_CONFIG,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        # schema：加列本身是幂等 DDL；写业务数据前仍受匹配率门槛保护
        ensure_columns(conn)

        all_matched: List[Dict] = []
        all_unmatched: List[Dict] = []
        all_ambiguous: List[Dict] = []
        month_stats = []

        # ---------- Phase A: 全量拉取 + 匹配（只读） ----------
        with httpx.Client() as client:
            for y, m in iter_months(start_d, end_d):
                begin, end = month_range(y, m)
                print(f"\n=== {begin} ~ {end} ===")
                try:
                    api_rows = fetch_month_results(client, begin, end)
                except Exception as e:
                    print(f"  fetch month failed: {e}")
                    month_stats.append(
                        {
                            "month": f"{y:04d}-{m:02d}",
                            "error": str(e),
                            "api": 0,
                            "matched": 0,
                            "unmatched": 0,
                            "ambiguous": 0,
                            "rate": 0,
                        }
                    )
                    continue

                db_rows = load_db_matches(conn, begin, end)
                matched, unmatched, ambiguous = match_api_to_db(api_rows, db_rows)

                rate = (len(matched) / len(api_rows)) if api_rows else 1.0
                singles_api = sum(
                    1 for a in api_rows if int(a.get("bettingSingle") or 0) == 1
                )
                singles_matched = sum(1 for x in matched if x["betting_single"] == 1)
                print(
                    f"  api={len(api_rows)} db_window={len(db_rows)} "
                    f"matched={len(matched)} unmatched={len(unmatched)} "
                    f"ambiguous={len(ambiguous)} rate={rate:.2%} "
                    f"api_single={singles_api} matched_single={singles_matched}"
                )

                month_stats.append(
                    {
                        "month": f"{y:04d}-{m:02d}",
                        "api": len(api_rows),
                        "matched": len(matched),
                        "unmatched": len(unmatched),
                        "ambiguous": len(ambiguous),
                        "rate": round(rate, 4),
                        "api_single": singles_api,
                        "matched_single": singles_matched,
                    }
                )
                all_matched.extend(matched)
                all_unmatched.extend([_api_brief(a) for a in unmatched])
                all_ambiguous.extend(ambiguous)

            total_api = sum(x.get("api", 0) for x in month_stats) or 1
            total_matched = sum(x.get("matched", 0) for x in month_stats)
            overall_rate = total_matched / total_api
            print(
                f"\n[summary] overall_match_rate={overall_rate:.2%} "
                f"({total_matched}/{total_api}) ambiguous={len(all_ambiguous)} "
                f"unmatched={len(all_unmatched)}"
            )

            p0_preview = preview_p0_stats(all_matched)
            print(f"[summary] P0 preview: {p0_preview}")

            # ---------- Phase B: 写库（仅 --apply，且匹配率达标） ----------
            p0_stats: Dict[str, int] = p0_preview
            if dry_run:
                print("[dry-run] 不写库")
            else:
                if not args.force and overall_rate < args.min_match_rate:
                    print(
                        f"[ABORT] 匹配率 {overall_rate:.2%} < {args.min_match_rate:.2%}，"
                        f"拒绝写库。排查 unmatched/ambiguous 后可用 --force。"
                    )
                    report = {
                        "mode": "aborted",
                        "reason": "low_match_rate",
                        "overall_match_rate": overall_rate,
                        "month_stats": month_stats,
                        "p0_preview": p0_preview,
                        "unmatched_count": len(all_unmatched),
                        "ambiguous_count": len(all_ambiguous),
                    }
                    report_path.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2)
                    )
                    (LOG_DIR / f"unmatched_{mode}_{stamp}.json").write_text(
                        json.dumps(all_unmatched, ensure_ascii=False, indent=2)
                    )
                    if all_ambiguous:
                        (LOG_DIR / f"ambiguous_{mode}_{stamp}.json").write_text(
                            json.dumps(all_ambiguous, ensure_ascii=False, indent=2)
                        )
                    print(f"[report] {report_path}")
                    sys.exit(1)

                print("[apply] writing P0 updates (batched, idempotent)...")
                try:
                    p0_stats = apply_p0_updates(conn, all_matched)
                    print(f"[apply] P0 committed: {p0_stats}")
                except Exception as e:
                    conn.rollback()
                    print(f"[apply] P0 error (partial batches may have committed; safe to rerun): {e}")
                    raise

            p1_stats: Dict[str, Any] = {}
            if args.with_fixed_bonus:
                ck = LOG_DIR / f"fixed_bonus_checkpoint_{start_d}_{end_d}_{args.fixed_bonus_mode}.json"
                p1_stats = apply_p1_fixed_bonus(
                    conn,
                    client,
                    all_matched,
                    dry_run=dry_run,
                    checkpoint_path=ck,
                    mode=args.fixed_bonus_mode,
                )
                print(f"[summary] P1: {p1_stats}")

        report = {
            "mode": mode,
            "range": [start_d.isoformat(), end_d.isoformat()],
            "overall_match_rate": overall_rate,
            "month_stats": month_stats,
            "p0": p0_stats,
            "p1": p1_stats,
            "unmatched_sample": all_unmatched[:100],
            "unmatched_count": len(all_unmatched),
            "ambiguous_sample": all_ambiguous[:50],
            "ambiguous_count": len(all_ambiguous),
            "matched_single_sample": [
                {
                    "match_id": m["db"]["match_id"],
                    "sporttery_match_id": m["sporttery_match_id"],
                    "code": m["api"].get("matchNumStr"),
                    "home": m["db"]["home_team_name"],
                    "api_home": m["api"].get("homeTeam"),
                    "score": m["score"],
                    "reason": m["reason"],
                    "betting_single": m["betting_single"],
                }
                for m in all_matched
                if m["betting_single"] == 1
            ][:80],
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"[report] {report_path}")

        (LOG_DIR / f"unmatched_{mode}_{stamp}.json").write_text(
            json.dumps(all_unmatched, ensure_ascii=False, indent=2)
        )
        if all_ambiguous:
            (LOG_DIR / f"ambiguous_{mode}_{stamp}.json").write_text(
                json.dumps(all_ambiguous, ensure_ascii=False, indent=2)
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
