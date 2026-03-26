from __future__ import annotations

import asyncio
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


class QueueFullError(RuntimeError):
    """表示当前排队请求已经达到设定上限。AI by zb"""

    def __init__(self, queue_limit: int) -> None:
        """记录当前队列上限，便于 API 层返回明确错误。AI by zb"""
        super().__init__(f"当前排队请求已达到上限 {queue_limit}，请稍后再试。")
        self.queue_limit = queue_limit


@dataclass(slots=True)
class QueueJob:
    """表示一个等待串行执行的工作流任务。AI by zb"""

    action: str
    executor: Callable[[], Awaitable[Any]]
    future: asyncio.Future[Any]
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    queue_position: int | None = 1
    state: str = "queued"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: Any | None = None
    error_message: str | None = None
    error_type: str | None = None


class WorkflowJobQueue:
    """用单工作协程串行执行 Telegram 任务，避免多请求串台。AI by zb"""

    def __init__(self, queue_limit: int) -> None:
        """初始化排队上限、内部队列和状态同步原语。AI by zb"""
        self._queue_limit = queue_limit
        self._jobs: deque[QueueJob] = deque()
        self._job_index: dict[str, QueueJob] = {}
        self._condition = asyncio.Condition()
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self._active_job: QueueJob | None = None
        self._shutdown_message = "服务正在关闭，运行中的任务已取消。"

    async def start(self) -> None:
        """启动后台工作协程，开始消费排队中的工作流任务。AI by zb"""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop(), name="telegram-workflow-queue")

    async def stop(self) -> None:
        """停止队列服务，并取消排队中与执行中的任务。AI by zb"""
        async with self._condition:
            self._running = False
            while self._jobs:
                job = self._jobs.popleft()
                if not job.future.done():
                    job.future.cancel()
                job.state = "cancelled"
                job.error_type = "CancelledError"
                job.error_message = "服务正在关闭，排队任务已取消。"
                job.finished_at = datetime.now(timezone.utc)
            self._refresh_queue_positions()
            self._condition.notify_all()

        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def submit(self, action: str, executor: Callable[[], Awaitable[Any]]) -> QueueJob:
        """提交一个新的工作流任务，若排队已满则直接拒绝。AI by zb"""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        job = QueueJob(
            action=action,
            executor=executor,
            future=future,
        )

        async with self._condition:
            if len(self._jobs) >= self._queue_limit:
                raise QueueFullError(self._queue_limit)

            self._jobs.append(job)
            self._job_index[job.request_id] = job
            self._refresh_queue_positions()
            self._condition.notify_all()

        return job

    async def wait_result(self, job: QueueJob) -> Any:
        """等待指定任务执行完成，并屏蔽外层取消对内部 future 的影响。AI by zb"""
        return await asyncio.shield(job.future)

    async def snapshot(self) -> dict[str, Any]:
        """返回当前队列长度、活动任务和队列上限等状态信息。AI by zb"""
        async with self._condition:
            return {
                "queue_size": len(self._jobs),
                "queue_limit": self._queue_limit,
                "active_action": self._active_job.action if self._active_job else None,
                "active_request_id": self._active_job.request_id if self._active_job else None,
            }

    async def get_job(self, request_id: str) -> QueueJob | None:
        """按请求 ID 查询任务当前状态与执行结果。AI by zb"""
        async with self._condition:
            return self._job_index.get(request_id)

    async def _worker_loop(self) -> None:
        """持续串行执行队列中的任务，直到服务停止且队列清空。AI by zb"""
        while True:
            async with self._condition:
                while self._running and not self._jobs:
                    await self._condition.wait()

                if not self._running and not self._jobs:
                    return

                job = self._jobs.popleft()
                self._active_job = job
                job.state = "running"
                job.queue_position = 1
                job.started_at = datetime.now(timezone.utc)
                self._refresh_queue_positions()

            try:
                result = await job.executor()
                job.result = result
                job.state = "completed"
                job.finished_at = datetime.now(timezone.utc)
                if not job.future.done():
                    job.future.set_result(result)
            except asyncio.CancelledError:
                job.error_type = "CancelledError"
                job.error_message = self._shutdown_message
                job.state = "cancelled"
                job.finished_at = datetime.now(timezone.utc)
                if not job.future.done():
                    job.future.cancel()
                raise
            except Exception as exc:
                job.error_type = type(exc).__name__
                job.error_message = str(exc)
                job.state = "failed"
                job.finished_at = datetime.now(timezone.utc)
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                async with self._condition:
                    self._active_job = None
                    self._refresh_queue_positions()
                    self._condition.notify_all()

    def _refresh_queue_positions(self) -> None:
        """在队列变化时刷新等待任务的位置，便于外部查询排队情况。AI by zb"""
        for index, job in enumerate(self._jobs, start=1):
            job.queue_position = index + (1 if self._active_job is not None else 0)

        if self._active_job is not None:
            self._active_job.queue_position = 1
