import asyncio
import aiomysql
from typing import Dict, List, Optional, Any

# 假设这是你的模块结构
from src.scrapers.base import BaseScraper
from src.models import ProviderSearchInfo
from src import crud
from src.scraper_manager import ScraperManager

async def main():
    # 1. 初始化数据库连接池
    pool = await aiomysql.create_pool(
        host='localhost',
        port=3306,
        user='root',
        password='root',
        db='127.0.0.1',
        minsize=1,
        maxsize=10
    )
    
    # 2. 创建 ScraperManager 实例
    scraper_manager = ScraperManager(pool)
    
    try:
        # 3. 加载并同步爬虫
        await scraper_manager.load_and_sync_scrapers()
        
        # 4. 检查是否有启用的爬虫
        if not scraper_manager.has_enabled_scrapers:
            print("警告: 没有启用的搜索源!")
            return
        
        # 5. 执行搜索
        keywords = ["淮水竹亭"]
        episode_info = {"season": 1, "episode": 2}  # 可选参数
        
        print("开始搜索...")
        results = await scraper_manager.search_all(keywords, episode_info)
        
        # 6. 处理结果
        print(f"找到 {len(results)} 个结果:")
        for result in results:
            print(f"- 提供方: {result.provider}, 媒体ID: {result.mediaId}, 标题: {result.title}")
            
    finally:
        # 7. 清理资源
        await scraper_manager.close_all()
        pool.close()
        await pool.wait_closed()
        print("资源已清理")

if __name__ == "__main__":
    asyncio.run(main())