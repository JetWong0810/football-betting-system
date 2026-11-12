"""微信知社推送回调:POST /api/wx/callback(Bearer 校验,先落库后返回)。"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

from . import repository as store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wx", tags=["wx-articles"])

MAX_CONTENT = 400_000


def _check_key(authorization: Optional[str]) -> None:
    expect = (os.getenv("WX_CALLBACK_KEY") or "").strip()
    if not expect:
        raise HTTPException(status_code=503, detail="回调未配置")      # 未配置时一律拒绝,不放行
    got = ""
    if authorization and authorization.startswith("Bearer "):
        got = authorization[7:].strip()
    if not got or not hmac.compare_digest(got.encode(), expect.encode()):
        raise HTTPException(status_code=401, detail="unauthorized")


@router.post("/callback")
def wx_callback(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    _check_key(authorization)
    if not payload.get("id") or not payload.get("title"):
        raise HTTPException(status_code=400, detail="缺少 id/title")
    c = payload.get("content")
    if isinstance(c, str) and len(c) > MAX_CONTENT:
        payload["content"] = c[:MAX_CONTENT]
    try:
        is_new = store.insert_article(payload)
    except store.WxStoreUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    logger.info("wx callback %s [%s] %s new=%s", payload.get("id"), payload.get("name"),
                str(payload.get("title"))[:40], is_new)
    return {"ok": True, "duplicate": not is_new}
