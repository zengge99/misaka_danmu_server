import asyncio
import logging
import re

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


def _clean_movie_title(title: Optional[str]) -> Optional[str]:
    """
    从标题中移除 "剧场版" 或 "The Movie" 等词语。
    """
    if not title:
        return None
    # A list of phrases to remove, case-insensitively
    phrases_to_remove = ["劇場版", "the movie"]
    
    cleaned_title = title
    for phrase in phrases_to_remove:
        # This regex removes the phrase, optional surrounding whitespace, and an optional trailing colon.
        cleaned_title = re.sub(r'\s*' + re.escape(phrase) + r'\s*:?', '', cleaned_title, flags=re.IGNORECASE)

    # Clean up any double spaces that might result from the removal and leading/trailing separators
    cleaned_title = re.sub(r'\s{2,}', ' ', cleaned_title).strip().strip(':- ')
    
    return cleaned_title


async def _get_robust_image_base_url(pool: aiomysql.Pool) -> str:
    """
    获取TMDB图片基础URL，并对其进行健壮性处理。
    如果用户只配置了域名，则自动附加默认的尺寸路径。
    """
    image_base_url_config = await crud.get_config_value(
        pool, "tmdb_image_base_url", "https://image.tmdb.org/t/p/w500"
    )
    
    # 如果配置中不包含 /t/p/ 路径，说明用户可能只填写了域名
    if '/t/p/' not in image_base_url_config:
        # 我们附加一个默认的尺寸路径，使其成为一个有效的图片基础URL
        return f"{image_base_url_config.rstrip('/')}/t/p/w500"
    
    return image_base_url_config

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
    # 增加健壮性：如果用户输入的域名已经包含了 /3，则不再重复添加
    cleaned_domain = domain.rstrip('/')
    if cleaned_domain.endswith('/3'):
        base_url = cleaned_domain
    else:
        base_url = f"{cleaned_domain}/3"

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

class TMDBEpisodeGroup(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    episode_count: int
    group_count: int
    type: int

class TMDBEpisodeGroupList(BaseModel):
    results: List[TMDBEpisodeGroup]
    id: int

class TMDBEpisodeInGroupDetail(BaseModel):
    id: int
    name: str
    episode_number: int
    season_number: int
    air_date: Optional[str] = None
    overview: Optional[str] = ""

class TMDBGroupInGroupDetail(BaseModel):
    id: str
    name: str
    order: int
    episodes: List[TMDBEpisodeInGroupDetail]

class TMDBSearchResponseItem(BaseModel):
    id: int
    name: str
    image_url: Optional[str] = None

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
    original_language: str
    original_name: str
    alternative_titles: Optional[TMDBAlternativeTitles] = None
    external_ids: Optional[TMDBExternalIDs] = None

class TMDBMovieDetails(BaseModel):
    id: int
    original_language: str
    title: str
    original_title: str
    alternative_titles: Optional[TMDBAlternativeTitles] = None
    external_ids: Optional[TMDBExternalIDs] = None

class TMDBEpisodeGroupDetails(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    episode_count: int
    group_count: int
    groups: List[TMDBGroupInGroupDetail]
    network: Optional[Dict[str, Any]] = None
    type: int


@router.get("/search/tv", response_model=List[TMDBSearchResponseItem], summary="搜索 TMDB 电视剧")
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
        image_base_url = await _get_robust_image_base_url(pool)

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
 
@router.get("/search/movie", response_model=List[TMDBSearchResponseItem], summary="搜索 TMDB 电影作品")
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
        image_base_url = await _get_robust_image_base_url(pool)

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

        # Initialize variables
        name_en = None
        name_jp = None
        name_romaji = None
        aliases_cn = []
        imdb_id = None
        tvdb_id = None
        
        # Get base details
        if media_type == "tv":
            details = TMDBTVDetails.model_validate(details_json)
            main_title_cn = details.name
            original_title = details.original_name
            original_language = details.original_language
        else: # movie
            details = TMDBMovieDetails.model_validate(details_json)
            main_title_cn = details.title
            original_title = details.original_title
            original_language = details.original_language

        # Extract external IDs
        if details.external_ids:
            imdb_id = details.external_ids.imdb_id
            tvdb_id = details.external_ids.tvdb_id

        # Process alternative titles for more accurate names
        if details.alternative_titles:
            found_titles = {}
            for alt_title in details.alternative_titles.titles:
                # Chinese Aliases
                if alt_title.iso_3166_1 in ["CN", "HK", "TW"]:
                    aliases_cn.append(alt_title.title)
                # Japanese Title
                elif alt_title.iso_3166_1 == "JP":
                    if alt_title.type == "Romaji":
                        if 'romaji' not in found_titles: found_titles['romaji'] = alt_title.title
                    else:
                        if 'jp' not in found_titles: found_titles['jp'] = alt_title.title
                # English Title (prefer US, then GB)
                elif alt_title.iso_3166_1 == "US":
                    if 'en' not in found_titles: found_titles['en'] = alt_title.title
                elif alt_title.iso_3166_1 == "GB" and 'en' not in found_titles:
                    found_titles['en'] = alt_title.title
            
            name_en, name_jp, name_romaji = found_titles.get('en'), found_titles.get('jp'), found_titles.get('romaji')

        if not name_en and original_language == 'en': name_en = original_title
        if not name_jp and original_language == 'ja': name_jp = original_title
        if main_title_cn: aliases_cn.append(main_title_cn)
        
        cleaned_aliases_cn = [_clean_movie_title(alias) for alias in aliases_cn if alias]

        return {
            "id": details.id,
            "imdb_id": imdb_id,
            "tvdb_id": tvdb_id,
            "name_en": _clean_movie_title(name_en),
            "name_jp": _clean_movie_title(name_jp),
            "name_romaji": _clean_movie_title(name_romaji),
            "aliases_cn": list(dict.fromkeys(cleaned_aliases_cn)) # Deduplicate
        }

@router.get("/tv/{tmdb_id}/episode_groups", response_model=List[TMDBEpisodeGroup], summary="获取电视剧的所有剧集组")
async def get_tmdb_episode_groups(
    tmdb_id: int = Path(..., description="TMDB电视剧ID"),
    client: httpx.AsyncClient = Depends(get_tmdb_client),
):
    async with client:
        response = await client.get(f"/tv/{tmdb_id}/episode_groups")
        if response.status_code == 401:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="TMDB API Key is invalid.")
        if response.status_code == 404:
            return [] # Not found is a valid case, just return empty list
        response.raise_for_status()
        
        data = TMDBEpisodeGroupList.model_validate(response.json())
        return data.results

@router.get("/episode_group/{group_id}", response_model=TMDBEpisodeGroupDetails, summary="获取特定剧集组的详情")
async def get_tmdb_episode_group_details(
    group_id: str = Path(..., description="TMDB剧集组ID"),
    client: httpx.AsyncClient = Depends(get_tmdb_client),
):
    async with client:
        response = await client.get(f"/tv/episode_group/{group_id}")
        if response.status_code == 401:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="TMDB API Key is invalid.")
        if response.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode group not found.")
        response.raise_for_status()
        
        return TMDBEpisodeGroupDetails.model_validate(response.json())
