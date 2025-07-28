import asyncio
import logging
import traceback
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List
from uuid import uuid4

from . import models

logger = logging.getLogger(__name__)

class TaskStatus(str, Enum):
    PENDING = "排队中"
    RUNNING = "运行中"
    COMPLETED = "已完成"
    FAILED = "失败"

class Task:
    def __init__(self, task_id: str, title: str, coro_factory: Callable[[Callable], Coroutine]):
        self.task_id = task_id
        self.title = title
        self.coro_factory = coro_factory
        self.status: TaskStatus = TaskStatus.PENDING
        self.progress: int = 0
        self.description: str = "等待执行..."

    def to_info(self) -> models.TaskInfo:
        return models.TaskInfo(
            task_id=self.task_id,
            title=self.title,
            status=self.status,
            progress=self.progress,
            description=self.description,
        )

class TaskManager:
    def __init__(self):
        self._tasks: Dict[str, Task] = {}
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
            task.status = TaskStatus.RUNNING
            task.progress = 0
            task.description = "正在初始化..."
            try:
                # 创建一个回调函数，该函数将由任务内部调用以更新其进度
                progress_callback = self.get_progress_callback(task.task_id)
                # task.coro_factory 是一个需要回调函数作为参数的 lambda
                # 调用它以获取真正的、可等待的协程
                actual_coroutine = task.coro_factory(progress_callback)
                await actual_coroutine
                task.status = TaskStatus.COMPLETED
                task.progress = 100
                task.description = "任务成功完成"
                logger.info(f"任务 '{task.title}' (ID: {task.task_id}) 已成功完成。")
            except Exception:
                task.status = TaskStatus.FAILED
                task.description = "任务执行失败"
                logger.error(f"任务 '{task.title}' (ID: {task.task_id}) 执行失败: {traceback.format_exc()}")
            finally:
                self._queue.task_done()

    async def submit_task(self, coro_factory: Callable[[Callable], Coroutine], title: str) -> str:
        """提交一个新任务到队列。"""
        task_id = str(uuid4())
        task = Task(task_id, title, coro_factory)
        self._tasks[task_id] = task
        await self._queue.put(task)
        logger.info(f"任务 '{title}' 已提交，ID: {task_id}")
        return task_id

    def update_task_progress(self, task_id: str, progress: int, description: str):
        """由任务本身调用的回调函数，用于更新进度。"""
        if task := self._tasks.get(task_id):
            task.progress = int(progress)
            task.description = description

    def get_all_tasks(self) -> List[models.TaskInfo]:
        """获取所有任务的当前状态。"""
        # 返回一个按提交顺序（大致）的列表
        return [task.to_info() for task in self._tasks.values()]

    def get_progress_callback(self, task_id: str) -> Callable:
        """为特定任务创建一个回调闭包。"""
        def callback(progress: int, description: str):
            self.update_task_progress(task_id, progress, description)
        return callback