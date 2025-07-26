import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Dict, List

from .scrapers.base import BaseScraper
from .models import ProviderSearchInfo


class ScraperManager:
    def __init__(self):
        self.scrapers: Dict[str, BaseScraper] = {}
        self._load_scrapers()

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

    async def search_all(self, keyword: str) -> List[ProviderSearchInfo]:
        """
        在所有已注册的爬虫上并发搜索关键词。
        """
        if not self.scrapers:
            return []

        tasks = [scraper.search(keyword) for scraper in self.scrapers.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_search_results = []
        for i, result in enumerate(results):
            provider_name = list(self.scrapers.keys())[i]
            if isinstance(result, Exception):
                print(f"在数据源 '{provider_name}' 上搜索时出错: {result}")
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