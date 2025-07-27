import asyncio
import httpx
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError

from .base import BaseScraper
from .. import models
 
# --- Pydantic 模型，用于解析腾讯API的响应 ---

class TencentEpisode(BaseModel):
    vid: str = Field(..., description="分集视频ID")
    title: str = Field(..., description="分集标题")
    is_trailer: str = Field("0", alias="isTrailer")

class TencentComment(BaseModel):
    id: str = Field(..., description="弹幕ID")
    time_offset: int = Field(..., alias="timeOffset", description="弹幕时间偏移(毫秒)")
    content: str = Field(..., description="弹幕内容")

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
        self.client = httpx.AsyncClient(headers=self.base_headers, cookies=self.cookies, timeout=20.0)

    @property
    def provider_name(self) -> str:
        return "tencent"

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()

    async def search(self, keyword: str) -> List[models.ProviderSearchInfo]:
        """通过腾讯搜索API查找番剧。"""
        url = "https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.HttpMobileRecall/MbSearchHttp"
        payload = {"query": keyword}
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
                    # 根据C#代码，增加对年份的过滤，提高结果质量
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
            print(f"腾讯搜索请求失败: {e}")
        except (ValidationError, KeyError) as e:
            print(f"解析腾讯搜索结果失败: {e}")

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

        print(f"开始为 cid='{cid}' 获取分集列表...")

        while True:
            payload = {
                "pageParams": {
                    "cid": cid,
                    "pageSize": str(page_size),
                    "pageContext": page_context,
                }
            }
            try:
                response = await self.client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                # 解析深层嵌套的JSON数据
                item_datas = data.get("data", {}).get("moduleListDatas", [{}])[0].get("moduleDatas", [{}])[0].get("itemDataLists", {}).get("itemDatas", [])

                if not item_datas:
                    print("未找到更多分集，或API结构已更改。")
                    break

                new_episodes_found = 0
                current_page_vids = []
                for item in item_datas:
                    params = item.get("itemParams", {})
                    if not params.get("vid"):
                        continue
                    
                    episode = TencentEpisode.model_validate(params)
                    
                    # 过滤预告片和非正片内容
                    is_preview = episode.is_trailer == "1" or any(kw in episode.title for kw in ["预告", "彩蛋", "直拍"])
                    
                    if not is_preview and episode.vid not in all_episodes:
                        all_episodes[episode.vid] = episode
                        new_episodes_found += 1
                    
                    current_page_vids.append(episode.vid)

                print(f"当前页获取 {len(item_datas)} 个项目，新增 {new_episodes_found} 个有效分集。总数: {len(all_episodes)}")

                # 检查是否需要翻页以及防止死循环
                if len(item_datas) < page_size or not current_page_vids or current_page_vids[-1] == last_vid_of_page:
                    print("已到达最后一页或检测到重复数据，停止翻页。")
                    break

                last_vid_of_page = current_page_vids[-1]
                
                # 构造下一页的上下文
                begin_num += page_size
                end_num = begin_num + page_size - 1
                page_context = f"episode_begin={begin_num}&episode_end={end_num}&episode_step={page_size}"

                await asyncio.sleep(0.5)  # 礼貌性等待

            except httpx.HTTPStatusError as e:
                print(f"请求分集列表失败: {e}")
                break
            except (KeyError, IndexError) as e:
                print(f"解析分集列表JSON失败: {e}, 响应: {data}")
                break

        print(f"分集列表获取完成，共 {len(all_episodes)} 个。")
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
            if not segment_index:
                print(f"vid='{vid}' 没有找到弹幕分段索引。")
                return []
        except Exception as e:
            print(f"获取弹幕索引失败 (vid={vid}): {e}")
            return []

        # 2. 遍历分段，获取弹幕内容
        print(f"为 vid='{vid}' 找到 {len(segment_index)} 个弹幕分段，开始获取...")
        # 确保按时间顺序处理分段
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
                print(f"获取分段 {segment_name} 失败: {e}")
                continue
        
        print(f"vid='{vid}' 弹幕获取完成，共 {len(all_comments)} 条。")
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
            timestamp = c.time_offset / 1000.0
            # 格式: 时间,模式,颜色,来源
            p_string = f"{timestamp},1,16777215,{self.provider_name}"
            formatted_comments.append({"cid": c.id, "p": p_string, "m": c.content, "t": timestamp})

        return formatted_comments