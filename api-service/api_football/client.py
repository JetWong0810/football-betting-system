"""API-Football v3 客户端: key 来自环境变量 API_FOOTBALL_KEY, 记录剩余额度, errors 非空视为失败。"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

BASE = "https://v3.football.api-sports.io"


class AfError(RuntimeError):
    pass


class AfClient:
    def __init__(self, timeout: float = 25.0, min_interval: float = 0.25):
        key = (os.getenv("API_FOOTBALL_KEY") or "").strip()
        if not key:
            raise AfError("缺少 API_FOOTBALL_KEY(api-service/.env)")
        self._c = httpx.Client(timeout=timeout, headers={"x-apisports-key": key})
        self._lock = threading.Lock()
        self._last = 0.0
        self._gap = min_interval
        self.requests = 0
        self.day_remaining: Optional[int] = None
        self.minute_remaining: Optional[int] = None

    def close(self) -> None:
        self._c.close()

    def __enter__(self) -> "AfClient":
        return self

    def __exit__(self, *a) -> None:
        self.close()

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            wait = self._last + self._gap - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
        r = self._c.get(BASE + path, params=params or None)
        self.requests += 1
        try:
            self.day_remaining = int(r.headers.get("x-ratelimit-requests-remaining"))
            self.minute_remaining = int(r.headers.get("x-ratelimit-remaining"))
        except (TypeError, ValueError):
            pass
        if r.status_code == 429:
            raise AfError("API-Football 429 限流")
        r.raise_for_status()
        d = r.json()
        err = d.get("errors")
        if err:                                    # 空时为 [] 或 {}
            raise AfError(f"API-Football 错误 {path} {params}: {err}")
        return d
