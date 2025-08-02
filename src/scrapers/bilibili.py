import asyncio
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urlencode
from datetime import datetime

import aiomysql
import httpx
from pydantic import BaseModel, Field, ValidationError

# --- Start of merged dm_dynamic.py content ---
# This block dynamically generates the Protobuf message classes required for Bilibili's danmaku API.
# It's placed here to encapsulate the logic within the only scraper that uses it,
# simplifying the project structure by removing the need for a separate dm_dynamic.py file.
from google.protobuf.descriptor_pb2 import FileDescriptorProto
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message_factory import MessageFactory

# 1. Create a FileDescriptorProto object, which is a protobuf message itself.
# This describes the .proto file in a structured way.
file_descriptor_proto = FileDescriptorProto()
file_descriptor_proto.name = 'dm.proto'
file_descriptor_proto.package = 'biliproto.community.service.dm.v1'
file_descriptor_proto.syntax = 'proto3'

# 2. Define the 'DanmakuElem' message
danmaku_elem_desc = file_descriptor_proto.message_type.add()
danmaku_elem_desc.name = 'DanmakuElem'
danmaku_elem_desc.field.add(name='id', number=1, type=3)  # TYPE_INT64
danmaku_elem_desc.field.add(name='progress', number=2, type=5)  # TYPE_INT32
danmaku_elem_desc.field.add(name='mode', number=3, type=5)  # TYPE_INT32
danmaku_elem_desc.field.add(name='fontsize', number=4, type=5)  # TYPE_INT32
danmaku_elem_desc.field.add(name='color', number=5, type=13)  # TYPE_UINT32
danmaku_elem_desc.field.add(name='midHash', number=6, type=9)  # TYPE_STRING
danmaku_elem_desc.field.add(name='content', number=7, type=9)  # TYPE_STRING
danmaku_elem_desc.field.add(name='ctime', number=8, type=3)  # TYPE_INT64
danmaku_elem_desc.field.add(name='weight', number=9, type=5)  # TYPE_INT32
danmaku_elem_desc.field.add(name='action', number=10, type=9)  # TYPE_STRING
danmaku_elem_desc.field.add(name='pool', number=11, type=5)  # TYPE_INT32
danmaku_elem_desc.field.add(name='idStr', number=12, type=9)  # TYPE_STRING
danmaku_elem_desc.field.add(name='attr', number=13, type=5)  # TYPE_INT32
danmaku_elem_desc.field.add(name='animation', number=14, type=9) # TYPE_STRING
danmaku_elem_desc.field.add(name='like_num', number=15, type=13) # TYPE_UINT32
danmaku_elem_desc.field.add(name='color_v2', number=16, type=9) # TYPE_STRING
danmaku_elem_desc.field.add(name='dm_type_v2', number=17, type=13) # TYPE_UINT32

# 3. Define the 'Flag' message
flag_desc = file_descriptor_proto.message_type.add()
flag_desc.name = 'Flag'
flag_desc.field.add(name='value', number=1, type=5)  # TYPE_INT32
flag_desc.field.add(name='description', number=2, type=9)  # TYPE_STRING

# 4. Define the 'DmSegMobileReply' message
dm_seg_reply_desc = file_descriptor_proto.message_type.add()
dm_seg_reply_desc.name = 'DmSegMobileReply'
elems_field = dm_seg_reply_desc.field.add(name='elems', number=1, type=11, type_name='.biliproto.community.service.dm.v1.DanmakuElem')
elems_field.label = 3  # LABEL_REPEATED
dm_seg_reply_desc.field.add(name='state', number=2, type=5)  # TYPE_INT32
ai_flag_field = dm_seg_reply_desc.field.add(name='ai_flag_for_summary', number=3, type=11, type_name='.biliproto.community.service.dm.v1.Flag')

# 5. Build the descriptors and create message classes
pool = DescriptorPool()
pool.Add(file_descriptor_proto)
factory = MessageFactory(pool)

# 6. Get the prototype message classes using the hashable descriptors
danmaku_elem_descriptor = pool.FindMessageTypeByName('biliproto.community.service.dm.v1.DanmakuElem')
flag_descriptor = pool.FindMessageTypeByName('biliproto.community.service.dm.v1.Flag')
dm_seg_reply_descriptor = pool.FindMessageTypeByName('biliproto.community.service.dm.v1.DmSegMobileReply')
DanmakuElem = factory.GetPrototype(danmaku_elem_descriptor)
Flag = factory.GetPrototype(flag_descriptor)
DmSegMobileReply = factory.GetPrototype(dm_seg_reply_descriptor)
# --- End of merged dm_dynamic.py content ---

from .. import models
from .base import BaseScraper

# --- Pydantic Models for Bilibili API ---

class BiliSearchMedia(BaseModel):
    media_id: Optional[int] = None
    season_id: Optional[int] = None
    title: str
    pubtime: Optional[int] = 0
    pubdate: Union[str, int, None] = None
    season_type_name: Optional[str] = Field(None, alias="season_type_name")
    ep_size: Optional[int] = None
    bvid: Optional[str] = None
    goto_url: Optional[str] = None
    cover: Optional[str] = None

class BiliSearchGroup(BaseModel):
    result_type: str = Field(alias="result_type")
    data: Optional[List[BiliSearchMedia]] = None

class BiliSearchData(BaseModel):
    result: Optional[List[BiliSearchGroup]] = None

class BiliApiResult(BaseModel):
    code: int
    message: str
    data: Optional[BiliSearchData] = None

class BiliEpisode(BaseModel):
    id: int  # ep_id
    aid: int
    cid: int
    bvid: str
    title: str
    long_title: str

class BiliSeasonData(BaseModel):
    episodes: List[BiliEpisode]

class BiliSeasonResult(BaseModel):
    code: int
    message: str
    result: Optional[BiliSeasonData] = None

class BiliVideoPart(BaseModel):
    cid: int
    page: int
    part: str

class BiliVideoViewData(BaseModel):
    bvid: str
    aid: int
    title: str
    pic: str
    pages: List[BiliVideoPart]

class BiliVideoViewResult(BaseModel):
    code: int
    message: str
    data: Optional[BiliVideoViewData] = None

# --- Main Scraper Class ---

class BilibiliScraper(BaseScraper):
    provider_name = "bilibili"

    def __init__(self, pool: aiomysql.Pool):
        super().__init__(pool)
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
            },
            timeout=20.0,
            follow_redirects=True,
        )

    async def close(self):
        await self.client.aclose()

    async def _ensure_session_cookie(self):
        if "buvid3" in self.client.cookies:
            return
        try:
            await self.client.get("https://www.bilibili.com/")
            self.logger.info("Bilibili: 成功获取会话Cookie (buvid3)。")
        except Exception as e:
            self.logger.warning(f"Bilibili: 获取会话Cookie失败: {e}")

    async def search(self, keyword: str, episode_info: Optional[Dict[str, Any]] = None) -> List[models.ProviderSearchInfo]:
        cache_key = f"search_{self.provider_name}_{keyword}"
        cached_results = await self._get_from_cache(cache_key)
        if cached_results is not None:
            return [models.ProviderSearchInfo.model_validate(r) for r in cached_results]

        await self._ensure_session_cookie()
        url = f"https://api.bilibili.com/x/web-interface/search/all/v2?keyword={urlencode({'keyword': keyword})[8:]}"
        
        results = []
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            api_result = BiliApiResult.model_validate(response.json())

            if api_result.code == 0 and api_result.data and api_result.data.result:
                for group in api_result.data.result:
                    if group.result_type in ["media_bangumi", "media_ft"] and group.data:
                        for item in group.data:
                            media_id = ""
                            media_type = "tv_series"
                            if group.result_type == "media_bangumi" and item.season_id:
                                media_id = f"ss{item.season_id}"
                            elif group.result_type == "media_ft" and item.bvid:
                                media_id = f"bv{item.bvid}"
                                if item.season_type_name == "电影":
                                    media_type = "movie"
                            
                            if not media_id: continue

                            year = None
                            try:
                                if item.pubdate:
                                    if isinstance(item.pubdate, int):
                                        year = datetime.fromtimestamp(item.pubdate).year
                                    elif isinstance(item.pubdate, str) and len(item.pubdate) >= 4:
                                        year = int(item.pubdate[:4])
                                elif item.pubtime:
                                    year = datetime.fromtimestamp(item.pubtime).year
                            except (ValueError, TypeError, OSError):
                                pass

                            results.append(models.ProviderSearchInfo(
                                provider=self.provider_name,
                                mediaId=media_id,
                                title=re.sub(r'<.*?>', '', item.title).replace(":", "："),
                                type=media_type,
                                year=year,
                                imageUrl=item.cover,
                                episodeCount=item.ep_size,
                                currentEpisodeIndex=episode_info.get("episode") if episode_info else None
                            ))
        except Exception as e:
            self.logger.error(f"Bilibili: 搜索 '{keyword}' 失败: {e}", exc_info=True)

        await self._set_to_cache(cache_key, [r.model_dump() for r in results], 'search_ttl_seconds', 300)
        return results

    async def get_episodes(self, media_id: str, target_episode_index: Optional[int] = None, db_media_type: Optional[str] = None) -> List[models.ProviderEpisodeInfo]:
        if media_id.startswith("ss"):
            return await self._get_pgc_episodes(media_id, target_episode_index)
        elif media_id.startswith("bv"):
            return await self._get_ugc_episodes(media_id, target_episode_index)
        return []

    async def _get_pgc_episodes(self, media_id: str, target_episode_index: Optional[int] = None) -> List[models.ProviderEpisodeInfo]:
        season_id = media_id[2:]
        url = f"https://api.bilibili.com/pgc/view/web/ep/list?season_id={season_id}"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = BiliSeasonResult.model_validate(response.json())
            if data.code == 0 and data.result and data.result.episodes:
                episodes = [
                    models.ProviderEpisodeInfo(
                        provider=self.provider_name,
                        episodeId=f"{ep.aid},{ep.cid}",
                        title=ep.long_title or ep.title,
                        episodeIndex=i + 1,
                        url=f"https://www.bilibili.com/bangumi/play/ep{ep.id}"
                    ) for i, ep in enumerate(data.result.episodes)
                ]
                if target_episode_index:
                    return [ep for ep in episodes if ep.episodeIndex == target_episode_index]
                return episodes
        except Exception as e:
            self.logger.error(f"Bilibili: 获取PGC分集列表失败 (media_id={media_id}): {e}", exc_info=True)
        return []

    async def _get_ugc_episodes(self, media_id: str, target_episode_index: Optional[int] = None) -> List[models.ProviderEpisodeInfo]:
        bvid = media_id[2:]
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = BiliVideoViewResult.model_validate(response.json())
            if data.code == 0 and data.data and data.data.pages:
                aid = data.data.aid
                episodes = [
                    models.ProviderEpisodeInfo(
                        provider=self.provider_name,
                        episodeId=f"{aid},{p.cid}",
                        title=p.part,
                        episodeIndex=p.page,
                        url=f"https://www.bilibili.com/video/{bvid}?p={p.page}"
                    ) for p in data.data.pages
                ]
                if target_episode_index:
                    return [ep for ep in episodes if ep.episodeIndex == target_episode_index]
                return episodes
        except Exception as e:
            self.logger.error(f"Bilibili: 获取UGC分集列表失败 (media_id={media_id}): {e}", exc_info=True)
        return []

    async def get_comments(self, episode_id: str, progress_callback: Optional[Callable] = None) -> List[dict]:
        try:
            aid_str, cid_str = episode_id.split(',')
            aid, cid = int(aid_str), int(cid_str)
        except (ValueError, IndexError):
            self.logger.error(f"Bilibili: 无效的 episode_id 格式: '{episode_id}'")
            return []

        all_comments = []
        segment_index = 1
        while True:
            try:
                if progress_callback:
                    # 无法预知总分段数，只能显示当前正在获取哪个
                    progress_callback(min(95, segment_index * 10), f"正在获取分段 {segment_index}")

                url = f"https://api.bilibili.com/x/v2/dm/web/seg.so?type=1&oid={cid}&pid={aid}&segment_index={segment_index}"
                response = await self.client.get(url)
                
                if response.status_code == 304: # Not Modified
                    self.logger.info(f"Bilibili: 弹幕分段 {segment_index} 未修改，获取结束。")
                    break
                response.raise_for_status()
                if not response.content:
                    self.logger.info(f"Bilibili: 弹幕分段 {segment_index} 内容为空，获取结束。")
                    break
                
                danmu_reply = DmSegMobileReply()
                danmu_reply.ParseFromString(response.content)

                if not danmu_reply.elems:
                    break

                all_comments.extend(danmu_reply.elems)
                segment_index += 1
                await asyncio.sleep(0.2)

            except httpx.HTTPStatusError as e:
                # B站有时对不存在的分段返回404，这是正常的结束标志
                if e.response.status_code == 404:
                    self.logger.info(f"Bilibili: 找不到弹幕分段 {segment_index}，获取结束。")
                    break
                self.logger.error(f"Bilibili: 获取弹幕分段 {segment_index} 失败: {e}", exc_info=True)
                break # 出错时终止
            except Exception as e:
                self.logger.error(f"Bilibili: 处理弹幕分段 {segment_index} 时出错: {e}", exc_info=True)
                break

        if progress_callback:
            progress_callback(100, "弹幕整合完成")

        return self._format_comments(all_comments)

    def _format_comments(self, comments: List[DanmakuElem]) -> List[dict]:
        formatted = []
        for c in comments:
            timestamp = c.progress / 1000.0
            p_string = f"{timestamp:.3f},{c.mode},{c.fontsize},{c.color},[{self.provider_name}]"
            formatted.append({
                "cid": str(c.id),
                "p": p_string,
                "m": c.content,
                "t": timestamp
            })
        return formatted