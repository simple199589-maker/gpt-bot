from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Any

from job_queue import QueueFullError, WorkflowJobQueue
from workflow_service import BotWorkflowService, WorkflowError, WorkflowResult


LOGGER = logging.getLogger("telegram_button_automation.scheduled_redeem")


class ScheduledRedeemService:
    """在后台按固定时刻提交卡密兑换任务，复用现有串行队列。AI by zb"""

    def __init__(
        self,
        config: dict[str, Any],
        workflow_service: BotWorkflowService,
        job_queue: WorkflowJobQueue,
    ) -> None:
        """读取定时兑换配置并准备后台任务状态。AI by zb"""
        scheduled_config = config.get("scheduled_redeem", {})
        self._enabled = bool(scheduled_config.get("enabled", False))
        self._card_code = str(scheduled_config.get("card_code", "")).strip()
        self._times = _parse_schedule_times(scheduled_config.get("times", []))
        self._workflow_service = workflow_service
        self._job_queue = job_queue
        self._loop_task: asyncio.Task[None] | None = None
        self._run_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """在启用定时兑换时启动后台调度循环。AI by zb"""
        if not self._enabled:
            LOGGER.info("定时兑换未启用。")
            return

        if not self._card_code or not self._times:
            LOGGER.warning("定时兑换配置不完整，已跳过启动。")
            return

        if self._loop_task is not None and not self._loop_task.done():
            return

        schedule_text = ", ".join(_format_schedule_time(item) for item in self._times)
        LOGGER.info("定时兑换任务已启动: times=%s card_code=%s", schedule_text, _mask_card_code(self._card_code))
        self._loop_task = asyncio.create_task(self._run_loop(), name="scheduled-redeem-loop")

    async def stop(self) -> None:
        """停止调度循环并取消尚未结束的定时兑换任务。AI by zb"""
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        pending_tasks = list(self._run_tasks)
        for task in pending_tasks:
            task.cancel()

        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

        self._run_tasks.clear()

    async def _run_loop(self) -> None:
        """按配置的每日时刻持续派发兑换任务。AI by zb"""
        reference = datetime.now().astimezone().replace(second=0, microsecond=0) - timedelta(minutes=1)
        while True:
            next_run = _get_next_run_after(reference=reference, schedule_times=self._times)
            delay_seconds = max((next_run - datetime.now().astimezone()).total_seconds(), 0.0)
            LOGGER.info("定时兑换等待下一次执行: scheduled_for=%s", next_run.isoformat(timespec="seconds"))
            await asyncio.sleep(delay_seconds)

            task = asyncio.create_task(
                self._execute_once(scheduled_for=next_run),
                name=f"scheduled-redeem-{next_run.strftime('%Y%m%d-%H%M')}",
            )
            self._run_tasks.add(task)
            task.add_done_callback(self._run_tasks.discard)
            reference = next_run

    async def _execute_once(self, scheduled_for: datetime) -> None:
        """提交一次定时兑换任务并记录执行结果。AI by zb"""
        job = None
        try:
            LOGGER.info(
                "开始执行定时兑换: scheduled_for=%s card_code=%s",
                scheduled_for.isoformat(timespec="seconds"),
                _mask_card_code(self._card_code),
            )
            job = await self._job_queue.submit(
                action="redeem",
                executor=lambda: self._workflow_service.redeem(self._card_code),
            )
            LOGGER.info(
                "定时兑换已入队: scheduled_for=%s request_id=%s",
                scheduled_for.isoformat(timespec="seconds"),
                job.request_id,
            )
            result: WorkflowResult = await self._job_queue.wait_result(job)
            LOGGER.info(
                "定时兑换执行完成: scheduled_for=%s request_id=%s success=%s status=%s message=%s",
                scheduled_for.isoformat(timespec="seconds"),
                job.request_id,
                result.success,
                result.status,
                result.message,
            )
        except QueueFullError as exc:
            LOGGER.warning(
                "定时兑换入队失败，当前队列已满: scheduled_for=%s queue_limit=%s",
                scheduled_for.isoformat(timespec="seconds"),
                exc.queue_limit,
            )
        except WorkflowError as exc:
            LOGGER.warning(
                "定时兑换执行失败: scheduled_for=%s status_code=%s detail=%s",
                scheduled_for.isoformat(timespec="seconds"),
                exc.status_code,
                str(exc),
            )
        except asyncio.CancelledError:
            LOGGER.info("定时兑换任务已取消: scheduled_for=%s", scheduled_for.isoformat(timespec="seconds"))
            raise
        except Exception:
            LOGGER.exception("定时兑换出现未处理异常: scheduled_for=%s", scheduled_for.isoformat(timespec="seconds"))


def _parse_schedule_times(raw_times: Any) -> tuple[time, ...]:
    """将配置中的执行时间列表解析为去重后的每日时刻集合。AI by zb"""
    if not isinstance(raw_times, list):
        return ()

    parsed_times: list[time] = []
    seen: set[str] = set()
    for raw_time in raw_times:
        time_text = str(raw_time).strip()
        if not time_text:
            continue

        parsed_time = time.fromisoformat(time_text).replace(second=0, microsecond=0)
        normalized_text = _format_schedule_time(parsed_time)
        if normalized_text in seen:
            continue

        seen.add(normalized_text)
        parsed_times.append(parsed_time)

    return tuple(sorted(parsed_times, key=lambda item: (item.hour, item.minute)))


def _get_next_run_after(reference: datetime, schedule_times: tuple[time, ...]) -> datetime:
    """基于本地时区计算下一个需要执行兑换任务的绝对时间。AI by zb"""
    local_reference = reference.astimezone()
    for schedule_time in schedule_times:
        candidate = local_reference.replace(
            hour=schedule_time.hour,
            minute=schedule_time.minute,
            second=0,
            microsecond=0,
        )
        if candidate > local_reference:
            return candidate

    tomorrow = local_reference + timedelta(days=1)
    first_time = schedule_times[0]
    return tomorrow.replace(hour=first_time.hour, minute=first_time.minute, second=0, microsecond=0)


def _format_schedule_time(value: time) -> str:
    """将每日时刻格式化为统一的 `HH:MM` 文本。AI by zb"""
    return value.strftime("%H:%M")


def _mask_card_code(card_code: str) -> str:
    """脱敏日志中的卡密文本，避免完整卡密直接写入日志。AI by zb"""
    if len(card_code) <= 8:
        return "*" * len(card_code)

    return f"{card_code[:6]}...{card_code[-4:]}"
