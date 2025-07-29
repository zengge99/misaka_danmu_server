import logging
from typing import List, Optional, Dict
from datetime import datetime

import aiomysql
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from . import crud, models
from .database import get_db_pool

logger = logging.getLogger(__name__)

# 这个子路由将包含所有接口的实际实现。
# 它将被挂载到主路由的不同路径上。
implementation_router = APIRouter()

# 这是将包含在 main.py 中的主路由。
dandan_router = APIRouter()

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


# --- Models for /bangumi/{anime_id} ---

class BangumiTitle(BaseModel):
    language: str
    title: str

class BangumiEpisodeSeason(BaseModel):
    id: str
    airDate: Optional[datetime] = None
    name: str
    episodeCount: int
    summary: str

class BangumiEpisode(BaseModel):
    seasonId: Optional[str] = None
    episodeId: int
    episodeTitle: str
    episodeNumber: str
    lastWatched: Optional[datetime] = None
    airDate: Optional[datetime] = None

class BangumiIntro(BaseModel):
    animeId: int
    bangumiId: Optional[str] = ""
    animeTitle: str
    imageUrl: Optional[str] = None
    searchKeyword: Optional[str] = None
    isOnAir: bool = False
    airDay: int = 0
    isFavorited: bool = False
    isRestricted: bool = False
    rating: float = 0.0

class BangumiTag(BaseModel):
    id: int
    name: str
    count: int

class BangumiOnlineDatabase(BaseModel):
    name: str
    url: str

class BangumiTrailer(BaseModel):
    id: int
    url: str
    title: str
    imageUrl: str
    date: datetime

class BangumiDetails(BangumiIntro):
    type: str
    typeDescription: str
    episodeCount: int
    titles: List[BangumiTitle] = []
    seasons: List[BangumiEpisodeSeason] = []
    episodes: List[BangumiEpisode] = []
    summary: Optional[str] = ""
    metadata: List[str] = []
    bangumiUrl: Optional[str] = None
    userRating: int = 0
    favoriteStatus: Optional[str] = None
    comment: Optional[str] = None
    ratingDetails: Dict[str, float] = {}
    relateds: List[BangumiIntro] = []
    similars: List[BangumiIntro] = []
    tags: List[BangumiTag] = []
    onlineDatabases: List[BangumiOnlineDatabase] = []
    trailers: List[BangumiTrailer] = []

class BangumiDetailsResponse(DandanResponseBase):
    bangumi: Optional[BangumiDetails] = None

class PaginatedBangumiListResponse(DandanResponseBase):
    """用于 /bangumi/ 接口的响应模型，包含分页信息"""
    bangumiList: List[BangumiDetails]
    total: int
    page: int
    pageSize: int


async def _search_implementation(
    search_term: str,
    episode: Optional[str],
    pool: aiomysql.Pool
) -> DandanSearchEpisodesResponse:
    """搜索接口的通用实现，避免代码重复。"""
    search_term = search_term.strip()
    if not search_term:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required query parameter: 'anime' or 'keyword'"
        )

    episode_number = int(episode) if episode and episode.isdigit() else None
    
    flat_results = await crud.search_episodes_in_library(pool, search_term, episode_number)

    grouped_animes: Dict[int, DandanAnimeInfo] = {}

    for res in flat_results:
        anime_id = res['animeId']
        if anime_id not in grouped_animes:
            type_mapping = {
                "tv_series": "tvseries", "movie": "movie", "ova": "ova", "other": "other"
            }
            type_desc_mapping = {
                "tv_series": "TV动画", "movie": "剧场版", "ova": "OVA", "other": "其他"
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
            DandanEpisodeInfo(episodeId=res['episodeId'], episodeTitle=res['episodeTitle'])
        )
    
    return DandanSearchEpisodesResponse(animes=list(grouped_animes.values()))

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

@implementation_router.get(
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
    return await _search_implementation(search_term, episode, pool)

@implementation_router.get(
    "/search/anime",
    response_model=DandanSearchEpisodesResponse,
    summary="[dandanplay兼容] 搜索节目和分集 (兼容路径)"
)
async def search_anime_for_dandan(
    keyword: Optional[str] = Query(None, description="节目名称 (兼容 keyword)"),
    anime: Optional[str] = Query(None, description="节目名称 (兼容 anime)"),
    episode: Optional[str] = Query(None, description="分集标题 (通常是数字)"),
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    模拟 dandanplay 的搜索接口，兼容 /search/anime 路径。
    """
    search_term = keyword or anime
    if not search_term:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required query parameter: 'keyword' or 'anime'"
        )
    return await _search_implementation(search_term, episode, pool)

@implementation_router.get(
    "/bangumi/",
    response_model=PaginatedBangumiListResponse,
    summary="[dandanplay兼容] 获取所有番剧列表（分页）"
)
async def get_all_bangumi(
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页数量"),
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    获取媒体库中所有番剧的列表，支持分页。
    这是为了兼容某些客户端对 /bangumi/ 的请求。
    """
    paginated_data = await crud.get_all_anime_paginated(pool, page, pageSize)
    
    bangumi_list = []
    for anime_data in paginated_data['animes']:
        type_mapping = {"tv_series": "tvseries", "movie": "movie", "ova": "ova", "other": "other"}
        type_desc_mapping = {"tv_series": "TV动画", "movie": "剧场版", "ova": "OVA", "other": "其他"}
        dandan_type = type_mapping.get(anime_data.get('type'), "other")
        dandan_type_desc = type_desc_mapping.get(anime_data.get('type'), "其他")

        formatted_episodes = [
            BangumiEpisode(
                episodeId=ep['episodeId'],
                episodeTitle=ep['episodeTitle'],
                episodeNumber=str(ep['episodeNumber'])
            ) for ep in anime_data.get('episodes', [])
        ]

        bangumi_list.append(
            BangumiDetails(
                animeId=anime_data['animeId'],
                animeTitle=anime_data['animeTitle'],
                imageUrl=anime_data.get('imageUrl'),
                searchKeyword=anime_data['animeTitle'],
                type=dandan_type,
                typeDescription=dandan_type_desc,
                episodeCount=anime_data.get('episodeCount', 0),
                episodes=formatted_episodes,
                bangumiUrl=anime_data.get('bangumiUrl'),
                summary="暂无简介",
            )
        )

    return PaginatedBangumiListResponse(
        bangumiList=bangumi_list,
        total=paginated_data['total'],
        page=page,
        pageSize=pageSize
    )

@implementation_router.get(
    "/bangumi/{anime_id}",
    response_model=BangumiDetailsResponse,
    summary="[dandanplay兼容] 获取番剧详情"
)
async def get_bangumi_details(
    anime_id: int = Path(..., description="作品ID"),
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    模拟 dandanplay 的 /api/v2/bangumi/{bangumiId} 接口。
    返回数据库中存储的番剧详细信息。
    """
    details = await crud.get_anime_details_for_dandan(pool, anime_id)
    if not details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anime not found"
        )

    anime_data = details['anime']
    episodes_data = details['episodes']

    type_mapping = {"tv_series": "tvseries", "movie": "movie", "ova": "ova", "other": "other"}
    type_desc_mapping = {"tv_series": "TV动画", "movie": "剧场版", "ova": "OVA", "other": "其他"}
    dandan_type = type_mapping.get(anime_data.get('type'), "other")
    dandan_type_desc = type_desc_mapping.get(anime_data.get('type'), "其他")

    formatted_episodes = [
        BangumiEpisode(
            episodeId=ep['episodeId'],
            episodeTitle=ep['episodeTitle'],
            episodeNumber=str(ep['episodeNumber'])
        ) for ep in episodes_data
    ]

    bangumi_details = BangumiDetails(
        animeId=anime_data['animeId'],
        animeTitle=anime_data['animeTitle'],
        imageUrl=anime_data.get('imageUrl'),
        searchKeyword=anime_data['animeTitle'],
        type=dandan_type,
        typeDescription=dandan_type_desc,
        episodeCount=anime_data.get('episodeCount', 0),
        episodes=formatted_episodes,
        bangumiUrl=anime_data.get('bangumiUrl'),
        summary="暂无简介",
    )

    return BangumiDetailsResponse(bangumi=bangumi_details)

@implementation_router.get(
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

# --- 路由挂载 ---
# 将实现路由挂载到主路由上，以支持两种URL结构。

# 1. 挂载以支持直接路径: /api/{token}/bangumi/{anime_id}
dandan_router.include_router(implementation_router)
# 2. 挂载以支持兼容路径: /api/{token}/api/v2/bangumi/{anime_id}
dandan_router.include_router(implementation_router, prefix="/api/v2")