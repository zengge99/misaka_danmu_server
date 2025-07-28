import asyncio
import importlib
import inspect
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
            module = importlib.import_module(module_name, package="src")
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseScraper) and obj is not BaseScraper:
                    provider_name = obj().provider_name # 临时实例化以获取名称
                    discovered_providers.append(provider_name)
                    scraper_classes[provider_name] = obj
        
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

    async def search_all(self, keyword: str, episode_info: Optional[Dict[str, Any]] = None) -> List[ProviderSearchInfo]:
        """
        在所有已注册的爬虫上并发搜索关键词。
        """
        if not self.scrapers:
            return []

        # 将爬虫实例和它们的搜索任务一起创建，以便后续处理
        scraper_instances = list(self.scrapers.values())
        tasks = [scraper.search(keyword, episode_info=episode_info) for scraper in scraper_instances]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_search_results = []
        # 使用 zip 将爬虫实例和其对应的结果安全地配对
        for scraper, result in zip(scraper_instances, results):
            if isinstance(result, Exception):
                print(f"在数据源 '{scraper.provider_name}' 上搜索时出错: {result}")
            elif result:
                all_search_results.extend(result)

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