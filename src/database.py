import aiomysql
import secrets
import string
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

async def create_initial_admin_user(app: FastAPI):
    """在应用启动时创建初始管理员用户（如果已配置且不存在）"""
    # 将导入移到函数内部以避免循环导入
    from . import crud
    from . import models

    admin_user = settings.admin.initial_user
    if not admin_user:
        return

    pool = app.state.db_pool
    existing_user = await crud.get_user_by_username(pool, admin_user)

    if existing_user:
        print(f"管理员用户 '{admin_user}' 已存在，跳过创建。")
        return

    # 用户不存在，开始创建
    admin_pass = settings.admin.initial_password
    if not admin_pass:
        # 生成一个安全的16位随机密码
        alphabet = string.ascii_letters + string.digits
        admin_pass = ''.join(secrets.choice(alphabet) for _ in range(16))
        print("未提供初始管理员密码，已生成随机密码。")

    user_to_create = models.UserCreate(username=admin_user, password=admin_pass)
    await crud.create_user(pool, user_to_create)

    # 打印凭据信息，方便用户查看日志
    print("\n" + "="*60)
    print(f"=== 初始管理员账户已创建 (用户: {admin_user}) ".ljust(56) + "===")
    print(f"=== 请使用以下随机生成的密码登录: {admin_pass} ".ljust(56) + "===")
    print("="*60 + "\n")

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
