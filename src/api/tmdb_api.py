import asyncio
import logging

import aiomysql
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status, Path
from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Optional, Any

from .. import crud, models, security
from ..config import settings
from ..database import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_tmdb_client(
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool),
) -> httpx.AsyncClient:
    """依赖项：创建一个带有 TMDB 授权的 httpx 客户端。"""
    # Fetch all configs in parallel
    keys = ["tmdb_api_key", "tmdb_api_base_url"]
    tasks = [crud.get_config_value(pool, key, "") for key in keys]
    api_key, domain = await asyncio.gather(*tasks)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TMDB API Key not configured. Please set it in the settings page."
        )
    if not domain:
        domain = "https://api.themoviedb.org" # Fallback to default domain
        logger.warning("TMDB API Domain not configured, using default.")

    # 从域名构建完整的 API 基础 URL
    base_url = f"{domain.rstrip('/')}/3"

    # TMDB v3 API 使用 api_key 查询参数进行身份验证
    params = {"api_key": api_key}
    headers = {
        # 使用一个更通用的 User-Agent
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    return httpx.AsyncClient(base_url=base_url, params=params, headers=headers, timeout=20.0)

# --- Pydantic Models for TMDB API ---

class TMDBTVResult(BaseModel):
    id: int
    name: str
    poster_path: Optional[str] = None

class TMDBMovieResult(BaseModel):
    id: int
    title: str
    poster_path: Optional[str] = None

class TMDBTVSearchResults(BaseModel):
    results: List[TMDBTVResult]
    total_pages: int

class TMDBMovieSearchResults(BaseModel):
    results: List[TMDBMovieResult]
    total_pages: int

class TMDBExternalIDs(BaseModel):
    imdb_id: Optional[str] = None
    tvdb_id: Optional[int] = None


class TMDBAlternativeTitle(BaseModel):
    iso_3166_1: str
    title: str
    type: str


class TMDBAlternativeTitles(BaseModel):
    titles: List[TMDBAlternativeTitle] = []


class TMDBTVDetails(BaseModel):
    id: int
    name: str
    original_name: str
    alternative_titles: Optional[TMDBAlternativeTitles] = None
    external_ids: Optional[TMDBExternalIDs] = None

class TMDBMovieDetails(BaseModel):
    id: int
    title: str
    original_title: str
    alternative_titles: Optional[TMDBAlternativeTitles] = None
    external_ids: Optional[TMDBExternalIDs] = None


@router.get("/search/tv", response_model=List[Dict[str, str]], summary="搜索 TMDB 电视剧")
async def search_tmdb_subjects(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_tmdb_client),
    pool: aiomysql.Pool = Depends(get_db_pool),
):
    async with client:
        # 步骤 1: 初始搜索以获取ID列表
        params = {
            "query": keyword,
            "include_adult": False,
            "language": "zh-CN",
        }
        search_response = await client.get(
            "/search/tv", params=params
        )

        if search_response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TMDB API Key is invalid or unauthorized. Please check your key in the settings.",
            )

        if search_response.status_code != 200:
            logger.error(f"TMDB search for TV failed with status {search_response.status_code}: {search_response.text}")
            return []

        search_result = TMDBTVSearchResults.model_validate(search_response.json())
        if not search_result.results:
            return []

        # Fetch image base URL
        image_base_url = await crud.get_config_value(pool, "tmdb_image_base_url", "https://image.tmdb.org/t/p/w500")

        # 步骤 3: 组合并格式化最终结果
        final_results = []
        for subject in search_result.results:
            image_url = f"{image_base_url.rstrip('/')}{subject.poster_path}" if subject.poster_path else None
            try:
                final_results.append(
                    {
                        "id": subject.id,
                        "name": subject.name,
                        "image_url": image_url,
                    }
                )
            except ValidationError as e:
                logger.error(f"验证 TMDB subject 详情失败: {e}")

        return final_results
 
@router.get("/search/movie", response_model=List[Dict[str, str]], summary="搜索 TMDB 电影作品")
async def search_tmdb_movie_subjects(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_tmdb_client),
    pool: aiomysql.Pool = Depends(get_db_pool),
):
    async with client:
        # 步骤 1: 初始搜索以获取ID列表
        params = {
            "query": keyword,
            "include_adult": False,
            "language": "zh-CN",
        }
        search_response = await client.get(
            "/search/movie", params=params
        )

        if search_response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TMDB API Key is invalid or unauthorized. Please check your key in the settings.",
            )

        if search_response.status_code != 200:
            logger.error(f"TMDB search for Movie failed with status {search_response.status_code}: {search_response.text}")
            return []

        search_result = TMDBMovieSearchResults.model_validate(search_response.json())
        if not search_result.results:
            return []

        # Fetch image base URL
        image_base_url = await crud.get_config_value(pool, "tmdb_image_base_url", "https://image.tmdb.org/t/p/w500")

        return [
            {
                "id": subject.id,
                "name": subject.title,
                "image_url": f"{image_base_url.rstrip('/')}{subject.poster_path}" if subject.poster_path else None
            }
            for subject in search_result.results
        ]


@router.get("/details/{media_type}/{tmdb_id}", response_model=Dict[str, Any], summary="获取 TMDB 作品详情")
async def get_tmdb_details(
    media_type: str = Path(..., description="媒体类型, 'tv' 或 'movie'"),
    tmdb_id: int = Path(..., description="TMDB ID"),
    client: httpx.AsyncClient = Depends(get_tmdb_client),
):
    if media_type not in ["tv", "movie"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media type. Must be 'tv' or 'movie'.")

    async with client:
        params = {
            "append_to_response": "alternative_titles,external_ids",
            "language": "zh-CN",
        }
        details_response = await client.get(f"/{media_type}/{tmdb_id}", params=params)

        if details_response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TMDB API Key is invalid or unauthorized. Please check your key in the settings.",
            )
        if details_response.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TMDB entry not found.")
        
        details_response.raise_for_status()
        details_json = details_response.json()

        if media_type == "tv":
            details = TMDBTVDetails.model_validate(details_json)
            name_en = details.original_name
            name_romaji = None # TMDB doesn't provide this directly
        else: # movie
            details = TMDBMovieDetails.model_validate(details_json)
            name_en = details.original_title
            name_romaji = None

        aliases_cn = []
        if details.alternative_titles:
            for alt_title in details.alternative_titles.titles:
                if alt_title.iso_3166_1 == "CN":
                    aliases_cn.append(alt_title.title)
        
        return {
            "id": details.id,
            "name_en": name_en,
            "name_romaji": name_romaji,
            "aliases_cn": list(dict.fromkeys(aliases_cn)) # Deduplicate
        }
