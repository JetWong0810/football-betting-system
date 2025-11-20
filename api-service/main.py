from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import init_db, fetch_sync_status
from repository import OddsRepository
from user_repository import UserRepository
from auth import hash_password, verify_password, create_access_token, require_auth, get_current_user_id

app = FastAPI(title="Football Match Odds API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

repo = OddsRepository()
user_repo = UserRepository()


# Pydantic models
class RegisterRequest(BaseModel):
    username: str
    password: str
    phone: Optional[str] = None
    email: Optional[str] = None
    nickname: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    avatar: Optional[str] = None


class UpdateConfigRequest(BaseModel):
    starting_capital: Optional[float] = None
    fixed_ratio: Optional[float] = None
    kelly_factor: Optional[float] = None
    stop_loss_limit: Optional[int] = None
    target_monthly_return: Optional[float] = None
    theme: Optional[str] = None


class CreateBetRequest(BaseModel):
    bet_data: Dict[str, Any]
    bet_time: str
    status: str = "saved"
    stake: float
    odds: float
    result: Optional[str] = None
    profit: Optional[float] = None


class UpdateBetRequest(BaseModel):
    bet_data: Optional[Dict[str, Any]] = None
    bet_time: Optional[str] = None
    status: Optional[str] = None
    result: Optional[str] = None
    stake: Optional[float] = None
    odds: Optional[float] = None
    profit: Optional[float] = None


def format_match(row: Dict[str, Any]) -> Dict[str, Any]:
    kickoff_iso = None
    if row.get("match_timestamp"):
        kickoff_iso = datetime.utcfromtimestamp(row["match_timestamp"]).isoformat() + "Z"
    return {
        "matchId": row.get("match_id"),
        "matchNumber": row.get("match_number"),
        "matchCode": row.get("match_code"),
        "league": row.get("league_name"),
        "leagueFull": row.get("league_full_name"),
        "kickoff": kickoff_iso,
        "matchDate": row.get("match_date"),
        "matchTime": row.get("match_time"),
        "homeTeam": {
            "id": row.get("home_team_id"),
            "name": row.get("home_team_name"),
            "rank": row.get("home_team_rank"),
        },
        "awayTeam": {
            "id": row.get("away_team_id"),
            "name": row.get("away_team_name"),
            "rank": row.get("away_team_rank"),
        },
        "isSingle": bool(row.get("is_single")),
        "isLatestIssue": bool(row.get("is_latest_issue")),
        "status": row.get("match_status"),
        "notice": row.get("notice"),
        "oddsUpdateTime": row.get("odds_update_time"),
        "wdl": row.get("wdl_odds"),
    }


@app.on_event("startup")
async def startup_event():
    """
    启动时只初始化数据库连接
    不启动定时爬虫任务（数据同步由 mysql-backup 服务器负责）
    """
    init_db()
    # 注释掉定时任务相关代码
    # start_scheduler()
    # run_sync_job()


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件（无需关闭调度器）"""
    # shutdown_scheduler()
    pass


@app.get("/api/health")
def health_check():
    return {"status": "ok", "sync": fetch_sync_status()}


@app.post("/api/sync")
def trigger_sync():
    """
    手动触发同步接口
    注意：由于本服务器无法访问外部 API，此接口已禁用
    数据同步由 mysql-backup 服务器负责
    """
    raise HTTPException(
        status_code=503,
        detail="数据同步功能已转移至其他服务器，此接口不可用"
    )


@app.get("/api/matches")
def list_matches(
    date: Optional[str] = Query(default=None, description="按比赛日期过滤，格式 YYYY-MM-DD"),
    league: Optional[str] = Query(default=None, description="按联赛过滤"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
):
    data = repo.list_matches(date=date, league=league, page=page, page_size=page_size)
    items = [format_match(row) for row in data["items"]]
    return {"items": items, "total": data["total"], "page": page, "pageSize": page_size}


@app.get("/api/matches/{match_id}")
def get_match(match_id: str):
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="未找到比赛")
    detail = format_match(match)
    detail["wdl"] = repo.get_wdl_odds(match_id)
    return detail


@app.get("/api/matches/{match_id}/plays")
def get_match_plays(match_id: str):
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="未找到比赛")
    wdl = repo.get_wdl_odds(match_id)
    plays = {
        "had": wdl.get("had"),
        "hhad": wdl.get("hhad"),
        "crs": repo.get_scores(match_id),
        "ttg": repo.get_total_goals(match_id),
        "hafu": repo.get_hafu(match_id),
    }
    return {"match": format_match(match), "plays": plays}


# ==================== 用户相关API ====================

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    """用户注册"""
    # 检查用户名是否已存在
    existing_user = user_repo.get_user_by_username(req.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 创建用户
    password_hash = hash_password(req.password)
    try:
        user_id = user_repo.create_user(
            username=req.username,
            password_hash=password_hash,
            phone=req.phone,
            email=req.email,
            nickname=req.nickname
        )
        
        # 生成token
        token = create_access_token({"user_id": user_id, "username": req.username})
        
        return {
            "message": "注册成功",
            "token": token,
            "user": {
                "id": user_id,
                "username": req.username,
                "nickname": req.nickname or req.username
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"注册失败：{str(e)}")


@app.post("/api/auth/login")
def login(req: LoginRequest):
    """用户登录"""
    user = user_repo.get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # 更新最后登录时间
    user_repo.update_last_login(user["id"])
    
    # 生成token
    token = create_access_token({"user_id": user["id"], "username": user["username"]})
    
    return {
        "message": "登录成功",
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "nickname": user.get("nickname"),
            "avatar": user.get("avatar"),
            "phone": user.get("phone"),
            "email": user.get("email")
        }
    }


@app.get("/api/user/profile")
def get_profile(user_id: int = Depends(require_auth)):
    """获取用户信息"""
    user = user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return {
        "id": user["id"],
        "username": user["username"],
        "nickname": user.get("nickname"),
        "avatar": user.get("avatar"),
        "phone": user.get("phone"),
        "email": user.get("email"),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at")
    }


@app.put("/api/user/profile")
def update_profile(req: UpdateProfileRequest, user_id: int = Depends(require_auth)):
    """更新用户资料"""
    success = user_repo.update_user_profile(
        user_id=user_id,
        nickname=req.nickname,
        phone=req.phone,
        email=req.email,
        avatar=req.avatar
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="更新失败")
    
    return {"message": "更新成功"}


@app.get("/api/user/config")
def get_user_config(user_id: int = Depends(require_auth)):
    """获取用户配置"""
    config = user_repo.get_user_config(user_id)
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    return {
        "starting_capital": float(config.get("starting_capital", 10000)),
        "fixed_ratio": float(config.get("fixed_ratio", 0.03)),
        "kelly_factor": float(config.get("kelly_factor", 0.5)),
        "stop_loss_limit": int(config.get("stop_loss_limit", 3)),
        "target_monthly_return": float(config.get("target_monthly_return", 0.1)),
        "theme": config.get("theme", "light")
    }


@app.put("/api/user/config")
def update_user_config(req: UpdateConfigRequest, user_id: int = Depends(require_auth)):
    """更新用户配置"""
    config_data = req.model_dump(exclude_none=True)
    success = user_repo.update_user_config(user_id, config_data)
    
    if not success:
        raise HTTPException(status_code=400, detail="更新失败")
    
    return {"message": "配置已更新"}


# ==================== 投注记录相关API ====================

@app.post("/api/bets")
def create_bet(req: CreateBetRequest, user_id: int = Depends(require_auth)):
    """创建投注记录"""
    try:
        bet_id = user_repo.create_bet(
            user_id=user_id,
            bet_data=req.bet_data,
            bet_time=req.bet_time,
            status=req.status,
            stake=req.stake,
            odds=req.odds,
            result=req.result,
            profit=req.profit
        )
        return {"message": "创建成功", "id": bet_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败：{str(e)}")


@app.get("/api/bets")
def list_bets(
    status: Optional[str] = Query(default=None, description="按状态过滤：saved/betting/settled"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    user_id: int = Depends(require_auth)
):
    """获取投注记录列表"""
    data = user_repo.list_bets(user_id=user_id, status=status, page=page, page_size=page_size)
    return {
        "items": data["items"],
        "total": data["total"],
        "page": data["page"],
        "pageSize": data["page_size"]
    }


@app.get("/api/bets/{bet_id}")
def get_bet(bet_id: int, user_id: int = Depends(require_auth)):
    """获取单条投注记录"""
    bet = user_repo.get_bet(bet_id, user_id)
    if not bet:
        raise HTTPException(status_code=404, detail="投注记录不存在")
    return bet


@app.put("/api/bets/{bet_id}")
def update_bet(bet_id: int, req: UpdateBetRequest, user_id: int = Depends(require_auth)):
    """更新投注记录"""
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    
    success = user_repo.update_bet(bet_id, user_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="投注记录不存在或更新失败")
    
    return {"message": "更新成功"}


@app.delete("/api/bets/{bet_id}")
def delete_bet(bet_id: int, user_id: int = Depends(require_auth)):
    """删除投注记录"""
    success = user_repo.delete_bet(bet_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="投注记录不存在")
    return {"message": "删除成功"}
