import aiomysql
import secrets
import string
from fastapi import FastAPI, Request
from .config import settings


async def create_db_pool(app: FastAPI) -> aiomysql.Pool:
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
    return app.state.db_pool

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
    """初始化数据库和表，并处理简单的 schema 迁移"""
    db_name = settings.database.name
    # 1. 先尝试连接MySQL实例，但不指定数据库
    try:
        conn = await aiomysql.connect(
            host=settings.database.host, port=settings.database.port,
            user=settings.database.user, password=settings.database.password
        )
    except Exception as e:
        print(f"数据库连接失败，请检查配置: {e}")
        raise RuntimeError(f"无法连接到数据库: {e}") from e

    async with conn.cursor() as cursor:
        # 2. 创建数据库 (如果不存在)
        await cursor.execute("SHOW DATABASES LIKE %s", (db_name,))
        if not await cursor.fetchone():
            print(f"数据库 '{db_name}' 不存在，正在创建...")
            await cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            print(f"数据库 '{db_name}' 创建成功。")
    conn.close()

    # 3. 检查并创建/更新表
    async with app.state.db_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # --- 步骤 3.1: 使用幂等的 "CREATE TABLE IF NOT EXISTS" 确保所有表都存在 ---
            print("正在确保所有数据表都存在...")
            # 创建 anime 表
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `anime` (
              `id` BIGINT NOT NULL AUTO_INCREMENT,
              `title` VARCHAR(255) NOT NULL,
              `type` ENUM('tv_series', 'movie', 'ova', 'other') NOT NULL DEFAULT 'tv_series',
              `image_url` VARCHAR(512) NULL,
              `season` INT NOT NULL DEFAULT 1,
              `source_url` VARCHAR(512) NULL,
              `created_at` TIMESTAMP NULL,
              PRIMARY KEY (`id`),
              FULLTEXT INDEX `idx_title_fulltext` (`title`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # 创建 episode 表
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `episode` (
              `id` BIGINT NOT NULL AUTO_INCREMENT,
              `source_id` BIGINT NOT NULL,
              `title` VARCHAR(255) NOT NULL,
              `episode_index` INT NOT NULL,
              `provider_episode_id` VARCHAR(255) NULL,
              `source_url` VARCHAR(512) NULL,
              `fetched_at` TIMESTAMP NULL,
              PRIMARY KEY (`id`),
              UNIQUE INDEX `idx_source_episode_unique` (`source_id` ASC, `episode_index` ASC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # 创建 comment 表
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `comment` (
              `id` BIGINT NOT NULL AUTO_INCREMENT, `cid` VARCHAR(255) NOT NULL, `episode_id` BIGINT NOT NULL,
              `p` VARCHAR(255) NOT NULL, `m` TEXT NOT NULL, `t` DECIMAL(10, 3) NOT NULL,
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
              `token` TEXT NULL,
              `token_update` TIMESTAMP NULL,
              `created_at` TIMESTAMP NULL,
              PRIMARY KEY (`id`),
              UNIQUE INDEX `idx_username_unique` (`username` ASC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # 创建 scrapers 表
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `scrapers` (
              `provider_name` VARCHAR(50) NOT NULL,
              `is_enabled` BOOLEAN NOT NULL DEFAULT TRUE,
              `display_order` INT NOT NULL DEFAULT 0,
              PRIMARY KEY (`provider_name`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # 创建 anime_sources 表
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `anime_sources` (
              `id` BIGINT NOT NULL AUTO_INCREMENT,
              `anime_id` BIGINT NOT NULL,
              `provider_name` VARCHAR(50) NOT NULL,
              `media_id` VARCHAR(255) NOT NULL,
              `created_at` TIMESTAMP NULL,
              PRIMARY KEY (`id`),
              UNIQUE INDEX `idx_anime_provider_media_unique` (`anime_id` ASC, `provider_name` ASC, `media_id` ASC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            print("数据表检查完成。")

            # --- 步骤 3.2: 为已存在的表运行 schema 迁移检查 ---
            print("正在检查旧的 schema 是否需要更新...")
            
            # 迁移检查：users 表
            await cursor.execute("SHOW COLUMNS FROM `users` LIKE 'token'")
            if not await cursor.fetchone():
                print("检测到旧的 'users' 表 schema，正在添加 'token' 和 'token_update' 字段...")
                await cursor.execute("""
                    ALTER TABLE `users`
                    ADD COLUMN `token` TEXT NULL AFTER `hashed_password`,
                    ADD COLUMN `token_update` TIMESTAMP NULL AFTER `token`;
                """)
                print("'users' 表 schema 更新完成。")

            # 迁移检查：anime 表的 image_url
            await cursor.execute("SHOW COLUMNS FROM `anime` LIKE 'image_url'")
            if not await cursor.fetchone():
                print("检测到旧的 'anime' 表 schema，正在添加 'image_url' 字段...")
                await cursor.execute("ALTER TABLE `anime` ADD COLUMN `image_url` VARCHAR(512) NULL AFTER `type`;")
                print("'anime' 表 schema 更新完成。")
            
            # 迁移检查：comment 表的 t 字段精度
            await cursor.execute("""
                SELECT NUMERIC_SCALE 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'comment' AND COLUMN_NAME = 't'
            """, (db_name,))
            t_column_info = await cursor.fetchone()
            if t_column_info and t_column_info[0] != 3:
                print("检测到旧的 'comment' 表 schema，正在更新 't' 字段的精度...")
                await cursor.execute("ALTER TABLE `comment` MODIFY COLUMN `t` DECIMAL(10, 3) NOT NULL;")
                print("'comment' 表 't' 字段精度更新完成。")

            # 迁移检查：episode 表的 source_url 和 fetched_at
            await cursor.execute("SHOW COLUMNS FROM `episode` LIKE 'source_url'")
            if not await cursor.fetchone():
                print("检测到旧的 'episode' 表 schema，正在添加 'source_url' 和 'fetched_at' 字段...")
                await cursor.execute("""
                    ALTER TABLE `episode`
                    ADD COLUMN `source_url` VARCHAR(512) NULL AFTER `episode_index`,
                    ADD COLUMN `fetched_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `source_url`;
                """)
                # 再次修改以移除默认值，确保与新schema一致
                await cursor.execute("ALTER TABLE `episode` MODIFY COLUMN `fetched_at` TIMESTAMP NULL;");
                print("'episode' 表 schema 更新完成。")

            # 迁移检查：episode 表的 provider_episode_id
            await cursor.execute("SHOW COLUMNS FROM `episode` LIKE 'provider_episode_id'")
            if not await cursor.fetchone():
                print("检测到旧的 'episode' 表 schema，正在添加 'provider_episode_id' 字段...")
                await cursor.execute("""
                    ALTER TABLE `episode` ADD COLUMN `provider_episode_id` VARCHAR(255) NULL AFTER `episode_index`;
                """)
                print("'episode' 表 schema 更新完成。")

            # 迁移检查：移除所有 created_at 和 fetched_at 的默认值
            tables_with_timestamps = ['anime', 'users', 'anime_sources', 'episode']
            for table in tables_with_timestamps:
                column = 'fetched_at' if table == 'episode' else 'created_at'
                await cursor.execute("""
                    SELECT COLUMN_DEFAULT FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
                """, (db_name, table, column))
                default_val = await cursor.fetchone()
                if default_val and default_val[0] is not None:
                    print(f"检测到旧的 '{table}' 表 schema，正在移除 '{column}' 字段的默认值...")
                    await cursor.execute(f"ALTER TABLE `{table}` ALTER COLUMN `{column}` DROP DEFAULT;")
                    print(f"'{table}' 表 '{column}' 字段默认值移除完成。")


            # 主要迁移：从 anime(provider, media_id) 迁移到 anime_sources，并更新 episode 表
            await cursor.execute("SHOW COLUMNS FROM `anime` LIKE 'provider'")
            if await cursor.fetchone():
                print("检测到旧的 'anime' 和 'episode' 表 schema，开始进行数据迁移...")
                
                # 1. 获取所有需要迁移的旧数据
                await cursor.execute("SELECT id, provider, media_id FROM anime WHERE provider IS NOT NULL AND media_id IS NOT NULL")
                old_anime_data = await cursor.fetchall()

                # 2. 为每个旧 anime 记录在 anime_sources 中创建对应的条目
                if old_anime_data:
                    insert_query = "INSERT IGNORE INTO anime_sources (anime_id, provider_name, media_id) VALUES (%s, %s, %s)"
                    await cursor.executemany(insert_query, old_anime_data)
                    print(f"成功迁移 {len(old_anime_data)} 条源数据到 'anime_sources' 表。")

                # 3. 更新 episode 表结构
                print("正在更新 'episode' 表结构...")
                await cursor.execute("ALTER TABLE `episode` ADD COLUMN `source_id` BIGINT NULL AFTER `id`, DROP INDEX `idx_anime_episode_unique`, ADD UNIQUE INDEX `idx_source_episode_unique` (`source_id` ASC, `episode_index` ASC)")
                
                # 4. 将 episode.anime_id 的数据填充到新的 episode.source_id
                # 这里做一个简化假设：一个旧番剧只对应一个源。
                await cursor.execute("UPDATE episode e JOIN anime_sources s ON e.anime_id = s.anime_id SET e.source_id = s.id")
                
                # 5. 移除旧列
                print("正在从 'anime' 和 'episode' 表中移除旧字段...")
                await cursor.execute("ALTER TABLE `anime` DROP COLUMN `provider`, DROP COLUMN `media_id`")
                await cursor.execute("ALTER TABLE `episode` DROP COLUMN `anime_id`, MODIFY COLUMN `source_id` BIGINT NOT NULL")
                print("Schema 迁移完成。")
            else:
                print("Schema 检查完成，无需迁移。")
