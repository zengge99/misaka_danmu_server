import logging
from typing import Any, Dict

from .base import BaseWebhook
from ..api.ui import generic_import_task
from ..scraper_manager import ScraperManager

logger = logging.getLogger(__name__)

class EmbyWebhook(BaseWebhook):
    async def handle(self, payload: Dict[str, Any]):
        event_type = payload.get("Event")
        # 我们只关心新媒体入库的事件
        if event_type != "item.add":
            logger.info(f"Emby Webhook: 忽略非 'item.add' 事件 (类型: {event_type})")
            return

        item = payload.get("Item", {})
        if not item:
            logger.warning("Emby Webhook: 负载中缺少 'Item' 信息。")
            return

        item_type = item.get("Type")
        if item_type not in ["Episode", "Movie"]:
            logger.info(f"Emby Webhook: 忽略非 'Episode' 或 'Movie' 类型的媒体项 (类型: {item_type})")
            return

        # 提取通用信息
        provider_ids = item.get("ProviderIds", {})
        tmdb_id = provider_ids.get("Tmdb")
        
        # 根据媒体类型分别处理
        if item_type == "Episode":
            series_title = item.get("SeriesName")
            season_number = item.get("SeasonNumber")
            episode_number = item.get("EpisodeNumber")
            
            if not all([series_title, season_number is not None, episode_number is not None]):
                logger.warning(f"Emby Webhook: 忽略一个剧集，因为缺少系列标题、季度或集数信息: {item}")
                return

            logger.info(f"Emby Webhook: 收到新增剧集通知 - '{series_title}' S{season_number:02d}E{episode_number:02d}")
            
            task_title = f"Webhook导入: {series_title} - S{season_number:02d}E{episode_number:02d}"
            search_keyword = f"{series_title} S{season_number:02d}E{episode_number:02d}"
            media_type = "tv_series"
            anime_title = series_title
            
        elif item_type == "Movie":
            movie_title = item.get("Name")
            if not movie_title:
                logger.warning(f"Emby Webhook: 忽略一个电影，因为缺少标题信息: {item}")
                return
            
            logger.info(f"Emby Webhook: 收到新增电影通知 - '{movie_title}'")
            
            task_title = f"Webhook导入: {movie_title}"
            search_keyword = movie_title
            media_type = "movie"
            season_number = 1
            episode_number = 1 # 电影按单集处理
            anime_title = movie_title

        # 动态创建一个 ScraperManager 实例以供导入任务使用
        scraper_manager = ScraperManager(self.pool)
        await scraper_manager.load_and_sync_scrapers()

        # 复用通用的导入任务逻辑
        task_coro = lambda callback: generic_import_task(
            provider=None, media_id=search_keyword, anime_title=anime_title, media_type=media_type,
            season=season_number, current_episode_index=episode_number, image_url=None,
            douban_id=None, tmdb_id=str(tmdb_id) if tmdb_id else None,
            progress_callback=callback, pool=self.pool, manager=scraper_manager, is_webhook=True
        )
        await self.task_manager.submit_task(task_coro, task_title)