import asyncio
import logging
import aiomysql
import re
import json
from typing import ClassVar
import zlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator

from .. import models
from .base import BaseScraper

# --- Pydantic Models for iQiyi API ---

class IqiyiSearchVideoInfo(BaseModel):
    item_link: str = Field(alias="itemLink")

class IqiyiSearchAlbumInfo(BaseModel):
    album_id: int = Field(alias="albumId")
    item_total_number: Optional[int] = Field(None, alias="itemTotalNumber")
    site_id: str = Field(alias="siteId")
    album_link: str = Field(alias="albumLink")
    video_doc_type: int = Field(alias="videoDocType")
    album_title: str = Field(alias="albumTitle")
    channel: str
    release_date: Optional[str] = Field(None, alias="releaseDate")
    album_img: Optional[str] = Field(None, alias="albumImg")
    videoinfos: Optional[List[IqiyiSearchVideoInfo]] = None

    @property
    def link_id(self) -> Optional[str]:
        link_to_parse = self.album_link
        if self.videoinfos and self.videoinfos[0].item_link:
            link_to_parse = self.videoinfos[0].item_link

        match = re.search(r"v_(\w+?)\.html", link_to_parse)
        return match.group(1).strip() if match else None

    @property
    def year(self) -> Optional[int]:
        if self.release_date and len(self.release_date) >= 4:
            try:
                return int(self.release_date[:4])
            except ValueError:
                return None
        return None

class IqiyiAlbumDoc(BaseModel):
    score: float
    album_doc_info: IqiyiSearchAlbumInfo = Field(alias="albumDocInfo")

class IqiyiSearchDoc(BaseModel):
    docinfos: List[IqiyiAlbumDoc]

class IqiyiSearchResult(BaseModel):
    data: IqiyiSearchDoc

class IqiyiHtmlAlbumInfo(BaseModel):
    video_count: int = Field(alias="videoCount")

class IqiyiHtmlVideoInfo(BaseModel):
    album_id: int = Field(alias="albumQipuId")
    tv_id: Optional[int] = Field(None, alias="tvId")
    video_id: Optional[int] = Field(None, alias="videoId")
    video_name: str = Field(alias="videoName")
    video_url: str = Field(alias="videoUrl")
    channel_name: str = Field(alias="channelName")
    duration: int
    video_count: int = 0

    @model_validator(mode='after')
    def merge_ids(self) -> 'IqiyiHtmlVideoInfo':
        if self.tv_id is None and self.video_id is not None:
            self.tv_id = self.video_id
        return self

class IqiyiEpisodeInfo(BaseModel):
    tv_id: int = Field(alias="tvId")
    name: str
    order: int
    play_url: str = Field(alias="playUrl")

    @property
    def link_id(self) -> Optional[str]:
        match = re.search(r"v_(\w+?)\.html", self.play_url)
        return match.group(1).strip() if match else None

class IqiyiVideoData(BaseModel):
    epsodelist: List[IqiyiEpisodeInfo]

class IqiyiVideoResult(BaseModel):
    data: IqiyiVideoData

class IqiyiUserInfo(BaseModel):
    uid: str

class IqiyiComment(BaseModel):
    content_id: str = Field(alias="contentId")
    content: str
    show_time: int = Field(alias="showTime")
    color: str
    # user_info 字段在XML中可能不存在，设为可选
    user_info: Optional[IqiyiUserInfo] = Field(None, alias="userInfo")

# --- Main Scraper Class ---

class IqiyiScraper(BaseScraper):
    provider_name = "iqiyi"

    def __init__(self, pool: aiomysql.Pool):
        super().__init__(pool)
        self.mobile_user_agent = "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36 Edg/136.0.0.0"
        self.reg_video_info = re.compile(r'"videoInfo":(\{.+?\}),')
        self.reg_album_info = re.compile(r'"albumInfo":(\{.+?\}),')

        self.client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)

    async def close(self):
        await self.client.aclose()

    async def search(self, keyword: str, episode_info: Optional[Dict[str, Any]] = None) -> List[models.ProviderSearchInfo]:
        cache_key = f"search_{keyword}"
        cached_results = await self._get_from_cache(cache_key)
        if cached_results is not None:
            self.logger.info(f"爱奇艺: 从缓存中命中搜索结果 '{keyword}'")
            return [models.ProviderSearchInfo.model_validate(r) for r in cached_results]

        url = f"https://search.video.iqiyi.com/o?if=html5&key={keyword}&pageNum=1&pageSize=20"
        results = []
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = IqiyiSearchResult.model_validate(response.json())

            if not data.data or not data.data.docinfos:
                return []

            for doc in data.data.docinfos:
                if doc.score < 0.7: continue
                
                album = doc.album_doc_info
                if not ("iqiyi.com" in album.album_link and album.site_id == "iqiyi" and album.video_doc_type == 1):
                    continue
                if "原创" in album.channel or "教育" in album.channel:
                    continue

                link_id = album.link_id
                if not link_id:
                    continue

                channel_name = album.channel.split(',')[0]
                media_type = "movie" if channel_name == "电影" else "tv_series"

                results.append(models.ProviderSearchInfo(
                    provider=self.provider_name,
                    mediaId=link_id,
                    title=album.album_title,
                    type=media_type,
                    year=album.year,
                    imageUrl=album.album_img,
                    episodeCount=album.item_total_number,
                ))

        except Exception as e:
            self.logger.error(f"爱奇艺: 搜索 '{keyword}' 失败: {e}", exc_info=True)

        results_to_cache = [r.model_dump() for r in results]
        await self._set_to_cache(cache_key, results_to_cache, 'search_ttl_seconds', 300)
        return results

    async def _get_video_base_info(self, link_id: str) -> Optional[IqiyiHtmlVideoInfo]:
        cache_key = f"base_info_{link_id}"
        cached_info = await self._get_from_cache(cache_key)
        if cached_info is not None:
            self.logger.info(f"爱奇艺: 从缓存中命中基础信息 (link_id={link_id})")
            return IqiyiHtmlVideoInfo.model_validate(cached_info)

        url = f"https://m.iqiyi.com/v_{link_id}.html"
        # 模仿 C# 代码中的 LimitRequestFrequently
        await asyncio.sleep(1)
        try:
            response = await self.client.get(url, headers={"User-Agent": self.mobile_user_agent})
            response.raise_for_status()
            html = response.text

            video_match = self.reg_video_info.search(html)
            album_match = self.reg_album_info.search(html)

            if not video_match:
                self.logger.warning(f"爱奇艺: 在 link_id {link_id} 的HTML中找不到 videoInfo JSON")
                return None

            video_info = IqiyiHtmlVideoInfo.model_validate(json.loads(video_match.group(1)))
            if album_match:
                album_info = IqiyiHtmlAlbumInfo.model_validate(json.loads(album_match.group(1)))
                video_info.video_count = album_info.video_count
            
            info_to_cache = video_info.model_dump()
            await self._set_to_cache(cache_key, info_to_cache, 'base_info_ttl_seconds', 1800)
            return video_info
        except Exception as e:
            self.logger.error(f"爱奇艺: 获取 link_id {link_id} 的基础信息失败: {e}", exc_info=True)
            return None

    async def _get_tv_episodes(self, album_id: int, size: int) -> List[IqiyiEpisodeInfo]:
        # 这个函数被 get_episodes 调用，缓存应该在 get_episodes 层面处理
        url = f"https://pcw-api.iqiyi.com/albums/album/avlistinfo?aid={album_id}&page=1&size={size}"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = IqiyiVideoResult.model_validate(response.json())
            return data.data.epsodelist if data.data else []
        except Exception as e:
            self.logger.error(f"爱奇艺: 获取剧集列表失败 (album_id: {album_id}): {e}", exc_info=True)
            return []

    async def get_episodes(self, media_id: str, target_episode_index: Optional[int] = None) -> List[models.ProviderEpisodeInfo]:
        # 仅当请求完整列表时才使用缓存
        cache_key = f"episodes_{media_id}"
        if target_episode_index is None:
            cached_episodes = await self._get_from_cache(cache_key)
            if cached_episodes is not None:
                self.logger.info(f"爱奇艺: 从缓存中命中分集列表 (media_id={media_id})")
                return [models.ProviderEpisodeInfo.model_validate(e) for e in cached_episodes]

        base_info = await self._get_video_base_info(media_id)
        if not base_info:
            return []

        episodes: List[IqiyiEpisodeInfo] = []
        if base_info.channel_name == "电影":
            episodes.append(IqiyiEpisodeInfo(
                tv_id=base_info.tv_id or 0, # 确保 tv_id 不为 None，模仿 C# long 的默认值 0
                name=base_info.video_name,
                order=1,
                play_url=base_info.video_url
            ))
        elif base_info.channel_name == "电视剧" or base_info.channel_name == "动漫":
            episodes = await self._get_tv_episodes(base_info.album_id, base_info.video_count)
        else: # 综艺等其他类型暂不处理，C#代码中综艺逻辑复杂且易出错
            self.logger.warning(f"爱奇艺: 不支持的频道类型 '{base_info.channel_name}'，无法获取分集。")
            # 尝试使用电视剧逻辑获取，可能对某些频道有效
            episodes = await self._get_tv_episodes(base_info.album_id, base_info.video_count)

        provider_episodes = [
            models.ProviderEpisodeInfo(
                provider=self.provider_name,
                episodeId=str(ep.tv_id), # Use tv_id for danmaku
                title=ep.name,
                episodeIndex=ep.order,
                url=ep.play_url
            ) for ep in episodes if ep.link_id
        ]

        if target_episode_index is None:
            episodes_to_cache = [e.model_dump() for e in provider_episodes]
            await self._set_to_cache(cache_key, episodes_to_cache, 'episodes_ttl_seconds', 1800)

        if target_episode_index:
            target = next((ep for ep in provider_episodes if ep.episodeIndex == target_episode_index), None)
            return [target] if target else []

        return provider_episodes

    async def _get_danmu_content_by_mat(self, tv_id: str, mat: int) -> List[IqiyiComment]:
        if len(tv_id) < 4: return []
        
        s1 = tv_id[-4:-2]
        s2 = tv_id[-2:]
        url = f"http://cmts.iqiyi.com/bullet/{s1}/{s2}/{tv_id}_300_{mat}.z"
        
        try:
            response = await self.client.get(url)
            if response.status_code == 404:
                self.logger.info(f"爱奇艺: 找不到 tvId {tv_id} 的弹幕分段 {mat}，停止获取。")
                return [] # 404 means no more segments
            response.raise_for_status()

            # 根据用户的反馈，恢复为标准的 zlib 解压方式。
            decompressed_data = zlib.decompress(response.content)

            # 增加显式的UTF-8解析器以提高健壮性
            parser = ET.XMLParser(encoding="utf-8")
            root = ET.fromstring(decompressed_data, parser=parser)
            
            comments = []
            # 关键修复：根据日志，弹幕信息在 <bulletInfo> 标签内
            for item in root.findall('.//bulletInfo'):
                content_node = item.find('content')
                show_time_node = item.find('showTime')

                # 核心字段必须存在
                if not (content_node is not None and content_node.text and show_time_node is not None and show_time_node.text):
                    continue
                
                # 安全地获取可选字段
                content_id_node = item.find('contentId')
                color_node = item.find('color')
                user_info_node = item.find('userInfo')
                uid_node = user_info_node.find('uid') if user_info_node is not None else None

                comments.append(IqiyiComment(
                    contentId=content_id_node.text if content_id_node is not None and content_id_node.text else "0",
                    content=content_node.text,
                    showTime=int(show_time_node.text),
                    color=color_node.text if color_node is not None and color_node.text else "ffffff",
                    userInfo=IqiyiUserInfo(uid=uid_node.text) if uid_node is not None and uid_node.text else None
                ))
            return comments
        except zlib.error:
            self.logger.warning(f"爱奇艺: 解压 tvId {tv_id} 的弹幕分段 {mat} 失败，文件可能为空或已损坏。")
        except ET.ParseError:
            self.logger.warning(f"爱奇艺: 解析 tvId {tv_id} 的弹幕分段 {mat} 的XML失败。")
        except Exception as e:
            self.logger.error(f"爱奇艺: 获取 tvId {tv_id} 的弹幕分段 {mat} 时出错: {e}", exc_info=True)
        
        return []

    async def get_comments(self, episode_id: str) -> List[dict]:
        tv_id = episode_id # For iqiyi, episodeId is tvId
        all_comments = []
        
        # iqiyi danmaku is fetched in 300-second segments (5 minutes)
        # We loop through segments until we get an empty response or a 404
        for mat in range(1, 100): # Limit to 500 minutes to prevent infinite loops
            comments_in_mat = await self._get_danmu_content_by_mat(tv_id, mat)
            if not comments_in_mat:
                break
            all_comments.extend(comments_in_mat)
            await asyncio.sleep(0.1) # Be nice to the server

        return self._format_comments(all_comments)

    def _format_comments(self, comments: List[IqiyiComment]) -> List[dict]:
        formatted = []
        for c in comments:
            mode = 1 # Default scroll
            try:
                color = int(c.color, 16)
            except (ValueError, TypeError):
                color = 16777215 # Default white

            timestamp = float(c.show_time)
            p_string = f"{timestamp},{mode},{color},[{self.provider_name}]"
            formatted.append({
                "cid": c.content_id,
                "p": p_string,
                "m": c.content,
                "t": timestamp
            })
        return formatted