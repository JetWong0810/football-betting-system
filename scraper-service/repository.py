from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional
import json

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
        # is_single 只升不降：单关是历史事实，在售时同步为1，停售后API返回0时不回退
        # match_status 不降级：已有比分或已 finished/cancelled 时，不被体彩 Selling 写回 not_started
        def _update_expr(f: str) -> str:
            if f == "is_single":
                return "is_single=IF(VALUES(is_single)=1,1,is_single)"
            if f == "match_status":
                return (
                    "match_status=IF("
                    "home_score IS NOT NULL, 'finished', "
                    "IF(match_status IN ('finished','cancelled') "
                    "AND VALUES(match_status)='not_started', match_status, VALUES(match_status))"
                    ")"
                )
            return f"{f}=VALUES({f})"

        update_placeholders = ", ".join(
            _update_expr(f) for f in fields if f != "match_id"
        )
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
                is_single=IF(VALUES(is_single)=1,1,is_single),
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

    def append_odds_history(self, item: Dict[str, Any]) -> None:
        """记录竞彩赔率变动到 jczq_odds_history。

        与同场同类型最后一条对比；有变动(任一差值>0.005)或首条则 append。
        direction_*=新-旧的符号(-1/0/+1)。earliest=初盘, latest=终盘。
        odds_type 映射 had->spf / hhad->nspf 与历史导入口径一致。
        """
        match_id = item.get("match_id")
        # had/hhad(竞彩) -> spf/nspf(jczq_odds_history 约定)
        _TYPE_MAP = {"had": "spf", "hhad": "nspf"}
        odds_type = _TYPE_MAP.get(item.get("odds_type"))
        if not match_id or not odds_type:
            return
        try:
            win = float(item.get("win_odds") or 0)
            draw = float(item.get("draw_odds") or 0)
            lose = float(item.get("lose_odds") or 0)
        except (TypeError, ValueError):
            return
        if win <= 0 and draw <= 0 and lose <= 0:
            return

        now = datetime.utcnow().replace(microsecond=0)
        with get_db() as conn:
            cur = _execute(
                conn,
                """SELECT odds_win, odds_draw, odds_loss FROM jczq_odds_history
                   WHERE match_id=%s AND odds_type=%s
                   ORDER BY change_time DESC LIMIT 1""",
                (match_id, odds_type),
            )
            prev = cur.fetchone()
            if prev:
                pw, pd, pl = float(prev["odds_win"]), float(prev["odds_draw"]), float(prev["odds_loss"])
                # 赔率无变化则跳过(避免每10分钟写一条无意义记录)
                if abs(win - pw) < 0.005 and abs(draw - pd) < 0.005 and abs(lose - pl) < 0.005:
                    return
                dw = 0 if abs(win - pw) < 0.005 else (1 if win > pw else -1)
                dd = 0 if abs(draw - pd) < 0.005 else (1 if draw > pd else -1)
                dl = 0 if abs(lose - pl) < 0.005 else (1 if lose > pl else -1)
            else:
                dw = dd = dl = 0
            _execute(
                conn,
                """INSERT IGNORE INTO jczq_odds_history
                   (match_id, odds_type, odds_win, odds_draw, odds_loss,
                    direction_win, direction_draw, direction_loss, change_time)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (match_id, odds_type, win, draw, lose, dw, dd, dl, now),
            )

    def upsert_odds_score_bulk(self, match_id: str, rows: Iterable[Dict[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            return
        
        def normalize_score(row: Dict[str, Any], key: str) -> Optional[int]:
            """空比分用 -1 保存，避免 NULL 使唯一索引失效"""
            value = row.get(key)
            if value is None:
                return -1
            try:
                return int(value)
            except (TypeError, ValueError):
                return -1

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
                    normalize_score(row, "home_score"),
                    normalize_score(row, "away_score"),
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

    def get_finished_without_score(
        self,
        days: Optional[int] = None,
        *,
        prefer_after_seconds: int = 2 * 3600,
    ) -> List[Dict[str, Any]]:
        """查询已开赛但缺比分的比赛。

        开赛满 prefer_after_seconds(默认2h)的优先回填——此时大概率已完赛可出分；
        不满2h的仍尝试(早结束/腰斩)，但不盲标 finished。
        """
        now_ts = int(datetime.now().timestamp())
        prefer_before = now_ts - prefer_after_seconds
        ph = PLACEHOLDER
        sql = (
            "SELECT match_id, match_code, match_number, match_date, match_timestamp, "
            "home_team_name, away_team_name FROM matches "
            f"WHERE match_timestamp IS NOT NULL AND match_timestamp < {ph} "
            "AND home_score IS NULL "
            "AND (match_status IS NULL OR match_status != 'cancelled')"
        )
        params: List[Any] = [now_ts]
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            sql += f" AND match_date >= {ph}"
            params.append(cutoff)
        # 开赛≥2h 优先，同档按开赛时间升序(先踢完的先抓)
        sql += (
            f" ORDER BY CASE WHEN match_timestamp <= {ph} THEN 0 ELSE 1 END, "
            "match_timestamp ASC"
        )
        params.append(prefer_before)
        with get_db() as conn:
            cur = _execute(conn, sql, params)
            return list(cur.fetchall())

    def update_match_score(self, match_id: str, home_score: int, away_score: int) -> None:
        """回填比赛最终比分并标记完赛"""
        ph = PLACEHOLDER
        sql = (
            "UPDATE matches SET home_score=%s, away_score=%s, match_status='finished', "
            "updated_at=CURRENT_TIMESTAMP WHERE match_id=%s"
        )
        with get_db() as conn:
            _execute(conn, sql, (home_score, away_score, match_id))

    def get_match_timestamp(self, match_id: str) -> Optional[int]:
        """取开赛 unix 秒, 供终盘 change_time 对齐 kickoff。"""
        if not match_id:
            return None
        with get_db() as conn:
            cur = _execute(
                conn,
                "SELECT match_timestamp FROM matches WHERE match_id=%s",
                (match_id,),
            )
            row = cur.fetchone()
        if not row or row.get("match_timestamp") is None:
            return None
        try:
            return int(row["match_timestamp"])
        except (TypeError, ValueError):
            return None

    def apply_closing_spf(
        self,
        match_id: str,
        win: float,
        draw: float,
        lose: float,
        change_time: Optional[datetime] = None,
    ) -> bool:
        """用体彩赛果终赔校正 spf 终盘。

        在售池抓取常在封盘前停更, history 最后一条≠真终盘。
        与最后一条差异>0.005 则 append; 同步更新 odds_win_draw_lose.had。
        返回是否写入 history。
        """
        if not match_id:
            return False
        try:
            win_f, draw_f, lose_f = float(win), float(draw), float(lose)
        except (TypeError, ValueError):
            return False
        if win_f <= 0 or draw_f <= 0 or lose_f <= 0:
            return False

        with get_db() as conn:
            cur = _execute(
                conn,
                """SELECT odds_win, odds_draw, odds_loss, change_time FROM jczq_odds_history
                   WHERE match_id=%s AND odds_type='spf'
                   ORDER BY change_time DESC LIMIT 1""",
                (match_id,),
            )
            prev = cur.fetchone()
            if prev:
                pw, pd, pl = float(prev["odds_win"]), float(prev["odds_draw"]), float(prev["odds_loss"])
                if abs(win_f - pw) < 0.005 and abs(draw_f - pd) < 0.005 and abs(lose_f - pl) < 0.005:
                    # history 已是终盘, 仍校正当前表(可能停在中间值)
                    _execute(
                        conn,
                        """UPDATE odds_win_draw_lose
                           SET win_odds=%s, draw_odds=%s, lose_odds=%s, updated_at=CURRENT_TIMESTAMP
                           WHERE match_id=%s AND odds_type='had'
                             AND (ABS(win_odds-%s)>=0.005 OR ABS(draw_odds-%s)>=0.005
                                  OR ABS(lose_odds-%s)>=0.005)""",
                        (win_f, draw_f, lose_f, match_id, win_f, draw_f, lose_f),
                    )
                    return False
                dw = 0 if abs(win_f - pw) < 0.005 else (1 if win_f > pw else -1)
                dd = 0 if abs(draw_f - pd) < 0.005 else (1 if draw_f > pd else -1)
                dl = 0 if abs(lose_f - pl) < 0.005 else (1 if lose_f > pl else -1)
                prev_ct = prev["change_time"]
            else:
                dw = dd = dl = 0
                prev_ct = None

            ct = change_time or datetime.utcnow().replace(microsecond=0)
            if prev_ct is not None and ct <= prev_ct:
                ct = prev_ct + timedelta(seconds=1)

            _execute(
                conn,
                """INSERT IGNORE INTO jczq_odds_history
                   (match_id, odds_type, odds_win, odds_draw, odds_loss,
                    direction_win, direction_draw, direction_loss, change_time)
                   VALUES (%s,'spf',%s,%s,%s,%s,%s,%s,%s)""",
                (match_id, win_f, draw_f, lose_f, dw, dd, dl, ct),
            )
            # 当前赔率表也落到终盘
            _execute(
                conn,
                """UPDATE odds_win_draw_lose
                   SET win_odds=%s, draw_odds=%s, lose_odds=%s, updated_at=CURRENT_TIMESTAMP
                   WHERE match_id=%s AND odds_type='had'""",
                (win_f, draw_f, lose_f, match_id),
            )
            return True

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
        
        # 无比分且非 finished/cancelled；有分即离开(不按时长盲踢)
        where.append("home_score IS NULL")
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

    def list_live_for_asian(self) -> List[Dict[str, Any]]:
        """在售/未出赛果体彩场(含进行中无比分, 开赛超72h脏数据排除)。"""
        sql = """
            SELECT match_id, match_code, match_number, match_date, match_timestamp,
                   fid_500, fid_zgzcw, asian_handicap, asian_home_odds, asian_away_odds
            FROM matches
            WHERE match_id NOT LIKE 'jczq%%'
              AND home_score IS NULL
              AND (match_timestamp IS NULL
                   OR match_timestamp > UNIX_TIMESTAMP(NOW() - INTERVAL 72 HOUR))
            ORDER BY match_timestamp ASC
        """
        with get_db() as conn:
            cur = _execute(conn, sql)
            return list(cur.fetchall())

    def save_fid_zgzcw(
        self,
        match_id: str,
        fid: str,
        home_rank: Optional[str] = None,
        away_rank: Optional[str] = None,
    ) -> None:
        """写入足彩网 matchid, 不碰 fid_500。排名有值才覆盖。"""
        if not match_id or not fid:
            return
        sets = ["fid_zgzcw=%s"]
        params: list = [str(fid)]
        if home_rank:
            sets.append("home_team_rank=%s")
            params.append(str(home_rank))
        if away_rank:
            sets.append("away_team_rank=%s")
            params.append(str(away_rank))
        sets.append("updated_at=CURRENT_TIMESTAMP")
        params.append(match_id)
        with get_db() as conn:
            _execute(conn, f"UPDATE matches SET {', '.join(sets)} WHERE match_id=%s", tuple(params))

    def upsert_asian_bet365(
        self,
        match_id: str,
        fid: Optional[str] = None,
        *,
        raw_close_hc: float,
        raw_open_hc: Optional[float],
        close_home: Optional[float],
        close_away: Optional[float],
        open_home: Optional[float],
        open_away: Optional[float],
        fid_zgzcw: Optional[str] = None,
        overwrite_open: bool = False,
    ) -> None:
        """写入 matches 亚盘快照 + jczq_ah_history(Bet365)。

        raw_* 为 500.com / 足彩网原值(正=主让); history 存标准负=主让。
        终盘每次覆盖; 初盘 COALESCE 保留首抓。
        fid 只写入 fid_500; 足彩网 id 走 fid_zgzcw, 禁止混用。
        """
        open_std = -float(raw_open_hc) if raw_open_hc is not None else None
        close_std = -float(raw_close_hc)
        cols = [
            "asian_handicap=%s",
            "asian_home_odds=%s",
            "asian_away_odds=%s",
            "asian_company=%s",
        ]
        params = [raw_close_hc, close_home, close_away, "Bet365"]
        if fid:
            cols.append("fid_500=%s")
            params.append(str(fid))
        if fid_zgzcw:
            cols.append("fid_zgzcw=%s")
            params.append(str(fid_zgzcw))
        cols.append("updated_at=CURRENT_TIMESTAMP")
        params.append(match_id)
        with get_db() as conn:
            _execute(
                conn,
                f"UPDATE matches SET {', '.join(cols)} WHERE match_id=%s",
                tuple(params),
            )
            open_sql = (
                "open_handicap=VALUES(open_handicap), "
                "open_home_odds=VALUES(open_home_odds), "
                "open_away_odds=VALUES(open_away_odds), "
                if overwrite_open
                else
                "open_handicap=COALESCE(open_handicap, VALUES(open_handicap)), "
                "open_home_odds=COALESCE(open_home_odds, VALUES(open_home_odds)), "
                "open_away_odds=COALESCE(open_away_odds, VALUES(open_away_odds)), "
            )
            _execute(
                conn,
                f"""INSERT INTO jczq_ah_history
                   (match_id, open_handicap, open_home_odds, open_away_odds,
                    close_handicap, close_home_odds, close_away_odds, company)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                     {open_sql}
                     close_handicap=VALUES(close_handicap),
                     close_home_odds=VALUES(close_home_odds),
                     close_away_odds=VALUES(close_away_odds),
                     company=VALUES(company)""",
                (
                    match_id,
                    open_std, open_home, open_away,
                    close_std, close_home, close_away,
                    "Bet365",
                ),
            )

    def list_fenxi_meta(self, match_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not match_ids:
            return {}
        ph = ",".join(["%s"] * len(match_ids))
        sql = (
            f"SELECT match_id, asian_fetched_at, euro_fetched_at, form_fetched_at "
            f"FROM jczq_fenxi_cache WHERE match_id IN ({ph})"
        )
        with get_db() as conn:
            cur = _execute(conn, sql, tuple(match_ids))
            return {r["match_id"]: r for r in cur.fetchall()}

    def upsert_fenxi_cache(
        self,
        match_id: str,
        *,
        asian=None,
        euro=None,
        form=None,
    ) -> None:
        if not match_id or (asian is None and euro is None and form is None):
            return
        with get_db() as conn:
            _execute(conn, "INSERT IGNORE INTO jczq_fenxi_cache (match_id) VALUES (%s)", (match_id,))
            sets: List[str] = []
            params: list = []
            if asian is not None:
                sets.append("asian_json=%s")
                sets.append("asian_fetched_at=NOW()")
                params.append(json.dumps(asian, ensure_ascii=False))
            if euro is not None:
                sets.append("euro_json=%s")
                sets.append("euro_fetched_at=NOW()")
                params.append(json.dumps(euro, ensure_ascii=False))
            if form is not None:
                sets.append("form_json=%s")
                sets.append("form_fetched_at=NOW()")
                params.append(json.dumps(form, ensure_ascii=False))
            params.append(match_id)
            _execute(
                conn,
                f"UPDATE jczq_fenxi_cache SET {', '.join(sets)} WHERE match_id=%s",
                tuple(params),
            )
