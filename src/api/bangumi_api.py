import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from urllib.parse import urlencode, quote
import aiomysql
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import crud, models, security
from ..config import settings
from ..database import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()

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
    bangumi_user_id: Optional[int] = None
    authorized_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

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
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """生成用于 Bangumi OAuth 流程的重定向 URL。"""
    # 1. 创建并存储一个唯一的、有有效期的 state
    state = await crud.create_oauth_state(pool, current_user.id)

    # 构建回调 URL，它将指向我们的 /auth/callback 端点
    redirect_uri = request.url_for('bangumi_auth_callback')
    params = {
        "client_id": settings.bangumi.client_id,
        "response_type": "code",
        "redirect_uri": str(redirect_uri),
        "state": state, # 2. 将 state 添加到授权 URL
    }
    query_string = urlencode(params)
    auth_url = f"https://bgm.tv/oauth/authorize?{query_string}"
    return {"url": auth_url}

@router.get("/auth/callback", response_class=HTMLResponse, summary="Bangumi OAuth 回调", name="bangumi_auth_callback")
async def bangumi_auth_callback(
    code: str = Query(...),
    state: str = Query(...),
    pool: aiomysql.Pool = Depends(get_db_pool),
    request: Request = None
):
    """处理来自 Bangumi 的 OAuth 回调，用 code 交换 token。"""
    # 1. 验证并消费 state，获取发起授权的用户ID
    user_id = await crud.consume_oauth_state(pool, state)
    if user_id is None:
        logger.error(f"Bangumi OAuth回调失败：无效或已过期的 state '{state}'")
        return HTMLResponse("<h1>认证失败：无效的请求状态，请重新发起授权。</h1>", status_code=400)

    # 2. 从数据库获取用户信息
    user_dict = await crud.get_user_by_id(pool, user_id)
    if not user_dict:
        logger.error(f"Bangumi OAuth回调失败：找不到与 state 关联的用户 ID '{user_id}'")
        return HTMLResponse("<h1>认证失败：找不到与此授权请求关联的用户。</h1>", status_code=404)
    user = models.User.model_validate(user_dict)

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
        avatar_url=auth_info.get("avatar_url"),
        bangumi_user_id=auth_info.get("bangumi_user_id"),
        authorized_at=auth_info.get("authorized_at"),
        expires_at=auth_info.get("expires_at")
    )

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
        # 切换到用户提供的文档中描述的旧版 API (POST /search/subject/{keyword})
        # 这需要将关键词进行 URL 编码并放入路径中
        encoded_keyword = quote(keyword)
        url = f"https://api.bgm.tv/search/subject/{encoded_keyword}"

        payload = {
            "type": 2,  # 2 for anime
            "responseGroup": "small"
        }

        # 旧版 API 使用 POST 方法
        response = await client.post(url, json=payload)

        # 旧版 API 同样可能用 404 表示未找到结果
        if response.status_code == 404:
            return []

        # 对于其他错误，抛出异常
        response.raise_for_status()

        data = response.json()

        # 旧版 API 的响应结构是 {"results": ..., "list": [...]}
        search_list = data.get("list")
        if not search_list:
            return []

        # 复用现有的 Pydantic 模型来验证和提取数据
        validated_subjects = [BangumiSearchSubject.model_validate(item) for item in search_list if isinstance(item, dict)]
        return [{"id": subject.id, "name": subject.display_name} for subject in validated_subjects]