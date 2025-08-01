import uvicorn
import asyncio
from fastapi import FastAPI, Request, Depends
import logging
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import json
from .database import create_db_pool, close_db_pool, init_db_tables, create_initial_admin_user
from .api.ui import router as ui_router, auth_router
from .api.bangumi_api import router as bangumi_router
from .api.tmdb_api import router as tmdb_router
from .dandan_api import dandan_router
from .task_manager import TaskManager
from .scraper_manager import ScraperManager
from .scheduler import SchedulerManager
from .config import settings
from . import crud, security
from .log_manager import setup_logging

app = FastAPI(
    title="Danmaku API",
    description="一个基于dandanplay API风格的弹幕服务",
    version="1.0.0",
)

@app.middleware("http")
async def log_not_found_requests(request: Request, call_next):
    """
    中间件：捕获所有请求，如果响应是 404 Not Found，
    则以JSON格式记录详细的请求入参，方便调试。
    """
    response = await call_next(request)
    if response.status_code == 404:
        log_details = {
            "message": "HTTP 404 Not Found - 未找到匹配的API路由",
            "method": request.method,
            "url": str(request.url),
            "path_params": request.path_params,
            "query_params": dict(request.query_params),
            "client": f"{request.client.host}:{request.client.port}",
            "headers": {
                "user-agent": request.headers.get("user-agent"),
                "referer": request.headers.get("referer"),
            }
        }
        logging.getLogger(__name__).warning("未处理的请求详情:\n%s", json.dumps(log_details, indent=2, ensure_ascii=False))
    return response

async def cleanup_task(app: FastAPI):
    """定期清理过期缓存和OAuth states的后台任务。"""
    pool = app.state.db_pool
    while True:
        try:
            await asyncio.sleep(3600) # 每小时清理一次
            await crud.clear_expired_cache(pool)
            await crud.clear_expired_oauth_states(app.state.db_pool)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.getLogger(__name__).error(f"缓存清理任务出错: {e}")

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
    # 启动缓存清理后台任务
    app.state.cleanup_task = asyncio.create_task(cleanup_task(app))
    # 创建并启动定时任务调度器
    app.state.scheduler_manager = SchedulerManager(pool)
    await app.state.scheduler_manager.start()

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时，关闭数据库连接池和Scraper"""
    if hasattr(app.state, "cleanup_task"):
        app.state.cleanup_task.cancel()
        try:
            await app.state.cleanup_task
        except asyncio.CancelledError:
            pass
    await close_db_pool(app)
    if hasattr(app.state, "scraper_manager"):
        await app.state.scraper_manager.close_all()
    if hasattr(app.state, "task_manager"):
        await app.state.task_manager.stop()
    if hasattr(app.state, "scheduler_manager"):
        await app.state.scheduler_manager.stop()

# 挂载静态文件目录
# 注意：这应该在项目根目录运行，以便能找到 'static' 文件夹
app.mount("/static", StaticFiles(directory="static"), name="static")

# 包含 v2 版本的 API 路由
app.include_router(ui_router, prefix="/api/ui", tags=["Web UI API"])
app.include_router(auth_router, prefix="/api/ui/auth", tags=["Auth"])
app.include_router(dandan_router, prefix="/api/{token}", tags=["DanDanPlay Compatible"])
app.include_router(bangumi_router, prefix="/api/bgm", tags=["Bangumi"])
app.include_router(tmdb_router, prefix="/api/tmdb", tags=["TMDB"])

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
