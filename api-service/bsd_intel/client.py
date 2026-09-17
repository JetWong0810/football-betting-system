"""BSD HTTP 客户端：Token 头、429 退避、请求计数。"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

BASE = "https://sports.bzzoiro.com"


class BsdClient:
    def __init__(self, min_interval: float = 0.08, timeout: float = 30.0):
        token = (os.getenv("BSD_API_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("缺少 BSD_API_TOKEN（api-service/.env）")
        self.min_interval = min_interval
        self._last = 0.0
        self.req_n = 0
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Token {token}",
                "Accept": "application/json",
                "User-Agent": "football-betting-system/bsd-intel",
            },
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "BsdClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _throttle(self) -> None:
        gap = time.time() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.time()

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        last_err: Optional[Exception] = None
        for attempt in range(4):
            self._throttle()
            try:
                r = self.client.get(BASE + path, params=params or None)
                self.req_n += 1
            except httpx.HTTPError as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code == 429:
                wait = 2.0
                ra = r.headers.get("Retry-After")
                if ra:
                    try:
                        wait = min(max(float(ra), 1.0), 60.0)
                    except ValueError:
                        pass
                logger.warning("BSD 429 %s retry in %.1fs", path, wait)
                time.sleep(wait)
                continue
            return r
        if last_err:
            raise last_err
        raise RuntimeError(f"BSD 429 耗尽 {path}")


def cache_key(path: str, params: Optional[Dict[str, Any]] = None) -> str:
    if not params:
        return path
    items = sorted((k, v) for k, v in params.items() if v is not None)
    return path + "?" + urlencode(items)
