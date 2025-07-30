import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

import aiomysql
from .. import crud
from .. import models


class BaseScraper(ABC):
    """
    所有爬虫的抽象基类。
    定义了搜索媒体、获取分集和获取弹幕的通用接口。
    """

    def __init__(self, pool: aiomysql.Pool):
        self.pool = pool
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ttl_config: Dict[str, int] = {} # 用于缓存从数据库读取的TTL值

    async def _get_ttl(self, key: str, default: int) -> int:
        """获取并缓存TTL配置值。"""
        if key not in self.ttl_config:
            ttl_str = await crud.get_config_value(self.pool, key, str(default))
            self.ttl_config[key] = int(ttl_str)
        return self.ttl_config[key]

    async def _get_from_cache(self, key: str) -> Optional[Any]:
        """从数据库缓存中获取数据。"""
        return await crud.get_cache(self.pool, key)

    async def _set_to_cache(self, key: str, value: Any, config_key: str, default_ttl: int):
        """将数据存入数据库缓存，TTL从配置中读取。"""
        ttl = await self._get_ttl(config_key, default_ttl)
        if ttl > 0:
            await crud.set_cache(self.pool, key, value, ttl, provider=self.provider_name)

    # 每个子类都必须覆盖这个类属性
    provider_name: str

    @abstractmethod
    async def search(self, keyword: str, episode_info: Optional[Dict[str, Any]] = None) -> List[models.ProviderSearchInfo]:
        """
        根据关键词搜索媒体。
        episode_info: 可选字典，包含 'season' 和 'episode'。
        """
        raise NotImplementedError

    @abstractmethod
    async def get_episodes(self, media_id: str, target_episode_index: Optional[int] = None) -> List[models.ProviderEpisodeInfo]:
        """
        获取给定媒体ID的所有分集。
        如果提供了 target_episode_index，则可以优化为只获取到该分集为止。
        """
        raise NotImplementedError

    @abstractmethod
    async def get_comments(self, episode_id: str, progress_callback: Optional[Callable] = None) -> List[dict]:
        """
        获取给定分集ID的所有弹幕。
        返回的字典列表应与 crud.bulk_insert_comments 的期望格式兼容。
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self):
        """
        关闭所有打开的资源，例如HTTP客户端。
        """
        raise NotImplementedError