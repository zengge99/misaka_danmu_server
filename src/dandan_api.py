import asyncio
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


# --- Models for /search/anime ---
class DandanSearchAnimeItem(BaseModel):
    animeId: int
    bangumiId: Optional[str] = ""
    animeTitle: str
    type: str
    typeDescription: str
    imageUrl: Optional[str] = None
    startDate: Optional[datetime] = None
    episodeCount: int
    rating: float = 0.0
    isFavorited: bool = False

class DandanSearchAnimeResponse(DandanResponseBase):
    animes: List[DandanSearchAnimeItem]


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
    # 移除文件扩展名
    name_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename

    # 模式1: SXXEXX 格式 (e.g., "Some.Anime.S01E02.1080p.mkv")
    s_e_pattern = re.compile(
        r"^(?P<title>.+?)"
        r"[\s._-]*"
        r"[Ss](?P<season>\d{1,2})"
        r"[Ee](?P<episode>\d{1,4})"
        r"\b",
        re.IGNORECASE
    )
    match = s_e_pattern.search(name_without_ext)
    if match:
        data = match.groupdict()
        title = data["title"].replace(".", " ").replace("_", " ").strip()
        title = re.sub(r'\[.*?\]', '', title).strip() # 移除字幕组标签
        return {
            "title": title,
            "season": int(data["season"]),
            "episode": int(data["episode"])
        }

    # 模式2: 只有集数 (e.g., "[Subs] Some Anime - 02 [1080p].mkv")
    ep_only_patterns = [
        re.compile(r"^(?P<title>.+?)\s*[-_]\s*\b(?P<episode>\d{1,4})\b", re.IGNORECASE),
        re.compile(r"^(?P<title>.+?)\s+\b(?P<episode>\d{1,4})\b", re.IGNORECASE),
    ]
    for pattern in ep_only_patterns:
        match = pattern.search(name_without_ext)
        if match:
            data = match.groupdict()
            title = data["title"]
            # 清理标题中的元数据
            title = re.sub(r'\[.*?\]|\(.*?\)|\【.*?\】', '', title).strip()
            title = re.sub(r'1080p|720p|4k|bluray|x264|h\s*\.?\s*264|hevc|x265|h\s*\.?\s*265|aac|flac|web-dl|BDRip|WEBRip|TVRip|DVDrip|AVC|CHT|CHS|BIG5|GB', '', title, flags=re.IGNORECASE).strip()
            title = title.replace("_", " ").replace(".", " ").strip()
            title = title.strip(' -')
            return {
                "title": title,
                "season": None, # 此模式无法识别季度
                "episode": int(data["episode"]),
            }
    
    # 模式3: 电影或单文件视频 (没有集数)
    title = name_without_ext
    title = re.sub(r'\[.*?\]|\(.*?\)|\【.*?\】', '', title).strip()
    title = re.sub(r'1080p|720p|4k|bluray|x264|h\s*\.?\s*264|hevc|x265|h\s*\.?\s*265|aac|flac|web-dl|BDRip|WEBRip|TVRip|DVDrip|AVC|CHT|CHS|BIG5|GB', '', title, flags=re.IGNORECASE).strip()
    title = title.replace("_", " ").replace(".", " ").strip()
    title = re.sub(r'\(\d{4}\)', '', title).strip() # 移除年份
    title = title.strip(' -')
    
    if title:
        return {
            "title": title,
            "season": 1, # 对电影，默认匹配第1季
            "episode": 1, # 和第1集
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
    response_model=DandanSearchAnimeResponse,
    summary="[dandanplay兼容] 搜索作品"
)
async def search_anime_for_dandan(
    keyword: Optional[str] = Query(None, description="节目名称 (兼容 keyword)"),
    anime: Optional[str] = Query(None, description="节目名称 (兼容 anime)"),
    episode: Optional[str] = Query(None, description="分集标题 (此接口中未使用)"),
    token: str = Depends(get_token_from_path),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """
    模拟 dandanplay 的 /api/v2/search/anime 接口。
    它会搜索 **本地弹幕库** 中的番剧信息，不包含分集列表。
    """
    search_term = keyword or anime
    if not search_term:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required query parameter: 'keyword' or 'anime'"
        )

    db_results = await crud.search_animes_for_dandan(pool, search_term)
    
    animes = []
    for res in db_results:
        type_mapping = {
            "tv_series": "tvseries", "movie": "movie", "ova": "ova", "other": "other"
        }
        type_desc_mapping = {
            "tv_series": "TV动画", "movie": "剧场版", "ova": "OVA", "other": "其他"
        }
        dandan_type = type_mapping.get(res.get('type'), "other")
        dandan_type_desc = type_desc_mapping.get(res.get('type'), "其他")

        animes.append(DandanSearchAnimeItem(
            animeId=res['animeId'],
            bangumiId=res.get('bangumiId') or f"A{res['animeId']}",
            animeTitle=res['animeTitle'],
            type=dandan_type,
            typeDescription=dandan_type_desc,
            imageUrl=res.get('imageUrl'),
            startDate=res.get('startDate'),
            episodeCount=res.get('episodeCount', 0),
        ))
    
    return DandanSearchAnimeResponse(animes=animes)

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

    results = await crud.search_episodes_in_library(pool, parsed_info["title"], parsed_info["episode"], parsed_info.get("season"))

    # 优先处理被精确标记的源
    favorited_results = [r for r in results if r.get('isFavorited')]
    if favorited_results:
        res = favorited_results[0]
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

    # 如果没有精确标记，则只有当结果唯一时才算成功
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
    logger.info(f"收到 /match 请求, 文件名: '{request.fileName}'")
    parsed_info = _parse_filename_for_match(request.fileName)
    logger.info(f"文件名解析结果: {parsed_info}")
    if not parsed_info:
        response = DandanMatchResponse(isMatched=False)
        logger.info(f"发送 /match 响应 (解析失败): {response.model_dump_json(indent=2)}")
        return response

    results = await crud.search_episodes_in_library(pool, parsed_info["title"], parsed_info["episode"], parsed_info.get("season"))
    logger.info(f"数据库为 '{parsed_info['title']}' (季:{parsed_info.get('season')} 集:{parsed_info.get('episode')}) 搜索到 {len(results)} 条记录")
    
    # 新增：对结果进行严格的标题过滤，避免模糊匹配带来的问题
    normalized_search_title = parsed_info["title"].replace("：", ":").replace(" ", "")
    if normalized_search_title:
        exact_matches = [
            r for r in results 
            if r['animeTitle'].replace("：", ":").replace(" ", "") == normalized_search_title
        ]
        if len(exact_matches) < len(results):
            logger.info(f"过滤掉 {len(results) - len(exact_matches)} 条模糊匹配的结果。")
            results = exact_matches

    if not results:
        response = DandanMatchResponse(isMatched=False, matches=[])
        logger.info(f"发送 /match 响应 (无精确匹配): {response.model_dump_json(indent=2)}")
        return response

    # 优先处理被精确标记的源
    favorited_results = [r for r in results if r.get('isFavorited')]
    if favorited_results:
        res = favorited_results[0]
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
        response = DandanMatchResponse(isMatched=True, matches=[match])
        logger.info(f"发送 /match 响应 (精确标记匹配): {response.model_dump_json(indent=2)}")
        return response

    # 如果没有精确标记，检查所有匹配项是否都指向同一个番剧ID
    first_anime_id = results[0]['animeId']
    all_from_same_anime = all(res['animeId'] == first_anime_id for res in results)

    if all_from_same_anime:
        # 结果已由数据库按 标题长度和源顺序 排序，直接取第一个
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
        response = DandanMatchResponse(isMatched=True, matches=[match])
        logger.info(f"发送 /match 响应 (单一作品匹配): {response.model_dump_json(indent=2)}")
        return response

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

    response = DandanMatchResponse(isMatched=False, matches=matches)
    logger.info(f"发送 /match 响应 (多个匹配): {response.model_dump_json(indent=2)}")
    return response


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

# 2. 挂载以支持兼容路径: /api/{token}/api/v2/bangumi/{anime_id}
dandan_router.include_router(implementation_router, prefix="/api/v2")
# 1. 挂载以支持直接路径: /api/{token}/bangumi/{anime_id}
dandan_router.include_router(implementation_router)


