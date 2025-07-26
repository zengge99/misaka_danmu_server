import aiomysql
from fastapi import FastAPI, Request
from .config import settings

async def create_db_pool(app: FastAPI):
    """创建数据库连接池并存储在 app.state 中"""
    app.state.db_pool = await aiomysql.create_pool(
        host=settings.database.host,
        port=settings.database.port,
        user=settings.database.user,
        password=settings.database.password,
        db=settings.database.name,
        autocommit=True  # 建议在Web应用中开启自动提交
    )
    print("数据库连接池创建成功。")

async def get_db_pool(request: Request) -> aiomysql.Pool:
    """依赖项：从应用状态获取数据库连接池"""
    return request.app.state.db_pool

async def close_db_pool(app: FastAPI):
    """关闭数据库连接池"""
    if hasattr(app.state, "db_pool") and app.state.db_pool:
        app.state.db_pool.close()
        await app.state.db_pool.wait_closed()
        print("数据库连接池已关闭。")

async def init_db_tables(app: FastAPI):
    """初始化数据库和表"""
    # 1. 先尝试连接MySQL实例，但不指定数据库
    try:
        conn = await aiomysql.connect(
            host=settings.database.host, port=settings.database.port,
            user=settings.database.user, password=settings.database.password
        ) 
    except Exception as e:
        print(f"数据库连接失败，请检查 config.yml 中的配置: {e}") 
        raise RuntimeError(f"无法连接到数据库: {e}") from e

    async with conn.cursor() as cursor:
        # 2. 创建数据库 (如果不存在)
        await cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{settings.database.name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.close()

    # 3. 连接到指定数据库，并创建表
    # 使用 app.state 中的连接池
    async with app.state.db_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 创建 anime 表
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `anime` (
              `id` BIGINT NOT NULL AUTO_INCREMENT,
              `title` VARCHAR(255) NOT NULL,
              `type` ENUM('tv_series', 'movie', 'ova', 'other') NOT NULL DEFAULT 'tv_series',
              `season` INT NOT NULL DEFAULT 1,
              `source_url` VARCHAR(512) NULL,
              `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (`id`),
              FULLTEXT INDEX `idx_title_fulltext` (`title`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # 创建 episode 表
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `episode` (
              `id` BIGINT NOT NULL AUTO_INCREMENT,
              `anime_id` BIGINT NOT NULL,
              `title` VARCHAR(255) NOT NULL,
              `episode_index` INT NOT NULL,
              PRIMARY KEY (`id`),
              UNIQUE INDEX `idx_anime_episode_unique` (`anime_id` ASC, `episode_index` ASC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # 创建 comment 表
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `comment` (
              `id` BIGINT NOT NULL AUTO_INCREMENT, `cid` VARCHAR(255) NOT NULL, `episode_id` BIGINT NOT NULL,
              `p` VARCHAR(255) NOT NULL, `m` TEXT NOT NULL, `t` DECIMAL(10, 2) NOT NULL,
              PRIMARY KEY (`id`), UNIQUE INDEX `idx_episode_cid_unique` (`episode_id` ASC, `cid` ASC),
              INDEX `idx_episode_time` (`episode_id` ASC, `t` ASC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # 创建 users 表
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `users` (
              `id` BIGINT NOT NULL AUTO_INCREMENT,
              `username` VARCHAR(50) NOT NULL,
              `hashed_password` VARCHAR(255) NOT NULL,
              `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (`id`),
              UNIQUE INDEX `idx_username_unique` (`username` ASC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
    print("数据库和表初始化完成。")
