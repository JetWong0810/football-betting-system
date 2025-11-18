from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from database import get_db, update_sync_status

PLACEHOLDER = "%s"


def _execute(conn, sql: str, params=None):
    """执行 SQL 语句（MySQL）"""
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params or ())
        return cursor
    except Exception:
        cursor.close()
        raise


class OddsRepository:
    def upsert_match(self, match: Dict[str, Any]) -> None:
        fields = [
            "match_id",
            "match_number",
            "match_code",
            "project_type",
            "league_id",
            "league_name",
            "league_full_name",
            "match_date",
            "match_time",
            "match_timestamp",
            "home_team_id",
            "home_team_name",
            "home_team_rank",
            "away_team_id",
            "away_team_name",
            "away_team_rank",
            "is_single",
            "match_status",
            "notice",
            "odds_update_time",
        ]
        columns = ", ".join(fields)
        values = [match.get(f) for f in fields]
        placeholders = ", ".join([PLACEHOLDER] * len(fields))
        update_placeholders = ", ".join([f"{f}=VALUES({f})" for f in fields if f != "match_id"])
        sql = f"""
            INSERT INTO matches ({columns}) VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {update_placeholders}, updated_at = CURRENT_TIMESTAMP
        """
        
        with get_db() as conn:
            _execute(conn, sql, values)

    def upsert_odds_wdl(self, item: Dict[str, Any]) -> None:
        ph = PLACEHOLDER
        sql = f"""
            INSERT INTO odds_win_draw_lose (
                match_id, odds_type, handicap,
                win_odds, draw_odds, lose_odds,
                win_support, draw_support, lose_support,
                is_single, updated_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP)
            ON DUPLICATE KEY UPDATE
                handicap=VALUES(handicap),
                win_odds=VALUES(win_odds),
                draw_odds=VALUES(draw_odds),
                lose_odds=VALUES(lose_odds),
                win_support=VALUES(win_support),
                draw_support=VALUES(draw_support),
                lose_support=VALUES(lose_support),
                is_single=VALUES(is_single),
                updated_at=CURRENT_TIMESTAMP
        """
        
        values = [
            item.get("match_id"),
            item.get("odds_type"),
            item.get("handicap"),
            item.get("win_odds"),
            item.get("draw_odds"),
            item.get("lose_odds"),
            item.get("win_support"),
            item.get("draw_support"),
            item.get("lose_support"),
            item.get("is_single", 0),
        ]
        with get_db() as conn:
            _execute(conn, sql, values)

    def upsert_odds_score_bulk(self, match_id: str, rows: Iterable[Dict[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            return
        
        ph = PLACEHOLDER
        sql = f"""
            INSERT INTO odds_correct_score (
                match_id, result_type, home_score, away_score, score_label, odds, is_other, updated_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP)
            ON DUPLICATE KEY UPDATE
                odds=VALUES(odds),
                score_label=VALUES(score_label),
                updated_at=CURRENT_TIMESTAMP
        """
        
        with get_db() as conn:
            for row in rows:
                _execute(conn, sql, (
                    match_id,
                    row.get("result_type"),
                    row.get("home_score"),
                    row.get("away_score"),
                    row.get("score_label"),
                    row.get("odds"),
                    row.get("is_other", 0),
                ))

    def upsert_odds_goals_bulk(self, match_id: str, rows: Iterable[Dict[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            return
        
        ph = PLACEHOLDER
        sql = f"""
            INSERT INTO odds_total_goals (
                match_id, goal_range, min_goals, max_goals, odds, updated_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP)
            ON DUPLICATE KEY UPDATE
                min_goals=VALUES(min_goals),
                max_goals=VALUES(max_goals),
                odds=VALUES(odds),
                updated_at=CURRENT_TIMESTAMP
        """
        
        with get_db() as conn:
            for row in rows:
                _execute(conn, sql, (
                    match_id,
                    row.get("goal_range"),
                    row.get("min_goals"),
                    row.get("max_goals"),
                    row.get("odds"),
                ))

    def upsert_odds_hafu_bulk(self, match_id: str, rows: Iterable[Dict[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            return
        
        ph = PLACEHOLDER
        sql = f"""
            INSERT INTO odds_half_full_time (
                match_id, half_result, full_result, result_label, odds, updated_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP)
            ON DUPLICATE KEY UPDATE
                result_label=VALUES(result_label),
                odds=VALUES(odds),
                updated_at=CURRENT_TIMESTAMP
        """
        
        with get_db() as conn:
            for row in rows:
                _execute(conn, sql, (
                    match_id,
                    row.get("half_result"),
                    row.get("full_result"),
                    row.get("result_label"),
                    row.get("odds"),
                ))

    def finalize_sync(self, total_matches: int, total_odds: int) -> None:
        with get_db() as conn:
            update_sync_status(conn, total_matches, total_odds)

    def get_latest_issue(self) -> Optional[str]:
        with get_db() as conn:
            cur = _execute(conn, "SELECT MAX(match_number) AS max_match_number FROM matches")
            row = cur.fetchone()
            return row["max_match_number"] if row else None

    # Query helpers for API
    def list_matches(
        self,
        *,
        date: Optional[str] = None,
        league: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        offset = (page - 1) * page_size
        where = []
        params: List[Any] = []
        ph = PLACEHOLDER
        
        if date:
            where.append(f"match_date = {ph}")
            params.append(date)
        if league:
            where.append(f"league_name = {ph}")
            params.append(league)
        
        latest_issue = self.get_latest_issue()
        if not date:
            today = datetime.now().strftime("%Y-%m-%d")
            where.append(f"(match_date IS NULL OR match_date >= {ph})")
            params.append(today)
            now_ts = int(datetime.now().timestamp())
            where.append(f"(match_timestamp IS NULL OR match_timestamp >= {ph})")
            params.append(now_ts)
        
        # 默认只展示在售或未开赛的赛事
        where.append("(match_status IS NULL OR match_status NOT IN ('finished', 'cancelled'))")
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        
        base_sql = (
            "SELECT * FROM matches "
            f"{where_clause} "
            "ORDER BY match_date ASC, COALESCE(match_time, ''), match_code ASC "
            f"LIMIT {ph} OFFSET {ph}"
        )
        
        with get_db() as conn:
            cur = _execute(conn, base_sql, (*params, page_size, offset))
            rows = cur.fetchall()
            
            count_sql = f"SELECT COUNT(*) as cnt FROM matches {where_clause}"
            cur = _execute(conn, count_sql, params)
            count_row = cur.fetchone()
            total = count_row["cnt"] if count_row else 0
        
        match_ids = [row["match_id"] for row in rows]
        odds_map = self.fetch_wdl_for_matches(match_ids)
        for row in rows:
            row["wdl_odds"] = odds_map.get(row["match_id"], {})
            if latest_issue:
                row["is_latest_issue"] = 1 if row.get("match_number") == latest_issue else 0
            else:
                row["is_latest_issue"] = 0
        
        return {"items": rows, "total": total}

    def get_match(self, match_id: str) -> Optional[Dict[str, Any]]:
        latest_issue = self.get_latest_issue()
        ph = PLACEHOLDER
        
        with get_db() as conn:
            cur = _execute(conn, f"SELECT * FROM matches WHERE match_id = {ph}", (match_id,))
            row = cur.fetchone()
            if not row:
                return None
            
            data = row
            if latest_issue:
                data["is_latest_issue"] = 1 if data.get("match_number") == latest_issue else 0
            else:
                data["is_latest_issue"] = 0
            return data

    def get_wdl_odds(self, match_id: str) -> Dict[str, Dict[str, Any]]:
        ph = PLACEHOLDER
        
        with get_db() as conn:
            cur = _execute(conn, f"SELECT * FROM odds_win_draw_lose WHERE match_id = {ph}", (match_id,))
            rows = cur.fetchall()
            return {row["odds_type"]: row for row in rows}

    def fetch_wdl_for_matches(self, match_ids: List[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        if not match_ids:
            return {}
        
        placeholders = ",".join([PLACEHOLDER] * len(match_ids))
        sql = f"SELECT * FROM odds_win_draw_lose WHERE match_id IN ({placeholders})"
        
        with get_db() as conn:
            cur = _execute(conn, sql, match_ids)
            result: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for row in cur.fetchall():
                match_id = row["match_id"]
                result.setdefault(match_id, {})[row["odds_type"]] = row
            return result

    def get_scores(self, match_id: str) -> List[Dict[str, Any]]:
        ph = PLACEHOLDER
        
        with get_db() as conn:
            cur = _execute(conn,
                f"SELECT result_type, home_score, away_score, score_label, odds, is_other FROM odds_correct_score WHERE match_id = {ph}",
                (match_id,),
            )
            rows = cur.fetchall()
            return list(rows)

    def get_total_goals(self, match_id: str) -> List[Dict[str, Any]]:
        ph = PLACEHOLDER
        
        with get_db() as conn:
            cur = _execute(conn,
                f"SELECT goal_range, min_goals, max_goals, odds FROM odds_total_goals WHERE match_id = {ph}",
                (match_id,),
            )
            rows = cur.fetchall()
            return list(rows)

    def get_hafu(self, match_id: str) -> List[Dict[str, Any]]:
        ph = PLACEHOLDER
        
        with get_db() as conn:
            cur = _execute(conn,
                f"SELECT half_result, full_result, result_label, odds FROM odds_half_full_time WHERE match_id = {ph}",
                (match_id,),
            )
            rows = cur.fetchall()
            return list(rows)
