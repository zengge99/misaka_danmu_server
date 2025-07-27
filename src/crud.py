import aiomysql
from datetime import datetime
from typing import List, Optional, Dict, Any

from . import models, security


async def get_library_anime(pool: aiomysql.Pool) -> List[Dict[str, Any]]:
    """获取媒体库中的所有番剧及其关联信息（如分集数）"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 使用 LEFT JOIN 和 GROUP BY 来统计每个番剧的分集数
            query = """
                SELECT
                    a.id as animeId,
                    a.image_url as imageUrl,
                    a.title,
                    a.season,
                    a.created_at as createdAt,
                    (SELECT COUNT(DISTINCT e.id) FROM anime_sources s JOIN episode e ON s.id = e.source_id WHERE s.anime_id = a.id) as episodeCount,
                    (SELECT COUNT(*) FROM anime_sources WHERE anime_id = a.id) as sourceCount
                FROM anime a
                GROUP BY a.id
                ORDER BY a.created_at DESC
            """
            await cursor.execute(query)
            return await cursor.fetchall()


async def search_anime(pool: aiomysql.Pool, keyword: str) -> List[Dict[str, Any]]:
    """在数据库中搜索番剧 (使用FULLTEXT索引)"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id, title, type FROM anime WHERE MATCH(title) AGAINST(%s IN BOOLEAN MODE)"
            # 为关键词添加通配符以支持前缀匹配
            await cursor.execute(query, (keyword + '*',))
            return await cursor.fetchall()


async def find_anime_by_title(pool: aiomysql.Pool, title: str) -> Optional[Dict[str, Any]]:
    """通过标题精确查找番剧"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id, title, type FROM anime WHERE title = %s"
            await cursor.execute(query, (title,))
            return await cursor.fetchone()


async def find_episode(pool: aiomysql.Pool, source_id: int, episode_index: int) -> Optional[Dict[str, Any]]:
    """查找特定源的特定分集"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id, title FROM episode WHERE source_id = %s AND episode_index = %s"
            await cursor.execute(query, (source_id, episode_index))
            return await cursor.fetchone()


async def check_episode_exists(pool: aiomysql.Pool, episode_id: int) -> bool:
    """检查指定ID的分集是否存在"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "SELECT 1 FROM episode WHERE id = %s LIMIT 1"
            await cursor.execute(query, (episode_id,))
            result = await cursor.fetchone()
            return result is not None


async def fetch_comments(pool: aiomysql.Pool, episode_id: int) -> List[Dict[str, Any]]:
    """获取指定分集的所有弹幕"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT p, m FROM comment WHERE episode_id = %s"
            await cursor.execute(query, (episode_id,))
            return await cursor.fetchall()

async def get_or_create_anime(pool: aiomysql.Pool, title: str, media_type: str) -> int:
    """通过标题查找番剧，如果不存在则创建，并返回其ID。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id FROM anime WHERE title = %s", (title,))
            result = await cursor.fetchone()
            if result:
                return result[0]
            
            await cursor.execute(
                "INSERT INTO anime (title, type, created_at) VALUES (%s, %s, %s)",
                (title, media_type, datetime.now())
            )
            return cursor.lastrowid

async def link_source_to_anime(pool: aiomysql.Pool, anime_id: int, provider: str, media_id: str) -> int:
    """将一个外部数据源链接到一个番剧，如果链接已存在则直接返回，否则创建新链接。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 使用 INSERT IGNORE 来安全地插入，如果唯一键冲突则什么都不做
            await cursor.execute(
                "INSERT IGNORE INTO anime_sources (anime_id, provider_name, media_id, created_at) VALUES (%s, %s, %s, %s)",
                (anime_id, provider, media_id, datetime.now())
            )
            # 获取刚刚插入或已存在的源ID
            await cursor.execute("SELECT id FROM anime_sources WHERE anime_id = %s AND provider_name = %s AND media_id = %s", (anime_id, provider, media_id))
            source = await cursor.fetchone()
            return source[0]

async def get_or_create_episode(pool: aiomysql.Pool, source_id: int, episode_index: int, title: str, url: Optional[str], provider_episode_id: str) -> int:
    """如果分集不存在则创建，并返回其ID"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 检查是否存在
            await cursor.execute("SELECT id FROM episode WHERE source_id = %s AND episode_index = %s", (source_id, episode_index))
            result = await cursor.fetchone()
            if result:
                return result[0]
            
            # 不存在则创建
            await cursor.execute(
                "INSERT INTO episode (source_id, episode_index, provider_episode_id, title, source_url, fetched_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (source_id, episode_index, provider_episode_id, title, url, datetime.now())
            )
            return cursor.lastrowid


async def bulk_insert_comments(pool: aiomysql.Pool, episode_id: int, comments: List[Dict[str, Any]]) -> int:
    """批量插入弹幕，利用 INSERT IGNORE 忽略重复弹幕"""
    if not comments:
        return 0
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "INSERT IGNORE INTO comment (episode_id, cid, p, m, t) VALUES (%s, %s, %s, %s, %s)"
            # 准备数据
            data_to_insert = [
                (episode_id, c['cid'], c['p'], c['m'], c['t']) for c in comments
            ]
            affected_rows = await cursor.executemany(query, data_to_insert)
            return affected_rows


async def get_user_by_username(pool: aiomysql.Pool, username: str) -> Optional[Dict[str, Any]]:
    """通过用户名查找用户"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id, username, hashed_password, token FROM users WHERE username = %s"
            await cursor.execute(query, (username,))
            return await cursor.fetchone()


async def create_user(pool: aiomysql.Pool, user: models.UserCreate) -> int:
    """创建新用户"""
    hashed_password = security.get_password_hash(user.password)
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "INSERT INTO users (username, hashed_password, created_at) VALUES (%s, %s, %s)"
            await cursor.execute(query, (user.username, hashed_password, datetime.now()))
            return cursor.lastrowid


async def update_user_password(pool: aiomysql.Pool, username: str, new_hashed_password: str) -> None:
    """更新用户的密码"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "UPDATE users SET hashed_password = %s WHERE username = %s"
            await cursor.execute(query, (new_hashed_password, username))


async def update_user_login_info(pool: aiomysql.Pool, username: str, token: str):
    """更新用户的最后登录时间和当前令牌"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 使用 NOW() 获取数据库服务器的当前时间
            query = "UPDATE users SET token = %s, token_update = NOW() WHERE username = %s"
            await cursor.execute(query, (token, username))

async def get_anime_source_info(pool: aiomysql.Pool, source_id: int) -> Optional[Dict[str, Any]]:
    """获取指定源ID的详细信息及其关联的作品信息。"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT s.id as source_id, s.anime_id, s.provider_name, s.media_id, a.title, a.type FROM anime_sources s JOIN anime a ON s.anime_id = a.id WHERE s.id = %s"
            await cursor.execute(query, (source_id,))
            return await cursor.fetchone()

async def get_anime_sources(pool: aiomysql.Pool, anime_id: int) -> List[Dict[str, Any]]:
    """获取指定作品的所有关联数据源。"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id as source_id, provider_name, media_id, created_at FROM anime_sources WHERE anime_id = %s ORDER BY created_at ASC"
            await cursor.execute(query, (anime_id,))
            return await cursor.fetchall()

async def get_episodes_for_source(pool: aiomysql.Pool, source_id: int) -> List[Dict[str, Any]]:
    """获取指定数据源的所有分集信息。"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id, title, episode_index, source_url, fetched_at FROM episode WHERE source_id = %s ORDER BY episode_index ASC"
            await cursor.execute(query, (source_id,))
            return await cursor.fetchall()

async def get_episode_provider_info(pool: aiomysql.Pool, episode_id: int) -> Optional[Dict[str, Any]]:
    """获取分集的原始提供方信息 (provider_name, provider_episode_id)"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = """
                SELECT
                    s.provider_name,
                    e.provider_episode_id
                FROM episode e
                JOIN anime_sources s ON e.source_id = s.id
                WHERE e.id = %s
            """
            await cursor.execute(query, (episode_id,))
            return await cursor.fetchone()

async def clear_source_data(pool: aiomysql.Pool, source_id: int):
    """清空指定源的所有分集和弹幕，用于刷新。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id FROM episode WHERE source_id = %s", (source_id,))
            episode_ids = [row[0] for row in await cursor.fetchall()]
            if episode_ids:
                format_strings = ','.join(['%s'] * len(episode_ids))
                await cursor.execute(f"DELETE FROM comment WHERE episode_id IN ({format_strings})", tuple(episode_ids))
                await cursor.execute(f"DELETE FROM episode WHERE id IN ({format_strings})", tuple(episode_ids))

async def clear_episode_comments(pool: aiomysql.Pool, episode_id: int):
    """清空指定分集的所有弹幕"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("DELETE FROM comment WHERE episode_id = %s", (episode_id,))

async def update_anime_info(pool: aiomysql.Pool, anime_id: int, title: str, season: int) -> bool:
    """更新番剧信息"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "UPDATE anime SET title = %s, season = %s WHERE id = %s"
            affected_rows = await cursor.execute(query, (title, season, anime_id))
            return affected_rows > 0

async def update_episode_title(pool: aiomysql.Pool, episode_id: int, new_title: str) -> bool:
    """更新分集的标题"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "UPDATE episode SET title = %s WHERE id = %s"
            affected_rows = await cursor.execute(query, (new_title, episode_id))
            return affected_rows > 0

async def delete_anime(pool: aiomysql.Pool, anime_id: int) -> bool:
    """
    删除一个番剧及其所有关联数据（分集、弹幕）。
    此操作在事务中执行以保证数据一致性。
    """
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            try:
                await conn.begin()  # 开始事务

                # 1. 获取该作品关联的所有源ID
                await cursor.execute("SELECT id FROM anime_sources WHERE anime_id = %s", (anime_id,))
                source_ids = [row[0] for row in await cursor.fetchall()]

                if source_ids:
                    # 2. 删除所有源关联的分集和弹幕
                    for source_id in source_ids:
                        await clear_source_data(pool, source_id)

                    # 3. 删除所有源记录
                    format_strings = ','.join(['%s'] * len(source_ids))
                    await cursor.execute(f"DELETE FROM anime_sources WHERE id IN ({format_strings})", tuple(source_ids))

                # 4. 删除作品本身
                affected_rows = await cursor.execute("DELETE FROM anime WHERE id = %s", (anime_id,))
                await conn.commit()  # 提交事务
                return affected_rows > 0
            except Exception as e:
                await conn.rollback()  # 如果出错则回滚
                raise e

async def delete_episode(pool: aiomysql.Pool, episode_id: int) -> bool:
    """
    删除一个分集及其所有弹幕。
    此操作在事务中执行以保证数据一致性。
    """
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            try:
                await conn.begin()
                # 1. 删除弹幕
                await cursor.execute("DELETE FROM comment WHERE episode_id = %s", (episode_id,))
                # 2. 删除分集
                affected_rows = await cursor.execute("DELETE FROM episode WHERE id = %s", (episode_id,))
                await conn.commit()
                return affected_rows > 0
            except Exception as e:
                await conn.rollback()
                raise e

async def sync_scrapers_to_db(pool: aiomysql.Pool, provider_names: List[str]):
    """将发现的爬虫同步到数据库，新爬虫会被添加进去。"""
    if not provider_names:
        return
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 1. 获取所有已存在的爬虫
            await cursor.execute("SELECT provider_name FROM scrapers")
            existing_providers = {row[0] for row in await cursor.fetchall()}

            # 2. 找出新发现的爬虫
            new_providers = [name for name in provider_names if name not in existing_providers]

            if not new_providers:
                return

            # 3. 如果有新爬虫，则插入它们
            await cursor.execute("SELECT MAX(display_order) FROM scrapers")
            max_order = (await cursor.fetchone())[0] or 0

            # 只插入新的爬虫
            query = "INSERT INTO scrapers (provider_name, display_order) VALUES (%s, %s)"
            data_to_insert = [(name, max_order + i + 1) for i, name in enumerate(new_providers)]
            await cursor.executemany(query, data_to_insert)

async def get_all_scraper_settings(pool: aiomysql.Pool) -> List[Dict[str, Any]]:
    """获取所有爬虫的设置，按顺序排列。"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT provider_name, is_enabled, display_order FROM scrapers ORDER BY display_order ASC")
            return await cursor.fetchall()

async def update_scrapers_settings(pool: aiomysql.Pool, settings: List[models.ScraperSetting]):
    """批量更新爬虫的设置。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "UPDATE scrapers SET is_enabled = %s, display_order = %s WHERE provider_name = %s"
            data_to_update = [(s.is_enabled, s.display_order, s.provider_name) for s in settings]
            await cursor.executemany(query, data_to_update)

async def update_episode_fetch_time(pool: aiomysql.Pool, episode_id: int):
    """更新分集的采集时间"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE episode SET fetched_at = %s WHERE id = %s", (datetime.now(), episode_id))
