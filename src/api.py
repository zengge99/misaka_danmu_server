import re
from typing import Optional, List, Any, Dict, Callable
import asyncio
import secrets
import logging

from datetime import timedelta, datetime, timezone
import aiomysql
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm

from . import crud, models, security
from .log_manager import get_logs
from .task_manager import TaskManager
from .scraper_manager import ScraperManager
from .config import settings
from .database import get_db_pool

router = APIRouter()
auth_router = APIRouter()
logger = logging.getLogger(__name__)

def parse_search_keyword(keyword: str) -> dict:
    """
    解析搜索关键词，提取标题、季数和集数。
    例如: "吞噬星空 S01E172" -> {'title': '吞噬星空', 'season': 1, 'episode': 172}
    """
    # Pattern for "Title S01E172"
    pattern = re.compile(r"^(?P<title>.+?)\s*S(?P<season>\d{1,2})E(?P<episode>\d{1,4})$", re.IGNORECASE)
    match = pattern.match(keyword.strip())
    if match:
        data = match.groupdict()
        return {
            "title": data["title"].strip(),
            "season": int(data["season"]),
            "episode": int(data["episode"]),
        }
    return {"title": keyword, "season": None, "episode": None}

async def get_scraper_manager(request: Request) -> ScraperManager:
    """依赖项：从应用状态获取 Scraper 管理器"""
    return request.app.state.scraper_manager

async def get_task_manager(request: Request) -> TaskManager:
    """依赖项：从应用状态获取任务管理器"""
    return request.app.state.task_manager

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
    """
    从所有已配置的数据源（如腾讯、B站等）搜索节目信息。
    支持 "标题 SXXEXX" 格式来指定集数。
    """
    parsed_keyword = parse_search_keyword(keyword)

    # 新增：检查是否有启用的搜索源
    if not manager.has_enabled_scrapers:
        # 如果没有启用任何源，直接返回错误，而不是空列表
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有启用的搜索源，请在“搜索源”页面中启用至少一个。"
        )

    search_title = parsed_keyword["title"]
    episode_info = {
        "season": parsed_keyword["season"],
        "episode": parsed_keyword["episode"]
    } if parsed_keyword["episode"] is not None else None

    results = await manager.search_all(search_title, episode_info=episode_info)
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

@router.get("/library", response_model=models.LibraryResponse, summary="获取媒体库内容")
async def get_library(
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """获取数据库中所有已收录的番剧信息，用于“弹幕情况”展示。"""
    db_results = await crud.get_library_anime(pool)
    # Pydantic 会自动处理 datetime 到 ISO 8601 字符串的转换
    animes = [models.LibraryAnimeInfo.model_validate(item) for item in db_results]
    return models.LibraryResponse(animes=animes)

@router.put("/library/anime/{anime_id}", status_code=status.HTTP_204_NO_CONTENT, summary="编辑影视信息")
async def edit_anime_info(
    anime_id: int,
    update_data: models.AnimeInfoUpdate,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """更新指定番剧的标题和季数。"""
    updated = await crud.update_anime_info(pool, anime_id, update_data.title, update_data.season)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anime not found")
    logger.info(f"用户 '{current_user.username}' 更新了番剧 ID: {anime_id} 的信息。")
    return

@router.get("/library/anime/{anime_id}/sources", response_model=List[Dict[str, Any]], summary="获取作品的所有数据源")
async def get_anime_sources_for_anime(
    anime_id: int,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """获取指定作品关联的所有数据源列表。"""
    return await crud.get_anime_sources(pool, anime_id)

@router.get("/library/source/{source_id}/episodes", response_model=List[models.EpisodeDetail], summary="获取数据源的所有分集")
async def get_source_episodes(
    source_id: int,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """获取指定数据源下的所有已收录分集列表。"""
    return await crud.get_episodes_for_source(pool, source_id)

@router.put("/library/episode/{episode_id}", status_code=status.HTTP_204_NO_CONTENT, summary="编辑分集信息")
async def edit_episode_info(
    episode_id: int,
    update_data: models.EpisodeInfoUpdate,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """更新指定分集的标题、集数和链接。"""
    updated = await crud.update_episode_info(
        pool,
        episode_id,
        update_data.title,
        update_data.episode_index,
        update_data.source_url
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    logger.info(f"用户 '{current_user.username}' 更新了分集 ID: {episode_id} 的信息。")
    return

@router.delete("/library/episode/{episode_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定分集")
async def delete_episode_from_source(
    episode_id: int,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """删除一个分集及其所有关联的弹幕。"""
    deleted = await crud.delete_episode(pool, episode_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    logger.info(f"用户 '{current_user.username}' 删除了分集 ID: {episode_id}。")
    return

@router.post("/library/episode/{episode_id}/refresh", status_code=status.HTTP_202_ACCEPTED, summary="刷新单个分集的弹幕")
async def refresh_single_episode(
    episode_id: int,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool),
    scraper_manager: ScraperManager = Depends(get_scraper_manager),
    task_manager: TaskManager = Depends(get_task_manager)
):
    """为指定分集启动一个后台任务，重新获取其弹幕。"""
    # 检查分集是否存在，以提供更友好的404错误
    episode = await crud.get_episode_for_refresh(pool, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    
    logger.info(f"用户 '{current_user.username}' 请求刷新分集 ID: {episode_id} ({episode['title']})")
    
    task_coro = lambda callback: refresh_episode_task(episode_id, pool, scraper_manager, callback)
    task_id = await task_manager.submit_task(task_coro, f"刷新分集: {episode['title']}")

    return {"message": f"分集 '{episode['title']}' 的刷新任务已提交。", "task_id": task_id}

@router.post("/library/source/{source_id}/refresh", status_code=status.HTTP_202_ACCEPTED, summary="全量刷新指定源的弹幕")
async def refresh_anime(
    source_id: int,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool),
    scraper_manager: ScraperManager = Depends(get_scraper_manager),
    task_manager: TaskManager = Depends(get_task_manager)
):
    """为指定数据源启动一个后台任务，删除其所有旧弹幕并从源重新获取。"""
    source_info = await crud.get_anime_source_info(pool, source_id)
    if not source_info or not source_info.get("provider_name") or not source_info.get("media_id"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anime not found or missing source information for refresh.")
    
    logger.info(f"用户 '{current_user.username}' 为番剧 '{source_info['title']}' (源ID: {source_id}) 启动了全量刷新任务。")
    
    task_coro = lambda callback: full_refresh_task(source_id, pool, scraper_manager, callback)
    task_id = await task_manager.submit_task(task_coro, f"刷新: {source_info['title']}")

    return {"message": f"番剧 '{source_info['title']}' 的全量刷新任务已提交。", "task_id": task_id}

@router.delete("/library/anime/{anime_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除媒体库中的番剧")
async def delete_anime_from_library(
    anime_id: int,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """删除一个番剧及其所有关联的分集和弹幕。"""
    try:
        deleted = await crud.delete_anime(pool, anime_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anime not found or already deleted")
    except Exception as e:
        logger.error(f"删除番剧 (ID: {anime_id}) 时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred while deleting the anime.")
    return

@router.get("/scrapers", response_model=List[models.ScraperSetting], summary="获取所有爬虫源的设置")
async def get_scraper_settings(
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """获取所有可用爬虫源的列表及其配置（启用状态、顺序）。"""
    settings = await crud.get_all_scraper_settings(pool)
    return [models.ScraperSetting.model_validate(s) for s in settings]

@router.put("/scrapers", status_code=status.HTTP_204_NO_CONTENT, summary="更新爬虫源的设置")
async def update_scraper_settings(
    settings: List[models.ScraperSetting],
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool),
    manager: ScraperManager = Depends(get_scraper_manager)
):
    """批量更新爬虫源的启用状态和显示顺序。"""
    await crud.update_scrapers_settings(pool, settings)
    # 更新数据库后，触发 ScraperManager 重新加载爬虫
    await manager.load_and_sync_scrapers()
    logger.info(f"用户 '{current_user.username}' 更新了爬虫源设置，已重新加载。")
    return

@router.get("/logs", response_model=List[str], summary="获取最新的服务器日志")
async def get_server_logs(current_user: models.User = Depends(security.get_current_user)):
    """获取存储在内存中的最新日志条目。"""
    return get_logs()

@router.get("/tasks", response_model=List[models.TaskInfo], summary="获取所有后台任务的状态")
async def get_all_tasks(
    current_user: models.User = Depends(security.get_current_user),
    task_manager: TaskManager = Depends(get_task_manager)
):
    """获取当前所有（排队中、运行中、已完成）后台任务的列表和状态。"""
    return task_manager.get_all_tasks()

@router.get("/tokens", response_model=List[models.ApiTokenInfo], summary="获取所有弹幕API Token")
async def get_all_api_tokens(
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """获取所有为第三方播放器创建的 API Token。"""
    tokens = await crud.get_all_api_tokens(pool)
    return [models.ApiTokenInfo.model_validate(t) for t in tokens]

@router.post("/tokens", response_model=models.ApiTokenInfo, status_code=status.HTTP_201_CREATED, summary="创建一个新的API Token")
async def create_new_api_token(
    token_data: models.ApiTokenCreate,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """创建一个新的、随机的 API Token。"""
    # 生成一个20位的随机字符串
    new_token_str = secrets.token_urlsafe(15) # 15字节 -> 20个URL安全字符
    token_id = await crud.create_api_token(pool, token_data.name, new_token_str)
    # 重新从数据库获取以包含所有字段
    new_token = await crud.get_api_token_by_id(pool, token_id) # 假设这个函数存在
    return models.ApiTokenInfo.model_validate(new_token)

@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除一个API Token")
async def delete_api_token(
    token_id: int,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """根据ID删除一个 API Token。"""
    deleted = await crud.delete_api_token(pool, token_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    return

@router.put("/tokens/{token_id}/toggle", status_code=status.HTTP_204_NO_CONTENT, summary="切换API Token的启用状态")
async def toggle_api_token_status(
    token_id: int,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool)
):
    """切换指定 API Token 的启用/禁用状态。"""
    toggled = await crud.toggle_api_token(pool, token_id)
    if not toggled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    return

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
    media_type: str,
    current_episode_index: Optional[int],
    image_url: Optional[str],
    progress_callback: Callable,
    pool: aiomysql.Pool,
    manager: ScraperManager
):
    """
    后台任务：执行从指定数据源导入弹幕的完整流程。
    """
    total_comments_added = 0
    try:
        scraper = manager.get_scraper(provider)

        # 1. 在数据库中创建或获取番剧ID，并链接数据源
        anime_id = await crud.get_or_create_anime(pool, anime_title, media_type, image_url)
        source_id = await crud.link_source_to_anime(pool, anime_id, provider, media_id)

        logger.info(f"媒体 '{anime_title}' (ID: {anime_id}, 类型: {media_type}) 已准备就绪。")

        # 2. 获取所有分集信息
        # 将目标集数信息传递给 scraper，让其可以优化获取过程
        episodes = await scraper.get_episodes(media_id, target_episode_index=current_episode_index)
        if not episodes:
            logger.warning(f"未能为 provider='{provider}' media_id='{media_id}' 获取到任何分集。")
            if current_episode_index:
                logger.warning(f"特别是，未能找到指定的目标分集: {current_episode_index}。")
            logger.warning("任务终止。")
            return

        # 如果是电影，即使返回了多个版本（如原声、国语），也只处理第一个
        if media_type == "movie" and episodes:
            logger.info(f"检测到媒体类型为电影，将只处理第一个分集 '{episodes[0].title}'。")
            episodes = episodes[:1]
        
        # 3. 为每个分集获取并存储弹幕
        for i, episode in enumerate(episodes):
            logger.info(f"--- 开始处理分集 {i+1}/{len(episodes)}: '{episode.title}' (ID: {episode.episodeId}) ---")
            progress_callback(progress=(i / len(episodes)) * 100, description=f"正在处理: {episode.title} ({i+1}/{len(episodes)})")
            
            # 3.1 在数据库中创建或获取分集ID
            episode_db_id = await crud.get_or_create_episode(pool, source_id, episode.episodeIndex, episode.title, episode.url, episode.episodeId)

            # 3.2 获取弹幕
            comments = await scraper.get_comments(episode.episodeId)
            if not comments:
                logger.info(f"分集 '{episode.title}' 未找到弹幕，跳过。")
                continue

            # 3.3 批量插入弹幕 (get_comments 已按要求格式化)
            added_count = await crud.bulk_insert_comments(pool, episode_db_id, comments)
            total_comments_added += added_count
            logger.info(f"分集 '{episode.title}' (DB ID: {episode_db_id}) 新增 {added_count} 条弹幕。")

    except Exception as e:
        logger.error(f"导入任务发生严重错误: {e}", exc_info=True)
    finally:
        logger.info(f"--- {provider} 导入任务完成 (media_id={media_id})。总共新增 {total_comments_added} 条弹幕。 ---")

async def full_refresh_task(source_id: int, pool: aiomysql.Pool, manager: ScraperManager, progress_callback: Callable):
    """
    后台任务：全量刷新一个已存在的番剧。
    """
    logger.info(f"开始刷新源 ID: {source_id}")
    source_info = await crud.get_anime_source_info(pool, source_id)
    if not source_info:
        progress_callback(100, "失败: 找不到源信息")
        logger.error(f"刷新失败：在数据库中找不到源 ID: {source_id}")
        return
    
    anime_id = source_info["anime_id"]
    # 1. 清空旧数据
    progress_callback(10, "正在清空旧数据...")
    await crud.clear_source_data(pool, source_id)
    logger.info(f"已清空源 ID: {source_id} 的旧分集和弹幕。") # image_url 在这里不会被传递，因为刷新时我们不希望覆盖已有的海报
    # 2. 重新执行通用导入逻辑
    await generic_import_task(source_info["provider_name"], source_info["media_id"], source_info["title"], source_info["type"], None, None, progress_callback, pool, manager)

async def refresh_episode_task(episode_id: int, pool: aiomysql.Pool, manager: ScraperManager, progress_callback: Callable):
    """后台任务：刷新单个分集的弹幕"""
    logger.info(f"开始刷新分集 ID: {episode_id}")
    try:
        progress_callback(0, "正在获取分集信息...")
        # 1. 获取分集的源信息
        info = await crud.get_episode_provider_info(pool, episode_id)
        if not info or not info.get("provider_name") or not info.get("provider_episode_id"):
            logger.error(f"刷新失败：在数据库中找不到分集 ID: {episode_id} 的源信息")
            progress_callback(100, "失败: 找不到源信息")
            return

        provider_name = info["provider_name"]
        provider_episode_id = info["provider_episode_id"]
        scraper = manager.get_scraper(provider_name)

        # 2. 清空旧弹幕
        progress_callback(25, "正在清空旧弹幕...")
        await crud.clear_episode_comments(pool, episode_id)
        logger.info(f"已清空分集 ID: {episode_id} 的旧弹幕。")

        # 3. 获取新弹幕并插入
        progress_callback(50, "正在从源获取新弹幕...")
        comments = await scraper.get_comments(provider_episode_id)
        progress_callback(75, f"正在写入 {len(comments)} 条新弹幕...")
        added_count = await crud.bulk_insert_comments(pool, episode_id, comments)
        await crud.update_episode_fetch_time(pool, episode_id)
        logger.info(f"分集 ID: {episode_id} 刷新完成，新增 {added_count} 条弹幕。")
        progress_callback(100, f"刷新完成，新增 {added_count} 条弹幕。")

    except Exception as e:
        logger.error(f"刷新分集 ID: {episode_id} 时发生严重错误: {e}", exc_info=True)
        progress_callback(100, "任务失败")
        raise e # Re-raise so the task manager catches it and marks as FAILED

@router.post("/import", status_code=status.HTTP_202_ACCEPTED, summary="从指定数据源导入弹幕")
async def import_from_provider(
    request_data: models.ImportRequest,
    current_user: models.User = Depends(security.get_current_user),
    pool: aiomysql.Pool = Depends(get_db_pool),
    scraper_manager: ScraperManager = Depends(get_scraper_manager),
    task_manager: TaskManager = Depends(get_task_manager)
):
    try:
        # 在启动任务前检查provider是否存在
        scraper_manager.get_scraper(request_data.provider)
        logger.info(f"用户 '{current_user.username}' 正在从 '{request_data.provider}' 导入 '{request_data.anime_title}' (media_id={request_data.media_id})")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # 创建一个将传递给任务管理器的协程工厂 (lambda)
    task_coro = lambda callback: generic_import_task(
        provider=request_data.provider,
        media_id=request_data.media_id,
        anime_title=request_data.anime_title,
        media_type=request_data.type,
        current_episode_index=request_data.current_episode_index,
        image_url=request_data.image_url,
        progress_callback=callback,
        pool=pool,
        manager=scraper_manager
    )
    
    # 提交任务并获取任务ID
    task_id = await task_manager.submit_task(task_coro, f"导入: {request_data.anime_title}")

    return {"message": f"'{request_data.anime_title}' 的导入任务已提交。请在任务管理器中查看进度。", "task_id": task_id}

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
    # 更新用户的登录信息
    await crud.update_user_login_info(pool, user["username"], access_token)
    
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
