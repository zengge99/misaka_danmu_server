import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from urllib.parse import urlencode
import aiomysql
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import crud, models, security
from ..config import settings
from ..database import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bangumi", tags=["Bangumi"])

# --- Pydantic Models for Bangumi API ---

class BangumiTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: int

class BangumiUser(BaseModel):
    id: int
    username: str
    nickname: str
    avatar: Dict[str, str]

class BangumiSearchSubject(BaseModel):
    id: int
    name: str
    name_cn: str

    @property
    def display_name(self) -> str:
        return self.name_cn or self.name

class BangumiSearchResponse(BaseModel):
    data: Optional[List[BangumiSearchSubject]] = None

class BangumiAuthState(BaseModel):
    is_authenticated: bool
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None

class DirectTokenRequest(BaseModel):
    access_token: str

# --- Helper Function ---

async def get_bangumi_client(
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
) -> httpx.AsyncClient:
    """依赖项：创建一个带有 Bangumi 授权的 httpx 客户端。"""
    auth_info = await crud.get_bangumi_auth(pool, current_user.id)
    if not auth_info or not auth_info.get("access_token"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bangumi not authenticated")

    # 检查 token 是否过期
    expires_at = auth_info.get("expires_at")
    if expires_at and datetime.now() >= expires_at:
        # 尝试刷新 token
        try:
            async with httpx.AsyncClient() as client:
                token_data = {
                    "grant_type": "refresh_token",
                    "client_id": settings.bangumi.client_id,
                    "client_secret": settings.bangumi.client_secret,
                    "refresh_token": auth_info["refresh_token"],
                }
                response = await client.post("https://bgm.tv/oauth/access_token", data=token_data)
                response.raise_for_status()
                new_token_info = BangumiTokenResponse.model_validate(response.json())

                auth_info["access_token"] = new_token_info.access_token
                auth_info["refresh_token"] = new_token_info.refresh_token
                auth_info["expires_at"] = datetime.now() + timedelta(seconds=new_token_info.expires_in)
                await crud.save_bangumi_auth(pool, current_user.id, auth_info)
                logger.info(f"用户 '{current_user.username}' 的 Bangumi token 已成功刷新。")
        except Exception as e:
            logger.error(f"刷新 Bangumi token 失败: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bangumi token expired and refresh failed")

    headers = {
        "Authorization": f"Bearer {auth_info['access_token']}",
        "User-Agent": "l429609201/danmu_api_server(https://github.com/l429609201/danmu_api_server)",
    }
    return httpx.AsyncClient(headers=headers, timeout=20.0)

# --- API Endpoints ---

@router.get("/auth/url", response_model=Dict[str, str], summary="获取 Bangumi OAuth 授权链接")
async def get_bangumi_auth_url(
    request: Request,
    current_user: models.User = Depends(security.get_current_user)
):
    """生成用于 Bangumi OAuth 流程的重定向 URL。"""
    # 构建回调 URL，它将指向我们的 /auth/callback 端点
    redirect_uri = request.url_for('bangumi_auth_callback')
    params = {
        "client_id": settings.bangumi.client_id,
        "response_type": "code",
        "redirect_uri": str(redirect_uri),
    }
    query_string = urlencode(params)
    auth_url = f"https://bgm.tv/oauth/authorize?{query_string}"
    return {"url": auth_url}

@router.get("/auth/callback", response_class=HTMLResponse, summary="Bangumi OAuth 回调", name="bangumi_auth_callback")
async def bangumi_auth_callback(
    code: str = Query(...),
    pool: aiomysql.Pool = Depends(get_db_pool),
    request: Request = None
):
    """处理来自 Bangumi 的 OAuth 回调，用 code 交换 token。"""
    # 在回调中，我们不知道是哪个用户发起的，所以不能用 Depends(get_current_user)
    # 但我们可以从会话中获取当前登录的用户
    try:
        token = request.cookies.get("danmu_api_token")
        user = await security.get_current_user(token, pool)
    except HTTPException:
        return HTMLResponse("<h1>认证失败：无法识别用户会话，请重新登录后再试。</h1>", status_code=401)

    token_data = {
        "grant_type": "authorization_code",
        "client_id": settings.bangumi.client_id,
        "client_secret": settings.bangumi.client_secret,
        "code": code,
        "redirect_uri": str(request.url_for('bangumi_auth_callback')),
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("https://bgm.tv/oauth/access_token", data=token_data)
            response.raise_for_status()
            token_info = BangumiTokenResponse.model_validate(response.json())

            # 获取用户信息
            user_resp = await client.get("https://api.bgm.tv/v0/me", headers={"Authorization": f"Bearer {token_info.access_token}"})
            user_resp.raise_for_status()
            bgm_user = BangumiUser.model_validate(user_resp.json())

            # 保存授权信息
            auth_to_save = {
                "bangumi_user_id": bgm_user.id,
                "nickname": bgm_user.nickname,
                "avatar_url": bgm_user.avatar.get("large"),
                "access_token": token_info.access_token,
                "refresh_token": token_info.refresh_token,
                "expires_at": datetime.now() + timedelta(seconds=token_info.expires_in)
            }
            await crud.save_bangumi_auth(pool, user.id, auth_to_save)

        # 返回一个HTML页面，该页面将关闭自身并通知父窗口
        return HTMLResponse("<script>window.opener.postMessage('BANGUMI-OAUTH-COMPLETE', '*'); window.close();</script>")
    except Exception as e:
        logger.error(f"Bangumi OAuth 回调处理失败: {e}", exc_info=True)
        return HTMLResponse(f"<h1>认证失败: {e}</h1>", status_code=500)

@router.get("/auth/state", response_model=BangumiAuthState, summary="获取 Bangumi 授权状态")
async def get_bangumi_auth_state(
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    auth_info = await crud.get_bangumi_auth(pool, current_user.id)
    if not auth_info:
        return BangumiAuthState(is_authenticated=False)
    return BangumiAuthState(
        is_authenticated=True,
        nickname=auth_info.get("nickname"),
        avatar_url=auth_info.get("avatar_url")
    )

@router.post("/auth/token", status_code=status.HTTP_204_NO_CONTENT, summary="直接设置 Access Token")
async def set_direct_access_token(
    data: DirectTokenRequest,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    # 这种方式无法获取 refresh token 和过期时间，所以这些字段为 null
    auth_to_save = {"access_token": data.access_token, "refresh_token": None, "expires_at": None}
    await crud.save_bangumi_auth(pool, current_user.id, auth_to_save)

@router.delete("/auth", status_code=status.HTTP_204_NO_CONTENT, summary="注销 Bangumi 授权")
async def deauthorize_bangumi(
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    await crud.delete_bangumi_auth(pool, current_user.id)

@router.get("/search", response_model=List[Dict[str, Any]], summary="搜索 Bangumi 作品")
async def search_bangumi_subjects(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_bangumi_client)
):
    async with client:
        response = await client.get(f"https://api.bgm.tv/v0/search/subjects?keyword={keyword}", params={"type": 2}) # type=2 for anime
        response.raise_for_status()
        search_result = BangumiSearchResponse.model_validate(response.json())
        if not search_result.data:
            return []
        return [{"id": subject.id, "name": subject.display_name} for subject in search_result.data]