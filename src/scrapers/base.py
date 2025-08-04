import logging
import time
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type

import aiomysql
from .. import crud
from .. import models


def _roman_to_int(s: str) -> int:
    """将罗马数字字符串转换为整数。"""
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    s = s.upper()
    result = 0
    i = 0
    while i < len(s):
        # 处理减法规则 (e.g., IV, IX)
        if i + 1 < len(s) and roman_map[s[i]] < roman_map[s[i+1]]:
            result += roman_map[s[i+1]] - roman_map[s[i]]
            i += 2
        else:
            result += roman_map[s[i]]
            i += 1
    return result

def get_season_from_title(title: str) -> int:
    """从标题中解析季度信息，返回季度数。"""
    if not title:
        return 1
    
    # 模式的顺序很重要
    patterns = [
        (re.compile(r"(?:S|Season)\s*(\d+)", re.I), lambda m: int(m.group(1))),
        (re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*[季部]", re.I), 
         lambda m: {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}.get(m.group(1)) or int(m.group(1))),
        (re.compile(r"\s+([Ⅰ-Ⅻ])\b", re.I), 
         lambda m: {'Ⅰ': 1, 'Ⅱ': 2, 'Ⅲ': 3, 'Ⅳ': 4, 'Ⅴ': 5, 'Ⅵ': 6, 'Ⅶ': 7, 'Ⅷ': 8, 'Ⅸ': 9, 'Ⅹ': 10, 'Ⅺ': 11, 'Ⅻ': 12}.get(m.group(1).upper())),
        (re.compile(r"\s+([IVXLCDM]+)$", re.I), lambda m: _roman_to_int(m.group(1))),
    ]

    for pattern, handler in patterns:
        match = pattern.search(title)
        if match:
            try:
                if season := handler(match): return season
            except (ValueError, KeyError, IndexError):
                continue
    return 1 # Default to season 1

class BaseScraper(ABC):
    """
    所有搜索源的抽象基类。
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
    async def get_episodes(self, media_id: str, target_episode_index: Optional[int] = None, db_media_type: Optional[str] = None) -> List[models.ProviderEpisodeInfo]:
        """
        获取给定媒体ID的所有分集。
        如果提供了 target_episode_index，则可以优化为只获取到该分集为止。
        db_media_type: 从数据库中读取的媒体类型 ('movie', 'tv_series')，可用于指导刮削策略。
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