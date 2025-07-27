import re
from typing import Optional, List
import asyncio

from datetime import timedelta
import aiomysql
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm

from . import crud, models, security
from .scraper_manager import ScraperManager
from .config import settings
from .database import get_db_pool

router = APIRouter()
auth_router = APIRouter()
async def get_scraper_manager(request: Request) -> ScraperManager:
    """依赖项：从应用状态获取 Scraper 管理器"""
    return request.app.state.scraper_manager

def parse_filename_for_match(filename: str) -> Optional[dict]:
    """使用正则表达式从文件名中解析出番剧标题和集数"""
    PATTERNS = [
        re.compile(r"\[.*?\]\s*(?P<title>.+?)\s*[-_]\s*(?P<episode>\d{1,3})"),
        re.compile(r"(?P<title>.+?)\s*[-_]\s*(?P<episode>\d{1,3})"),
    ]
    for pattern in PATTERNS:
        match = pattern.search(filename)
        if match:
            data = match.groupdict()
            return {
                "title": data["title"].strip().replace("_", " "),
                "episode": int(data["episode"]),
            }
    return None

@router.get(
    "/search/anime",
    response_model=models.AnimeSearchResponse,
    summary="搜索本地数据库中的节目信息",
)
async def search_anime_local(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    pool=Depends(get_db_pool)
):
    db_results = await crud.search_anime(pool, keyword)
    animes = [
        models.AnimeInfo(animeId=item["id"], animeTitle=item["title"], type=item["type"])
        for item in db_results
    ]
    return models.AnimeSearchResponse(animes=animes)

@router.get(
    "/search/provider",
    response_model=models.ProviderSearchResponse,
    summary="从外部数据源搜索节目",
)
async def search_anime_provider(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    manager: ScraperManager = Depends(get_scraper_manager)
):
    """从所有已配置的数据源（如腾讯、B站等）搜索节目信息。"""
    results = await manager.search_all(keyword)
    return models.ProviderSearchResponse(results=results)

@router.get(
    "/match",
    response_model=models.MatchResponse,
    summary="匹配本地文件获取弹幕库",
)
async def match_episode(
    fileName: str = Query(..., description="本地文件名"),
    pool=Depends(get_db_pool)
):
    parsed = parse_filename_for_match(fileName)
    if not parsed:
        return models.MatchResponse(isMatched=False, matches=[])

    anime = await crud.find_anime_by_title(pool, parsed["title"])
    if not anime:
        return models.MatchResponse(isMatched=False, matches=[])

    episode = await crud.find_episode(pool, anime["id"], parsed["episode"])
    if not episode:
        return models.MatchResponse(isMatched=False, matches=[])

    match_info = models.MatchInfo(
        animeId=anime["id"],
        animeTitle=anime["title"],
        episodeId=episode["id"],
        episodeTitle=episode["title"],
        type=anime["type"],
    )
    return models.MatchResponse(isMatched=True, matches=[match_info])

@router.get(
    "/comment/{episode_id}",
    response_model=models.CommentResponse,
    summary="获取指定分集的弹幕",
)
async def get_comments(
    episode_id: int,
    pool=Depends(get_db_pool)
):
    # 检查episode是否存在，如果不存在则返回404
    if not await crud.check_episode_exists(pool, episode_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    comments_data = await crud.fetch_comments(pool, episode_id)
    
    comments = [models.Comment(p=item["p"], m=item["m"]) for item in comments_data]
    return models.CommentResponse(count=len(comments), comments=comments)

async def generic_import_task(
    provider: str,
    media_id: str,
    anime_title: str,
    pool: aiomysql.Pool,
    manager: ScraperManager
):
    """
    后台任务：执行从指定数据源导入弹幕的完整流程。
    """
    total_comments_added = 0
    try:
        scraper = manager.get_scraper(provider)

        # 1. 在数据库中创建或获取番剧ID
        anime_id = await crud.get_or_create_anime(pool, anime_title)
        print(f"番剧 '{anime_title}' (ID: {anime_id}) 已准备就绪。")

        # 2. 获取所有分集信息
        episodes = await scraper.get_episodes(media_id)
        if not episodes:
            print(f"未能为 provider='{provider}' media_id='{media_id}' 获取到任何分集。任务终止。")
            return

        # 3. 为每个分集获取并存储弹幕
        for i, episode in enumerate(episodes):
            print(f"--- 开始处理分集 {i+1}/{len(episodes)}: '{episode.title}' (ID: {episode.episodeId}) ---")
            
            # 3.1 在数据库中创建或获取分集ID
            episode_db_id = await crud.get_or_create_episode(pool, anime_id, episode.episodeIndex, episode.title)

            # 3.2 获取弹幕
            comments = await scraper.get_comments(episode.episodeId)
            if not comments:
                print(f"分集 '{episode.title}' 未找到弹幕，跳过。")
                continue

            # 3.3 批量插入弹幕 (get_comments 已按要求格式化)
            added_count = await crud.bulk_insert_comments(pool, episode_db_id, comments)
            total_comments_added += added_count
            print(f"分集 '{episode.title}' (DB ID: {episode_db_id}) 新增 {added_count} 条弹幕。")

    except Exception as e:
        print(f"导入任务发生严重错误: {e}")
    finally:
        print(f"--- {provider} 导入任务完成 (media_id={media_id})。总共新增 {total_comments_added} 条弹幕。 ---")


@router.post("/import", status_code=status.HTTP_202_ACCEPTED, summary="从指定数据源导入弹幕")
async def import_from_provider(
    request_data: models.ImportRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool),
    manager: ScraperManager = Depends(get_scraper_manager)
):
    try:
        # 在启动任务前检查provider是否存在
        manager.get_scraper(request_data.provider)
        print(f"用户 '{current_user.username}' 正在导入数据...")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    background_tasks.add_task(
        generic_import_task,
        request_data.provider,
        request_data.media_id,
        request_data.anime_title,
        pool,
        manager
    )
    return {"message": f"{request_data.provider} 弹幕导入任务已在后台开始。请查看服务器日志了解进度。"}

@auth_router.post("/register", response_model=models.User, status_code=status.HTTP_201_CREATED, summary="注册新用户")
async def register_user(
    user: models.UserCreate,
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    db_user = await crud.get_user_by_username(pool, user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    user_id = await crud.create_user(pool, user)
    return {"id": user_id, "username": user.username}


@auth_router.post("/token", response_model=models.Token, summary="用户登录获取令牌")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    user = await crud.get_user_by_username(pool, form_data.username)
    if not user or not security.verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.jwt.access_token_expire_minutes)
    access_token = security.create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@auth_router.get("/users/me", response_model=models.User, summary="获取当前用户信息")
async def read_users_me(current_user: models.User = Depends(security.get_current_user)):
    return current_user


@auth_router.put("/users/me/password", status_code=status.HTTP_204_NO_CONTENT, summary="修改当前用户密码")
async def change_current_user_password(
    password_data: models.PasswordChange,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    # 1. 从数据库获取完整的用户信息，包括哈希密码
    user_in_db = await crud.get_user_by_username(pool, current_user.username)
    if not user_in_db:
        # 理论上不会发生，因为 get_current_user 已经验证过
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # 2. 验证旧密码是否正确
    if not security.verify_password(password_data.old_password, user_in_db["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect old password")

    # 3. 更新密码
    new_hashed_password = security.get_password_hash(password_data.new_password)
    await crud.update_user_password(pool, current_user.username, new_hashed_password)
