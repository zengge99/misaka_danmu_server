import asyncio
import logging
import re
import json
import zlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError

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
    tv_id: int = Field(alias="tvId")
    video_name: str = Field(alias="videoName")
    video_url: str = Field(alias="videoUrl")
    channel_name: str = Field(alias="channelName")
    duration: int
    video_count: int = 0

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

class IqiyiComment(BaseModel):
    content_id: str = Field(alias="contentId")
    content: str
    show_time: int = Field(alias="showTime")
    color: str
    uid: str

# --- Main Scraper Class ---

class IqiyiScraper(BaseScraper):
    def __init__(self):
        self.mobile_user_agent = "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36 Edg/136.0.0.0"
        self.reg_video_info = re.compile(r'"videoInfo":(\{.+?\}),')
        self.reg_album_info = re.compile(r'"albumInfo":(\{.+?\}),')

        self.client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
        self.logger = logging.getLogger(__name__)

    @property
    def provider_name(self) -> str:
        return "iqiyi"

    async def close(self):
        await self.client.aclose()

    async def search(self, keyword: str, episode_info: Optional[Dict[str, Any]] = None) -> List[models.ProviderSearchInfo]:
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
        
        return results

    async def _get_video_base_info(self, link_id: str) -> Optional[IqiyiHtmlVideoInfo]:
        url = f"https://m.iqiyi.com/v_{link_id}.html"
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
            
            return video_info
        except Exception as e:
            self.logger.error(f"爱奇艺: 获取 link_id {link_id} 的基础信息失败: {e}", exc_info=True)
            return None

    async def _get_tv_episodes(self, album_id: int, size: int) -> List[IqiyiEpisodeInfo]:
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
        base_info = await self._get_video_base_info(media_id)
        if not base_info:
            return []

        episodes: List[IqiyiEpisodeInfo] = []
        if base_info.channel_name == "电影":
            episodes.append(IqiyiEpisodeInfo(
                tv_id=base_info.tv_id,
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

            decompressed_data = zlib.decompress(response.content)
            root = ET.fromstring(decompressed_data)
            
            comments = []
            for entry in root.findall('entry'):
                for item in entry.findall('list/item'):
                    content_id_node = item.find('contentId')
                    content_node = item.find('content')
                    show_time_node = item.find('showTime')
                    color_node = item.find('color')
                    uid_node = item.find('userInfo/uid')

                    if all(n is not None and n.text for n in [content_id_node, content_node, show_time_node, color_node, uid_node]):
                        comments.append(IqiyiComment(
                            contentId=content_id_node.text,
                            content=content_node.text,
                            showTime=int(show_time_node.text),
                            color=color_node.text,
                            uid=uid_node.text
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