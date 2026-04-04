from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any, cast

from api_server import _build_workflow_response
from job_queue import QueueJob
from workflow_service import WorkflowResult


async def _noop_executor() -> None:
    """提供一个不会实际执行的异步占位执行器。AI by zb"""
    return None


def _create_job(state: str) -> QueueJob:
    """创建用于 API 响应测试的最小队列任务对象。AI by zb"""
    return QueueJob(
        action="activate_team",
        executor=_noop_executor,
        future=cast(Any, object()),
        response_future=cast(Any, object()),
        request_id="request-123",
        queued_at=datetime(2026, 4, 5, 3, 11, tzinfo=timezone.utc),
        queue_position=1,
        state=state,
    )


class WorkflowResponseTests(unittest.TestCase):
    """验证首个工作流响应中的 state 字段映射。AI by zb"""

    def test_build_workflow_response_exposes_running_state_for_processing(self) -> None:
        """确保处理中响应会显式带出当前运行态。AI by zb"""
        job = _create_job(state="running")
        result = WorkflowResult(
            action="activate_team",
            success=True,
            status="processing",
            message="已收到请求，请稍候。",
            raw_message="已收到请求，请稍候。",
        )

        response = _build_workflow_response(job=job, result=result)

        self.assertEqual(response.state, "running")
        self.assertEqual(response.status, "processing")
        self.assertTrue(response.success)

    def test_build_workflow_response_exposes_completed_state_for_success(self) -> None:
        """确保最终成功响应会显式带出 completed 状态。AI by zb"""
        job = _create_job(state="completed")
        result = WorkflowResult(
            action="activate_team",
            success=True,
            status="success",
            message="激活成功",
            raw_message="激活成功",
        )

        response = _build_workflow_response(job=job, result=result)

        self.assertEqual(response.state, "completed")
        self.assertEqual(response.status, "success")
        self.assertTrue(response.success)
