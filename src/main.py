import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .database import create_db_pool, close_db_pool, init_db_tables, create_initial_admin_user
from .api import router as api_router, auth_router
from .task_manager import TaskManager
from .scraper_manager import ScraperManager
from .config import settings
from .log_manager import setup_logging

app = FastAPI(
    title="Danmaku API",
    description="一个基于dandanplay API风格的弹幕服务",
    version="1.0.0",
)

@app.on_event("startup")
async def startup_event():
    """应用启动时，创建数据库连接池、Scraper管理器并初始化表"""
    # 初始化日志系统
    setup_logging()
    # 创建数据库连接池
    pool = await create_db_pool(app)
    # 在进行任何依赖表的数据库操作前，先确保表已存在
    await init_db_tables(app)
    # 创建 Scraper 管理器
    app.state.scraper_manager = ScraperManager(pool)
    await app.state.scraper_manager.load_and_sync_scrapers()
    # 创建并启动任务管理器
    app.state.task_manager = TaskManager()
    app.state.task_manager.start()
    # 创建初始管理员用户（如果需要）
    await create_initial_admin_user(app)

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时，关闭数据库连接池和Scraper"""
    await close_db_pool(app)
    if hasattr(app.state, "scraper_manager"):
        await app.state.scraper_manager.close_all()
    if hasattr(app.state, "task_manager"):
        await app.state.task_manager.stop()

# 挂载静态文件目录
# 注意：这应该在项目根目录运行，以便能找到 'static' 文件夹
app.mount("/static", StaticFiles(directory="static"), name="static")

# 包含 v2 版本的 API 路由
app.include_router(api_router, prefix="/api/v2", tags=["v2"])
app.include_router(auth_router, prefix="/api/v2/auth", tags=["Auth"])

# 根路径返回前端页面
@app.get("/", response_class=FileResponse, include_in_schema=False)
async def read_index():
    return "static/index.html"

# 添加一个运行入口，以便直接从配置启动
# 这样就可以通过 `python -m src.main` 来运行，并自动使用 config.yml 中的端口和主机
if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.server.host,
        port=settings.server.port
    )
