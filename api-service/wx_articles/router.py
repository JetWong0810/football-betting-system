"""微信知社推送回调:POST /api/wx/callback(Bearer 校验,先落库后返回)。"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Any, Dict, Optional

from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from auth import require_auth

from . import query as q
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


# ---------------------------------------------------------------- 查询(需登录,所有登录用户可见)
class LinkIn(BaseModel):
    match_id: str


@router.get("/articles")
def articles(link: str = Query("all", pattern="^(all|linked|unlinked)$"), wxid: str = "", match_id: str = "",
             date: str = "", page: int = 1, size: int = 20, user_id: int = Depends(require_auth)):
    return q.list_articles(link, wxid, match_id, date, page, size)


@router.get("/articles/{article_id}")
def article(article_id: int, user_id: int = Depends(require_auth)):
    d = q.article_detail(article_id)
    if not d:
        raise HTTPException(status_code=404, detail="文章不存在")
    return d


@router.get("/accounts")
def accounts(user_id: int = Depends(require_auth)):
    return {"items": q.accounts()}


@router.get("/match-counts")
def match_counts(ids: str = Query("", description="逗号分隔 match_id"), user_id: int = Depends(require_auth)):
    return {"counts": q.match_counts([x for x in ids.split(",") if x][:200])}


@router.get("/articles/{article_id}/candidates")
def candidates(article_id: int, user_id: int = Depends(require_auth)):
    return {"items": q.link_candidates(article_id)}


@router.post("/articles/{article_id}/link")
def link(article_id: int, body: LinkIn, user_id: int = Depends(require_auth)):
    if not q.manual_link(article_id, body.match_id):
        raise HTTPException(status_code=404, detail="文章或比赛不存在")
    return {"ok": True}


@router.delete("/articles/{article_id}/link/{match_id}")
def unlink(article_id: int, match_id: str, user_id: int = Depends(require_auth)):
    return {"ok": q.unlink(article_id, match_id)}


@router.post("/articles/{article_id}/reprocess")
def reprocess(article_id: int, user_id: int = Depends(require_auth)):
    r = q.reprocess(article_id)
    if r == "notfound":
        raise HTTPException(status_code=404, detail="文章不存在")
    if r == "notallowed":
        raise HTTPException(status_code=400, detail="仅失败或未关联的文章可重新分析")
    if r == "limit":
        raise HTTPException(status_code=429, detail="已达重新分析次数上限")
    return {"ok": True}


@router.get("/stats")
def stats(user_id: int = Depends(require_auth)):
    return {"items": q.account_stats(), "minSample": q.MIN_SAMPLE}
