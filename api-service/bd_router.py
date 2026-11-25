"""北单(非竞彩)比赛列表接口。聊天复用 /api/predict/{match_id}/chat, match_id 形如 bd_{fid}。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

import bd_service
from auth import require_auth

router = APIRouter(prefix="/api/bd", tags=["beidan"])


@router.get("/matches")
def bd_matches(refresh: int = 0, user_id: int = Depends(require_auth)):
    """北单场次列表。打开列表页时刷新(10 分钟内复用缓存); 抓取失败时返回库里已有数据并带 listStatus。"""
    status = bd_service.refresh_list(force=bool(refresh))
    try:
        items = bd_service.list_matches()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"北单列表读取失败: {type(e).__name__}")
    leagues = {}
    for m in items:
        leagues[m["league"]] = leagues.get(m["league"], 0) + 1
    return {"matches": items, "leagues": [{"name": k, "count": v} for k, v in sorted(leagues.items(), key=lambda x: -x[1])],
            "listStatus": status}
