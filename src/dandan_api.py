import logging
import re
from typing import List, Optional, Dict, Any
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

# --- Models for /match ---

class DandanMatchInfo(BaseModel):
    episodeId: int
    animeId: int
    animeTitle: str
    episodeTitle: str
    type: str
    typeDescription: str
    shift: int = 0

class DandanMatchResponse(DandanResponseBase):
    isMatched: bool = False
    matches: List[DandanMatchInfo] = []

# --- Models for /match/batch ---

class DandanBatchMatchRequestItem(BaseModel):
    fileName: str
    fileHash: Optional[str] = None
    fileSize: Optional[int] = None
    videoDuration: Optional[int] = None
    matchMode: Optional[str] = "hashAndFileName"

class DandanBatchMatchRequest(BaseModel):
    requests: List[DandanBatchMatchRequestItem]


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
                bangumiId=res.get('bangumiId') or f"A{anime_id}",
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

def _parse_filename_for_match(filename: str) -> Optional[Dict[str, Any]]:
    """
    使用正则表达式从文件名中解析出番剧标题和集数。
    这是一个简化的实现，用于 dandanplay 兼容接口。
    """
    # 常见的番剧命名格式: [字幕组] 番剧名 - 01 [分辨率].mkv
    PATTERNS = [
        # 匹配 [xxx] xxx - 01, [xxx] xxx - 01 (xxx)
        re.compile(r"\[.*?\]\s*(?P<title>.+?)\s*[-_]\s*(?P<episode>\d{1,4})", re.IGNORECASE),
        # 匹配 xxx - 01
        re.compile(r"^(?P<title>.+?)\s*[-_]\s*(?P<episode>\d{1,4})", re.IGNORECASE),
        # 匹配 [xxx] xxx 01
        re.compile(r"\[.*?\]\s*(?P<title>.+?)\s+(?P<episode>\d{1,4})", re.IGNORECASE),
        # 匹配 xxx 01
        re.compile(r"^(?P<title>.+?)\s+(?P<episode>\d{1,4})", re.IGNORECASE),
    ]
    for pattern in PATTERNS:
        match = pattern.search(filename)
        if match:
            data = match.groupdict()
            # 移除标题中的常见干扰词
            title = re.sub(r'\[.*?\]|\(.*?\)|\d{1,4}話|第\d{1,4}話', '', data["title"]).strip()
            title = title.replace("_", " ")
            return {
                "title": title,
                "episode": int(data["episode"]),
            }
    
    # 如果以上模式都未匹配，则假定为电影或单文件视频
    # 1. 移除文件扩展名
    title_part = filename
    if '.' in filename:
        title_part = filename.rsplit('.', 1)[0]
    
    # 2. 移除括号内的常见标签
    cleaned_title = re.sub(r'\[.*?\]|\(.*?\)|\【.*?\】', '', title_part).strip()
    
    # 3. 移除常见质量和编码标签
    cleaned_title = re.sub(r'1080p|720p|4k|bluray|x264|x265|aac|flac|web-dl', '', cleaned_title, flags=re.IGNORECASE).strip()
    
    # 4. 将分隔符替换为空格并清理
    cleaned_title = cleaned_title.replace("_", " ").replace(".", " ").strip()
    
    if cleaned_title:
        return {
            "title": cleaned_title,
            "episode": 1, # 对电影或单文件，默认匹配第1集
        }

    return None


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
    "/bangumi/{anime_id}",
    response_model=BangumiDetailsResponse,
    summary="[dandanplay兼容] 获取番剧详情"
)
async def get_bangumi_details(
    anime_id: str = Path(..., description="作品ID, A开头的备用ID, 或真实的Bangumi ID"),
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    模拟 dandanplay 的 /api/v2/bangumi/{bangumiId} 接口。
    返回数据库中存储的番剧详细信息。
    """
    anime_id_int: Optional[int] = None
    if anime_id.startswith('A') and anime_id[1:].isdigit():
        anime_id_int = int(anime_id[1:])
    elif anime_id.isdigit():
        anime_id_int = int(anime_id)
    else:
        # 假定为真实的 bangumi_id
        anime_id_int = await crud.get_anime_id_by_bangumi_id(pool, anime_id)

    if anime_id_int is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anime not found by identifier")

    details = await crud.get_anime_details_for_dandan(pool, anime_id_int)
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

    bangumi_id_str = anime_data.get('bangumiId') or f"A{anime_data['animeId']}"

    bangumi_details = BangumiDetails(
        animeId=anime_data['animeId'],
        bangumiId=bangumi_id_str,
        animeTitle=anime_data['animeTitle'],
        imageUrl=anime_data.get('imageUrl'),
        searchKeyword=anime_data['animeTitle'],
        type=dandan_type,
        typeDescription=dandan_type_desc,
        episodes=formatted_episodes,
        bangumiUrl=anime_data.get('bangumiUrl'),
        summary="暂无简介",
    )

    return BangumiDetailsResponse(bangumi=bangumi_details)

async def _process_single_batch_match(item: DandanBatchMatchRequestItem, pool: aiomysql.Pool) -> DandanMatchResponse:
    """处理批量匹配中的单个文件，仅在精确匹配（1个结果）时返回成功。"""
    parsed_info = _parse_filename_for_match(item.fileName)
    if not parsed_info:
        return DandanMatchResponse(success=False, isMatched=False)

    results = await crud.search_episodes_in_library(pool, parsed_info["title"], parsed_info["episode"])

    if len(results) == 1:
        res = results[0]
        type_mapping = {"tv_series": "tvseries", "movie": "movie", "ova": "ova", "other": "other"}
        type_desc_mapping = {"tv_series": "TV动画", "movie": "剧场版", "ova": "OVA", "other": "其他"}
        dandan_type = type_mapping.get(res.get('type'), "other")
        dandan_type_desc = type_desc_mapping.get(res.get('type'), "其他")

        match = DandanMatchInfo(
            episodeId=res['episodeId'],
            animeId=res['animeId'],
            animeTitle=res['animeTitle'],
            episodeTitle=res['episodeTitle'],
            type=dandan_type,
            typeDescription=dandan_type_desc,
        )
        return DandanMatchResponse(success=True, isMatched=True, matches=[match])
    
    return DandanMatchResponse(success=False, isMatched=False)

@implementation_router.post(
    "/match",
    response_model=DandanMatchResponse,
    summary="[dandanplay兼容] 匹配单个文件"
)
async def match_single_file(
    request: DandanBatchMatchRequestItem,
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    通过文件名匹配弹幕库。此接口不使用文件Hash。
    """
    parsed_info = _parse_filename_for_match(request.fileName)
    if not parsed_info:
        return DandanMatchResponse(isMatched=False)

    results = await crud.search_episodes_in_library(pool, parsed_info["title"], parsed_info["episode"])
    
    if not results:
        return DandanMatchResponse(isMatched=False, matches=[])

    # 检查所有匹配项是否都指向同一个番剧ID
    # 这对于处理拥有多个数据源的电影或剧集非常重要
    first_anime_id = results[0]['animeId']
    all_from_same_anime = all(res['animeId'] == first_anime_id for res in results)

    # 如果所有匹配项都属于同一个番剧（例如，一个电影有多个源），
    # 我们就认为这是一个精确匹配，并只返回第一个源作为代表。
    if all_from_same_anime:
        res = results[0]
        type_mapping = {"tv_series": "tvseries", "movie": "movie", "ova": "ova", "other": "other"}
        type_desc_mapping = {"tv_series": "TV动画", "movie": "剧场版", "ova": "OVA", "other": "其他"}
        dandan_type = type_mapping.get(res.get('type'), "other")
        dandan_type_desc = type_desc_mapping.get(res.get('type'), "其他")

        match = DandanMatchInfo(
            episodeId=res['episodeId'],
            animeId=res['animeId'],
            animeTitle=res['animeTitle'],
            episodeTitle=res['episodeTitle'],
            type=dandan_type,
            typeDescription=dandan_type_desc,
        )
        return DandanMatchResponse(isMatched=True, matches=[match])

    # 如果匹配到了多个不同的番剧，则返回所有结果让用户选择
    matches = []
    for res in results:
        type_mapping = {"tv_series": "tvseries", "movie": "movie", "ova": "ova", "other": "other"}
        type_desc_mapping = {"tv_series": "TV动画", "movie": "剧场版", "ova": "OVA", "other": "其他"}
        dandan_type = type_mapping.get(res.get('type'), "other")
        dandan_type_desc = type_desc_mapping.get(res.get('type'), "其他")

        matches.append(DandanMatchInfo(
            episodeId=res['episodeId'],
            animeId=res['animeId'],
            animeTitle=res['animeTitle'],
            episodeTitle=res['episodeTitle'],
            type=dandan_type,
            typeDescription=dandan_type_desc,
        ))

    return DandanMatchResponse(isMatched=False, matches=matches)


@implementation_router.post(
    "/match/batch",
    response_model=List[DandanMatchResponse],
    summary="[dandanplay兼容] 批量匹配文件"
)
async def match_batch_files(
    request: DandanBatchMatchRequest,
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    批量匹配文件，只返回精确匹配（1个结果）的项。
    """
    if len(request.requests) > 32:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="批量匹配请求不能超过32个文件。")

    tasks = [_process_single_batch_match(item, pool) for item in request.requests]
    results = await asyncio.gather(*tasks)
    return results

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