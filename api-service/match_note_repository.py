"""比赛个人分析备注(用户维度)"""
from typing import Any, Dict, List, Optional

from database import get_db

_TABLE_READY = False

NOTE_MAX_LEN = 5000


def ensure_match_notes_table() -> None:
    """幂等建表(用户显式要求服务端存储个人分析)。"""
    global _TABLE_READY
    if _TABLE_READY:
        return
    sql = """
        CREATE TABLE IF NOT EXISTS match_personal_notes (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            match_id VARCHAR(64) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_user_match (user_id, match_id),
            INDEX idx_match_id (match_id),
            INDEX idx_user_updated (user_id, updated_at),
            CONSTRAINT fk_match_notes_user
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    _TABLE_READY = True


def _row_to_note(row: Dict[str, Any]) -> Dict[str, Any]:
    updated = row.get("updated_at")
    created = row.get("created_at")
    return {
        "matchId": row["match_id"],
        "content": row.get("content") or "",
        "updatedAt": updated.isoformat(sep=" ", timespec="seconds") if updated else None,
        "createdAt": created.isoformat(sep=" ", timespec="seconds") if created else None,
    }


class MatchNoteRepository:
    def list_by_match_ids(self, user_id: int, match_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        ensure_match_notes_table()
        ids = [str(m).strip() for m in match_ids if m]
        if not ids:
            return {}
        # 去重保序
        seen = set()
        uniq = []
        for mid in ids:
            if mid in seen:
                continue
            seen.add(mid)
            uniq.append(mid)
        placeholders = ",".join(["%s"] * len(uniq))
        sql = f"""
            SELECT match_id, content, created_at, updated_at
            FROM match_personal_notes
            WHERE user_id = %s AND match_id IN ({placeholders})
        """
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id, *uniq))
                rows = cur.fetchall() or []
        return {r["match_id"]: _row_to_note(r) for r in rows}

    def get_note(self, user_id: int, match_id: str) -> Optional[Dict[str, Any]]:
        ensure_match_notes_table()
        mid = (match_id or "").strip()
        if not mid:
            return None
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT match_id, content, created_at, updated_at
                    FROM match_personal_notes
                    WHERE user_id = %s AND match_id = %s
                    """,
                    (user_id, mid),
                )
                row = cur.fetchone()
        return _row_to_note(row) if row else None

    def upsert_note(self, user_id: int, match_id: str, content: str) -> Dict[str, Any]:
        ensure_match_notes_table()
        mid = (match_id or "").strip()
        text = (content or "").strip()
        if not mid:
            raise ValueError("match_id 不能为空")
        if len(text) > NOTE_MAX_LEN:
            raise ValueError(f"分析内容不能超过 {NOTE_MAX_LEN} 字")
        if not text:
            self.delete_note(user_id, mid)
            return {"matchId": mid, "content": "", "updatedAt": None, "createdAt": None, "deleted": True}
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO match_personal_notes (user_id, match_id, content)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE content = VALUES(content), updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, mid, text),
                )
        note = self.get_note(user_id, mid)
        if note:
            note["deleted"] = False
        return note or {"matchId": mid, "content": text, "deleted": False}

    def delete_note(self, user_id: int, match_id: str) -> bool:
        ensure_match_notes_table()
        mid = (match_id or "").strip()
        if not mid:
            return False
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM match_personal_notes WHERE user_id = %s AND match_id = %s",
                    (user_id, mid),
                )
                return cur.rowcount > 0
