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
from odds500_service import get_fid_for_match, fetch_all_indices, fetch_euro_history, fetch_asian_history, fetch_ou_history, fetch_match_data
from predict_service import predict_match
from auth import hash_password, verify_password, create_access_token, require_auth, get_current_user_id
from settings import WECHAT_APPID, WECHAT_SECRET, WECHAT_API_URL
import httpx

# 先初始化 logger
logger = logging.getLogger("football_betting_api")
logging.basicConfig(level=logging.INFO)

# OCR相关模块
try:
    from ocr_service import recognize_image, get_ocr_instance
    from bet_parser import parse_bet_image_result
    OCR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"OCR模块导入失败，OCR功能将不可用: {e}")
    OCR_AVAILABLE = False

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


class WechatSilentLoginRequest(BaseModel):
    code: str  # 微信登录code


class BindPhoneRequest(BaseModel):
    phone: str
    code: Optional[str] = None  # 短信验证码（预留）


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
    risk_tolerance: Optional[str] = None


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


class OcrParseImageRequest(BaseModel):
    image_base64: str = Field(..., description="base64编码的图片")


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
        "homeScore": row.get("home_score"),
        "awayScore": row.get("away_score"),
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

    # 后台线程预热 OCR 模型，避免首次请求阻塞
    if OCR_AVAILABLE:
        import threading
        threading.Thread(target=get_ocr_instance, daemon=True).start()


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


@app.get("/api/matches/{match_id}/indices")
def get_match_indices(match_id: str):
    """获取比赛指数数据(欧赔/亚盘/大小球) - 实时从500.com抓取"""
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="未找到比赛")

    match_code = match.get("match_code")
    if not match_code:
        raise HTTPException(status_code=400, detail="比赛缺少编号信息")

    # 售卖日期从期号解析 (260604201 -> 2026-06-04)
    from repository import derive_sale_date
    sale_date = derive_sale_date(match) or match.get("match_date")
    if not sale_date:
        raise HTTPException(status_code=400, detail="比赛缺少日期信息")

    fid = get_fid_for_match(sale_date, match_code)
    if not fid:
        raise HTTPException(status_code=404, detail="未找到500.com对应比赛")

    indices = fetch_all_indices(fid)
    return {
        "match": format_match(match),
        "fid": fid,
        "indices": indices,
    }


@app.get("/api/matches/{match_id}/data")
def get_match_data(match_id: str):
    """获取比赛基本面数据(交锋历史/近期战绩/未来赛程)"""
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="未找到比赛")

    match_code = match.get("match_code")
    if not match_code:
        raise HTTPException(status_code=400, detail="比赛缺少编号信息")

    from repository import derive_sale_date
    sale_date = derive_sale_date(match) or match.get("match_date")
    if not sale_date:
        raise HTTPException(status_code=400, detail="比赛缺少日期信息")

    fid = get_fid_for_match(sale_date, match_code)
    if not fid:
        raise HTTPException(status_code=404, detail="未找到500.com对应比赛")

    data = fetch_match_data(fid)
    return {"match": format_match(match), "data": data}


@app.get("/api/odds/history")
def get_odds_history(fid: str, cid: int, type: str = "european"):
    """获取某公司赔率变动历史"""
    if type == "european":
        data = fetch_euro_history(fid, cid)
    elif type == "asian":
        data = fetch_asian_history(fid, cid)
    elif type == "overunder":
        data = fetch_ou_history(fid, cid)
    else:
        raise HTTPException(status_code=400, detail="type 必须是 european/asian/overunder")
    return {"history": data}


# ==================== 用户相关API ====================

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    """用户注册"""
    import re
    
    # 检查用户名是否已存在
    existing_user = user_repo.get_user_by_username(req.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 手机号必填校验
    if not req.phone:
        raise HTTPException(status_code=400, detail="手机号为必填项")
    
    # 手机号格式验证
    if not re.match(r'^1[3-9]\d{9}$', req.phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    
    # 检查手机号是否已存在
    existing_phone_user = user_repo.get_user_by_phone(req.phone)
    if existing_phone_user:
        raise HTTPException(status_code=400, detail="该手机号已被注册")
    
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
    """用户登录（支持用户名或手机号）"""
    import re
    
    # 判断是否为手机号格式
    if re.match(r'^1[3-9]\d{9}$', req.username):
        # 按手机号查询
        user = user_repo.get_user_by_phone(req.username)
    else:
        # 按用户名查询
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


@app.post("/api/auth/wechat-silent-login")
async def wechat_silent_login(req: WechatSilentLoginRequest):
    """微信小程序静默登录（仅用于已注册用户的自动登录）"""
    try:
        if not WECHAT_APPID or not WECHAT_SECRET:
            raise HTTPException(status_code=500, detail="微信配置未设置，请联系管理员")

        if not req.code:
            raise HTTPException(status_code=400, detail="缺少登录凭证code")
        
        # 1. code 换取 openid
        session_data = await fetch_wechat_session(req.code)
        openid = session_data["openid"]

        # 2. 查找用户
        user = user_repo.get_user_by_openid(openid)
        
        if not user:
            # 用户不存在，返回特定错误码，前端需要跳转到注册页面
            raise HTTPException(status_code=404, detail="用户未注册，需要完成注册流程")
        
        # 3. 用户存在，更新最后登录时间
        user_repo.update_last_login(user["id"])
        
        # 4. 生成token
        token = create_access_token({"user_id": user["id"], "username": user["username"]})
        
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
        logger.exception("Unhandled wechat silent login error")
        raise HTTPException(status_code=500, detail=f"静默登录失败：{str(exc)}")


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
        
        # 判断用户是否已绑定手机号和完善资料
        phone_bound = bool(user.get("phone"))
        profile_completed = bool(user.get("nickname") or user.get("wechat_nickname"))
        
        # 提示前端下一步操作
        next_step = None
        if not phone_bound:
            next_step = "bind_phone"
        elif not profile_completed:
            next_step = "complete_profile"
        
        return {
            "message": "登录成功",
            "token": token,
            "phone_bound": phone_bound,
            "profile_completed": profile_completed,
            "next_step": next_step,
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


@app.post("/api/auth/bind-phone")
async def bind_phone(req: BindPhoneRequest, user_id: int = Depends(require_auth)):
    """手机号绑定接口（小程序）"""
    import re
    
    # 手机号格式验证
    if not re.match(r'^1[3-9]\d{9}$', req.phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    
    # 获取当前用户信息
    current_user = user_repo.get_user_by_id(user_id)
    if not current_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 检查手机号是否已被其他账号使用
    existing_user = user_repo.get_user_by_phone(req.phone)
    
    if existing_user and existing_user["id"] == user_id:
        # 已经绑定过该手机号
        return {
            "message": "该手机号已经绑定到当前账号",
            "merged": False,
            "token": create_access_token({"user_id": user_id, "username": current_user["username"]}),
            "user": {
                "id": current_user["id"],
                "username": current_user["username"],
                "phone": current_user["phone"],
                "nickname": current_user.get("nickname") or current_user.get("wechat_nickname"),
                "avatar": current_user.get("avatar") or current_user.get("wechat_avatar"),
                "phone_bound": True,
                "profile_completed": bool(current_user.get("nickname") or current_user.get("wechat_nickname"))
            }
        }
    
    if existing_user:
        # 手机号已被其他账号使用 -> 账号合并
        try:
            from database import get_db
            
            with get_db() as conn:
                with conn.cursor() as cursor:
                    # 为避免违反 openid 唯一约束，先将当前微信临时账号的 openid 置空
                    # 然后再把 openid 绑定到已有账号上，最后删除临时账号
                    if current_user["id"] != existing_user["id"] and current_user.get("openid"):
                        cursor.execute(
                            "UPDATE users SET openid = NULL WHERE id = %s",
                            (current_user["id"],),
                        )

                    # 将当前用户的 openid 和微信信息更新到已有账号
                    cursor.execute(
                        """
                        UPDATE users 
                        SET openid = %s,
                            wechat_nickname = COALESCE(wechat_nickname, %s),
                            wechat_avatar   = COALESCE(wechat_avatar, %s),
                            login_type      = 'both',
                            updated_at      = NOW()
                        WHERE id = %s
                        """,
                        (
                            current_user.get("openid"),
                            current_user.get("wechat_nickname"),
                            current_user.get("wechat_avatar"),
                            existing_user["id"],
                        ),
                    )

                    # 如果合并后 wechat_nickname / wechat_avatar 仍为空，则用当前账号的昵称 / 头像兜底
                    cursor.execute(
                        """
                        UPDATE users
                        SET wechat_nickname = COALESCE(wechat_nickname, nickname),
                            wechat_avatar   = COALESCE(wechat_avatar, avatar)
                        WHERE id = %s
                        """,
                        (existing_user["id"],),
                    )
                    
                    # 删除当前小程序临时账号（可选：也可以软删除）
                    if current_user["id"] != existing_user["id"]:
                        # 先删除关联的 user_configs
                        cursor.execute("DELETE FROM user_configs WHERE user_id = %s", (current_user["id"],))
                        # 再删除用户
                        cursor.execute("DELETE FROM users WHERE id = %s", (current_user["id"],))
            
            # 重新获取合并后的用户信息
            merged_user = user_repo.get_user_by_id(existing_user["id"])
            
            # 生成新 token
            token = create_access_token({"user_id": merged_user["id"], "username": merged_user["username"]})
            
            return {
                "message": "账号已合并，欢迎回来",
                "merged": True,
                "token": token,
                "user": {
                    "id": merged_user["id"],
                    "username": merged_user["username"],
                    "phone": merged_user["phone"],
                    "nickname": merged_user.get("nickname") or merged_user.get("wechat_nickname"),
                    "avatar": merged_user.get("avatar") or merged_user.get("wechat_avatar"),
                    "phone_bound": True,
                    "profile_completed": True
                }
            }
        except Exception as e:
            logger.exception("账号合并失败")
            raise HTTPException(status_code=500, detail=f"账号合并失败：{str(e)}")
    
    # 手机号未被使用 -> 直接绑定（典型场景：纯微信新用户首次绑定手机）
    # 这里我们认为资料尚未完善，需要后续引导到头像昵称完善页
    try:
        user_repo.update_user_profile(user_id=user_id, phone=req.phone)
        updated_user = user_repo.get_user_by_id(user_id)
        
        return {
            "message": "绑定成功",
            "merged": False,
            "token": create_access_token({"user_id": user_id, "username": updated_user["username"]}),
            "user": {
                "id": updated_user["id"],
                "username": updated_user["username"],
                "phone": updated_user["phone"],
                "nickname": updated_user.get("nickname") or updated_user.get("wechat_nickname"),
                "avatar": updated_user.get("avatar") or updated_user.get("wechat_avatar"),
                "phone_bound": True,
                # 直接绑定场景统一视为资料未完善，后续由前端跳转到头像昵称完善页
                "profile_completed": False,
            }
        }
    except Exception as e:
        logger.exception("手机号绑定失败")
        raise HTTPException(status_code=500, detail=f"绑定失败：{str(e)}")


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
        "theme": config.get("theme", "light"),
        "risk_tolerance": config.get("risk_tolerance", "balanced")
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


# ==================== OCR图片识别相关API ====================

@app.post("/api/ocr/parse-bet-image")
def parse_bet_image(req: OcrParseImageRequest, user_id: int = Depends(require_auth)):
    """OCR识别投注图片，提取投注信息
    
    接收base64编码的图片，返回解析后的投注信息
    """
    if not OCR_AVAILABLE:
        raise HTTPException(
            status_code=503, 
            detail="OCR功能暂不可用，请检查服务器配置"
        )
    
    try:
        # 调用OCR识别
        ocr_result = recognize_image(
            image_source=req.image_base64,
            source_type="base64"
        )
        
        # 解析投注信息
        result = parse_bet_image_result(ocr_result)
        
        return result
        
    except ValueError as e:
        # 图片格式错误等用户输入问题
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"OCR识别失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"识别失败：{str(e)}")


@app.get("/api/ocr/status")
def ocr_status():
    """检查OCR服务状态"""
    return {
        "available": OCR_AVAILABLE,
        "message": "OCR服务正常" if OCR_AVAILABLE else "OCR服务不可用"
    }


# ==================== 预测相关API ====================

class PredictRequest(BaseModel):
    market_heat: Optional[str] = Field(default=None, description="用户手动输入的市场热度描述")


@app.get("/api/predict/matches")
def list_predict_matches(
    status: str = Query(default="not_started", description="not_started 或 finished"),
    date: Optional[str] = Query(default=None, description="按日期过滤 YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=50),
):
    """获取预测页可选赛事列表（包含未开始和已结束）"""
    import time as _time
    offset = (page - 1) * page_size
    now_ts = int(_time.time())

    where = []
    params: List = []

    if status == "finished":
        # 已开赛的比赛（通过 match_timestamp 判断）
        where.append("match_timestamp IS NOT NULL AND match_timestamp < %s")
        params.append(now_ts)
    else:
        # 未开赛：match_timestamp 在未来
        where.append("(match_timestamp IS NULL OR match_timestamp >= %s)")
        params.append(now_ts)

    if date:
        date_prefix = date[2:].replace("-", "")
        where.append("match_number LIKE %s")
        params.append(f"{date_prefix}%")

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    order = "ORDER BY match_date DESC, match_time DESC" if status == "finished" else "ORDER BY match_date ASC, match_time ASC"

    from database import get_db
    with get_db() as conn:
        count_sql = f"SELECT COUNT(*) as cnt FROM matches {where_clause}"
        cur = conn.cursor()
        cur.execute(count_sql, params)
        total = cur.fetchone()["cnt"]

        sql = f"SELECT * FROM matches {where_clause} {order} LIMIT %s OFFSET %s"
        cur.execute(sql, (*params, page_size, offset))
        rows = cur.fetchall()

    items = []
    match_ids = [row["match_id"] for row in rows]
    odds_map = repo.fetch_wdl_for_matches(match_ids) if match_ids else {}

    for row in rows:
        item = format_match(row)
        wdl = odds_map.get(row["match_id"], {})
        item["wdl"] = wdl
        ts = row.get("match_timestamp")
        item["matchStatus"] = "finished" if (ts and ts < now_ts) else "not_started"
        # 让球信息从让球胜平负赔率中获取
        if wdl.get("hhad") and wdl["hhad"].get("handicap") is not None:
            item["handicap"] = float(wdl["hhad"]["handicap"])
        items.append(item)

    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@app.get("/api/predict/dates")
def list_predict_dates(
    status: str = Query(default="finished", description="not_started 或 finished"),
):
    """获取预测页可选日期列表——按售卖期号(match_number前6位)分组，与赛果查询一致"""
    import time as _time
    now_ts = int(_time.time())

    from database import get_db
    with get_db() as conn:
        cur = conn.cursor()
        if status == "finished":
            cur.execute(
                """SELECT LEFT(match_number, 6) as sale_prefix FROM matches
                   WHERE match_timestamp IS NOT NULL AND match_timestamp < %s
                     AND match_number IS NOT NULL AND LENGTH(match_number) >= 6
                   GROUP BY sale_prefix
                   ORDER BY sale_prefix DESC
                   LIMIT 30""",
                (now_ts,),
            )
        else:
            cur.execute(
                """SELECT LEFT(match_number, 6) as sale_prefix FROM matches
                   WHERE (match_timestamp IS NULL OR match_timestamp >= %s)
                     AND match_number IS NOT NULL AND LENGTH(match_number) >= 6
                   GROUP BY sale_prefix
                   ORDER BY sale_prefix ASC""",
                (now_ts,),
            )
        dates = []
        for r in cur.fetchall():
            prefix = r["sale_prefix"]
            sale_date = f"20{prefix[:2]}-{prefix[2:4]}-{prefix[4:6]}"
            dates.append(sale_date)

    return {"dates": dates}


@app.post("/api/predict/{match_id}")
def predict_match_direction(match_id: str, req: PredictRequest = None):
    """对指定比赛进行亚盘方向预测"""
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="未找到比赛")

    # 判断是否单关：赔率表中任意玩法有 is_single=1 即为单关
    is_single = bool(match.get("is_single"))
    if not is_single:
        from database import get_db as _get_db
        with _get_db() as _conn:
            _cur = _conn.cursor()
            _cur.execute("SELECT MAX(is_single) as s FROM odds_win_draw_lose WHERE match_id=%s", (match_id,))
            row = _cur.fetchone()
            if row and row["s"]:
                is_single = True

    # 构建比赛信息
    match_info = {
        "league": match.get("league_name"),
        "home_team": match.get("home_team_name"),
        "away_team": match.get("away_team_name"),
        "home_rank": match.get("home_team_rank"),
        "away_rank": match.get("away_team_rank"),
        "match_date": match.get("match_date"),
        "is_single": is_single,
    }

    # 获取让球盘口
    odds_data = repo.get_wdl_odds(match_id)
    if odds_data and odds_data.get("hhad"):
        handicap_val = odds_data["hhad"].get("handicap")
        if handicap_val is not None:
            match_info["handicap"] = float(handicap_val)

    # 如果用户提供了市场热度描述
    if req and req.market_heat:
        match_info["market_heat_desc"] = req.market_heat

    # 获取500.com的fid，用于拉取基本面和亚盘/欧赔数据
    match_data = None
    asian_data = None
    euro_data = None
    fid = None

    # 优先使用数据库已存储的 fid_500
    stored_fid = match.get("fid_500")
    if stored_fid:
        fid = str(stored_fid)
    else:
        match_code = match.get("match_code")
        if match_code:
            from repository import derive_sale_date
            sale_date = derive_sale_date(match) or match.get("match_date")
            if sale_date:
                fid = get_fid_for_match(sale_date, match_code)
                # 缓存 fid 到数据库，避免重复请求
                if fid:
                    try:
                        from database import get_db as _get_db2
                        with _get_db2() as _conn2:
                            _conn2.cursor().execute(
                                "UPDATE matches SET fid_500 = %s WHERE match_id = %s",
                                (fid, match_id))
                    except Exception:
                        pass

    if fid:
        try:
            match_data = fetch_match_data(fid)
            # 用500.com页面抓取的实时排名补充/覆盖DB排名
            if match_data.get("homeRank"):
                match_info["home_rank"] = match_data["homeRank"]
            if match_data.get("awayRank"):
                match_info["away_rank"] = match_data["awayRank"]
        except Exception as e:
            logger.warning(f"获取基本面数据失败: {e}")
        try:
            from odds500_service import fetch_asian_handicap, fetch_european_odds
            asian_data = fetch_asian_handicap(fid)
        except Exception as e:
            logger.warning(f"获取亚盘数据失败: {e}")
        try:
            euro_data = fetch_european_odds(fid)
        except Exception as e:
            logger.warning(f"获取欧赔数据失败: {e}")

    # 优先使用500.com亚盘的真实盘口值（比竞彩hhad的整数盘口更精确）
    # 500.com: 正值=主队让球, 负值=客队让球(受让)
    # 系统内统一: 负值=主队让球(与竞彩hhad一致)
    # 取多家主流公司即时盘口的中位数（即时盘比初盘更反映当前市场判断）
    if asian_data:
        mainstream = ["Pinnacle", "Bet365", "皇冠", "威廉希尔", "澳门", "立博"]
        curr_handicaps = []
        for c in asian_data:
            if c.get("bookmaker") in mainstream:
                h = c.get("current", {}).get("handicap")
                if h is not None:
                    curr_handicaps.append(float(h))
        if curr_handicaps:
            curr_handicaps.sort()
            mid = len(curr_handicaps) // 2
            median_hcap = curr_handicaps[mid]
            match_info["handicap"] = -median_hcap

    # 比分回填：已结束但DB无比分时，从500.com竞彩列表页抓取并落库
    import time as _t
    ts = match.get("match_timestamp")
    is_finished = ts and ts < int(_t.time())
    if is_finished and match.get("home_score") is None:
        try:
            from repository import derive_sale_date
            from odds500_service import fetch_match_score
            sale_date = derive_sale_date(match) or match.get("match_date")
            mcode = match.get("match_code")
            if sale_date and mcode:
                score = fetch_match_score(sale_date, mcode)
                if score:
                    match["home_score"], match["away_score"] = score[0], score[1]
                    from database import get_db as _get_db3
                    with _get_db3() as _conn3:
                        _conn3.cursor().execute(
                            "UPDATE matches SET home_score=%s, away_score=%s, match_status='finished' "
                            "WHERE match_id=%s", (score[0], score[1], match_id))
        except Exception as e:
            logger.warning(f"比分回填失败: {e}")

    try:
        result = predict_match(match_info, match_data=match_data, asian_data=asian_data, euro_data=euro_data)
        match_formatted = format_match(match)
        # 返回实际使用的亚盘盘口值
        if match_info.get("handicap") is not None:
            match_formatted["handicap"] = match_info["handicap"]
        return {
            "match": match_formatted,
            "factors": result["factors"],
            "prediction": result["prediction"],
        }
    except Exception as e:
        logger.error(f"预测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预测分析失败：{str(e)}")


# ========== 世界杯专属预测模块 ==========

@app.get("/api/worldcup/matches")
def worldcup_matches():
    """获取世界杯在售比赛（仅未开赛）"""
    import time as _t
    now_ts = int(_t.time())
    from database import get_db
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT m.*, o.handicap, o.win_odds, o.draw_odds, o.lose_odds, o.is_single
            FROM matches m
            LEFT JOIN odds_win_draw_lose o ON o.match_id = m.match_id AND o.odds_type = 'hhad'
            WHERE m.league_name = '世界杯'
              AND m.match_timestamp > %s
            ORDER BY m.match_timestamp ASC
        """, (now_ts,))
        rows = cur.fetchall()
    return [format_match(r) for r in rows]


@app.post("/api/worldcup/predict/{match_id}")
def worldcup_predict(match_id: str, req: PredictRequest = None):
    """世界杯比赛6因子预测"""
    from wc_predict_service import predict_wc_match

    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="未找到比赛")

    is_single = bool(match.get("is_single"))
    if not is_single:
        from database import get_db as _get_db
        with _get_db() as _conn:
            _cur = _conn.cursor()
            _cur.execute("SELECT MAX(is_single) as s FROM odds_win_draw_lose WHERE match_id=%s", (match_id,))
            row = _cur.fetchone()
            if row and row["s"]:
                is_single = True

    match_info = {
        "league": match.get("league_name"),
        "home_team": match.get("home_team_name"),
        "away_team": match.get("away_team_name"),
        "home_rank": match.get("home_team_rank"),
        "away_rank": match.get("away_team_rank"),
        "match_date": match.get("match_date"),
        "is_single": is_single,
    }

    odds_data = repo.get_wdl_odds(match_id)
    if odds_data and odds_data.get("hhad"):
        handicap_val = odds_data["hhad"].get("handicap")
        if handicap_val is not None:
            match_info["handicap"] = float(handicap_val)

    if req and req.market_heat:
        match_info["market_heat_desc"] = req.market_heat

    match_data = None
    asian_data = None
    euro_data = None
    fid = None

    stored_fid = match.get("fid_500")
    if stored_fid:
        fid = str(stored_fid)
    else:
        match_code = match.get("match_code")
        if match_code:
            from repository import derive_sale_date
            sale_date = derive_sale_date(match) or match.get("match_date")
            if sale_date:
                fid = get_fid_for_match(sale_date, match_code)
                if fid:
                    try:
                        from database import get_db as _get_db2
                        with _get_db2() as _conn2:
                            _conn2.cursor().execute(
                                "UPDATE matches SET fid_500 = %s WHERE match_id = %s",
                                (fid, match_id))
                    except Exception:
                        pass

    if fid:
        try:
            match_data = fetch_match_data(fid)
            if match_data.get("homeRank"):
                match_info["home_rank"] = match_data["homeRank"]
            if match_data.get("awayRank"):
                match_info["away_rank"] = match_data["awayRank"]
        except Exception as e:
            logger.warning(f"[worldcup] 获取基本面数据失败: {e}")
        try:
            from odds500_service import fetch_asian_handicap, fetch_european_odds
            asian_data = fetch_asian_handicap(fid)
        except Exception as e:
            logger.warning(f"[worldcup] 获取亚盘数据失败: {e}")
        try:
            euro_data = fetch_european_odds(fid)
        except Exception as e:
            logger.warning(f"[worldcup] 获取欧赔数据失败: {e}")

    if asian_data:
        mainstream = ["Pinnacle", "Bet365", "皇冠", "威廉希尔", "澳门", "立博"]
        curr_handicaps = []
        for c in asian_data:
            if c.get("bookmaker") in mainstream:
                h = c.get("current", {}).get("handicap")
                if h is not None:
                    curr_handicaps.append(float(h))
        if curr_handicaps:
            curr_handicaps.sort()
            mid = len(curr_handicaps) // 2
            match_info["handicap"] = -curr_handicaps[mid]

    try:
        result = predict_wc_match(match_info, match_data=match_data, asian_data=asian_data, euro_data=euro_data)
        match_formatted = format_match(match)
        if match_info.get("handicap") is not None:
            match_formatted["handicap"] = match_info["handicap"]

        # 保存预测记录(覆盖上次)
        prediction = result["prediction"]
        try:
            import json as _json
            from database import get_db as _get_db3
            with _get_db3() as _conn3:
                _conn3.cursor().execute("""
                    INSERT INTO prediction_history
                        (match_id, predict_type, direction, confidence, overall_reverse, handicap, factors_json, analysis)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        direction=VALUES(direction), confidence=VALUES(confidence),
                        overall_reverse=VALUES(overall_reverse), handicap=VALUES(handicap),
                        factors_json=VALUES(factors_json), analysis=VALUES(analysis),
                        predicted_at=CURRENT_TIMESTAMP
                """, (
                    match_id, "worldcup", prediction.get("direction", "neutral"),
                    prediction.get("confidence", 50),
                    1 if prediction.get("overall_reverse") else 0,
                    match_info.get("handicap"),
                    _json.dumps(result["factors"], ensure_ascii=False),
                    prediction.get("analysis", ""),
                ))
        except Exception as save_err:
            logger.warning(f"[worldcup] 保存预测记录失败: {save_err}")

        return {
            "match": match_formatted,
            "factors": result["factors"],
            "prediction": result["prediction"],
        }
    except Exception as e:
        logger.error(f"[worldcup] 预测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"世界杯预测分析失败：{str(e)}")


@app.get("/api/worldcup/prediction-history/{match_id}")
def worldcup_prediction_history(match_id: str):
    """获取某场比赛的上次预测记录"""
    from database import get_db as _get_db
    with _get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT direction, confidence, overall_reverse, handicap,
                   factors_json, analysis, predicted_at
            FROM prediction_history
            WHERE match_id = %s AND predict_type = 'worldcup'
        """, (match_id,))
        row = cur.fetchone()
    if not row:
        return None
    import json as _json
    return {
        "direction": row["direction"],
        "confidence": row["confidence"],
        "overallReverse": bool(row["overall_reverse"]),
        "handicap": float(row["handicap"]) if row["handicap"] else None,
        "factors": _json.loads(row["factors_json"]) if row["factors_json"] else [],
        "analysis": row["analysis"],
        "predictedAt": str(row["predicted_at"]),
    }


@app.get("/api/worldcup/similar-odds")
def worldcup_similar_odds(
    open_win: float = None, open_draw: float = None, open_loss: float = None,
    close_win: float = None, close_draw: float = None, close_loss: float = None,
):
    """历史同赔独立查询接口"""
    from wc_similar_odds import find_similar

    if None in (open_win, open_draw, open_loss, close_win, close_draw, close_loss):
        raise HTTPException(status_code=400, detail="请填写完整的初盘和终盘赔率")

    result = find_similar(open_win, open_draw, open_loss, close_win, close_draw, close_loss)
    return result


@app.get("/api/match-results")
def list_match_results(
    date: str = Query(..., description="日期 YYYY-MM-DD"),
):
    """赛果查询：返回指定售卖期日期已完赛比赛及预测记录"""
    import time as _time
    from database import get_db as _get_db

    # 按售卖期号日期查询（同一期的比赛统一归属同一天，即使跨日凌晨场）
    date_prefix = date[2:].replace("-", "")  # "2026-06-09" -> "260609"

    with _get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM matches
               WHERE match_number LIKE %s
                 AND match_timestamp IS NOT NULL
                 AND match_timestamp < %s
               ORDER BY match_date ASC, match_time ASC""",
            (f"{date_prefix}%", int(_time.time())),
        )
        rows = cur.fetchall()

    if not rows:
        return {"items": [], "date": date}

    # 按需回填缺比分的比赛（从500.com抓取）
    pending = [r for r in rows if r.get("home_score") is None]
    if pending:
        try:
            from odds500_service import fetch_match_score as _fetch_score
            from repository import derive_sale_date as _derive_sale
            for m in pending:
                sale_date = _derive_sale(m) or m.get("match_date")
                mcode = m.get("match_code")
                if not sale_date or not mcode:
                    continue
                score = _fetch_score(sale_date, mcode)
                if score:
                    m["home_score"], m["away_score"] = score[0], score[1]
                    with _get_db() as _conn:
                        _conn.cursor().execute(
                            "UPDATE matches SET home_score=%s, away_score=%s, match_status='finished' "
                            "WHERE match_id=%s", (score[0], score[1], m["match_id"]))
        except Exception as e:
            logger.warning(f"赛果页比分回填失败: {e}")

    match_ids = [r["match_id"] for r in rows]
    odds_map = repo.fetch_wdl_for_matches(match_ids)

    # 亚盘缓存：对DB中缺亚盘数据的已完赛比赛，从500.com抓取并落库
    need_asian = [r for r in rows if r.get("asian_handicap") is None and r.get("home_score") is not None]
    if need_asian:
        try:
            from repository import derive_sale_date as _derive_sale2
            from odds500_service import get_fid_for_match, fetch_asian_handicap
            for m in need_asian:
                sale_date = _derive_sale2(m) or m.get("match_date")
                mcode = m.get("match_code")
                if not sale_date or not mcode:
                    continue
                fid = get_fid_for_match(sale_date, mcode)
                if not fid:
                    continue
                asian_list = fetch_asian_handicap(fid)
                preferred = next((a for a in asian_list if a.get("bookmaker") == "澳门"), None) or (asian_list[0] if asian_list else None)
                if preferred and preferred.get("current"):
                    hc = preferred["current"].get("handicap")
                    home_odds = preferred["current"].get("home")
                    away_odds = preferred["current"].get("away")
                    company = preferred.get("bookmaker", "")
                    if hc is not None:
                        m["asian_handicap"] = hc
                        m["asian_home_odds"] = home_odds
                        m["asian_away_odds"] = away_odds
                        m["asian_company"] = company
                        with _get_db() as _conn2:
                            _conn2.cursor().execute(
                                "UPDATE matches SET asian_handicap=%s, asian_home_odds=%s, asian_away_odds=%s, asian_company=%s "
                                "WHERE match_id=%s",
                                (hc, home_odds, away_odds, company, m["match_id"]))
        except Exception as e:
            logger.warning(f"亚盘缓存回填失败: {e}")

    # 查预测记录
    from database import get_db as _get_db2
    pred_map = {}
    with _get_db2() as conn:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(match_ids))
        cur.execute(
            f"""SELECT match_id, predict_type, direction, confidence, overall_reverse,
                       handicap, predicted_at
                FROM prediction_history
                WHERE match_id IN ({placeholders})""",
            match_ids,
        )
        for p in cur.fetchall():
            pred_map[p["match_id"]] = p

    items = []
    for row in rows:
        mid = row["match_id"]
        item = format_match(row)
        wdl = odds_map.get(mid, {})
        item["wdl"] = wdl
        if wdl.get("hhad") and wdl["hhad"].get("handicap") is not None:
            item["handicap"] = float(wdl["hhad"]["handicap"])

        # 附带亚盘终盘数据
        if row.get("asian_handicap") is not None:
            item["asian"] = {
                "handicap": float(row["asian_handicap"]),
                "homeOdds": float(row["asian_home_odds"]) if row.get("asian_home_odds") else None,
                "awayOdds": float(row["asian_away_odds"]) if row.get("asian_away_odds") else None,
                "company": row.get("asian_company"),
            }
        else:
            item["asian"] = None

        pred = pred_map.get(mid)
        if pred:
            item["prediction"] = {
                "direction": pred["direction"],
                "confidence": pred["confidence"],
                "overallReverse": bool(pred["overall_reverse"]),
                "handicap": float(pred["handicap"]) if pred["handicap"] else None,
                "predictedAt": str(pred["predicted_at"]),
            }
        else:
            item["prediction"] = None

        items.append(item)

    return {"items": items, "date": date}


@app.get("/api/match-results/dates")
def list_result_dates():
    """返回有赛果的日期列表（降序，最近30个）——按售卖期号日期分组"""
    import time as _time
    from database import get_db as _get_db

    with _get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT LEFT(match_number, 6) as sale_prefix, COUNT(*) as cnt FROM matches
               WHERE match_timestamp IS NOT NULL AND match_timestamp < %s
                 AND match_number IS NOT NULL AND LENGTH(match_number) >= 6
               GROUP BY sale_prefix
               ORDER BY sale_prefix DESC
               LIMIT 30""",
            (int(_time.time()),),
        )
        dates = []
        for r in cur.fetchall():
            prefix = r["sale_prefix"]
            sale_date = f"20{prefix[:2]}-{prefix[2:4]}-{prefix[4:6]}"
            dates.append({"date": sale_date, "count": r["cnt"]})

    return {"dates": dates}


class NLQueryRequest(BaseModel):
    question: str
    model: str = "claude"


@app.post("/api/nl-query")
async def nl_query_endpoint(req: NLQueryRequest):
    from nl_query import generate_sql, parse_response, execute_sql
    from analysis_functions import try_analysis_function

    # 优先尝试分析函数（复杂的多步/跨库逻辑）
    af_result = try_analysis_function(req.question, req.model)
    if af_result:
        columns = list(af_result["rows"][0].keys()) if af_result["rows"] else []
        rows = []
        for r in af_result["rows"]:
            cleaned = {k: _transform_value(k, str(v)) for k, v in r.items() if v is not None}
            rows.append(cleaned)
        if rows:
            valid_cols = [c for c in columns if any(r.get(c) for r in rows)]
            columns = valid_cols
            rows = [{k: v for k, v in r.items() if k in valid_cols} for r in rows]
        rows, columns = _post_process(rows, columns)
        return {
            "success": True,
            "source": af_result.get("source", "分析"),
            "sql": af_result.get("sql", ""),
            "count": len(rows),
            "columns": columns,
            "rows": rows,
            "text": af_result.get("text"),
        }

    # 普通查询：AI 生成 SQL
    raw = generate_sql(req.question, req.model)
    if not raw:
        return {"success": False, "error": "生成SQL失败，请稍后重试"}

    db, sql = parse_response(raw)

    if not sql.strip().upper().startswith("SELECT"):
        return {"success": False, "error": "安全限制：仅支持查询操作"}

    result = execute_sql(db, sql)

    if isinstance(result, str):
        retry_q = (
            f"SQL执行报错。数据库: {db}, 错误: {result}\n"
            f"原始SQL: {sql}\n"
            f"注意: SQLite 不支持在 UNION ALL 子查询中使用 ORDER BY + LIMIT，"
            f"请改用子查询 SELECT MIN(id) 或 GROUP BY year 的方式。\n"
            f"请修正SQL。原始问题: {req.question}"
        )
        raw2 = generate_sql(retry_q, req.model)
        if raw2:
            _, sql2 = parse_response(raw2)
            if sql2.strip().upper().startswith("SELECT"):
                result = execute_sql(db, sql2)
                sql = sql2
        if isinstance(result, str):
            return {"success": False, "error": result, "sql": sql, "db": db}

    source = "世界杯" if db == "worldcup" else "竞彩"
    columns = list(result[0].keys()) if result else []
    rows = []
    for row in result:
        cleaned = {}
        for k, v in row.items():
            if v is None:
                continue
            cleaned[k] = _transform_value(k, str(v))
        rows.append(cleaned)

    # 世界杯结果：如果有比分但没盘口结果，自动补充
    if db == "worldcup" and rows and "盘口结果" not in (rows[0] if rows else {}):
        rows, columns = _enrich_handicap_result(rows, columns)

    # 去掉所有行都为空值的列
    if rows:
        valid_cols = [c for c in columns if any(r.get(c) for r in rows)]
        columns = valid_cols
        rows = [{k: v for k, v in r.items() if k in valid_cols} for r in rows]

    # 后处理：合并字段、简化展示
    rows, columns = _post_process(rows, columns)

    return {
        "success": True,
        "source": source,
        "sql": sql,
        "count": len(rows),
        "columns": columns,
        "rows": rows,
    }


# 值转换：英文队名→中文、结果代码→中文
_TEAM_CN = {
    "France": "法国", "Brazil": "巴西", "Germany": "德国", "Argentina": "阿根廷",
    "Spain": "西班牙", "Netherlands": "荷兰", "England": "英格兰", "Portugal": "葡萄牙",
    "Italy": "意大利", "Japan": "日本", "South Korea": "韩国", "Nigeria": "尼日利亚",
    "Cameroon": "喀麦隆", "Croatia": "克罗地亚", "Belgium": "比利时", "Mexico": "墨西哥",
    "Colombia": "哥伦比亚", "Uruguay": "乌拉圭", "Switzerland": "瑞士", "Australia": "澳大利亚",
    "Iran": "伊朗", "Saudi Arabia": "沙特", "Morocco": "摩洛哥", "Senegal": "塞内加尔",
    "Ghana": "加纳", "Ecuador": "厄瓜多尔", "Qatar": "卡塔尔", "Wales": "威尔士",
    "USA": "美国", "Canada": "加拿大", "Serbia": "塞尔维亚", "Denmark": "丹麦",
    "Tunisia": "突尼斯", "Poland": "波兰", "Peru": "秘鲁", "Costa Rica": "哥斯达黎加",
    "Panama": "巴拿马", "Iceland": "冰岛", "Sweden": "瑞典", "Russia": "俄罗斯",
    "South Africa": "南非", "Chile": "智利", "Algeria": "阿尔及利亚", "Honduras": "洪都拉斯",
    "Greece": "希腊", "New Zealand": "新西兰", "Slovakia": "斯洛伐克", "Paraguay": "巴拉圭",
    "Côte d'Ivoire": "科特迪瓦", "North Korea": "朝鲜", "Slovenia": "斯洛文尼亚",
    "Bosnia and Herzegovina": "波黑", "Egypt": "埃及",
}

_RESULT_CN = {"H": "主胜", "D": "平局", "A": "客胜"}

_STAGE_CN = {
    "group": "小组赛", "group_stage": "小组赛",
    "round_of_16": "16强", "quarter": "1/4决赛", "quarter_final": "1/4决赛",
    "semi": "半决赛", "semi_final": "半决赛",
    "final": "决赛", "third": "三四名", "third_place": "三四名",
}


def _transform_value(col_name: str, value: str) -> str:
    if not value:
        return value
    if value in _TEAM_CN:
        return _TEAM_CN[value]
    if value in _RESULT_CN and ("结果" in col_name or "result" in col_name.lower()):
        return _RESULT_CN[value]
    if value in _STAGE_CN:
        return _STAGE_CN[value]
    return value


def _enrich_handicap_result(rows, columns):
    """为世界杯查询结果补充盘口结果列（如果有比分信息）"""
    from nl_query import execute_sqlite

    # 检测是否有比分相关字段
    col_set = set(columns)
    has_score = ("比分" in col_set) or ("主队进球" in col_set)
    has_teams = "主队" in col_set and "客队" in col_set
    if not has_score or not has_teams:
        return rows, columns

    # 批量查出世界杯所有澳门终盘亚盘
    handicap_map = {}
    try:
        hcap_rows = execute_sqlite(
            "SELECT m.home_team, m.away_team, m.year, ah.close_handicap_value "
            "FROM wc_asian_handicap ah JOIN matches m ON ah.match_id = m.id "
            "WHERE ah.company = '澳门'"
        )
        if not isinstance(hcap_rows, str):
            for r in hcap_rows:
                key = (r["home_team"], r["away_team"], str(r["year"]))
                handicap_map[key] = r["close_handicap_value"]
    except Exception:
        return rows, columns

    if not handicap_map:
        return rows, columns

    # 反向队名映射(中文→英文)
    cn_to_en = {v: k for k, v in _TEAM_CN.items()}

    for row in rows:
        home_cn = row.get("主队", "")
        away_cn = row.get("客队", "")
        year = row.get("年份", "")
        home_en = cn_to_en.get(home_cn, home_cn)
        away_en = cn_to_en.get(away_cn, away_cn)

        handicap = handicap_map.get((home_en, away_en, str(year)))
        if handicap is None:
            row["盘口结果"] = "-"
            continue

        # 解析比分
        score_str = row.get("比分", "")
        if ":" in score_str:
            parts = score_str.split(":")
        elif "-" in score_str:
            parts = score_str.split("-")
        else:
            h = row.get("主队进球", "0")
            a = row.get("客队进球", "0")
            parts = [h, a]

        try:
            home_score = int(parts[0])
            away_score = int(parts[1])
            hcap = float(handicap)

            if hcap >= 0:
                diff = home_score - away_score - hcap
            else:
                diff = away_score - home_score - abs(hcap)

            if diff > 0:
                row["盘口结果"] = "赢盘"
            elif diff == 0:
                row["盘口结果"] = "走水"
            else:
                row["盘口结果"] = "输盘"
        except (ValueError, TypeError, IndexError):
            row["盘口结果"] = "-"

    if "盘口结果" not in columns:
        columns.append("盘口结果")

    return rows, columns


# 盘口文字 → 数值
_HANDICAP_MAP = {
    "平手": "0", "平手/半球": "+0.25", "半球": "+0.5", "半球/一球": "+0.75",
    "一球": "+1", "一球/球半": "+1.25", "球半": "+1.5", "球半/两球": "+1.75",
    "两球": "+2", "两球/两球半": "+2.25", "两球半": "+2.5", "两球半/三球": "+2.75", "三球": "+3",
    "受平手/半球": "-0.25", "受半球": "-0.5", "受半球/一球": "-0.75",
    "受一球": "-1", "受一球/球半": "-1.25", "受球半": "-1.5", "受球半/两球": "-1.75",
    "受两球": "-2", "受两球/两球半": "-2.25", "受两球半": "-2.5",
}


def _post_process(rows, columns):
    if not rows:
        return rows, columns

    new_rows = []
    merge_rules = []

    # 检测需要合并的字段
    col_set = set(columns)
    has_score_split = "主队进球" in col_set and "客队进球" in col_set
    has_initial_water = "初盘主队水位" in col_set and "初盘客队水位" in col_set
    has_close_water = "终盘主队水位" in col_set and "终盘客队水位" in col_set
    has_initial_handicap = "初盘让球" in col_set
    has_close_handicap = "终盘让球" in col_set

    for row in rows:
        new_row = dict(row)

        # 合并进球 → 比分
        if has_score_split:
            h = new_row.pop("主队进球", "")
            a = new_row.pop("客队进球", "")
            if h or a:
                new_row["比分"] = f"{h}:{a}"

        # 初盘让球文字 → 数值
        if has_initial_handicap and "初盘让球" in new_row:
            val = new_row["初盘让球"]
            new_row["初盘让球"] = _HANDICAP_MAP.get(val, val)

        # 终盘让球文字 → 数值
        if has_close_handicap and "终盘让球" in new_row:
            val = new_row["终盘让球"]
            new_row["终盘让球"] = _HANDICAP_MAP.get(val, val)

        # 合并初盘水位 → "主/客"
        if has_initial_water:
            h = new_row.pop("初盘主队水位", "")
            a = new_row.pop("初盘客队水位", "")
            if h or a:
                new_row["初盘水位"] = f"{h}/{a}"

        # 合并终盘水位 → "主/客"
        if has_close_water:
            h = new_row.pop("终盘主队水位", "")
            a = new_row.pop("终盘客队水位", "")
            if h or a:
                new_row["终盘水位"] = f"{h}/{a}"

        # 合并竞彩初盘赔率 → "主/平/客"
        has_jc_init = "竞彩初盘主胜" in col_set
        if has_jc_init:
            w = new_row.pop("竞彩初盘主胜", "")
            d = new_row.pop("竞彩初盘平", "")
            l = new_row.pop("竞彩初盘客胜", "")
            if w or d or l:
                new_row["竞彩初盘"] = f"{w}/{d}/{l}"

        # 合并竞彩终盘赔率 → "主/平/客"
        has_jc_close = "竞彩终盘主胜" in col_set
        if has_jc_close:
            w = new_row.pop("竞彩终盘主胜", "")
            d = new_row.pop("竞彩终盘平", "")
            l = new_row.pop("竞彩终盘客胜", "")
            if w or d or l:
                new_row["竞彩终盘"] = f"{w}/{d}/{l}"

        # 合并普通初盘/终盘赔率(非竞彩标记的)
        has_init_odds = "初盘主胜" in col_set and "竞彩初盘主胜" not in col_set
        if has_init_odds:
            w = new_row.pop("初盘主胜", "")
            d = new_row.pop("初盘平局", "")
            l = new_row.pop("初盘客胜", "")
            if w or d or l:
                new_row["初盘赔率"] = f"{w}/{d}/{l}"

        has_close_odds = "终盘主胜" in col_set and "竞彩终盘主胜" not in col_set
        if has_close_odds:
            w = new_row.pop("终盘主胜", "")
            d = new_row.pop("终盘平局", "")
            l = new_row.pop("终盘客胜", "")
            if w or d or l:
                new_row["终盘赔率"] = f"{w}/{d}/{l}"

        new_rows.append(new_row)

    # 重建列顺序
    merge_map = {
        "主队进球": "比分", "客队进球": "比分",
        "初盘主队水位": "初盘水位", "初盘客队水位": "初盘水位",
        "终盘主队水位": "终盘水位", "终盘客队水位": "终盘水位",
        "竞彩初盘主胜": "竞彩初盘", "竞彩初盘平": "竞彩初盘", "竞彩初盘客胜": "竞彩初盘",
        "竞彩终盘主胜": "竞彩终盘", "竞彩终盘平": "竞彩终盘", "竞彩终盘客胜": "竞彩终盘",
        "初盘主胜": "初盘赔率", "初盘平局": "初盘赔率", "初盘客胜": "初盘赔率",
        "终盘主胜": "终盘赔率", "终盘平局": "终盘赔率", "终盘客胜": "终盘赔率",
    }

    new_columns = []
    for c in columns:
        target = merge_map.get(c, c)
        if target not in new_columns:
            new_columns.append(target)

    return new_rows, new_columns


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7001)
