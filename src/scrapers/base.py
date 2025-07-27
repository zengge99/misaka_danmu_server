from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from .. import models


class BaseScraper(ABC):
    """
    所有爬虫的抽象基类。
    定义了搜索媒体、获取分集和获取弹幕的通用接口。
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        数据源的唯一名称 (例如, 'tencent')。
        """
        raise NotImplementedError

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
    async def get_comments(self, episode_id: str) -> List[dict]:
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