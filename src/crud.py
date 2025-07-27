import aiomysql
from typing import List, Optional, Dict, Any

from . import models, security


async def search_anime(pool: aiomysql.Pool, keyword: str) -> List[Dict[str, Any]]:
    """在数据库中搜索番剧 (使用FULLTEXT索引)"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 使用布尔全文搜索，+ 表示必须包含
            query = "SELECT id, title, type FROM anime WHERE MATCH(title) AGAINST(%s IN BOOLEAN MODE)"
            # 为每个词添加+号，例如 "复仇者 联盟" -> "+复仇者 +联盟"
            search_term = ' '.join([f'+{word}' for word in keyword.split()])
            await cursor.execute(query, (search_term,))
            return await cursor.fetchall()


async def find_anime_by_title(pool: aiomysql.Pool, title: str) -> Optional[Dict[str, Any]]:
    """通过标题精确查找番剧"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id, title, type FROM anime WHERE title = %s"
            await cursor.execute(query, (title,))
            return await cursor.fetchone()


async def find_episode(pool: aiomysql.Pool, anime_id: int, episode_index: int) -> Optional[Dict[str, Any]]:
    """查找特定分集"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT id, title FROM episode WHERE anime_id = %s AND episode_index = %s"
            await cursor.execute(query, (anime_id, episode_index))
            return await cursor.fetchone()


async def fetch_comments(pool: aiomysql.Pool, episode_id: int) -> List[Dict[str, Any]]:
    """获取弹幕"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            query = "SELECT p, m FROM comment WHERE episode_id = %s ORDER BY t ASC"
            await cursor.execute(query, (episode_id,))
            return await cursor.fetchall()


async def check_episode_exists(pool: aiomysql.Pool, episode_id: int) -> bool:
    """检查分集是否存在"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "SELECT 1 FROM episode WHERE id = %s LIMIT 1"
            await cursor.execute(query, (episode_id,))
            result = await cursor.fetchone()
            return result is not None


async def get_or_create_anime(pool: aiomysql.Pool, title: str) -> int:
    """如果番剧不存在则创建，并返回其ID"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 检查是否存在
            await cursor.execute("SELECT id FROM anime WHERE title = %s", (title,))
            result = await cursor.fetchone()
            if result:
                return result[0]
            
            # 不存在则创建
            await cursor.execute("INSERT INTO anime (title, type) VALUES (%s, %s)", (title, 'tv_series'))
            return cursor.lastrowid


async def get_or_create_episode(pool: aiomysql.Pool, anime_id: int, episode_index: int, title: str) -> int:
    """如果分集不存在则创建，并返回其ID"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 检查是否存在
            await cursor.execute("SELECT id FROM episode WHERE anime_id = %s AND episode_index = %s", (anime_id, episode_index))
            result = await cursor.fetchone()
            if result:
                return result[0]
            
            # 不存在则创建
            await cursor.execute(
                "INSERT INTO episode (anime_id, episode_index, title) VALUES (%s, %s, %s)",
                (anime_id, episode_index, title)
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
            query = "SELECT id, username, hashed_password, current_token FROM users WHERE username = %s"
            await cursor.execute(query, (username,))
            return await cursor.fetchone()


async def create_user(pool: aiomysql.Pool, user: models.UserCreate) -> int:
    """创建新用户"""
    hashed_password = security.get_password_hash(user.password)
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "INSERT INTO users (username, hashed_password) VALUES (%s, %s)"
            await cursor.execute(query, (user.username, hashed_password))
            return cursor.lastrowid


async def update_user_password(pool: aiomysql.Pool, username: str, new_hashed_password: str) -> None:
    """更新用户的密码"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = "UPDATE users SET hashed_password = %s WHERE username = %s"
            await cursor.execute(query, (new_hashed_password, username))


async def update_user_login_info(pool: aiomysql.Pool, username: str, token: str) -> None:
    """更新用户的最后登录时间和当前令牌"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 使用 NOW() 获取数据库服务器的当前时间
            query = "UPDATE users SET current_token = %s, last_login_at = NOW() WHERE username = %s"
            await cursor.execute(query, (token, username))
