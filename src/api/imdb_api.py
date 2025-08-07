import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from .. import models, security

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_imdb_client(
    current_user: models.User = Depends(security.get_current_user),
) -> httpx.AsyncClient:
    """依赖项：创建一个带有特定请求头的 httpx 客户端，以模拟浏览器访问。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7", # 优先请求英文内容以获得更规范的数据
    }
    return httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True)


class ImdbSearchResult(BaseModel):
    id: str
    title: str
    details: str
    image_url: Optional[str] = None


async def _scrape_imdb_search(keyword: str, client: httpx.AsyncClient) -> List[ImdbSearchResult]:
    """从 IMDb 网站抓取搜索结果。"""
    """通过关键词在 IMDb 网站上搜索影视作品。"""
    # s=tt 表示搜索所有标题, ttype=ft 表示只搜索影视剧
    search_url = f"https://www.imdb.com/find/?q={keyword}&s=tt&ttype=ft"
    try:
        response = await client.get(search_url)
        response.raise_for_status()
        html = response.text

        results = []
        # IMDb 的搜索结果列表项 class 为 "ipc-metadata-list-summary-item"
        result_items_html = re.findall(r'<li class="ipc-metadata-list-summary-item.*?</li>', html, re.DOTALL)

        for item_html in result_items_html:
            # 提取 ID
            id_match = re.search(r'/title/(tt\d+)/', item_html)
            if not id_match: continue
            imdb_id = id_match.group(1)

            # 提取标题
            title_match = re.search(r'<a.*?>(.*?)</a>', item_html)
            title = title_match.group(1).strip() if title_match else "未知标题"

            # 提取年份
            year_match = re.search(r'<span class="ipc-metadata-list-summary-item__li">(\d{4})</span>', item_html)
            year = year_match.group(1) if year_match else ""

            # 提取演员/导演信息作为详情
            meta_items = re.findall(r'<li role="presentation" class="ipc-metadata-list-summary-item__li">(.*?)</li>', item_html, re.DOTALL)
            meta_text = ' / '.join([re.sub('<.*?>', '', m).strip() for m in meta_items if re.sub('<.*?>', '', m).strip()]).strip(' / ')

            # 提取图片
            img_match = re.search(r'<img.*?src="([^"]+)".*?>', item_html)
            img_url = img_match.group(1) if img_match else None

            results.append(
                ImdbSearchResult(
                    id=imdb_id,
                    title=title,
                    details=f"{year} / {meta_text}".strip(' / '),
                    image_url=img_url,
                )
            )
        return results
    except Exception as e:
        logger.error(f"解析 IMDb 搜索结果时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="解析 IMDb 搜索结果失败。")


@router.get("/search", response_model=List[ImdbSearchResult], summary="搜索 IMDb 作品")
async def search_imdb(
    keyword: str = Query(..., min_length=1),
    client: httpx.AsyncClient = Depends(get_imdb_client),
):
    """通过关键词在 IMDb 网站上搜索影视作品。"""
    return await _scrape_imdb_search(keyword, client)


async def _scrape_imdb_details(imdb_id: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """从 IMDb 详情页抓取作品信息。"""
    details_url = f"https://www.imdb.com/title/{imdb_id}/"
    try:
        response = await client.get(details_url)
        response.raise_for_status()
        html = response.text

        # 提取别名 ("Also known as")
        aliases_cn = []
        # 别名在一个特定的 data-testid 中
        akas_section_match = re.search(r'<div data-testid="akas".*?>(.*?)</div>', html, re.DOTALL)
        if akas_section_match:
            akas_html = akas_section_match.group(1)
            # 每个别名都在一个 <li> 标签内
            alias_matches = re.findall(r'<li.*?<a.*?>(.*?)</a>', akas_html, re.DOTALL)
            aliases_cn = [alias.strip() for alias in alias_matches]

        # 提取日文名和英文名 (IMDb 页面结构复杂，这里使用简化逻辑)
        # 英文名通常是主标题
        title_match = re.search(r'<h1.*?><span.*?>(.*?)</span></h1>', html)
        name_en = title_match.group(1).strip() if title_match else None

        return {
            "id": imdb_id,
            "imdb_id": imdb_id,
            "name_en": name_en,
            "name_jp": None, # IMDb 页面很难稳定地提取日文名
            "aliases_cn": aliases_cn,
        }

    except Exception as e:
        logger.error(f"解析 IMDb 详情页时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="解析 IMDb 详情页失败。")


@router.get("/details/{imdb_id}", response_model=Dict[str, Any], summary="获取 IMDb 作品详情")
async def get_imdb_details(
    imdb_id: str = Path(...), client: httpx.AsyncClient = Depends(get_imdb_client)
):
    """获取指定 IMDb ID 的作品详情，主要用于提取别名。"""
    return await _scrape_imdb_details(imdb_id, client)