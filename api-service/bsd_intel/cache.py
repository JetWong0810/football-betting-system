"""HTTP 响应缓存：按 TTL 命中 bsd_http_cache。"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from .client import BsdClient, cache_key
from . import db

logger = logging.getLogger(__name__)


class BsdCache:
    def __init__(self, client: BsdClient):
        self.client = client

    def get_json(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        ttl_s: int = 1800,
        force: bool = False,
    ) -> Any:
        key = cache_key(path, params)
        if not force:
            hit = self._read(key, ttl_s)
            if hit is not None:
                return hit
        r = self.client.get(path, params)
        body: Any
        try:
            body = r.json() if r.content else None
        except ValueError:
            body = {"_raw": (r.text or "")[:2000]}
        self._write(key, path, r.status_code, body)
        if r.status_code >= 400:
            logger.warning("BSD %s %s -> %s", r.status_code, key, str(body)[:180])
        return body

    def _read(self, key: str, ttl_s: int) -> Any:
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT payload_json, http_status,
                           TIMESTAMPDIFF(SECOND, fetched_at, NOW()) AS age_s
                    FROM bsd_http_cache
                    WHERE cache_key=%s
                    """,
                    (key,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        age = row.get("age_s")
        if age is None or int(age) > ttl_s:
            return None
        raw = row["payload_json"]
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def _write(self, key: str, endpoint: str, status: int, body: Any) -> None:
        payload = json.dumps(body, ensure_ascii=False, default=str)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO bsd_http_cache (cache_key, endpoint, payload_json, http_status, fetched_at)
                    VALUES (%s,%s,%s,%s,NOW())
                    ON DUPLICATE KEY UPDATE
                      payload_json=VALUES(payload_json),
                      http_status=VALUES(http_status),
                      fetched_at=VALUES(fetched_at),
                      endpoint=VALUES(endpoint)
                    """,
                    (key, endpoint[:256], payload, status),
                )
            conn.commit()
        finally:
            conn.close()
