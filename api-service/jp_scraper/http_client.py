"""HTTP 客户端：限速 + 统一 UA。"""
from __future__ import annotations

import time
from typing import Optional

import httpx

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DATA_BASE = "https://data.j-league.or.jp"
GEKI_BASE = "https://web.gekisaka.jp"


class JpHttp:
    def __init__(self, min_interval: float = 0.8, timeout: float = 30.0):
        self.min_interval = min_interval
        self._last = 0.0
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept-Language": "ja,en;q=0.8",
            },
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "JpHttp":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _throttle(self) -> None:
        gap = time.time() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.time()

    def get(self, url: str, **params) -> httpx.Response:
        self._throttle()
        if params:
            return self.client.get(url, params=params)
        return self.client.get(url)

    def get_text(self, url: str, **params) -> str:
        r = self.get(url, **params)
        r.raise_for_status()
        return r.text
