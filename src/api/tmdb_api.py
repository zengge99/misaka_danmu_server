import asyncio
import logging

import aiomysql
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Optional

from .. import crud, models, security
from ..config import settings
from ..database import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_tmdb_client(
    current_user: models.User = Depends(security.get_current_user),
) -> httpx.AsyncClient:
    """依赖项：创建一个带有 TMDB 授权的 httpx 客户端。"""
    headers = {
        "Authorization": f"Bearer {settings.tmdb.api_key}",
        "User-Agent": "l429609201/danmu_api_server(https://github.com/l429609201/danmu_api_server)",
    }
    return httpx.AsyncClient(headers=headers, timeout=20.0)

# --- Pydantic Models for TMDB API ---


class TMDBTitle(BaseModel):
    title: str


class TMDBResults(BaseModel):
    id: int
    name: str
    poster_path: Optional[str] = None

    @property
    def image_url(self) -> Optional[str]:
        """从 images 字典中获取一个合适的图片URL。"""

        if self.poster_path:
            return f"https://image.tmdb.org/t/p/w500{self.poster_path}"
        return None


class TMDBsearchresults(BaseModel):
    results: List[TMDBResults]
    total_pages: int


@router.get("/search", response_model=List[Dict[str, str]], summary="搜索 TMDB 作品")
async def search_tmdb_subjects(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_tmdb_client),
):
    async with client:
        # 步骤 1: 初始搜索以获取ID列表
        params = {
            "query": keyword,
            "include_adult": False,
            "language": "zh-CN",
        }
        search_response = await client.get(
            "https://api.themoviedb.org/3/search/tv", params=params
        )

        if search_response.status_code == 404:
            return []
        search_response.raise_for_status()

        search_result = TMDBsearchresults.model_validate(search_response.json())
        if not search_result.results:
            return []

        # 步骤 3: 组合并格式化最终结果
        final_results = []
        for subject in search_result.results:
            try:
                final_results.append(
                    {
                        "id": subject.id,
                        "name": subject.name,
                        "image_url": subject.image_url,
                    }
                )
            except ValidationError as e:
                logger.error(f"验证 TMDB subject 详情失败: {e}")

        return final_results


@router.get("/movie/search", response_model=List[Dict[str, str]], summary="搜索 TMDB 电影作品")
async def search_tmdb_movie_subjects(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_tmdb_client),
):
    async with client:
        # 步骤 1: 初始搜索以获取ID列表
        params = {
            "query": keyword,
            "include_adult": False,
            "language": "zh-CN",
        }
        search_response = await client.get(
            "https://api.themoviedb.org/3/search/movie", params=params
        )

        if search_response.status_code == 404:
            return []
        search_response.raise_for_status()

        search_result = TMDBsearchresults.model_validate(search_response.json())
        if not search_result.results:
            return []
        return [{"id": subject.id, "name": subject.name, "image_url": subject.image_url} for subject in search_result.results]
