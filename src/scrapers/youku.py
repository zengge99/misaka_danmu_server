import asyncio
import base64
import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from .. import models
from .base import BaseScraper

# --- Pydantic Models for Youku API ---

# Search
class YoukuSearchTitleDTO(BaseModel):
    display_name: str = Field(alias="displayName")

class YoukuSearchCommonData(BaseModel):
    show_id: str = Field(alias="showId")
    episode_total: int = Field(alias="episodeTotal")
    feature: str
    is_youku: int = Field(alias="isYouku")
    has_youku: int = Field(alias="hasYouku")
    title_dto: YoukuSearchTitleDTO = Field(alias="titleDTO")

class YoukuSearchComponent(BaseModel):
    common_data: Optional[YoukuSearchCommonData] = Field(None, alias="commonData")

class YoukuSearchResult(BaseModel):
    page_component_list: Optional[List[YoukuSearchComponent]] = Field(None, alias="pageComponentList")

# Episodes
class YoukuEpisodeInfo(BaseModel):
    id: str
    title: str
    duration: str
    category: str

    @property
    def total_mat(self) -> int:
        try:
            duration_float = float(self.duration)
            return int(duration_float // 60) + 1
        except (ValueError, TypeError):
            return 0

class YoukuVideoResult(BaseModel):
    total: int
    videos: List[YoukuEpisodeInfo]

# Danmaku
class YoukuCommentProperty(BaseModel):
    color: int
    pos: int
    size: int

class YoukuComment(BaseModel):
    id: int
    content: str
    playat: int # milliseconds
    propertis: str
    uid: str

class YoukuDanmakuData(BaseModel):
    result: List[YoukuComment]

class YoukuDanmakuResult(BaseModel):
    data: YoukuDanmakuData

class YoukuRpcData(BaseModel):
    result: str # This is a JSON string

class YoukuRpcResult(BaseModel):
    data: YoukuRpcData

# --- Main Scraper Class ---

class YoukuScraper(BaseScraper):
    def __init__(self):
        # Regexes from C#
        self.year_reg = re.compile(r"[12][890][0-9][0-9]")
        self.unused_words_reg = re.compile(r"<[^>]+>|【.+?】")

        self.client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"},
            timeout=20.0,
            follow_redirects=True
        )
        self.logger = logging.getLogger(__name__)

        # For danmaku signing
        self._cna = ""
        self._token = ""

    @property
    def provider_name(self) -> str:
        return "youku"

    async def close(self):
        await self.client.aclose()

    async def search(self, keyword: str, episode_info: Optional[Dict[str, Any]] = None) -> List[models.ProviderSearchInfo]:
        ua_encoded = urlencode({"userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"})
        keyword_encoded = urlencode({"keyword": keyword})
        url = f"https://search.youku.com/api/search?{keyword_encoded}&{ua_encoded}&site=1&categories=0&ftype=0&ob=0&pg=1"
        
        results = []
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = YoukuSearchResult.model_validate(response.json())

            if not data.page_component_list:
                return []

            for component in data.page_component_list:
                common_data = component.common_data
                if not common_data or not common_data.title_dto or (common_data.is_youku != 1 and common_data.has_youku != 1):
                    continue
                
                title = common_data.title_dto.display_name
                if any(kw in title for kw in ["中配版", "抢先看", "非正片", "解读", "揭秘", "赏析", "《"]):
                    continue

                year_match = self.year_reg.search(common_data.feature)
                year = int(year_match.group(0)) if year_match else None
                
                cleaned_title = self.unused_words_reg.sub("", title).strip()
                media_type = "movie" if "电影" in common_data.feature else "tv_series"
                
                current_episode = episode_info.get("episode") if episode_info else None

                results.append(models.ProviderSearchInfo(
                    provider=self.provider_name,
                    mediaId=common_data.show_id,
                    title=cleaned_title,
                    type=media_type,
                    year=year,
                    episodeCount=common_data.episode_total,
                    currentEpisodeIndex=current_episode
                ))

        except Exception as e:
            self.logger.error(f"Youku search failed for '{keyword}': {e}", exc_info=True)
        
        return results

    async def get_episodes(self, media_id: str, target_episode_index: Optional[int] = None) -> List[models.ProviderEpisodeInfo]:
        all_episodes = []
        page = 1
        page_size = 20
        total_episodes = 0

        while True:
            try:
                page_result = await self._get_episodes_page(media_id, page, page_size)
                if not page_result or not page_result.videos:
                    break
                
                if page == 1:
                    total_episodes = page_result.total

                filtered_videos = [v for v in page_result.videos if "彩蛋" not in v.title]
                all_episodes.extend(filtered_videos)

                if len(all_episodes) >= total_episodes or len(page_result.videos) < page_size:
                    break
                
                if target_episode_index and len(all_episodes) >= target_episode_index:
                    self.logger.info(f"Youku: Found target episode index {target_episode_index}, stopping pagination.")
                    break

                page += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                self.logger.error(f"Youku: Failed to get episodes page {page} for media_id {media_id}: {e}", exc_info=True)
                break
        
        provider_episodes = [
            models.ProviderEpisodeInfo(
                provider=self.provider_name,
                episodeId=ep.id.replace("=", "_"),
                title=ep.title,
                episodeIndex=i + 1
            ) for i, ep in enumerate(all_episodes)
        ]

        if target_episode_index:
            target = next((ep for ep in provider_episodes if ep.episodeIndex == target_episode_index), None)
            return [target] if target else []
            
        return provider_episodes

    async def _get_episodes_page(self, show_id: str, page: int, page_size: int) -> Optional[YoukuVideoResult]:
        url = f"https://openapi.youku.com/v2/shows/videos.json?client_id=53e6cc67237fc59a&package=com.huawei.hwvplayer.youku&ext=show&show_id={show_id}&page={page}&count={page_size}"
        response = await self.client.get(url)
        response.raise_for_status()
        return YoukuVideoResult.model_validate(response.json())

    async def get_comments(self, episode_id: str) -> List[dict]:
        vid = episode_id.replace("_", "=")
        
        try:
            await self._ensure_token_cookie()
            
            episode_info_url = f"https://openapi.youku.com/v2/videos/show_basic.json?client_id=53e6cc67237fc59a&package=com.huawei.hwvplayer.youku&video_id={vid}"
            episode_info_resp = await self.client.get(episode_info_url)
            episode_info_resp.raise_for_status()
            episode_info = YoukuEpisodeInfo.model_validate(episode_info_resp.json())
            total_mat = episode_info.total_mat

            if total_mat == 0:
                self.logger.warning(f"Youku: Video {vid} has duration 0, no danmaku to fetch.")
                return []

            all_comments = []
            for mat in range(total_mat):
                comments_in_mat = await self._get_danmu_content_by_mat(vid, mat)
                if comments_in_mat:
                    all_comments.extend(comments_in_mat)
                await asyncio.sleep(0.2)

            return self._format_comments(all_comments)

        except Exception as e:
            self.logger.error(f"Youku: Failed to get danmaku for vid {vid}: {e}", exc_info=True)
            return []

    async def _ensure_token_cookie(self):
        cna_cookie = self.client.cookies.get("cna", domain="mmstat.com")
        if not cna_cookie:
            await self.client.get("https://log.mmstat.com/eg.js")
        
        self._cna = self.client.cookies.get("cna", domain="mmstat.com") or ""

        token_cookie = self.client.cookies.get("_m_h5_tk", domain="youku.com")
        if not token_cookie:
            await self.client.get("https://acs.youku.com/h5/mtop.com.youku.aplatform.weakget/1.0/?jsv=2.5.1&appKey=24679788")
        
        self._token = (self.client.cookies.get("_m_h5_tk", domain="youku.com") or "").split("_")[0]

        if not self._cna or not self._token:
            self.logger.warning("Youku: Failed to obtain necessary cookies (cna, _m_h5_tk) for danmaku.")

    def _generate_msg_sign(self, msg_enc: str) -> str:
        s = msg_enc + "MkmC9SoIw6xCkSKHhJ7b5D2r51kBiREr"
        return hashlib.md5(s.encode('utf-8')).hexdigest().lower()

    def _generate_token_sign(self, t: str, app_key: str, data: str) -> str:
        s = "&".join([self._token, t, app_key, data])
        return hashlib.md5(s.encode('utf-8')).hexdigest().lower()

    async def _get_danmu_content_by_mat(self, vid: str, mat: int) -> List[YoukuComment]:
        if not self._token:
            self.logger.error("Youku: Cannot get danmaku, _m_h5_tk is missing.")
            return []

        ctime = int(time.time() * 1000)
        msg = {
            "pid": 0, "ctype": 10004, "sver": "3.1.0", "cver": "v1.0",
            "ctime": ctime, "guid": self._cna, "vid": vid, "mat": mat,
            "mcount": 1, "type": 1
        }
        msg_ordered_str = json.dumps(dict(sorted(msg.items())), separators=(',', ':'))
        msg_enc = base64.b64encode(msg_ordered_str.encode('utf-8')).decode('utf-8')
        
        msg['msg'] = msg_enc
        msg['sign'] = self._generate_msg_sign(msg_enc)
        
        app_key = "24679788"
        data_payload = json.dumps(msg, separators=(',', ':'))
        t = str(int(time.time() * 1000))
        
        params = {
            "jsv": "2.7.0",
            "appKey": app_key,
            "t": t,
            "sign": self._generate_token_sign(t, app_key, data_payload),
            "api": "mopen.youku.danmu.list",
            "v": "1.0",
            "type": "originaljson",
            "dataType": "jsonp",
            "timeout": "20000",
            "jsonpIncPrefix": "utility"
        }
        
        url = f"https://acs.youku.com/h5/mopen.youku.danmu.list/1.0/?{urlencode(params)}"
        
        response = await self.client.post(
            url,
            data={"data": data_payload},
            headers={"Referer": "https://v.youku.com"}
        )
        response.raise_for_status()
        
        jsonp_text = response.text
        match = re.search(r'utility\d+\((.*)\)', jsonp_text)
        if not match:
            self.logger.warning(f"Youku: Danmaku response is not valid JSONP: {jsonp_text[:200]}")
            return []
        
        json_str = match.group(1)
        rpc_result = YoukuRpcResult.model_validate(json.loads(json_str))
        
        if rpc_result.data and rpc_result.data.result:
            try:
                comment_result = YoukuDanmakuResult.model_validate(json.loads(rpc_result.data.result))
                if comment_result.data and comment_result.data.result:
                    return comment_result.data.result
            except (json.JSONDecodeError, ValidationError) as e:
                self.logger.error(f"Youku: Failed to parse inner danmaku result string: {e}")
        
        return []

    def _format_comments(self, comments: List[YoukuComment]) -> List[dict]:
        formatted = []
        for c in comments:
            mode = 1
            color = 16777215
            
            try:
                props = json.loads(c.propertis)
                prop_model = YoukuCommentProperty.model_validate(props)
                color = prop_model.color
                if prop_model.pos == 1: mode = 5
                elif prop_model.pos == 2: mode = 4
            except (json.JSONDecodeError, ValidationError):
                pass

            timestamp = c.playat / 1000.0
            p_string = f"{timestamp},{mode},{color},{self.provider_name}"
            formatted.append({"cid": str(c.id), "p": p_string, "m": c.content, "t": timestamp})
        return formatted