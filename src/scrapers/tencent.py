import asyncio
import httpx
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError
from datetime import datetime

from .base import BaseScraper
from .. import models

# --- Pydantic 模型，用于解析腾讯API的响应 ---

# --- Models for Get Comments API ---
class TencentCommentContentStyle(BaseModel):
    color: Optional[str] = None
    position: Optional[int] = None

class TencentEpisode(BaseModel):
    vid: str = Field(..., description="分集视频ID")
    title: str = Field(..., description="分集标题")
    is_trailer: str = Field("0", alias="isTrailer")

class TencentComment(BaseModel):
    id: str = Field(..., description="弹幕ID")
    time_offset: int = Field(..., alias="timeOffset", description="弹幕时间偏移(毫秒)")
    content: str = Field(..., description="弹幕内容")
    content_style: Optional[TencentCommentContentStyle] = Field(None, alias="contentStyle")

# --- 用于搜索API的新模型 ---
class TencentSearchVideoInfo(BaseModel):
    title: str
    year: Optional[int] = None
    type_name: str = Field(alias="typeName")

class TencentSearchDoc(BaseModel):
    id: str  # 这是 cid

class TencentSearchItem(BaseModel):
    video_info: Optional[TencentSearchVideoInfo] = Field(None, alias="videoInfo")
    doc: TencentSearchDoc

class TencentSearchItemList(BaseModel):
    item_list: List[TencentSearchItem] = Field(alias="itemList")

class TencentSearchData(BaseModel):
    normal_list: Optional[TencentSearchItemList] = Field(None, alias="normalList")

class TencentSearchResult(BaseModel):
    data: Optional[TencentSearchData] = None

# --- 用于搜索API的请求模型 (参考C#代码) ---
class TencentSearchRequest(BaseModel):
    query: str
    version: str = ""
    filter_value: str = Field("firstTabid=150", alias="filterValue")
    retry: int = 0
    pagenum: int = 0
    pagesize: int = 20
    query_from: int = Field(4, alias="queryFrom")
    is_need_qc: bool = Field(True, alias="isneedQc")
    ad_request_info: str = Field("", alias="adRequestInfo")
    sdk_request_info: str = Field("", alias="sdkRequestInfo")
    scene_id: int = Field(21, alias="sceneId")
    platform: str = "23"

# --- 腾讯API客户端 ---

class TencentScraper(BaseScraper):
    """
    用于从腾讯视频抓取分集信息和弹幕的客户端。
    """
    def __init__(self):
        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://v.qq.com/",
        }
        # 根据C#代码，这个特定的cookie对于成功请求至关重要
        self.cookies = {
            "pgv_pvid": "40b67e3b06027f3d",
            "video_platform": "2",
            "vversion_name": "8.2.95",
            "video_bucketid": "4",
            "video_omgid": "0a1ff6bc9407c0b1cff86ee5d359614d"
        }
        # httpx.AsyncClient 是 Python 中功能强大的异步HTTP客户端，等同于 C# 中的 HttpClient
        # 此处通过 cookies 参数传入字典，httpx 会自动将其格式化为正确的 Cookie 请求头，效果与C#代码一致
        self.client = httpx.AsyncClient(headers=self.base_headers, cookies=self.cookies, timeout=20.0)
        # 获取一个专用的 logger 实例
        self.logger = logging.getLogger(__name__)

    @property
    def provider_name(self) -> str:
        return "tencent"

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()

    async def search(self, keyword: str) -> List[models.ProviderSearchInfo]:
        """通过腾讯搜索API查找番剧。"""
        url = "https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.HttpMobileRecall/MbSearchHttp"
        request_model = TencentSearchRequest(query=keyword)
        payload = request_model.model_dump(by_alias=True)
        results = []
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = TencentSearchResult.model_validate(response.json())

            if data.data and data.data.normal_list:
                for item in data.data.normal_list.item_list:
                    # 新增：检查 video_info 是否存在，因为API有时会返回null
                    if not item.video_info:
                        continue
                    # 参考C#代码，增加对年份的过滤，可以有效排除很多不相关的结果（如：资讯、短视频等）
                    if not item.video_info.year or item.video_info.year == 0:
                        continue

                    video_info = item.video_info
                    # 将腾讯的类型映射到我们内部的类型
                    media_type = "movie" if "电影" in video_info.type_name else "tv_series"

                    results.append(
                        models.ProviderSearchInfo(
                            provider=self.provider_name,
                            mediaId=item.doc.id,
                            title=video_info.title,
                            type=media_type,
                            year=video_info.year,
                            episodeCount=None  # 搜索API不提供总集数
                        )
                    )
        except httpx.HTTPStatusError as e:
            self.logger.error(f"搜索请求失败: {e}")
        except (ValidationError, KeyError) as e:
            self.logger.error(f"解析搜索结果失败: {e}", exc_info=True)

        return results

    async def _internal_get_episodes(self, cid: str) -> List[TencentEpisode]:
        """
        获取指定cid的所有分集列表。
        处理了腾讯视频复杂的分页逻辑。
        """
        url = "https://pbaccess.video.qq.com/trpc.universal_backend_service.page_server_rpc.PageServer/GetPageData?video_appid=3000010&vplatform=2"
        all_episodes: Dict[str, TencentEpisode] = {}
        # 采用C#代码中更可靠的分页逻辑
        page_size = 100
        begin_num = 1
        page_context = "" # 首次请求为空
        last_vid_of_page = ""

        self.logger.info(f"开始为 cid='{cid}' 获取分集列表...")

        while True:
            payload = {
                "pageParams": { # 这里的参数结构完全参考了C#代码，确保请求的正确性
                    "cid": cid,
                    "page_type": "detail_operation",
                    "page_id": "vsite_episode_list",
                    "id_type": "1",
                    "pageSize": str(page_size),
                    "lid": "0",
                    "req_from": "web_mobile",
                    "pageContext": page_context,
                },
            }
            try:
                self.logger.debug(f"请求分集列表 (cid={cid}), PageContext='{page_context}'")
                response = await self.client.post(url, json=payload)
                self.logger.debug(f"收到响应 (cid={cid}), Status Code: {response.status_code}")
                response.raise_for_status()
                data = response.json()

                # --- 参考C#代码实现的健壮解析逻辑 ---
                # 电影和电视剧的页面模块结构不同，此逻辑会遍历所有模块，
                # 以找到第一个包含有效项目列表 (itemDatas) 的模块。
                # 这避免了因页面结构变动导致解析失败的问题。
                item_datas = []
                module_list_datas = data.get("data", {}).get("moduleListDatas", [])
                
                for module_list_data in module_list_datas:
                    module_datas = module_list_data.get("moduleDatas", [])
                    for module_data in module_datas:
                        item_data_lists = module_data.get("itemDataLists", {})
                        found_items = item_data_lists.get("itemDatas")
                        if found_items:
                            item_datas = found_items
                            break 
                    if item_datas:
                        break
                # --- 解析逻辑健壮性改造结束 ---

                if not item_datas:
                    self.logger.warning(f"cid='{cid}': 未找到更多分集，或API结构已更改。")
                    self.logger.debug(f"完整响应内容 (cid={cid}): {data}")
                    break

                new_episodes_found = 0
                current_page_vids = []
                for item in item_datas:
                    params = item.get("itemParams", {})
                    if not params.get("vid"):
                        continue
                    
                    episode = TencentEpisode.model_validate(params)
                    
                    # 参考C#代码，增加更详细的过滤规则，过滤掉预告、彩蛋、直拍、直播回顾等非正片内容
                    is_preview = episode.is_trailer == "1" or any(kw in episode.title for kw in ["预告", "彩蛋", "直拍", "直播回顾"])
                    
                    if not is_preview and episode.vid not in all_episodes:
                        all_episodes[episode.vid] = episode
                        new_episodes_found += 1
                    
                    current_page_vids.append(episode.vid)

                self.logger.info(f"cid='{cid}': 当前页获取 {len(item_datas)} 个项目，新增 {new_episodes_found} 个有效分集。当前总数: {len(all_episodes)}")

                # 检查是否需要翻页，并防止因API返回重复数据导致的死循环
                if len(item_datas) < page_size or not current_page_vids or current_page_vids[-1] == last_vid_of_page:
                    self.logger.info(f"cid='{cid}': 已到达最后一页或检测到重复分页数据，停止翻页。")
                    break

                last_vid_of_page = current_page_vids[-1]
                
                # 构造下一页的上下文
                begin_num += page_size
                end_num = begin_num + page_size - 1
                page_context = f"episode_begin={begin_num}&episode_end={end_num}&episode_step={page_size}"

                await asyncio.sleep(0.5)  # 礼貌性等待

            except httpx.HTTPStatusError as e:
                self.logger.error(f"请求分集列表失败 (cid={cid}): {e}")
                self.logger.debug(f"失败响应内容: {e.response.text}")
                break
            except (KeyError, IndexError, ValidationError) as e:
                self.logger.error(f"解析分集列表JSON失败 (cid={cid}): {e}", exc_info=True)
                if 'data' in locals():
                    self.logger.debug(f"导致解析失败的JSON数据: {data}")
                break

        self.logger.info(f"分集列表获取完成 (cid={cid})，去重后共 {len(all_episodes)} 个。")
        # 某些综艺节目可能会返回重复的剧集，这里进行去重
        return list(all_episodes.values())

    async def get_episodes(self, media_id: str) -> List[models.ProviderEpisodeInfo]:
        """
        获取指定cid的所有分集列表。
        media_id 对于腾讯来说就是 cid。
        """
        tencent_episodes = await self._internal_get_episodes(media_id)
        return [
            models.ProviderEpisodeInfo(
                provider=self.provider_name,
                episodeId=ep.vid,
                title=ep.title,
                episodeIndex=i + 1
            )
            for i, ep in enumerate(tencent_episodes)
        ]

    async def _internal_get_comments(self, vid: str) -> List[TencentComment]:
        """
        获取指定vid的所有弹幕。
        分两步：先获取弹幕分段索引，再逐个获取分段内容。
        """
        all_comments: List[TencentComment] = []
        # 1. 获取弹幕分段索引
        index_url = f"https://dm.video.qq.com/barrage/base/{vid}"
        try:
            response = await self.client.get(index_url)
            response.raise_for_status()
            index_data = response.json()
            segment_index = index_data.get("segment_index", {})
            if not segment_index: # 如果视频没有弹幕，这里会是空的
                self.logger.warning(f"vid='{vid}' 没有找到弹幕分段索引。")
                return []
        except Exception as e:
            self.logger.error(f"获取弹幕索引失败 (vid={vid}): {e}", exc_info=True)
            return []

        # 2. 遍历分段，获取弹幕内容
        self.logger.info(f"为 vid='{vid}' 找到 {len(segment_index)} 个弹幕分段，开始获取...")
        # 与C#代码不同，这里我们直接遍历所有分段以获取全部弹幕，而不是抽样
        # 按key（时间戳）排序，确保弹幕顺序正确
        sorted_keys = sorted(segment_index.keys(), key=int)
        for key in sorted_keys:
            segment = segment_index[key]
            segment_name = segment.get("segment_name")
            if not segment_name:
                continue
            
            segment_url = f"https://dm.video.qq.com/barrage/segment/{vid}/{segment_name}"
            try:
                response = await self.client.get(segment_url)
                response.raise_for_status()
                comment_data = response.json()
                
                barrage_list = comment_data.get("barrage_list", [])
                for comment_item in barrage_list:
                    all_comments.append(TencentComment.model_validate(comment_item))
                
                await asyncio.sleep(0.2) # 礼貌性等待

            except Exception as e:
                self.logger.error(f"获取分段 {segment_name} 失败 (vid={vid}): {e}", exc_info=True)
                continue
        
        self.logger.info(f"vid='{vid}' 弹幕获取完成，共 {len(all_comments)} 条。")
        return all_comments

    async def get_comments(self, episode_id: str) -> List[dict]:
        """
        获取指定vid的所有弹幕。
        episode_id 对于腾讯来说就是 vid。
        返回一个字典列表，可直接用于批量插入数据库。
        """
        tencent_comments = await self._internal_get_comments(episode_id)

        formatted_comments = []
        for c in tencent_comments:
            # 默认值
            mode = 1  # 滚动
            color = 16777215  # 白色

            # 根据 style 调整模式和颜色
            if c.content_style:
                if c.content_style.position == 2:
                    mode = 5  # 顶部
                elif c.content_style.position == 3:
                    mode = 4  # 底部
                
                if c.content_style.color:
                    try:
                        # 将16进制颜色字符串转为10进制整数
                        color = int(c.content_style.color, 16)
                    except (ValueError, TypeError):
                        pass # 转换失败则使用默认白色

            timestamp = c.time_offset / 1000.0
            # 格式: 时间,模式,颜色,来源
            p_string = f"{timestamp},{mode},{color},{self.provider_name}"
            formatted_comments.append({"cid": c.id, "p": p_string, "m": c.content, "t": timestamp})

        return formatted_comments