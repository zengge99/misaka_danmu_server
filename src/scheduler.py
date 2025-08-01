import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import aiomysql
import httpx
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import crud, models

logger = logging.getLogger(__name__)

# --- Job Logic ---

async def _create_tmdb_client_for_job(pool: aiomysql.Pool) -> httpx.AsyncClient:
    """Non-FastAPI dependent version of get_tmdb_client."""
    keys = ["tmdb_api_key", "tmdb_api_base_url"]
    tasks = [crud.get_config_value(pool, key, "") for key in keys]
    api_key, domain = await asyncio.gather(*tasks)

    if not api_key:
        logger.error("TMDB自动映射任务失败：未配置TMDB API Key。")
        raise ValueError("TMDB API Key not configured.")
    
    domain = domain or "https://api.themoviedb.org"
    cleaned_domain = domain.rstrip('/')
    base_url = cleaned_domain if cleaned_domain.endswith('/3') else f"{cleaned_domain}/3"

    params = {"api_key": api_key}
    headers = {"User-Agent": "DanmuApiServer/1.0 (Scheduled Task)"}
    return httpx.AsyncClient(base_url=base_url, params=params, headers=headers, timeout=30.0)

async def _update_tmdb_mappings_for_job(pool: aiomysql.Pool, client: httpx.AsyncClient, tmdb_tv_id: int, group_id: str):
    """Non-FastAPI dependent version of update_tmdb_mappings."""
    response = await client.get(f"/tv/episode_group/{group_id}", params={"language": "zh-CN"})
    response.raise_for_status()
    group_details = models.TMDBEpisodeGroupDetails.model_validate(response.json())
    await crud.save_tmdb_episode_group_mappings(
        pool=pool,
        tmdb_tv_id=tmdb_tv_id,
        group_id=group_id,
        group_details=group_details
    )

def _select_best_episode_group(groups: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """根据用户逻辑选择最佳剧集组。"""
    if not groups:
        return None

    season_x_pattern = re.compile(r"^Season\s+\d+$", re.IGNORECASE)
    filtered_groups = [g for g in groups if not season_x_pattern.match(g.get("name", ""))]

    for group in filtered_groups:
        if group.get("name", "").lower() == "seasons":
            return group

    for group in filtered_groups:
        if "seasons" in group.get("name", "").lower():
            return group
    
    return filtered_groups[0] if filtered_groups else None

def _parse_tmdb_details_for_aliases(details: Dict[str, Any]) -> Dict[str, Any]:
    """从TMDB详情响应中提取并清理别名。"""
    def _clean_movie_title(title: Optional[str]) -> Optional[str]:
        if not title: return None
        phrases_to_remove = ["劇場版", "the movie"]
        cleaned_title = title
        for phrase in phrases_to_remove:
            cleaned_title = re.sub(r'\s*' + re.escape(phrase) + r'\s*:?', '', cleaned_title, flags=re.IGNORECASE)
        cleaned_title = re.sub(r'\s{2,}', ' ', cleaned_title).strip().strip(':- ')
        return cleaned_title

    name_en, name_jp, name_romaji, aliases_cn = None, None, None, []
    original_title = details.get('original_name') or details.get('original_title')
    original_language = details.get('original_language')
    main_title_cn = details.get('name') or details.get('title')

    if alt_titles := details.get('alternative_titles', {}).get('titles', []):
        found_titles = {}
        for alt_title in alt_titles:
            if alt_title.get('iso_3166_1') in ["CN", "HK", "TW"]:
                aliases_cn.append(alt_title.get('title'))
            elif alt_title.get('iso_3166_1') == "JP":
                if alt_title.get('type') == "Romaji":
                    if 'romaji' not in found_titles: found_titles['romaji'] = alt_title.get('title')
                else:
                    if 'jp' not in found_titles: found_titles['jp'] = alt_title.get('title')
            elif alt_title.get('iso_3166_1') == "US":
                if 'en' not in found_titles: found_titles['en'] = alt_title.get('title')
            elif alt_title.get('iso_3166_1') == "GB" and 'en' not in found_titles:
                found_titles['en'] = alt_title.get('title')
        name_en, name_jp, name_romaji = found_titles.get('en'), found_titles.get('jp'), found_titles.get('romaji')

    if not name_en and original_language == 'en': name_en = original_title
    if not name_jp and original_language == 'ja': name_jp = original_title
    if main_title_cn: aliases_cn.append(main_title_cn)
    
    return {
        "name_en": _clean_movie_title(name_en),
        "name_jp": _clean_movie_title(name_jp),
        "name_romaji": _clean_movie_title(name_romaji),
        "aliases_cn": list(dict.fromkeys([_clean_movie_title(a) for a in aliases_cn if a]))
    }

async def run_tmdb_auto_map_job(pool: aiomysql.Pool):
    """定时任务的核心逻辑。"""
    logger.info("开始执行 [TMDB自动映射与更新] 定时任务...")
    try:
        client = await _create_tmdb_client_for_job(pool)
    except ValueError as e:
        logger.error(f"无法创建TMDB客户端，任务中止: {e}")
        return

    async with client:
        shows_to_update = await crud.get_animes_with_tmdb_id(pool)
        logger.info(f"找到 {len(shows_to_update)} 个带TMDB ID的电视节目需要处理。")

        for show in shows_to_update:
            anime_id, tmdb_id, title = show['anime_id'], show['tmdb_id'], show['title']
            logger.info(f"正在处理: '{title}' (Anime ID: {anime_id}, TMDB ID: {tmdb_id})")
            try:
                if not show.get('tmdb_episode_group_id'):
                    groups_res = await client.get(f"/tv/{tmdb_id}/episode_groups")
                    if groups_res.status_code == 200:
                        groups = groups_res.json().get("results", [])
                        best_group = _select_best_episode_group(groups)
                        if best_group:
                            group_id = best_group['id']
                            logger.info(f"为 '{title}' 选择了剧集组: '{best_group['name']}' ({group_id})")
                            await crud.update_anime_tmdb_group_id(pool, anime_id, group_id)
                            await _update_tmdb_mappings_for_job(pool, client, int(tmdb_id), group_id)
                
                details_res = await client.get(f"/tv/{tmdb_id}", params={"append_to_response": "alternative_titles"})
                if details_res.status_code == 200:
                    aliases_to_update = _parse_tmdb_details_for_aliases(details_res.json())
                    await crud.update_anime_aliases_if_empty(pool, anime_id, aliases_to_update)

                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"处理 '{title}' (TMDB ID: {tmdb_id}) 时发生错误: {e}", exc_info=True)
    logger.info("定时任务 [TMDB自动映射与更新] 执行完毕。")

# --- Scheduler Manager ---

class SchedulerManager:
    def __init__(self, pool: aiomysql.Pool):
        self.pool = pool
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self._job_functions: Dict[str, Callable] = {"tmdb_auto_map": run_tmdb_auto_map_job}

    async def _handle_job_event(self, event: JobExecutionEvent):
        job = self.scheduler.get_job(event.job_id)
        if job:
            await crud.update_scheduled_task_run_times(self.pool, job.id, job.last_run_time, job.next_run_time)

    async def start(self):
        self.scheduler.add_listener(self._handle_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self.scheduler.start()
        await self.load_jobs_from_db()
        logger.info("定时任务调度器已启动。")

    async def stop(self):
        self.scheduler.shutdown()

    async def load_jobs_from_db(self):
        tasks = await crud.get_scheduled_tasks(self.pool)
        for task in tasks:
            if job_func := self._job_functions.get(task['job_type']):
                try:
                    job = self.scheduler.add_job(job_func, CronTrigger.from_crontab(task['cron_expression']), id=task['id'], name=task['name'], replace_existing=True, args=[self.pool])
                    if not task['is_enabled']: self.scheduler.pause_job(task['id'])
                    await crud.update_scheduled_task_run_times(self.pool, job.id, job.last_run_time, job.next_run_time)
                except Exception as e:
                    logger.error(f"加载定时任务 '{task['name']}' (ID: {task['id']}) 失败: {e}")

    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        """从数据库获取所有定时任务的列表。"""
        return await crud.get_scheduled_tasks(self.pool)

    async def add_task(self, name: str, job_type: str, cron: str, is_enabled: bool) -> Dict[str, Any]:
        if not (job_func := self._job_functions.get(job_type)): raise ValueError(f"未知的任务类型: {job_type}")
        task_id = str(uuid4())
        await crud.create_scheduled_task(self.pool, task_id, name, job_type, cron, is_enabled)
        job = self.scheduler.add_job(job_func, CronTrigger.from_crontab(cron), id=task_id, name=name, args=[self.pool])
        if not is_enabled: job.pause()
        await crud.update_scheduled_task_run_times(self.pool, task_id, None, job.next_run_time)
        return await crud.get_scheduled_task(self.pool, task_id)

    async def update_task(self, task_id: str, name: str, cron: str, is_enabled: bool) -> Optional[Dict[str, Any]]:
        if not (job := self.scheduler.get_job(task_id)): return None
        await crud.update_scheduled_task(self.pool, task_id, name, cron, is_enabled)
        job.modify(name=name)
        job.reschedule(trigger=CronTrigger.from_crontab(cron))
        if is_enabled: job.resume()
        else: job.pause()
        await crud.update_scheduled_task_run_times(self.pool, task_id, job.last_run_time, job.next_run_time)
        return await crud.get_scheduled_task(self.pool, task_id)

    async def delete_task(self, task_id: str):
        if self.scheduler.get_job(task_id): self.scheduler.remove_job(task_id)
        await crud.delete_scheduled_task(self.pool, task_id)

    async def run_task_now(self, task_id: str):
        if job := self.scheduler.get_job(task_id):
            job.modify(next_run_time=datetime.now(self.scheduler.timezone))
        else:
            raise ValueError("找不到指定的任务ID")