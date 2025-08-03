import asyncio
import aiomysql
import logging
import traceback
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Tuple
from uuid import uuid4

from . import models, crud

logger = logging.getLogger(__name__)

class TaskStatus(str, Enum):
    PENDING = "排队中"
    RUNNING = "运行中"
    COMPLETED = "已完成"
    FAILED = "失败"

class TaskSuccess(Exception):
    """自定义异常，用于表示任务成功完成并附带一条最终消息。"""
    pass

class Task:
    def __init__(self, task_id: str, title: str, coro_factory: Callable[[Callable], Coroutine]):
        self.task_id = task_id
        self.title = title
        self.coro_factory = coro_factory
        self.done_event = asyncio.Event()

class TaskManager:
    def __init__(self, pool: aiomysql.Pool):
        self._pool = pool
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    def start(self):
        """启动后台工作协程来处理任务队列。"""
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())
            logger.info("任务管理器已启动。")

    async def stop(self):
        """停止任务管理器。"""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
            logger.info("任务管理器已停止。")

    async def _worker(self):
        """从队列中获取并执行任务。"""
        while True:
            task: Task = await self._queue.get()
            logger.info(f"开始执行任务 '{task.title}' (ID: {task.task_id})")
            
            await crud.update_task_progress_in_history(
                self._pool, task.task_id, TaskStatus.RUNNING, 0, "正在初始化..."
            )
            
            try:
                # 创建一个回调函数，该函数将由任务内部调用以更新其进度
                progress_callback = self.get_progress_callback(task.task_id)
                # task.coro_factory 是一个需要回调函数作为参数的 lambda
                # 调用它以获取真正的、可等待的协程
                actual_coroutine = task.coro_factory(progress_callback)
                await actual_coroutine
                
                # 对于没有引发 TaskSuccess 异常而正常结束的任务，使用通用成功消息
                await crud.finalize_task_in_history(
                    self._pool, task.task_id, TaskStatus.COMPLETED, "任务成功完成"
                )
                logger.info(f"任务 '{task.title}' (ID: {task.task_id}) 已成功完成。")
            except TaskSuccess as e:
                # 捕获 TaskSuccess 异常，使用其消息作为最终描述
                final_message = str(e) if str(e) else "任务成功完成"
                await crud.finalize_task_in_history(
                    self._pool, task.task_id, TaskStatus.COMPLETED, final_message
                )
                logger.info(f"任务 '{task.title}' (ID: {task.task_id}) 已成功完成，消息: {final_message}")
            except Exception:
                error_message = "任务执行失败"
                await crud.finalize_task_in_history(
                    self._pool, task.task_id, TaskStatus.FAILED, error_message
                )
                logger.error(f"任务 '{task.title}' (ID: {task.task_id}) 执行失败: {traceback.format_exc()}")
            finally:
                self._queue.task_done()
                task.done_event.set()

    async def submit_task(self, coro_factory: Callable[[Callable], Coroutine], title: str) -> Tuple[str, asyncio.Event]:
        """提交一个新任务到队列，并在数据库中创建记录。返回任务ID和完成事件。"""
        task_id = str(uuid4())
        task = Task(task_id, title, coro_factory)
        
        await crud.create_task_in_history(
            self._pool, task_id, title, TaskStatus.PENDING, "等待执行..."
        )
        
        await self._queue.put(task)
        logger.info(f"任务 '{title}' 已提交，ID: {task_id}")
        return task_id, task.done_event

    def get_progress_callback(self, task_id: str) -> Callable:
        """为特定任务创建一个回调闭包。"""
        def callback(progress: int, description: str):
            # 这是一个“即发即忘”的调用，以避免阻塞正在运行的任务
            asyncio.create_task(
                crud.update_task_progress_in_history(
                    self._pool, task_id, TaskStatus.RUNNING, int(progress), description
                )
            )
        return callback