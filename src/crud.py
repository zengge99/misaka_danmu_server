import aiomysql
import json
import logging
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

async def search_episodes_in_library(pool: aiomysql.Pool, anime_title: str, episode_number: Optional[int], season_number: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    在本地库中通过番剧标题和可选的集数搜索匹配的分集。
    返回一个扁平化的列表，包含番剧和分集信息。
    """
    clean_title = anime_title.strip()
    if not clean_title:
        return []

    # Build WHERE clauses
    episode_condition = "AND e.episode_index = %s" if episode_number is not None else ""
    params_episode = [episode_number] if episode_number is not None else []
    season_condition = "AND a.season = %s" if season_number is not None else ""
    params_season = [season_number] if season_number is not None else []

    query_template = f"""
        SELECT
            a.id AS animeId,
            a.title AS animeTitle,
            a.type,
            a.image_url AS imageUrl,
            a.created_at AS startDate,
            e.id AS episodeId,
            CASE
                WHEN a.type = 'movie' THEN CONCAT(s.provider_name, ' 源')
                ELSE e.title
            END AS episodeTitle,
            sc.display_order,
            s.is_favorited AS isFavorited,
            (SELECT COUNT(DISTINCT e_count.id) FROM anime_sources s_count JOIN episode e_count ON s_count.id = e_count.source_id WHERE s_count.anime_id = a.id) as totalEpisodeCount,
            m.bangumi_id AS bangumiId
        FROM episode e
        JOIN anime_sources s ON e.source_id = s.id
        JOIN anime a ON s.anime_id = a.id
        JOIN scrapers sc ON s.provider_name = sc.provider_name
        LEFT JOIN anime_metadata m ON a.id = m.anime_id
        WHERE {{title_condition}} {episode_condition} {season_condition}
        ORDER BY LENGTH(a.title) ASC, sc.display_order ASC
    """

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 1. Try FULLTEXT search
            query_ft = query_template.format(title_condition="MATCH(a.title) AGAINST(%s IN BOOLEAN MODE)")
            await cursor.execute(query_ft, tuple([clean_title + '*'] + params_episode + params_season))
            results = await cursor.fetchall()
            if results:
                return results

            # 2. Fallback to LIKE search
            logging.info(f"FULLTEXT search for '{clean_title}' yielded no results, falling back to LIKE search.")
            # 为了处理全角/半角冒号和空格不一致的问题，我们在查询时进行归一化
            # 1. 将搜索词中的冒号统一为半角，并移除所有空格
            normalized_like_title = clean_title.replace("：", ":").replace(" ", "")
            # 2. 在SQL查询中，也对数据库字段进行替换，确保两侧格式一致
            query_like = query_template.format(title_condition="REPLACE(REPLACE(a.title, '：', ':'), ' ', '') LIKE %s")
            await cursor.execute(query_like, tuple([f"%{normalized_like_title}%"] + params_episode + params_season))
            return await cursor.fetchall()

async def search_animes_for_dandan(pool: aiomysql.Pool, keyword: str) -> List[Dict[str, Any]]:
    """
    在本地库中通过番剧标题搜索匹配的番剧，用于 /search/anime 接口。
    """
    clean_title = keyword.strip()
    if not clean_title:
        return []

    query_template = """
        SELECT
            a.id AS animeId,
            a.title AS animeTitle,
            a.type,
            a.image_url AS imageUrl,
            a.created_at AS startDate,
            (SELECT COUNT(DISTINCT e_count.id) FROM anime_sources s_count JOIN episode e_count ON s_count.id = e_count.source_id WHERE s_count.anime_id = a.id) as episodeCount,
            m.bangumi_id AS bangumiId
        FROM anime a
        LEFT JOIN anime_metadata m ON a.id = m.anime_id
        WHERE {title_condition}
        ORDER BY a.id
    """

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 1. Try FULLTEXT search
            query_ft = query_template.format(title_condition="MATCH(a.title) AGAINST(%s IN BOOLEAN MODE)")
            await cursor.execute(query_ft, (clean_title + '*',))
            results = await cursor.fetchall()
            if results:
                return results

            # 2. Fallback to LIKE search
            normalized_like_title = clean_title.replace("：", ":").replace(" ", "")
            query_like = query_template.format(title_condition="REPLACE(REPLACE(a.title, '：', ':'), ' ', '') LIKE %s")
            await cursor.execute(query_like, (f"%{normalized_like_title}%",))
            return await cursor.fetchall()

async def get_anime_details_for_dandan(pool: aiomysql.Pool, anime_id: int) -> Optional[Dict[str, Any]]:
    """获取番剧的详细信息及其所有分集，用于dandanplay API。"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 1. 获取番剧基本信息
            await cursor.execute("""
                SELECT
                    a.id AS animeId,
                    a.title AS animeTitle,
                    a.type,
                    a.image_url AS imageUrl,
                    a.created_at AS startDate,
                    a.source_url AS bangumiUrl,
                    (SELECT COUNT(DISTINCT e_count.id) FROM anime_sources s_count JOIN episode e_count ON s_count.id = e_count.source_id WHERE s_count.anime_id = a.id) as episodeCount,
                    m.bangumi_id AS bangumiId
                FROM anime a
                LEFT JOIN anime_metadata m ON a.id = m.anime_id
                WHERE a.id = %s
            """, (anime_id,))
            anime_details = await cursor.fetchone()

            if not anime_details:
                return None

            episodes = []
            # 2. 根据番剧类型决定如何获取“分集”列表
            if anime_details['type'] == 'movie':
                # 对于电影，我们将每个数据源视为一个“分集”，并使用搜索源的顺序作为集数
                await cursor.execute("""
                    SELECT
                        e.id AS episodeId,
                        CONCAT(s.provider_name, ' 源') AS episodeTitle,
                        sc.display_order AS episodeNumber
                    FROM anime_sources s
                    JOIN episode e ON s.id = e.source_id
                    JOIN scrapers sc ON s.provider_name = sc.provider_name
                    WHERE s.anime_id = %s
                    ORDER BY sc.display_order ASC
                """, (anime_id,))
                episodes = await cursor.fetchall()
            else:
                # 对于电视剧，正常获取分集列表
                await cursor.execute("""
                    SELECT e.id AS episodeId, e.title AS episodeTitle, e.episode_index AS episodeNumber
                    FROM episode e JOIN anime_sources s ON e.source_id = s.id
                    WHERE s.anime_id = %s ORDER BY e.episode_index ASC
                """, (anime_id,))
                episodes = await cursor.fetchall()

            # 3. 返回整合后的数据
            return {"anime": anime_details, "episodes": episodes}

async def get_anime_id_by_bangumi_id(pool: aiomysql.Pool, bangumi_id: str) -> Optional[int]:
    """通过 bangumi_id 查找 anime_id。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT anime_id FROM anime_metadata WHERE bangumi_id = %s", (bangumi_id,))
            result = await cursor.fetchone()
            return result[0] if result else None

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
            query = "SELECT id as cid, p, m FROM comment WHERE episode_id = %s"
            await cursor.execute(query, (episode_id,))
            return await cursor.fetchall()

async def get_or_create_anime(pool: aiomysql.Pool, title: str, media_type: str, image_url: Optional[str]) -> int:
    """通过标题查找番剧，如果不存在则创建。如果存在但缺少海报，则更新海报。返回其ID。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 1. 检查番剧是否已存在
            await cursor.execute("SELECT id, image_url FROM anime WHERE title = %s", (title, ))
            result = await cursor.fetchone()
            if result:
                anime_id = result[0]
                existing_image_url = result[1]
                # 如果番剧已存在，但没有海报，而这次导入提供了海报，则更新它
                if not existing_image_url and image_url:
                    await cursor.execute("UPDATE anime SET image_url = %s WHERE id = %s", (image_url, anime_id))
                return anime_id
            
            # 2. 番剧不存在，在事务中创建新记录
            try:
                await conn.begin()
                # 2.1 插入主表
                await cursor.execute(
                    "INSERT INTO anime (title, type, image_url, created_at) VALUES (%s, %s, %s, %s)",
                    (title, media_type, image_url, datetime.now())
                )
                anime_id = cursor.lastrowid
                # 2.2 插入元数据表
                await cursor.execute("INSERT INTO anime_metadata (anime_id) VALUES (%s)", (anime_id, ))
                await conn.commit()
                return anime_id
            except Exception as e:
                await conn.rollback()
                logging.error(f"创建番剧 '{title}' 时发生数据库错误: {e}", exc_info=True)
                raise

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
            # 如果成功插入了新弹幕，则更新分集的弹幕计数
            if affected_rows > 0:
                await cursor.execute("UPDATE episode SET comment_count = comment_count + %s WHERE id = %s", (affected_rows, episode_id))
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
            query = "SELECT id as source_id, provider_name, media_id, is_favorited, created_at FROM anime_sources WHERE anime_id = %s ORDER BY created_at ASC"
            await cursor.execute(query, (anime_id,))
            return await cursor.fetchall()

async def get_episodes_for_source(pool: aiomysql.Pool, source_id: int) -> List[Dict[str, Any]]:
    """获取指定数据源的所有分集信息。"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id, title, episode_index, source_url, fetched_at, comment_count FROM episode WHERE source_id = %s ORDER BY episode_index ASC"
            await cursor.execute(query, (source_id,))
            return await cursor.fetchall()

async def get_episode_for_refresh(pool: aiomysql.Pool, episode_id: int) -> Optional[Dict[str, Any]]:
    """获取分集的基本信息，用于刷新任务。"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id, title FROM episode WHERE id = %s"
            await cursor.execute(query, (episode_id,))
            return await cursor.fetchone()

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
                # 在此场景下，episode 很快会被删除，所以无需更新 comment_count
                await cursor.execute(f"DELETE FROM episode WHERE id IN ({format_strings})", tuple(episode_ids))

async def clear_episode_comments(pool: aiomysql.Pool, episode_id: int):
    """清空指定分集的所有弹幕"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("DELETE FROM comment WHERE episode_id = %s", (episode_id,))
            # 在只清空弹幕（用于刷新单个分集）的场景下，必须重置计数器
            await cursor.execute("UPDATE episode SET comment_count = 0 WHERE id = %s", (episode_id,))

async def update_anime_info(pool: aiomysql.Pool, anime_id: int, title: str, season: int) -> bool:
    """更新番剧信息"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "UPDATE anime SET title = %s, season = %s WHERE id = %s"
            affected_rows = await cursor.execute(query, (title, season, anime_id))
            return affected_rows > 0

async def update_episode_info(pool: aiomysql.Pool, episode_id: int, title: str, episode_index: int, source_url: Optional[str]) -> bool:
    """更新分集信息"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "UPDATE episode SET title = %s, episode_index = %s, source_url = %s WHERE id = %s"
            affected_rows = await cursor.execute(query, (title, episode_index, source_url, episode_id))
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

# --- 数据库缓存服务 ---

async def get_config_value(pool: aiomysql.Pool, key: str, default: str) -> str:
    """从数据库获取配置值。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT config_value FROM config WHERE config_key = %s", (key,))
            result = await cursor.fetchone()
            return result[0] if result else default

async def get_cache(pool: aiomysql.Pool, key: str) -> Optional[Any]:
    """从数据库缓存中获取数据。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT cache_value FROM cache_data WHERE cache_key = %s AND expires_at > NOW()", (key,))
            result = await cursor.fetchone()
            if result:
                try:
                    return json.loads(result[0])
                except json.JSONDecodeError:
                    return None # 缓存数据损坏
    return None

async def set_cache(pool: aiomysql.Pool, key: str, value: Any, ttl_seconds: int, provider: Optional[str] = None):
    """将数据存入数据库缓存。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            json_value = json.dumps(value, ensure_ascii=False)
            query = """
                INSERT INTO cache_data (cache_provider, cache_key, cache_value, expires_at) 
                VALUES (%s, %s, %s, NOW() + INTERVAL %s SECOND) 
                ON DUPLICATE KEY UPDATE 
                    cache_provider = VALUES(cache_provider), 
                    cache_value = VALUES(cache_value), 
                    expires_at = VALUES(expires_at)
            """
            await cursor.execute(query, (provider, key, json_value, ttl_seconds))

async def update_config_value(pool: aiomysql.Pool, key: str, value: str):
    """更新或插入一个配置项。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = """
                INSERT INTO config (config_key, config_value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)
            """
            await cursor.execute(query, (key, value))

async def clear_expired_cache(pool: aiomysql.Pool):
    """从数据库中清除过期的缓存条目。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            deleted_rows = await cursor.execute("DELETE FROM cache_data WHERE expires_at <= NOW()")
            if deleted_rows > 0:
                logging.getLogger(__name__).info(f"清除了 {deleted_rows} 条过期的数据库缓存。")

async def clear_all_cache(pool: aiomysql.Pool) -> int:
    """从数据库中清除所有缓存条目。返回删除的行数。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 使用 DELETE 并返回受影响的行数
            deleted_rows = await cursor.execute("DELETE FROM cache_data")
            if deleted_rows > 0:
                logging.getLogger(__name__).info(f"清除了所有 ({deleted_rows} 条) 数据库缓存。")
            return deleted_rows

async def update_episode_fetch_time(pool: aiomysql.Pool, episode_id: int):
    """更新分集的采集时间"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE episode SET fetched_at = %s WHERE id = %s", (datetime.now(), episode_id))

# --- API Token 管理服务 ---

async def get_all_api_tokens(pool: aiomysql.Pool) -> List[Dict[str, Any]]:
    """获取所有 API Token。"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT id, name, token, is_enabled, created_at FROM api_tokens ORDER BY created_at DESC")
            return await cursor.fetchall()

async def get_api_token_by_id(pool: aiomysql.Pool, token_id: int) -> Optional[Dict[str, Any]]:
    """通过ID获取一个 API Token。"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT id, name, token, is_enabled, created_at FROM api_tokens WHERE id = %s", (token_id,))
            return await cursor.fetchone()

async def create_api_token(pool: aiomysql.Pool, name: str, token: str) -> int:
    """创建一个新的 API Token。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("INSERT INTO api_tokens (name, token) VALUES (%s, %s)", (name, token))
            return cursor.lastrowid

async def delete_api_token(pool: aiomysql.Pool, token_id: int) -> bool:
    """删除一个 API Token。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            affected_rows = await cursor.execute("DELETE FROM api_tokens WHERE id = %s", (token_id,))
            return affected_rows > 0

async def toggle_api_token(pool: aiomysql.Pool, token_id: int) -> bool:
    """切换一个 API Token 的启用/禁用状态。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            affected_rows = await cursor.execute("UPDATE api_tokens SET is_enabled = NOT is_enabled WHERE id = %s", (token_id,))
            return affected_rows > 0

async def validate_api_token(pool: aiomysql.Pool, token: str) -> bool:
    """验证一个 API Token 是否有效且已启用。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT 1 FROM api_tokens WHERE token = %s AND is_enabled = TRUE", (token,))
            return await cursor.fetchone() is not None

async def toggle_source_favorite_status(pool: aiomysql.Pool, source_id: int) -> bool:
    """切换一个数据源的精确标记状态。一个作品只能有一个精确标记的源。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 首先，获取此源关联的 anime_id
            await cursor.execute("SELECT anime_id FROM anime_sources WHERE id = %s", (source_id,))
            result = await cursor.fetchone()
            if not result:
                return False
            anime_id = result[0]

            try:
                await conn.begin()
                # 将此作品下的所有其他源都设为非精确
                await cursor.execute("UPDATE anime_sources SET is_favorited = FALSE WHERE anime_id = %s AND id != %s", (anime_id, source_id))
                # 切换目标源的精确标记状态
                await cursor.execute("UPDATE anime_sources SET is_favorited = NOT is_favorited WHERE id = %s", (source_id,))
                await conn.commit()
                return True
            except Exception as e:
                await conn.rollback()
                logging.error(f"切换源收藏状态时出错: {e}", exc_info=True)
                return False
