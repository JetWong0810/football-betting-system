"""同赔页单场 AI 聊天接口(SSE)。"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import require_auth

from . import repository as store
from . import service
from .context import MatchNotFound, build_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/predict", tags=["match-chat"])

_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class ImageIn(BaseModel):
    media_type: str
    data: str = Field(..., description="base64,不含 data: 前缀")


class ChatIn(BaseModel):
    message: str = Field("", max_length=service.MAX_TEXT)
    images: List[ImageIn] = Field(default_factory=list)
    web: bool = True


def _sse(obj: Dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.get("/{match_id}/chat")
def get_chat(match_id: str, user_id: int = Depends(require_auth)):
    try:
        return {"messages": store.list_messages(user_id, match_id)}
    except store.ChatStoreUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/{match_id}/chat")
def clear_chat(match_id: str, user_id: int = Depends(require_auth)):
    try:
        return {"deleted": store.clear_messages(user_id, match_id)}
    except store.ChatStoreUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/{match_id}/chat/context")
def chat_context(match_id: str, user_id: int = Depends(require_auth)):
    """查看喂给模型的系统数据(调试/透明)。"""
    try:
        c = build_context(match_id)
    except MatchNotFound:
        raise HTTPException(status_code=404, detail="未找到比赛")
    return {"text": c["text"], "hash": c["hash"]}


@router.post("/{match_id}/chat")
def post_chat(match_id: str, req: ChatIn, user_id: int = Depends(require_auth)):
    text = (req.message or "").strip()
    if not text and not req.images:
        raise HTTPException(status_code=400, detail="消息不能为空")
    if len(req.images) > service.MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"最多 {service.MAX_IMAGES} 张图片")
    imgs = []
    for im in req.images:
        if im.media_type not in _ALLOWED_MEDIA:
            raise HTTPException(status_code=400, detail="不支持的图片格式")
        if len(im.data) > service.MAX_IMAGE_B64:
            raise HTTPException(status_code=413, detail="图片过大")
        try:
            base64.b64decode(im.data[:64] + "=" * (-len(im.data[:64]) % 4))
        except Exception:
            raise HTTPException(status_code=400, detail="图片编码无效")
        imgs.append({"media_type": im.media_type, "data": im.data})

    try:
        store.list_messages(user_id, match_id, limit=1)   # 表是否存在
    except store.ChatStoreUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not service.check_quota(user_id):
        raise HTTPException(status_code=429, detail="今日提问次数已达上限")

    def gen():
        try:
            for ev in service.run_turn(user_id, match_id, text, imgs, web=req.web):
                yield _sse(ev)
        except MatchNotFound:
            yield _sse({"type": "error", "text": "未找到比赛"})
        except Exception as e:  # noqa: BLE001
            logger.exception("match chat failed %s", match_id)
            yield _sse({"type": "error", "text": f"分析失败: {type(e).__name__}"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
