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
    """初始化数据库和表"""
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
            # --- 步骤 3.1: 检查并创建所有表 ---
            print("正在检查并创建数据表...")
            
            # 将所有建表语句放入一个字典中
            tables_to_create = {
                "anime": """CREATE TABLE `anime` (`id` BIGINT NOT NULL AUTO_INCREMENT, `title` VARCHAR(255) NOT NULL, `type` ENUM('tv_series', 'movie', 'ova', 'other') NOT NULL DEFAULT 'tv_series', `image_url` VARCHAR(512) NULL, `season` INT NOT NULL DEFAULT 1, `episode_count` INT NULL DEFAULT NULL, `source_url` VARCHAR(512) NULL, `created_at` TIMESTAMP NULL, PRIMARY KEY (`id`), FULLTEXT INDEX `idx_title_fulltext` (`title`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "episode": """CREATE TABLE `episode` (`id` BIGINT NOT NULL AUTO_INCREMENT, `source_id` BIGINT NOT NULL, `title` VARCHAR(255) NOT NULL, `episode_index` INT NOT NULL, `provider_episode_id` VARCHAR(255) NULL, `source_url` VARCHAR(512) NULL, `fetched_at` TIMESTAMP NULL, `comment_count` INT NOT NULL DEFAULT 0, PRIMARY KEY (`id`), UNIQUE INDEX `idx_source_episode_unique` (`source_id` ASC, `episode_index` ASC)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "comment": """CREATE TABLE `comment` (`id` BIGINT NOT NULL AUTO_INCREMENT, `cid` VARCHAR(255) NOT NULL, `episode_id` BIGINT NOT NULL, `p` VARCHAR(255) NOT NULL, `m` TEXT NOT NULL, `t` DECIMAL(10, 2) NOT NULL, PRIMARY KEY (`id`), UNIQUE INDEX `idx_episode_cid_unique` (`episode_id` ASC, `cid` ASC), INDEX `idx_episode_time` (`episode_id` ASC, `t` ASC)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "users": """CREATE TABLE `users` (`id` BIGINT NOT NULL AUTO_INCREMENT, `username` VARCHAR(50) NOT NULL, `hashed_password` VARCHAR(255) NOT NULL, `token` TEXT NULL, `token_update` TIMESTAMP NULL, `created_at` TIMESTAMP NULL, PRIMARY KEY (`id`), UNIQUE INDEX `idx_username_unique` (`username` ASC)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "scrapers": """CREATE TABLE `scrapers` (`provider_name` VARCHAR(50) NOT NULL, `is_enabled` BOOLEAN NOT NULL DEFAULT TRUE, `display_order` INT NOT NULL DEFAULT 0, PRIMARY KEY (`provider_name`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "anime_sources": """CREATE TABLE `anime_sources` (`id` BIGINT NOT NULL AUTO_INCREMENT, `anime_id` BIGINT NOT NULL, `provider_name` VARCHAR(50) NOT NULL, `media_id` VARCHAR(255) NOT NULL, `is_favorited` BOOLEAN NOT NULL DEFAULT FALSE, `created_at` TIMESTAMP NULL, PRIMARY KEY (`id`), UNIQUE INDEX `idx_anime_provider_media_unique` (`anime_id` ASC, `provider_name` ASC, `media_id` ASC)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "anime_metadata": """CREATE TABLE `anime_metadata` (`id` BIGINT NOT NULL AUTO_INCREMENT, `anime_id` BIGINT NOT NULL, `tmdb_id` VARCHAR(50) NULL, `tmdb_episode_group_id` VARCHAR(50) NULL, `imdb_id` VARCHAR(50) NULL, `tvdb_id` VARCHAR(50) NULL, `douban_id` VARCHAR(50) NULL, `bangumi_id` VARCHAR(50) NULL, PRIMARY KEY (`id`), UNIQUE INDEX `idx_anime_id_unique` (`anime_id` ASC)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "config": """CREATE TABLE `config` (`config_key` VARCHAR(100) NOT NULL, `config_value` VARCHAR(255) NOT NULL, `description` TEXT NULL, PRIMARY KEY (`config_key`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "cache_data": """CREATE TABLE `cache_data` (`cache_provider` VARCHAR(50) NULL, `cache_key` VARCHAR(255) NOT NULL, `cache_value` LONGTEXT NOT NULL, `expires_at` TIMESTAMP NOT NULL, PRIMARY KEY (`cache_key`), INDEX `idx_expires_at` (`expires_at`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "api_tokens": """CREATE TABLE `api_tokens` (`id` INT NOT NULL AUTO_INCREMENT, `name` VARCHAR(100) NOT NULL, `token` VARCHAR(50) NOT NULL, `is_enabled` BOOLEAN NOT NULL DEFAULT TRUE, `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, `expires_at` TIMESTAMP NULL DEFAULT NULL, PRIMARY KEY (`id`), UNIQUE INDEX `idx_token_unique` (`token` ASC)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "token_access_logs": """CREATE TABLE `token_access_logs` (`id` BIGINT NOT NULL AUTO_INCREMENT, `token_id` INT NOT NULL, `ip_address` VARCHAR(45) NOT NULL, `user_agent` TEXT NULL, `access_time` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, `status` VARCHAR(50) NOT NULL, `path` VARCHAR(512) NULL, PRIMARY KEY (`id`), INDEX `idx_token_id_time` (`token_id` ASC, `access_time` DESC)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "ua_rules": """CREATE TABLE `ua_rules` (`id` INT NOT NULL AUTO_INCREMENT, `ua_string` VARCHAR(255) NOT NULL, `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (`id`), UNIQUE INDEX `idx_ua_string_unique` (`ua_string` ASC)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "bangumi_auth": """CREATE TABLE `bangumi_auth` (`user_id` BIGINT NOT NULL, `bangumi_user_id` INT NULL, `nickname` VARCHAR(255) NULL, `avatar_url` VARCHAR(512) NULL, `access_token` TEXT NOT NULL, `refresh_token` TEXT NULL, `expires_at` TIMESTAMP NULL, `authorized_at` TIMESTAMP NULL, PRIMARY KEY (`user_id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "oauth_states": """CREATE TABLE `oauth_states` (`state_key` VARCHAR(100) NOT NULL, `user_id` BIGINT NOT NULL, `expires_at` TIMESTAMP NOT NULL, PRIMARY KEY (`state_key`), INDEX `idx_oauth_expires_at` (`expires_at`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "anime_aliases": """CREATE TABLE `anime_aliases` (`id` BIGINT NOT NULL AUTO_INCREMENT, `anime_id` BIGINT NOT NULL, `name_en` VARCHAR(255) NULL, `name_jp` VARCHAR(255) NULL, `name_romaji` VARCHAR(255) NULL, `alias_cn_1` VARCHAR(255) NULL, `alias_cn_2` VARCHAR(255) NULL, `alias_cn_3` VARCHAR(255) NULL, PRIMARY KEY (`id`), UNIQUE INDEX `idx_anime_id_unique` (`anime_id` ASC), CONSTRAINT `fk_aliases_anime` FOREIGN KEY (`anime_id`) REFERENCES `anime`(`id`) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "tmdb_episode_mapping": """CREATE TABLE `tmdb_episode_mapping` (`id` BIGINT NOT NULL AUTO_INCREMENT, `tmdb_tv_id` INT NOT NULL, `tmdb_episode_group_id` VARCHAR(50) NOT NULL, `tmdb_episode_id` INT NOT NULL, `tmdb_season_number` INT NOT NULL, `tmdb_episode_number` INT NOT NULL, `custom_season_number` INT NOT NULL, `custom_episode_number` INT NOT NULL, `absolute_episode_number` INT NOT NULL, PRIMARY KEY (`id`), UNIQUE KEY `idx_group_episode_unique` (`tmdb_episode_group_id`, `tmdb_episode_id`), INDEX `idx_custom_season_episode` (`tmdb_tv_id`, `tmdb_episode_group_id`, `custom_season_number`, `custom_episode_number`), INDEX `idx_absolute_episode` (`tmdb_tv_id`, `tmdb_episode_group_id`, `absolute_episode_number`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "scheduled_tasks": """CREATE TABLE `scheduled_tasks` (`id` VARCHAR(100) NOT NULL, `name` VARCHAR(255) NOT NULL, `job_type` VARCHAR(50) NOT NULL, `cron_expression` VARCHAR(100) NOT NULL, `is_enabled` BOOLEAN NOT NULL DEFAULT TRUE, `last_run_at` TIMESTAMP NULL, `next_run_at` TIMESTAMP NULL, PRIMARY KEY (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
                "task_history": """CREATE TABLE `task_history` (`id` VARCHAR(100) NOT NULL, `title` VARCHAR(255) NOT NULL, `status` VARCHAR(20) NOT NULL, `progress` INT NOT NULL DEFAULT 0, `description` TEXT NULL, `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, `finished_at` TIMESTAMP NULL, PRIMARY KEY (`id`), INDEX `idx_created_at` (`created_at` DESC)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",
            }

            # 先获取数据库中所有已存在的表
            await cursor.execute("SELECT table_name FROM information_schema.TABLES WHERE table_schema = %s", (db_name,))
            existing_tables = {row[0] for row in await cursor.fetchall()}

            # 遍历需要创建的表
            for table_name, create_sql in tables_to_create.items():
                if table_name in existing_tables:
                    print(f"数据表 '{table_name}' 已存在，跳过创建。")
                else:
                    print(f"正在创建数据表 '{table_name}'...")
                    # 在建表语句中保留 IF NOT EXISTS 作为最后的保险
                    await cursor.execute(create_sql.replace(f"CREATE TABLE `{table_name}`", f"CREATE TABLE IF NOT EXISTS `{table_name}`"))
                    print(f"数据表 '{table_name}' 创建成功。")
            
            print("数据表检查完成。")

            # --- 步骤 3.2: 初始化默认配置 ---
            await _init_default_config(cursor)

async def _init_default_config(cursor: aiomysql.Cursor):
    """初始化缓存配置表的默认值"""
    default_configs = [
        ('search_ttl_seconds', '300', '搜索结果的缓存时间（秒），默认5分钟。'),
        ('episodes_ttl_seconds', '1800', '分集列表的缓存时间（秒），默认30分钟。'),
        ('base_info_ttl_seconds', '1800', '基础媒体信息（如爱奇艺）的缓存时间（秒），默认30分钟。'),
        ('metadata_search_ttl_seconds', '1800', '元数据（如TMDB, Bangumi）搜索结果的缓存时间（秒），默认30分钟。'),
        ('custom_api_domain', '', '用于拼接弹幕API地址的自定义域名。'),
        ('jwt_expire_minutes', str(settings.jwt.access_token_expire_minutes), 'JWT令牌的有效期（分钟）。-1 表示永不过期。'),
        ('tmdb_api_key', '', '用于访问 The Movie Database API 的密钥。'),
        ('tmdb_api_base_url', 'https://api.themoviedb.org', 'TMDB API 的基础域名。'),
        ('tmdb_image_base_url', 'https://image.tmdb.org', 'TMDB 图片服务的基础 URL。'),
        ('ua_filter_mode', 'off', 'UA过滤模式: off, blacklist, whitelist')
    ]
    # 使用 INSERT IGNORE 来避免因主键冲突而报错
    query = "INSERT IGNORE INTO config (config_key, config_value, description) VALUES (%s, %s, %s)"
    await cursor.executemany(query, default_configs)
    print("默认缓存配置已初始化。")
