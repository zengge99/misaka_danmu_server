import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

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
        raise HTTPException(status_code=500, detail="TVDB API Key 未配置。")

    try:
        # TVDB V3 API的登录端点
        response = await client.post("https://api.thetvdb.com/login", json={"apikey": api_key})
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
        raise HTTPException(status_code=500, detail="TVDB认证失败。")


async def get_tvdb_client(
    current_user: models.User = Depends(security.get_current_user),
    pool=Depends(get_db_pool),
) -> httpx.AsyncClient:
    """依赖项：获取一个经过认证的TVDB客户端。"""
    client = httpx.AsyncClient(base_url="https://api.thetvdb.com", timeout=20.0)
    token = await get_tvdb_token(pool, client)
    client.headers.update(
        {"Authorization": f"Bearer {token}", "User-Agent": "DanmuApiServer/1.0"}
    )
    return client


# --- Pydantic Models for TVDB ---
class TvdbSearchResult(BaseModel):
    id: int
    seriesName: str
    image: Optional[str] = None
    overview: Optional[str] = None
    firstAired: Optional[str] = None


class TvdbSearchResponse(BaseModel):
    data: List[TvdbSearchResult]


class TvdbDetailsResponse(BaseModel):
    data: Dict[str, Any]


# --- API Endpoints ---
@router.get("/search", response_model=List[Dict[str, Any]], summary="搜索 TVDB 作品")
async def search_tvdb(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_tvdb_client),
):
    """通过关键词在 TheTVDB 上搜索电视剧。"""
    try:
        response = await client.get("/search/series", params={"name": keyword})
        response.raise_for_status()
        results = TvdbSearchResponse.model_validate(response.json()).data

        formatted_results = []
        for item in results:
            details = f"首播: {item.firstAired}" if item.firstAired else "无首播日期"
            if item.overview:
                details += f" / {item.overview[:100]}..."

            formatted_results.append(
                {
                    "id": str(item.id),
                    "title": item.seriesName,
                    "details": details,
                    "image_url": f"https://artworks.thetvdb.com/banners/{item.image}" if item.image else None,
                }
            )
        return formatted_results
    except Exception as e:
        logger.error(f"TVDB 搜索失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="TVDB 搜索失败。")


@router.get("/details/{tvdb_id}", response_model=Dict[str, Any], summary="获取 TVDB 作品详情")
async def get_tvdb_details(
    tvdb_id: str = Path(...), client: httpx.AsyncClient = Depends(get_tvdb_client)
):
    """获取指定 TVDB ID 的作品详情，主要用于提取别名和IMDb ID。"""
    try:
        response = await client.get(f"/series/{tvdb_id}")
        response.raise_for_status()
        details = TvdbDetailsResponse.model_validate(response.json()).data

        return {
            "id": details.get("id"),
            "tvdb_id": details.get("id"),
            "name_en": details.get("seriesName"),
            "aliases_cn": details.get("aliases", []),
            "name_jp": None,
            "name_romaji": None,
            "imdb_id": details.get("imdbId"),
        }
    except Exception as e:
        logger.error(f"获取 TVDB 详情失败 (ID: {tvdb_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取 TVDB 详情失败 (ID: {tvdb_id})。")