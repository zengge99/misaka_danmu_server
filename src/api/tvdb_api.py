import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import asyncio
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from .. import crud, models, security
from ..database import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_tvdb_token(pool, client: httpx.AsyncClient) -> str:
    """获取一个有效的TVDB令牌，如果需要则刷新，并将其存储在数据库中。"""
    # 1. 从数据库读取令牌和过期时间
    token_task = crud.get_config_value(pool, "tvdb_token", "")
    expires_at_str_task = crud.get_config_value(pool, "tvdb_token_expires_at", "0")
    token, expires_at_str = await asyncio.gather(token_task, expires_at_str_task)

    # 2. 检查令牌是否有效
    try:
        expires_at_ts = float(expires_at_str)
        # 使用 aware datetime 对象进行比较
        if token and datetime.fromtimestamp(expires_at_ts, tz=timezone.utc) > datetime.now(timezone.utc):
            logger.info("TVDB: 使用数据库中缓存的有效令牌。")
            return token
    except (ValueError, TypeError):
        logger.warning("TVDB: 数据库中的令牌过期时间格式无效，将重新获取。")

    logger.info("TVDB token 已过期或未找到，正在请求新的令牌。")
    api_key = await crud.get_config_value(pool, "tvdb_api_key", "")

    if not api_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TVDB API Key 未配置。")
    try:
        # TVDB V4 API 的登录端点
        response = await client.post("/login", json={"apikey": api_key})
        response.raise_for_status()
        # 根据TVDB API v4文档，token在 'data' 字段下
        new_token = response.json().get("data", {}).get("token")
        if not new_token:
            raise ValueError("登录响应中未包含令牌。")

        # 令牌有效期为24小时，我们设置一个23小时的缓存
        new_expires_at = datetime.now(timezone.utc) + timedelta(hours=23)
        update_token_task = crud.update_config_value(pool, "tvdb_token", new_token)
        update_expiry_task = crud.update_config_value(pool, "tvdb_token_expires_at", str(new_expires_at.timestamp()))
        await asyncio.gather(update_token_task, update_expiry_task)
        logger.info("成功获取新的TVDB令牌并已缓存至数据库。")
        return new_token
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