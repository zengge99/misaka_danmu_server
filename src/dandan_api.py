import logging
from typing import List, Optional

import aiomysql
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from . import crud, models
from .database import get_db_pool

dandan_router = APIRouter()
logger = logging.getLogger(__name__)


class DandanSearchMatch(BaseModel):
    """dandanplay 搜索接口的响应条目模型"""
    animeId: int
    animeTitle: str
    episodeId: int
    episodeTitle: str
    type: str = "动画" # dandanplay 似乎对类型不敏感，这里使用固定值
    typeDescription: str = "动画"
    shift: int = 0


class DandanSearchResponse(BaseModel):
    """dandanplay 搜索接口的响应模型"""
    hasMore: bool = False
    animes: List = [] # animes 字段似乎未使用，保持为空列表
    matches: List[DandanSearchMatch]


async def get_token_from_path(
    token: str = Path(..., description="路径中的API授权令牌"),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    一个 FastAPI 依赖项，用于验证路径中的 token。
    这是为 dandanplay 客户端设计的特殊鉴权方式。
    """
    is_valid = await crud.validate_api_token(pool, token)
    if not is_valid:
        # dandanplay 客户端期望收到 403 Forbidden
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API token")
    return token

@dandan_router.get(
    "/search/anime",
    response_model=DandanSearchResponse,
    summary="[dandanplay兼容] 搜索节目和分集"
)
async def search_for_dandan(
    keyword: Optional[str] = Query(None, description="节目名称 (e.g., dandanplay-qt)"),
    anime: Optional[str] = Query(None, description="节目名称 (e.g., dandanplay-legacy)"),
    episode: Optional[str] = Query(None, description="分集标题 (通常是数字)"),
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    模拟 dandanplay 的搜索接口。
    它会搜索 **本地弹幕库**，而不是调用外部爬虫。支持电视剧和电影的匹配。
    """
    search_term = (keyword or anime or "").strip()
    if not search_term:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required query parameter: 'keyword' or 'anime'"
        )

    # 检查是否提供了有效的分集号
    if episode and episode.isdigit():
        episode_number = int(episode)
        results = await crud.search_episodes_in_library(pool, search_term, episode_number)
    else:
        # 如果没有提供分集号，则假定为电影或对剧集进行模糊匹配。
        # 这种情况下，我们搜索第1集，这通常能匹配到电影，或是系列剧的开端。
        results = await crud.search_episodes_in_library(pool, search_term, 1)
    
    matches = []
    for res in results:
        matches.append(DandanSearchMatch(
            animeId=res['animeId'],
            animeTitle=res['animeTitle'],
            episodeId=res['episodeId'],
            episodeTitle=res['episodeTitle']
        ))

    return DandanSearchResponse(matches=matches)


@dandan_router.get(
    "/comment/{episode_id}",
    response_model=models.CommentResponse,
    summary="[dandanplay兼容] 获取弹幕"
)
async def get_comments_for_dandan(
    episode_id: int = Path(..., description="分集ID (来自 /search/episodes 响应中的 episodeId)"),
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    模拟 dandanplay 的弹幕获取接口。
    注意：这里的 episode_id 实际上是我们数据库中的主键 ID。
    """
    comments_data = await crud.fetch_comments(pool, episode_id)
    comments = [models.Comment(p=item["p"], m=item["m"]) for item in comments_data]
    return models.CommentResponse(count=len(comments), comments=comments)