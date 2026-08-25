"""比赛个人分析备注(用户维度)"""
import json
from typing import Any, Dict, List, Optional

from database import get_db

_TABLE_READY = False

NOTE_MAX_LEN = 5000
STRUCTURE_MAX_LEN = 8000
# 半星步进: 0.5–5.0, 库内 TINYINT 1–10 (满星=10)
_RATING_STEPS = {i / 2 for i in range(1, 11)}
# 预测页展示的 8 项: 7 因子 + 交锋历史
_CORE_FACTOR_NAMES = (
    "近期状态",
    "实力定位",
    "市场信号",
    "市场热度",
    "竞彩赔率",
    "历史同赔",
    "单关修正",
    "交锋历史",
)


def ensure_match_notes_table() -> None:
    """幂等建表 + rating/structure 列迁移。"""
    global _TABLE_READY
    if _TABLE_READY:
        return
    sql = """
        CREATE TABLE IF NOT EXISTS match_personal_notes (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            match_id VARCHAR(64) NOT NULL,
            content TEXT NOT NULL,
            rating TINYINT UNSIGNED NULL COMMENT '半星=1,满星=10',
            structure JSON NULL COMMENT '分类点选结构',
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
            cur.execute("SHOW COLUMNS FROM match_personal_notes LIKE 'rating'")
            if not cur.fetchone():
                cur.execute(
                    """
                    ALTER TABLE match_personal_notes
                    ADD COLUMN rating TINYINT UNSIGNED NULL
                        COMMENT '半星=1,满星=10' AFTER content
                    """
                )
            cur.execute("SHOW COLUMNS FROM match_personal_notes LIKE 'structure'")
            if not cur.fetchone():
                cur.execute(
                    """
                    ALTER TABLE match_personal_notes
                    ADD COLUMN structure JSON NULL
                        COMMENT '分类点选结构' AFTER rating
                    """
                )
    _TABLE_READY = True


def rating_to_db(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        f = float(val)
    except (TypeError, ValueError) as e:
        raise ValueError("评分无效") from e
    if f == 0:
        return None
    snapped = round(f * 2) / 2
    if snapped not in _RATING_STEPS:
        raise ValueError("评分须为 0.5–5 星(半星步进)")
    return int(snapped * 2)


def rating_from_db(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    return int(raw) / 2


def structure_to_db(val: Any) -> Optional[str]:
    if val is None or val == "":
        return None
    if isinstance(val, str):
        text = val.strip()
        if not text or text == "{}":
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError("结构数据无效") from e
    elif isinstance(val, dict):
        parsed = val
    else:
        raise ValueError("结构数据无效")
    if not isinstance(parsed, dict) or not parsed:
        return None
    if not structure_has_value(parsed):
        return None
    dumped = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    if dumped in ("{}", "null"):
        return None
    if len(dumped) > STRUCTURE_MAX_LEN:
        raise ValueError("结构数据过大")
    return dumped


def structure_from_db(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def summarize_core_factors(factors: Any) -> Dict[str, Any]:
    """8 项方向计数: 7 因子 + 交锋历史。"""
    upper = lower = neutral = 0
    for f in factors or []:
        if not isinstance(f, dict):
            continue
        if f.get("name") not in _CORE_FACTOR_NAMES:
            continue
        d = f.get("direction") or "neutral"
        if d == "upper":
            upper += 1
        elif d == "lower":
            lower += 1
        else:
            neutral += 1
    factor_dir = "mixed"
    factor_align = None
    total = upper + lower + neutral
    if total > 0 and upper == total:
        factor_dir, factor_align = "upper", "all"
    elif total > 0 and lower == total:
        factor_dir, factor_align = "lower", "all"
    elif upper >= 6:
        factor_dir, factor_align = "upper", "lean"
    elif lower >= 6:
        factor_dir, factor_align = "lower", "lean"
    return {
        "factorUpper": upper,
        "factorLower": lower,
        "factorNeutral": neutral,
        "factorDir": factor_dir,
        "factorAlign": factor_align,
        "factorItems": _compact_factor_items(factors),
    }


def _compact_factor_items(factors: Any) -> list:
    by_name = {}
    for f in factors or []:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        if name not in _CORE_FACTOR_NAMES:
            continue
        direction = f.get("direction") or "neutral"
        if direction not in ("upper", "lower", "neutral"):
            direction = "neutral"
        score = f.get("score")
        try:
            score = int(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        by_name[name] = {"name": name, "direction": direction, "score": score}
    return [by_name[n] for n in _CORE_FACTOR_NAMES if n in by_name]


def structure_has_value(val: Optional[Dict[str, Any]]) -> bool:
    if not val:
        return False
    for k, v in val.items():
        if k == "extra":
            if str(v or "").strip():
                return True
            continue
        if v not in (None, "", False, [], {}):
            return True
    return False


def _row_to_note(row: Dict[str, Any]) -> Dict[str, Any]:
    updated = row.get("updated_at")
    created = row.get("created_at")
    return {
        "matchId": row["match_id"],
        "content": row.get("content") or "",
        "rating": rating_from_db(row.get("rating")),
        "structure": structure_from_db(row.get("structure")),
        "updatedAt": updated.isoformat(sep=" ", timespec="seconds") if updated else None,
        "createdAt": created.isoformat(sep=" ", timespec="seconds") if created else None,
    }


class MatchNoteRepository:
    def list_by_match_ids(self, user_id: int, match_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        ensure_match_notes_table()
        ids = [str(m).strip() for m in match_ids if m]
        if not ids:
            return {}
        seen = set()
        uniq = []
        for mid in ids:
            if mid in seen:
                continue
            seen.add(mid)
            uniq.append(mid)
        placeholders = ",".join(["%s"] * len(uniq))
        sql = f"""
            SELECT match_id, content, rating, structure, created_at, updated_at
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
                    SELECT match_id, content, rating, structure, created_at, updated_at
                    FROM match_personal_notes
                    WHERE user_id = %s AND match_id = %s
                    """,
                    (user_id, mid),
                )
                row = cur.fetchone()
        return _row_to_note(row) if row else None

    def upsert_note(
        self,
        user_id: int,
        match_id: str,
        content: str,
        rating: Any = None,
        structure: Any = None,
    ) -> Dict[str, Any]:
        ensure_match_notes_table()
        mid = (match_id or "").strip()
        text = (content or "").strip()
        rating_db = rating_to_db(rating)
        structure_db = structure_to_db(structure)
        if not mid:
            raise ValueError("match_id 不能为空")
        if len(text) > NOTE_MAX_LEN:
            raise ValueError(f"分析内容不能超过 {NOTE_MAX_LEN} 字")
        if not text and rating_db is None and not structure_db:
            self.delete_note(user_id, mid)
            return {
                "matchId": mid,
                "content": "",
                "rating": None,
                "structure": None,
                "updatedAt": None,
                "createdAt": None,
                "deleted": True,
            }
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO match_personal_notes
                        (user_id, match_id, content, rating, structure)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        content = VALUES(content),
                        rating = VALUES(rating),
                        structure = VALUES(structure),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, mid, text, rating_db, structure_db),
                )
        note = self.get_note(user_id, mid)
        if note:
            note["deleted"] = False
        return note or {
            "matchId": mid,
            "content": text,
            "rating": rating_from_db(rating_db),
            "structure": structure_from_db(structure_db),
            "deleted": False,
        }

    def merge_factor_summary(self, user_id: int, match_id: str, factors: Any) -> Optional[Dict[str, Any]]:
        """预测完成后把因子计数合并进个人分析, 不覆盖其它点选。"""
        summary = summarize_core_factors(factors)
        existing = self.get_note(user_id, match_id) or {}
        struct = dict(existing.get("structure") or {})
        struct.update(summary)
        return self.upsert_note(
            user_id,
            match_id,
            existing.get("content") or "",
            existing.get("rating"),
            struct,
        )

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
