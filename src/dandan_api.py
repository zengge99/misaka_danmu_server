import logging
from typing import List, Optional, Dict
from datetime import datetime

import aiomysql
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from . import crud, models
from .database import get_db_pool

dandan_router = APIRouter()
logger = logging.getLogger(__name__)

class DandanResponseBase(BaseModel):
    """模仿 dandanplay API v2 的基础响应模型"""
    success: bool = True
    errorCode: int = 0
    errorMessage: Optional[str] = Field(None, description="错误信息")


class DandanEpisodeInfo(BaseModel):
    """dandanplay /search/episodes 接口中的分集信息模型"""
    episodeId: int
    episodeTitle: str

class DandanAnimeInfo(BaseModel):
    """dandanplay /search/episodes 接口中的番剧信息模型"""
    animeId: int
    bangumiId: Optional[str] = ""
    animeTitle: str
    type: str
    typeDescription: str
    imageUrl: Optional[str] = None
    startDate: Optional[datetime] = None
    episodeCount: int
    rating: int = 0
    isFavorited: bool = False
    episodes: List[DandanEpisodeInfo]

class DandanSearchEpisodesResponse(DandanResponseBase):
    hasMore: bool = False
    animes: List[DandanAnimeInfo]


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
    "/search/episodes",
    response_model=DandanSearchEpisodesResponse,
    summary="[dandanplay兼容] 搜索节目和分集"
)
async def search_episodes_for_dandan(
    anime: str = Query(..., description="节目名称"),
    episode: Optional[str] = Query(None, description="分集标题 (通常是数字)"),
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    模拟 dandanplay 的 /api/v2/search/episodes 接口。
    它会搜索 **本地弹幕库** 中的番剧和分集信息。
    """
    search_term = anime.strip()
    if not search_term:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required query parameter: 'anime'"
        )

    episode_number = int(episode) if episode and episode.isdigit() else None
    
    flat_results = await crud.search_episodes_in_library(pool, search_term, episode_number)

    grouped_animes: Dict[int, DandanAnimeInfo] = {}

    for res in flat_results:
        anime_id = res['animeId']
        if anime_id not in grouped_animes:
            type_mapping = {
                "tv_series": "tvseries",
                "movie": "movie",
                "ova": "ova",
                "other": "other"
            }
            type_desc_mapping = {
                "tv_series": "TV动画",
                "movie": "剧场版",
                "ova": "OVA",
                "other": "其他"
            }
            
            dandan_type = type_mapping.get(res.get('type'), "other")
            dandan_type_desc = type_desc_mapping.get(res.get('type'), "其他")

            grouped_animes[anime_id] = DandanAnimeInfo(
                animeId=anime_id,
                animeTitle=res['animeTitle'],
                type=dandan_type,
                typeDescription=dandan_type_desc,
                imageUrl=res.get('imageUrl'),
                startDate=res.get('startDate'),
                episodeCount=res.get('totalEpisodeCount', 0),
                episodes=[]
            )
        
        grouped_animes[anime_id].episodes.append(
            DandanEpisodeInfo(
                episodeId=res['episodeId'],
                episodeTitle=res['episodeTitle']
            )
        )
    
    return DandanSearchEpisodesResponse(animes=list(grouped_animes.values()))


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
    comments = [models.Comment(cid=item["cid"], p=item["p"], m=item["m"]) for item in comments_data]
    return models.CommentResponse(count=len(comments), comments=comments)