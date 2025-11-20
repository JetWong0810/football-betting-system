import base64
import binascii
import imghdr
import json
import logging
import os
import uuid
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError, Field
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from database import init_db, fetch_sync_status
from repository import OddsRepository
from user_repository import UserRepository
from auth import hash_password, verify_password, create_access_token, require_auth, get_current_user_id
from settings import WECHAT_APPID, WECHAT_SECRET, WECHAT_API_URL
import httpx

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = STATIC_DIR / "uploads"
UPLOAD_URL_PREFIX = "/static/uploads"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Football Match Odds API", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 添加全局异常处理器，改进验证错误提示
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误，提供更友好的错误信息"""
    errors = exc.errors()
    error_messages = []
    
    for error in errors:
        field = ".".join(str(loc) for loc in error.get("loc", []))
        msg = error.get("msg", "验证失败")
        error_type = error.get("type", "")
        
        # 提供更友好的错误信息
        if error_type == "missing":
            error_messages.append(f"缺少必需参数: {field}")
        elif error_type == "value_error.missing":
            error_messages.append(f"缺少必需参数: {field}")
        elif "int" in error_type and "parsing" in error_type:
            error_messages.append(f"参数 {field} 必须是整数")
        elif "value_error" in error_type:
            error_messages.append(f"参数 {field} 格式错误: {msg}")
        else:
            error_messages.append(f"{field}: {msg}")
    
    # 如果是认证相关的错误，返回 401
    if any("authorization" in str(err.get("loc", [])).lower() for err in errors):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "请先登录", "errors": error_messages}
        )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "; ".join(error_messages), "errors": error_messages}
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

repo = OddsRepository()
user_repo = UserRepository()
logger = logging.getLogger("wechat_login")
logging.basicConfig(level=logging.INFO)


def save_avatar_from_base64(data: str, file_ext: Optional[str] = None) -> str:
    """将 base64 编码的头像保存到本地，返回文件名"""
    if not data:
        raise ValueError("头像数据为空")
    try:
        decoded = base64.b64decode(data)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("头像数据格式错误") from exc

    detected_format = imghdr.what(None, decoded)
    cleaned_ext = file_ext.lstrip(".") if file_ext else None
    extension = (cleaned_ext or detected_format or "png").lower()
    if extension == "jpeg":
        extension = "jpg"
    if extension not in {"png", "jpg", "jpeg"}:
        extension = "png"

    filename = f"wechat_avatar_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex}.{extension}"
    file_path = UPLOAD_DIR / filename
    with open(file_path, "wb") as avatar_file:
        avatar_file.write(decoded)
    return filename


def build_static_url(request: Request, filename: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}{UPLOAD_URL_PREFIX}/{filename}"


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


class WechatLoginRequest(BaseModel):
    code: str  # 微信登录code
    encrypted_data: Optional[str] = Field(default=None, alias="encryptedData")  # 加密的用户信息
    iv: Optional[str] = None  # 加密算法的初始向量
    raw_data: Optional[str] = Field(default=None, alias="rawData")  # 原始数据字符串（用于签名校验）
    signature: Optional[str] = None  # 签名（用于校验）
    user_info: Optional[Dict[str, Any]] = Field(default=None, alias="userInfo")  # 用户信息（新版，从getUserProfile获取）
    provided_nickname: Optional[str] = Field(default=None, alias="providedNickname")
    avatar_base64: Optional[str] = Field(default=None, alias="avatarBase64")
    avatar_file_ext: Optional[str] = Field(default=None, alias="avatarFileExt")

    class Config:
        allow_population_by_field_name = True


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


def verify_wechat_signature(raw_data: str, session_key: str, signature: str) -> bool:
    """校验微信用户信息签名"""
    try:
        expected = sha1(f"{raw_data}{session_key}".encode("utf-8")).hexdigest()
        return expected == signature
    except Exception:
        return False


def decrypt_wechat_data(session_key: str, iv: str, encrypted_data: str) -> Optional[Dict[str, Any]]:
    """解密微信返回的加密用户数据"""
    try:
        session_key_bytes = base64.b64decode(session_key)
        iv_bytes = base64.b64decode(iv)
        encrypted_bytes = base64.b64decode(encrypted_data)

        cipher = Cipher(
            algorithms.AES(session_key_bytes),
            modes.CBC(iv_bytes),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_bytes) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        data = unpadder.update(decrypted) + unpadder.finalize()
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


async def fetch_wechat_session(code: str) -> Dict[str, Any]:
    """调用 code2Session 获取 openid 和 session_key"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{WECHAT_API_URL}/sns/jscode2session",
                params={
                    "appid": WECHAT_APPID,
                    "secret": WECHAT_SECRET,
                    "js_code": code,
                    "grant_type": "authorization_code"
                }
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="微信登录超时，请稍后重试")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="微信登录服务不可用，请检查网络后重试") from exc

    try:
        data = response.json()
    except Exception:
        raise HTTPException(status_code=502, detail="微信登录返回异常，请稍后重试")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"微信登录失败：{data.get('errmsg') or response.text}"
        )

    if data.get("errcode"):
        raise HTTPException(
            status_code=400,
            detail=f"微信登录失败：{data.get('errmsg', '未知错误')} ({data.get('errcode')})"
        )

    openid = data.get("openid")
    session_key = data.get("session_key")
    unionid = data.get("unionid")

    if not openid or not session_key:
        raise HTTPException(status_code=502, detail="微信登录返回数据缺失，请重试")

    return {"openid": openid, "session_key": session_key, "unionid": unionid}


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


@app.get("/api/auth/verify")
def verify_token(user_id: int = Depends(require_auth)):
    """验证token是否有效"""
    user = user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    return {
        "valid": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "nickname": user.get("nickname"),
            "avatar": user.get("avatar"),
            "phone": user.get("phone"),
            "email": user.get("email")
        }
    }


@app.post("/api/auth/wechat-login")
async def wechat_login(req: WechatLoginRequest, request: Request):
    """微信小程序登录"""
    try:
        if not WECHAT_APPID or not WECHAT_SECRET:
            raise HTTPException(status_code=500, detail="微信配置未设置，请联系管理员")

        if not req.code:
            raise HTTPException(status_code=400, detail="缺少登录凭证code")
        
        # 1. code 换取 openid / session_key
        session_data = await fetch_wechat_session(req.code)
        openid = session_data["openid"]
        session_key = session_data["session_key"]
        unionid = session_data.get("unionid")

        # 2. 校验签名（如果提供）
        if req.raw_data and req.signature:
            if not verify_wechat_signature(req.raw_data, session_key, req.signature):
                raise HTTPException(status_code=400, detail="用户信息校验失败，请重试")

        # 3. 解析用户资料（优先使用 getUserProfile 返回的数据，退化到解密数据）
        profile_data: Dict[str, Any] = req.user_info or {}
        decrypted_profile = None
        if req.encrypted_data and req.iv:
            decrypted_profile = decrypt_wechat_data(session_key, req.iv, req.encrypted_data)
            if not profile_data and decrypted_profile:
                profile_data = decrypted_profile
            if not unionid and decrypted_profile and decrypted_profile.get("unionId"):
                unionid = decrypted_profile.get("unionId")

        wechat_nickname = profile_data.get("nickName") if profile_data else None
        wechat_avatar = profile_data.get("avatarUrl") if profile_data else None

        manual_nickname = (req.provided_nickname or "").strip() if req.provided_nickname else None
        if manual_nickname:
            wechat_nickname = manual_nickname

        manual_avatar_url = None
        if req.avatar_base64:
            try:
                filename = save_avatar_from_base64(req.avatar_base64, req.avatar_file_ext)
                manual_avatar_url = build_static_url(request, filename)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if manual_avatar_url:
            wechat_avatar = manual_avatar_url

        # 4. 查找或创建/更新用户
        try:
            user = user_repo.get_user_by_openid(openid)

            if not user:
                user_id = user_repo.create_wechat_user(
                    openid=openid,
                    unionid=unionid,
                    wechat_nickname=wechat_nickname,
                    wechat_avatar=wechat_avatar
                )
                user = user_repo.get_user_by_id(user_id)
            else:
                if wechat_nickname or wechat_avatar:
                    user_repo.update_wechat_user_info(
                        user["id"],
                        wechat_nickname=wechat_nickname,
                        wechat_avatar=wechat_avatar
                    )
                    user = user_repo.get_user_by_id(user["id"])
                user_id = user["id"]
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("DB error during wechat login")
            raise HTTPException(status_code=500, detail=f"微信用户登录失败：{str(exc)}") from exc

        # 5. 更新最后登录时间
        user_repo.update_last_login(user_id)
        
        # 6. 生成token
        token = create_access_token({"user_id": user_id, "username": user["username"]})
        
        return {
            "message": "登录成功",
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "nickname": user.get("nickname") or user.get("wechat_nickname"),
                "avatar": user.get("avatar") or user.get("wechat_avatar"),
                "phone": user.get("phone"),
                "email": user.get("email"),
                "login_type": user.get("login_type", "wechat")
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled wechat login error")
        raise HTTPException(status_code=500, detail=f"微信登录失败：{str(exc)}")


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
    """获取用户配置（如果不存在则创建默认配置）"""
    config = user_repo.get_user_config(user_id)
    if not config:
        # 如果仍然不存在（理论上不应该发生），返回默认值
        return {
            "starting_capital": 10000.0,
            "fixed_ratio": 0.03,
            "kelly_factor": 0.5,
            "stop_loss_limit": 3,
            "target_monthly_return": 0.1,
            "theme": "light"
        }
    
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
