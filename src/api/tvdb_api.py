import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from .. import crud, models, security
from ..database import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()

# --- TVDB Token Management ---
# 使用一个简单的模块级缓存来存储TVDB的JWT令牌
_tvdb_token_cache: Dict[str, Any] = {"token": None, "expires_at": datetime.utcnow()}


async def get_tvdb_token(pool, client: httpx.AsyncClient) -> str:
    """获取一个有效的TVDB令牌，如果需要则刷新。"""
    global _tvdb_token_cache
    # 如果缓存中的token有效，则直接返回
    if _tvdb_token_cache["token"] and _tvdb_token_cache["expires_at"] > datetime.utcnow():
        return _tvdb_token_cache["token"]

    logger.info("TVDB token 已过期或未找到，正在请求新的令牌。")
    api_key = await crud.get_config_value(pool, "tvdb_api_key", "")

    if not api_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TVDB API Key 未配置。")

    try:
        # TVDB V4 API 的登录端点
        response = await client.post("/login", json={"apikey": api_key})
        response.raise_for_status()
        token = response.json().get("token")
        if not token:
            raise ValueError("登录响应中未包含令牌。")

        # 令牌有效期为24小时，我们设置一个23小时的缓存
        _tvdb_token_cache["token"] = token
        _tvdb_token_cache["expires_at"] = datetime.utcnow() + timedelta(hours=23)
        logger.info("成功获取新的TVDB令牌。")
        return token
    except Exception as e:
        logger.error(f"获取TVDB令牌失败: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TVDB认证失败。")


async def get_tvdb_client(
    current_user: models.User = Depends(security.get_current_user),
    pool=Depends(get_db_pool),
) -> httpx.AsyncClient:
    """依赖项：获取一个经过认证的TVDB客户端。"""
    client = httpx.AsyncClient(base_url="https://api4.thetvdb.com/v4", timeout=20.0)
    token = await get_tvdb_token(pool, client)
    client.headers.update(
        {"Authorization": f"Bearer {token}", "User-Agent": "DanmuApiServer/1.0"}
    )
    return client


# --- Pydantic Models for TVDB ---
class TvdbSearchResult(BaseModel):
    tvdb_id: str
    name: str
    image: Optional[str] = None
    overview: Optional[str] = None
    first_aired: Optional[str] = Field(None, alias="firstAired")
    year: Optional[str] = None

class TvdbSearchResponse(BaseModel):
    data: List[TvdbSearchResult]

class TvdbAlias(BaseModel):
    language: str
    name: str

class TvdbDetailsResponse(BaseModel):
    id: str
    name: str
    aliases: Optional[List[TvdbAlias]] = None
    overview: Optional[str] = None
    image: Optional[str] = None
    first_aired: Optional[str] = Field(None, alias="firstAired")
    last_aired: Optional[str] = Field(None, alias="lastAired")
    year: Optional[str] = None
    remote_ids: Optional[List[Dict[str, str]]] = Field(None, alias="remoteIds")

class TvdbExtendedDetailsResponse(BaseModel):
    data: TvdbDetailsResponse

# --- API Endpoints ---
@router.get("/search", response_model=List[Dict[str, Any]], summary="搜索 TVDB 作品")
async def search_tvdb(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_tvdb_client),
):
    """通过关键词在 TheTVDB 上搜索电视剧。"""
    try:
        response = await client.get("/search", params={"query": keyword, "type": "series"})
        response.raise_for_status()
        results = TvdbSearchResponse.model_validate(response.json()).data

        formatted_results = []
        for item in results:
            details = f"首播: {item.first_aired}" if item.first_aired else "无首播日期"
            if item.overview:
                details += f" / {item.overview[:100]}..."

            formatted_results.append(
                {
                    "id": item.tvdb_id,
                    "title": item.name,
                    "details": details,
                    "image_url": item.image,
                }
            )
        return formatted_results
    except Exception as e:
        logger.error(f"TVDB 搜索失败: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TVDB 搜索失败。")


@router.get("/details/{tvdb_id}", response_model=Dict[str, Any], summary="获取 TVDB 作品详情(扩展)")
async def get_tvdb_details(
    tvdb_id: str = Path(...), client: httpx.AsyncClient = Depends(get_tvdb_client)
):
    """获取指定 TVDB ID 的作品详情，主要用于提取别名和IMDb ID。"""
    try:
        response = await client.get(f"/series/{tvdb_id}/extended")
        response.raise_for_status()
        details = TvdbExtendedDetailsResponse.model_validate(response.json()).data

        imdb_id = None
        if details.remote_ids:
            for remote_id in details.remote_ids:
                if remote_id.get("sourceName") == "IMDB":
                    imdb_id = remote_id.get("id")
                    break

        return {
            "id": details.id,
            "tvdb_id": details.id,
            "name_en": details.name,
            "aliases_cn": [alias.name for alias in details.aliases] if details.aliases else [],
            "name_jp": None,
            "name_romaji": None,
            "imdb_id": imdb_id,
        }
    except Exception as e:
        logger.error(f"获取 TVDB 详情失败 (ID: {tvdb_id}): {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取 TVDB 详情失败 (ID: {tvdb_id})。")