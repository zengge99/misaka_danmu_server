import logging
from typing import List, Optional

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


class DandanSearchMatch(BaseModel):
    """dandanplay 搜索接口的响应条目模型"""
    animeId: int
    animeTitle: str
    episodeId: int
    episodeTitle: str
    type: str
    typeDescription: str
    shift: int = 0


class DandanSearchResponse(DandanResponseBase):
    """dandanplay 搜索接口的响应模型, 模仿 /api/v2/match 接口"""
    isMatched: bool = Field(False, description="是否精确匹配到结果")
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
        # 创建一个从数据库类型到显示类型的映射
        type_mapping = {
            "tv_series": "动画",
            "movie": "电影",
            "ova": "OVA",
            "other": "其他"
        }
        # 获取映射后的类型，如果数据库中没有或类型未知，则默认为"动画"
        display_type = type_mapping.get(res.get('type'), "动画")
        matches.append(DandanSearchMatch(
            animeId=res['animeId'],
            animeTitle=res['animeTitle'],
            episodeId=res['episodeId'],
            episodeTitle=res['episodeTitle'],
            type=display_type,
            typeDescription=display_type
        ))
    
    is_matched = len(matches) > 0
    # 根据 v2 规范，当 isMatched 为 true 时，通常只返回一个最佳匹配项。
    # 但为保持现有行为，我们返回所有匹配项。
    return DandanSearchResponse(matches=matches, isMatched=is_matched)


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