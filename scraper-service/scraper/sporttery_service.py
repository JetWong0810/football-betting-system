from datetime import datetime
from typing import Dict, List, Optional

import httpx

import settings
from repository import OddsRepository


def parse_decimal(value: Optional[str]) -> Optional[float]:
    if value in (None, "", "-", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_single_flag(value: Optional[object]) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0
    if isinstance(value, str):
        token = value.strip().lower()
        return 1 if token in {"1", "true", "y", "yes"} else 0
    return 0


def extract_pool_single_flags(match_data: Dict) -> Dict[str, int]:
    flags: Dict[str, int] = {}
    for pool in match_data.get("poolList", []):
        code = str(pool.get("poolCode") or "").strip().lower()
        if not code:
            continue
        flag = pool.get("single")
        if flag is None:
            flag = pool.get("bettingSingle")
        flags[code] = parse_single_flag(flag)
    return flags


class SportterySyncService:
    def __init__(self, repository: Optional[OddsRepository] = None):
        self.repository = repository or OddsRepository()
        self.client = httpx.Client(timeout=settings.HTTP_TIMEOUT, headers={"User-Agent": settings.USER_AGENT})
        self.stats = {"matches": 0, "odds": 0}

    def fetch_pool(self, pool_code: str) -> Dict:
        url = f"{settings.SPORTTERY_API_URL}?channel=c&poolCode={pool_code}"
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()

    def run_once(self) -> Dict[str, int]:
        self.stats = {"matches": 0, "odds": 0}
        for pool_name, pool_code in settings.POOL_CODES.items():
            data = self.fetch_pool(pool_code)
            self.parse_pool(pool_name, data)
        self.repository.finalize_sync(self.stats["matches"], self.stats["odds"])
        return self.stats

    # Parsing helpers -----------------------------------------------------
    def parse_pool(self, pool_name: str, data: Dict) -> None:
        if not data.get("success") or data.get("emptyFlag"):
            return
        match_info_list = data.get("value", {}).get("matchInfoList", [])
        for date_group in match_info_list:
            for match_data in date_group.get("subMatchList", []):
                if pool_name == "had_hhad":
                    single_flags = extract_pool_single_flags(match_data)
                    match = self.build_match(match_data)
                    self.repository.upsert_match(match)
                    self.stats["matches"] += 1
                    for odds in self.build_had_hhad(match_data, single_flags):
                        self.repository.upsert_odds_wdl(odds)
                        self.stats["odds"] += 1
                elif pool_name == "crs":
                    items = self.build_crs(match_data)
                    self.repository.upsert_odds_score_bulk(str(match_data.get("matchId")), items)
                    self.stats["odds"] += len(items)
                elif pool_name == "ttg":
                    items = self.build_ttg(match_data)
                    self.repository.upsert_odds_goals_bulk(str(match_data.get("matchId")), items)
                    self.stats["odds"] += len(items)
                elif pool_name == "hafu":
                    items = self.build_hafu(match_data)
                    self.repository.upsert_odds_hafu_bulk(str(match_data.get("matchId")), items)
                    self.stats["odds"] += len(items)

    def build_match(self, match_data: Dict) -> Dict:
        match_id = str(match_data.get("matchId"))
        match_date = match_data.get("matchDate")
        match_time = match_data.get("matchTime")
        timestamp = None
        if match_date and match_time:
            try:
                dt = datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M:%S")
                timestamp = int(dt.timestamp())
            except ValueError:
                dt = None
        else:
            dt = None
        status_map = {
            "Selling": "not_started",
            "Finished": "finished",
            "Cancelled": "cancelled",
        }
        match_status = status_map.get(match_data.get("matchStatus"), "not_started")
        return {
            "match_id": match_id,
            "match_number": match_data.get("matchNumDate"),
            "match_code": match_data.get("matchNumStr"),
            "project_type": "football",
            "league_id": match_data.get("leagueId"),
            "league_name": match_data.get("leagueAbbName"),
            "league_full_name": match_data.get("leagueAllName"),
            "match_date": match_date,
            "match_time": match_time,
            "match_timestamp": timestamp,
            "home_team_id": match_data.get("homeTeamId"),
            "home_team_name": match_data.get("homeTeamAbbName"),
            "home_team_rank": match_data.get("homeRank"),
            "away_team_id": match_data.get("awayTeamId"),
            "away_team_name": match_data.get("awayTeamAbbName"),
            "away_team_rank": match_data.get("awayRank"),
            "is_single": parse_single_flag(match_data.get("bettingSingle")),
            "match_status": match_status,
            "notice": match_data.get("matchTips"),
            "odds_update_time": match_data.get("oddsUpdateTime"),
        }

    def build_had_hhad(self, match_data: Dict, single_flags: Optional[Dict[str, int]] = None) -> List[Dict]:
        match_id = str(match_data.get("matchId"))
        results: List[Dict] = []
        single_flags = single_flags or {}
        default_single = parse_single_flag(match_data.get("bettingSingle"))

        had_data = match_data.get("had", {})
        if had_data and had_data.get("h"):
            is_single = single_flags.get("had", default_single)
            results.append(
                {
                    "match_id": match_id,
                    "odds_type": "had",
                    "handicap": 0,
                    "win_odds": parse_decimal(had_data.get("h")),
                    "draw_odds": parse_decimal(had_data.get("d")),
                    "lose_odds": parse_decimal(had_data.get("a")),
                    "win_support": parse_decimal(had_data.get("h_trend")),
                    "draw_support": parse_decimal(had_data.get("d_trend")),
                    "lose_support": parse_decimal(had_data.get("a_trend")),
                    "is_single": is_single,
                }
            )
        hhad_data = match_data.get("hhad", {})
        if hhad_data and hhad_data.get("h"):
            goal_line = hhad_data.get("goalLineValue", "0")
            try:
                handicap = float(goal_line)
            except (TypeError, ValueError):
                handicap = 0
            is_single = single_flags.get("hhad", default_single)
            results.append(
                {
                    "match_id": match_id,
                    "odds_type": "hhad",
                    "handicap": handicap,
                    "win_odds": parse_decimal(hhad_data.get("h")),
                    "draw_odds": parse_decimal(hhad_data.get("d")),
                    "lose_odds": parse_decimal(hhad_data.get("a")),
                    "win_support": parse_decimal(hhad_data.get("h_trend")),
                    "draw_support": parse_decimal(hhad_data.get("d_trend")),
                    "lose_support": parse_decimal(hhad_data.get("a_trend")),
                    "is_single": is_single,
                }
            )
        return results

    def build_crs(self, match_data: Dict) -> List[Dict]:
        match_id = str(match_data.get("matchId"))
        crs_data = match_data.get("crs", {})
        if not crs_data:
            return []
        items: List[Dict] = []
        segments = {
            "win": [
                ("1:0", "s01s00"), ("2:0", "s02s00"), ("2:1", "s02s01"),
                ("3:0", "s03s00"), ("3:1", "s03s01"), ("3:2", "s03s02"),
                ("4:0", "s04s00"), ("4:1", "s04s01"), ("4:2", "s04s02"),
                ("5:0", "s05s00"), ("5:1", "s05s01"), ("5:2", "s05s02"),
            ],
            "draw": [
                ("0:0", "s00s00"), ("1:1", "s01s01"), ("2:2", "s02s02"),
                ("3:3", "s03s03"),
            ],
            "lose": [
                ("0:1", "s00s01"), ("0:2", "s00s02"), ("1:2", "s01s02"),
                ("0:3", "s00s03"), ("1:3", "s01s03"), ("2:3", "s02s03"),
                ("0:4", "s00s04"), ("1:4", "s01s04"), ("2:4", "s02s04"),
                ("0:5", "s00s05"), ("1:5", "s01s05"), ("2:5", "s02s05"),
            ],
        }
        for result_type, pairs in segments.items():
            for label, key in pairs:
                odds_value = crs_data.get(key)
                if odds_value:
                    home, away = label.split(":")
                    items.append(
                        {
                            "result_type": result_type,
                            "home_score": int(home),
                            "away_score": int(away),
                            "score_label": label,
                            "odds": parse_decimal(odds_value),
                            "is_other": 0,
                        }
                    )
        special_map = {
            "win": ("s1sh", "胜其他"),
            "draw": ("spsh", "平其他"),
            "lose": ("sash", "负其他"),
        }
        for result_type, (key, label) in special_map.items():
            odds_value = crs_data.get(key)
            if odds_value:
                items.append(
                    {
                        "result_type": result_type,
                        # 用 -1 表示“其他”比分，避免插入 NULL 时唯一索引失效
                        "home_score": -1,
                        "away_score": -1,
                        "score_label": label,
                        "odds": parse_decimal(odds_value),
                        "is_other": 1,
                    }
                )
        return items

    def build_ttg(self, match_data: Dict) -> List[Dict]:
        ttg_data = match_data.get("ttg", {})
        if not ttg_data:
            return []
        ranges = [
            ("0", 0, 0, "s0"),
            ("1", 1, 1, "s1"),
            ("2", 2, 2, "s2"),
            ("3", 3, 3, "s3"),
            ("4", 4, 4, "s4"),
            ("5", 5, 5, "s5"),
            ("6", 6, 6, "s6"),
            ("7+", 7, None, "s7"),
        ]
        items = []
        for label, min_goals, max_goals, key in ranges:
            odds_value = ttg_data.get(key)
            if odds_value:
                items.append(
                    {
                        "goal_range": label,
                        "min_goals": min_goals,
                        "max_goals": max_goals,
                        "odds": parse_decimal(odds_value),
                    }
                )
        return items

    def build_hafu(self, match_data: Dict) -> List[Dict]:
        hafu_data = match_data.get("hafu", {})
        if not hafu_data:
            return []
        mapping = {
            "hh": ("win", "win", "胜胜"),
            "hd": ("win", "draw", "胜平"),
            "ha": ("win", "lose", "胜负"),
            "dh": ("draw", "win", "平胜"),
            "dd": ("draw", "draw", "平平"),
            "da": ("draw", "lose", "平负"),
            "ah": ("lose", "win", "负胜"),
            "ad": ("lose", "draw", "负平"),
            "aa": ("lose", "lose", "负负"),
        }
        items = []
        for key, (half, full, label) in mapping.items():
            odds_value = hafu_data.get(key)
            if odds_value:
                items.append(
                    {
                        "half_result": half,
                        "full_result": full,
                        "result_label": label,
                        "odds": parse_decimal(odds_value),
                    }
                )
        return items

    def close(self) -> None:
        self.client.close()
