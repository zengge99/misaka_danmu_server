import asyncio
import logging
import aiomysql
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Optional, Any

from .. import crud, models, security
from ..config import settings
from ..database import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_tmdb_client(
    current_user: models.User = Depends(security.get_current_user),
) -> httpx.AsyncClient:
    """依赖项：创建一个带有 TMDB 授权的 httpx 客户端。"""
    if not settings.tmdb.api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TMDB API Key not configured. Please set it in the settings page."
        )
    # TMDB v3 使用 api_key 作为查询参数，v4 使用 Bearer Token。文档推荐v3。
    # 我们将 api_key 作为默认参数添加到每个请求中。
    base_params = {"api_key": settings.tmdb.api_key}
    
    return httpx.AsyncClient(
        base_url="https://api.themoviedb.org/3",
        params=base_params,
        headers={"User-Agent": "l429609201/danmu_api_server(https://github.com/l429609201/danmu_api_server)"},
        timeout=20.0
    )

# --- Pydantic Models for TMDB API ---

class TMDBAlternativeTitle(BaseModel):
    iso_3166_1: str
    title: str
    type: str

class TMDBAlternativeTitles(BaseModel):
    titles: Optional[List[TMDBAlternativeTitle]] = None # For TV
    results: Optional[List[TMDBAlternativeTitle]] = None # For Movie

class TMDBDetail(BaseModel):
    id: int
    name: Optional[str] = None # For TV
    title: Optional[str] = None # For Movie
    original_name: Optional[str] = None # For TV
    original_title: Optional[str] = None # For Movie
    alternative_titles: Optional[TMDBAlternativeTitles] = Field(None, alias="alternative_titles")

    @property
    def display_name(self) -> str:
        return self.name or self.title or "Unknown"

    @property
    def original_display_name(self) -> str:
        return self.original_name or self.original_title or ""

    @property
    def aliases(self) -> Dict[str, Any]:
        data = {
            "name_en": None,
            "name_romaji": None, # TMDB doesn't provide romaji directly
            "aliases_cn": []
        }
        if not self.alternative_titles:
            return data

        titles_list = self.alternative_titles.titles or self.alternative_titles.results or []
        
        # Find the first official English title
        en_titles = [t.title for t in titles_list if t.iso_3166_1 == "US"]
        if en_titles:
            data["name_en"] = en_titles[0]

        # Collect Chinese aliases
        cn_aliases = {t.title for t in titles_list if t.iso_3166_1 in ["CN", "HK", "TW"]}
        
        # Also add the original name if it's different from the main display name
        if self.original_display_name and self.original_display_name != self.display_name:
            cn_aliases.add(self.original_display_name)

        data["aliases_cn"] = list(cn_aliases)
        return data

class TMDBResults(BaseModel):
    id: int
    name: Optional[str] = None # For TV
    title: Optional[str] = None # For Movie
    poster_path: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.name or self.title or "Unknown"

    @property
    def image_url(self) -> Optional[str]:
        if self.poster_path:
            return f"https://image.tmdb.org/t/p/w500{self.poster_path}"
        return None

class TMDBsearchresults(BaseModel):
    results: List[TMDBResults]
    total_pages: int


@router.get("/search/tv", response_model=List[Dict[str, Any]], summary="搜索 TMDB 电视剧")
async def search_tmdb_tv_subjects(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_tmdb_client),
):
    async with client:
        params = {"query": keyword, "include_adult": "false", "language": "zh-CN"}
        search_response = await client.get("/search/tv", params=params)

        if search_response.status_code == 404: return []
        search_response.raise_for_status()

        search_result = TMDBsearchresults.model_validate(search_response.json())
        if not search_result.results: return []

        return [{"id": subject.id, "name": subject.display_name, "image_url": subject.image_url} for subject in search_result.results]


@router.get("/search/movie", response_model=List[Dict[str, Any]], summary="搜索 TMDB 电影")
async def search_tmdb_movie_subjects(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_tmdb_client),
):
    async with client:
        params = {"query": keyword, "include_adult": "false", "language": "zh-CN"}
        search_response = await client.get("/search/movie", params=params)

        if search_response.status_code == 404: return []
        search_response.raise_for_status()

        search_result = TMDBsearchresults.model_validate(search_response.json())
        if not search_result.results: return []
        
        return [{"id": subject.id, "name": subject.display_name, "image_url": subject.image_url} for subject in search_result.results]

@router.get("/details/{media_type}/{media_id}", response_model=Dict[str, Any], summary="获取 TMDB 作品详情和别名")
async def get_tmdb_details(
    media_type: str,
    media_id: int,
    client: httpx.AsyncClient = Depends(get_tmdb_client)
):
    if media_type not in ["tv", "movie"]:
        raise HTTPException(status_code=400, detail="Invalid media type. Must be 'tv' or 'movie'.")
    
    async with client:
        params = {"language": "zh-CN", "append_to_response": "alternative_titles"}
        details_response = await client.get(f"/{media_type}/{media_id}", params=params)

        if details_response.status_code == 404:
            raise HTTPException(status_code=404, detail="Media not found on TMDB.")
        details_response.raise_for_status()

        try:
            details = TMDBDetail.model_validate(details_response.json())
            aliases = details.aliases
            return {
                "id": details.id,
                "name": details.display_name,
                "name_en": aliases.get("name_en"),
                "name_romaji": aliases.get("name_romaji"),
                "aliases_cn": aliases.get("aliases_cn", [])
            }
        except ValidationError as e:
            logger.error(f"验证 TMDB 详情失败 (ID: {media_id}): {e}")
            raise HTTPException(status_code=500, detail="Failed to parse TMDB details response.")

