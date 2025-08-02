import asyncio
import importlib
import inspect
import logging
import aiomysql
from pathlib import Path
from typing import Dict, List, Optional, Any

from .scrapers.base import BaseScraper
from .models import ProviderSearchInfo
from . import crud


class ScraperManager:
    def __init__(self, pool: aiomysql.Pool):
        self.scrapers: Dict[str, BaseScraper] = {}
        self.pool = pool
        # 注意：加载逻辑现在是异步的，将在应用启动时调用

    def _load_scrapers(self):
        """
        动态发现并加载 'scrapers' 目录下的所有爬虫类。
        """
        scrapers_dir = Path(__file__).parent / "scrapers"
        for file in scrapers_dir.glob("*.py"):
            if file.name.startswith("_") or file.name == "base.py":
                continue

            module_name = f".scrapers.{file.stem}"
            try:
                module = importlib.import_module(module_name, package="src")
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseScraper) and obj is not BaseScraper:
                        scraper_instance = obj()
                        if scraper_instance.provider_name in self.scrapers:
                            print(f"警告: 发现重复的爬虫 '{scraper_instance.provider_name}'。将被覆盖。")
                        self.scrapers[scraper_instance.provider_name] = scraper_instance
                        print(f"爬虫 '{scraper_instance.provider_name}' 已加载。")
            except Exception as e:
                print(f"从 {file.name} 加载爬虫失败: {e}")
    
    async def load_and_sync_scrapers(self):
        """
        动态发现、同步到数据库并根据数据库设置加载爬虫。
        此方法可以被再次调用以重新加载爬虫。
        """
        # 清理现有爬虫以确保全新加载
        await self.close_all()
        self.scrapers.clear()

        scrapers_dir = Path(__file__).parent / "scrapers"
        discovered_providers = []
        scraper_classes = {}

        for file in scrapers_dir.glob("*.py"):
            if file.name.startswith("_") or file.name == "base.py": continue
            module_name = f".scrapers.{file.stem}"
            try:
                module = importlib.import_module(module_name, package="src")
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseScraper) and obj is not BaseScraper:
                        provider_name = obj.provider_name # 直接访问类属性，避免实例化
                        discovered_providers.append(provider_name)
                        scraper_classes[provider_name] = obj
            except TypeError as e:
                if "Couldn't parse file content!" in str(e):
                    # 这是一个针对 protobuf 版本不兼容的特殊情况。
                    error_msg = (
                        f"加载爬虫模块 {module_name} 失败，疑似 protobuf 版本不兼容。 "
                        f"请确保已将 'protobuf' 版本固定为 '3.20.3' (在 requirements.txt 中), "
                        f"并且已经通过 'docker-compose build' 命令重新构建了您的 Docker 镜像。"
                    )
                    logging.getLogger(__name__).error(error_msg, exc_info=True)
                else:
                    # 正常处理其他 TypeError
                    logging.getLogger(__name__).error(f"加载爬虫模块 {module_name} 失败，已跳过。错误: {e}", exc_info=True)
            except Exception as e:
                # 使用标准日志记录器
                logging.getLogger(__name__).error(f"加载爬虫模块 {module_name} 失败，已跳过。错误: {e}", exc_info=True)
        
        await crud.sync_scrapers_to_db(self.pool, discovered_providers)
        settings = await crud.get_all_scraper_settings(self.pool)

        for setting in settings:
            if setting['is_enabled'] and setting['provider_name'] in scraper_classes:
                provider_name = setting['provider_name']
                self.scrapers[provider_name] = scraper_classes[provider_name](self.pool)
                print(f"已启用爬虫 '{provider_name}' (顺序: {setting['display_order']})。")

    @property
    def has_enabled_scrapers(self) -> bool:
        """检查是否有任何已启用的爬虫。"""
        return bool(self.scrapers)

    async def search_all(self, keywords: List[str], episode_info: Optional[Dict[str, Any]] = None) -> List[ProviderSearchInfo]:
        """
        在所有已注册的爬虫上并发搜索关键词列表。
        """
        if not self.scrapers:
            return []

        tasks = []
        for keyword in keywords:
            for scraper in self.scrapers.values():
                tasks.append(scraper.search(keyword, episode_info=episode_info))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_search_results = []
        seen_results = set() # 用于去重

        for result in results:
            if isinstance(result, Exception):
                logging.getLogger(__name__).error(f"搜索任务中出现错误: {result}")
            elif result:
                for item in result:
                    # 使用 (provider, mediaId) 作为唯一标识符
                    unique_id = (item.provider, item.mediaId)
                    if unique_id not in seen_results:
                        all_search_results.append(item)
                        seen_results.add(unique_id)

        return all_search_results

    async def close_all(self):
        """关闭所有爬虫的客户端。"""
        tasks = [scraper.close() for scraper in self.scrapers.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    def get_scraper(self, provider: str) -> BaseScraper:
        """通过名称获取指定的爬虫实例。"""
        scraper = self.scrapers.get(provider)
        if not scraper:
            raise ValueError(f"未找到提供方为 '{provider}' 的爬虫")
        return scraper