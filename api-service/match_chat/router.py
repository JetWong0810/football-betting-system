"""同赔页单场 AI 聊天接口(SSE)。"""
from __future__ import annotations

import base64
import json
import logging
import queue
import threading
import time
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


@router.get("/chat-stats/verdicts")
def verdict_stats(days: int = 14, user_id: int = Depends(require_auth)):
    """近 N 天 AI 倾向分布(让球 上盘/下盘/不确定, 大小球 大球/小球/不确定), 用于监控单边偏向。"""
    try:
        return store.verdict_stats(max(1, min(days, 180)))
    except store.ChatStoreUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


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
    return {"text": c["text"], "hash": c["hash"], "summary": c["summary"]}


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

    def produce(q: "queue.Queue", stop: threading.Event):
        t0 = time.time()
        first = None
        outcome = "ok"
        logger.info("chat start user=%s match=%s web=%s imgs=%s chars=%s", user_id, match_id, req.web, len(imgs), len(text))
        try:
            for ev in service.run_turn(user_id, match_id, text, imgs, web=req.web):
                if first is None and ev.get("type") == "delta":
                    first = time.time() - t0
                if ev.get("type") == "error":
                    outcome = "error:" + str(ev.get("text"))[:80]
                if stop.is_set():       # 客户端已断开: 关闭生成器,触发 run_turn 的 finally 保存已生成部分
                    outcome = "client_disconnected"
                    break
                q.put(ev)
        except MatchNotFound:
            q.put({"type": "error", "text": "未找到比赛"})
        except Exception as e:  # noqa: BLE001
            logger.exception("match chat failed %s", match_id)
            q.put({"type": "error", "text": f"分析失败: {type(e).__name__}"})
        finally:
            logger.info("chat end user=%s match=%s outcome=%s first_token=%ss total=%.1fs", user_id, match_id, outcome,
                        "-" if first is None else f"{first:.1f}", time.time() - t0)
            q.put(None)

    def gen():
        # 模型联网搜索/思考期间可能数十秒无输出,代理(nginx/Cloudflare)会判空闲断开,
        # 所以在独立线程里生成,主流每 10 秒补一个注释心跳。
        q: "queue.Queue" = queue.Queue()
        stop = threading.Event()
        threading.Thread(target=produce, args=(q, stop), daemon=True).start()
        try:
            while True:
                try:
                    ev = q.get(timeout=10)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                if ev is None:
                    return
                yield _sse(ev)
        finally:
            stop.set()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

