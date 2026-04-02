from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from job_queue import QueueFullError, QueueJob, WorkflowJobQueue
from scheduled_redeem import ScheduledRedeemService
from schemas import (
    ActivateRequest,
    CancelResponse,
    HealthResponse,
    RedeemRequest,
    RequestStatusResponse,
    ServiceStatusResponse,
    WorkflowResponse,
)
from telegram_service import TelegramBotService
from workflow_service import BotWorkflowService, WorkflowError, WorkflowResult


LOGGER = logging.getLogger("telegram_button_automation.api")
ACTIVATION_ACTIONS = {"activate_plus", "activate_team"}


def create_app(config: dict[str, Any], config_path: Path, allow_interactive_auth: bool) -> FastAPI:
    """创建 API 服务实例，并在生命周期内托管 Telegram 连接与串行队列。AI by zb"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        telegram_service = TelegramBotService(config=config, config_path=config_path)
        workflow_service = BotWorkflowService(telegram_service=telegram_service, config=config)
        job_queue = WorkflowJobQueue(queue_limit=int(config["api"]["queue_max_size"]))
        scheduled_redeem_service = ScheduledRedeemService(
            config=config,
            workflow_service=workflow_service,
            job_queue=job_queue,
        )

        await telegram_service.connect(allow_interactive_auth=allow_interactive_auth)
        await job_queue.start()
        await scheduled_redeem_service.start()

        app.state.config = config
        app.state.telegram_service = telegram_service
        app.state.workflow_service = workflow_service
        app.state.job_queue = job_queue
        app.state.scheduled_redeem_service = scheduled_redeem_service
        try:
            yield
        finally:
            await scheduled_redeem_service.stop()
            await job_queue.stop()
            await telegram_service.disconnect()

    app = FastAPI(
        title="Telegram GPT Bot API",
        version="0.1.0",
        lifespan=lifespan,
    )

    async def verify_api_key(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> None:
        """校验调用方提供的 API Key，支持 X-API-Key 与 Bearer 两种写法。AI by zb"""
        expected_key = str(request.app.state.config["api"]["api_key"]).strip()
        provided_key = _extract_api_key(x_api_key=x_api_key, authorization=authorization)
        if not provided_key or not secrets.compare_digest(provided_key, expected_key):
            raise HTTPException(status_code=401, detail="API Key 无效。")

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        """提供无需鉴权的健康检查接口，便于进程探活。AI by zb"""
        return HealthResponse(status="ok")

    @app.get("/api/v1/status", response_model=ServiceStatusResponse, dependencies=[Depends(verify_api_key)])
    async def service_status(request: Request) -> ServiceStatusResponse:
        """返回 Telegram 连接状态、排队长度和当前执行中的任务信息。AI by zb"""
        queue_snapshot = await request.app.state.job_queue.snapshot()
        return ServiceStatusResponse(
            connected_to_telegram=request.app.state.telegram_service.is_connected,
            queue_size=queue_snapshot["queue_size"],
            queue_limit=queue_snapshot["queue_limit"],
            active_action=queue_snapshot["active_action"],
            active_request_id=queue_snapshot["active_request_id"],
        )

    @app.get("/api/v1/requests/{request_id}", response_model=RequestStatusResponse, dependencies=[Depends(verify_api_key)])
    async def request_status(request_id: str, request: Request) -> RequestStatusResponse:
        """按 requestId 查询任务状态，便于长耗时接口做轮询补偿。AI by zb"""
        job = await request.app.state.job_queue.get_job(request_id)
        if job is None:
            raise HTTPException(status_code=404, detail="未找到对应的 requestId。")

        await _restore_activation_menu_if_needed(request=request, job=job)
        return _build_request_status_response(job)

    @app.post("/api/v1/activate/plus", response_model=WorkflowResponse, dependencies=[Depends(verify_api_key)])
    async def activate_plus(payload: ActivateRequest, request: Request) -> WorkflowResponse:
        """对外暴露 plus 激活接口，把 accessToken 注入 Telegram 工作流。AI by zb"""
        return await _run_workflow(
            request=request,
            action="activate_plus",
            executor=lambda progress_callback=None: request.app.state.workflow_service.activate_plus(
                payload.access_token,
                progress_callback=progress_callback,
            ),
        )

    @app.post("/api/v1/activate/team", response_model=WorkflowResponse, dependencies=[Depends(verify_api_key)])
    async def activate_team(payload: ActivateRequest, request: Request) -> WorkflowResponse:
        """对外暴露 team 激活接口，把 accessToken 注入 Telegram 工作流。AI by zb"""
        return await _run_workflow(
            request=request,
            action="activate_team",
            executor=lambda progress_callback=None: request.app.state.workflow_service.activate_team(
                payload.access_token,
                progress_callback=progress_callback,
            ),
        )

    @app.get("/api/v1/balance", response_model=WorkflowResponse, dependencies=[Depends(verify_api_key)])
    async def query_balance(request: Request) -> WorkflowResponse:
        """对外暴露余额查询接口，并直接返回机器人余额文本。AI by zb"""
        return await _run_workflow(
            request=request,
            action="query_balance",
            executor=lambda progress_callback=None: request.app.state.workflow_service.query_balance(),
        )

    @app.post("/api/v1/redeem", response_model=WorkflowResponse, dependencies=[Depends(verify_api_key)])
    async def redeem(payload: RedeemRequest, request: Request) -> WorkflowResponse:
        """对外暴露卡密兑换接口，把卡密参数注入 Telegram 工作流。AI by zb"""
        return await _run_workflow(
            request=request,
            action="redeem",
            executor=lambda progress_callback=None: request.app.state.workflow_service.redeem(payload.card_code),
        )

    @app.post("/api/v1/cancel", response_model=CancelResponse, dependencies=[Depends(verify_api_key)])
    async def cancel(request: Request) -> CancelResponse:
        """对外暴露取消接口，立即向机器人发送返回消息。AI by zb"""
        back_text = str(request.app.state.config["workflow"]["back_text"])
        await request.app.state.telegram_service.send_back(back_text)
        return CancelResponse(
            action="cancel",
            success=True,
            message="已发送返回消息。",
            sent_text=back_text,
        )

    return app


def _extract_api_key(x_api_key: str | None, authorization: str | None) -> str:
    """从 X-API-Key 或 Bearer 头中提取调用方传入的 API Key。AI by zb"""
    if x_api_key:
        return x_api_key.strip()

    if not authorization:
        return ""

    auth_text = authorization.strip()
    prefix = "bearer "
    if auth_text.casefold().startswith(prefix):
        return auth_text[len(prefix):].strip()

    return ""


async def _run_workflow(
    request: Request,
    action: str,
    executor: Callable[[Callable[[WorkflowResult], Awaitable[None]] | None], Awaitable[WorkflowResult]],
) -> WorkflowResponse | Response:
    """把业务执行请求提交到串行队列，并把结果转换为统一响应模型。AI by zb"""
    job_queue: WorkflowJobQueue = request.app.state.job_queue
    job: QueueJob | None = None

    async def publish_progress(progress_result: WorkflowResult) -> None:
        """把激活流程中间态发布给等待中的 HTTP 请求，并同步到 requestId 状态。AI by zb"""
        if job is None:
            return
        await job_queue.publish_response(job, progress_result)

    try:
        job = await job_queue.submit(
            action=action,
            executor=lambda: executor(publish_progress if action in ACTIVATION_ACTIONS else None),
        )
        LOGGER.info("请求已入队: action=%s request_id=%s", action, job.request_id)
        result = (
            await job_queue.wait_response(job)
            if action in ACTIVATION_ACTIONS
            else await job_queue.wait_result(job)
        )
    except asyncio.CancelledError:
        if job is not None and ((job.response_future.cancelled() if action in ACTIVATION_ACTIONS else job.future.cancelled()) or job.state == "cancelled"):
            LOGGER.info("请求在服务关闭期间被取消: action=%s request_id=%s", action, job.request_id)
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "服务正在关闭，任务已取消。",
                    "requestId": job.request_id,
                },
            )

        if job is not None:
            LOGGER.info("客户端已取消等待: action=%s request_id=%s", action, job.request_id)
            return JSONResponse(
                status_code=499,
                content={
                    "detail": "客户端已取消请求，任务仍可能在后台继续执行。",
                    "requestId": job.request_id,
                },
            )

        LOGGER.info("请求在提交到队列前已被取消: action=%s", action)
        return Response(status_code=499)
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc) or "工作流执行失败。") from exc

    return _build_workflow_response(job=job, result=result)


def _build_workflow_response(job, result: WorkflowResult) -> WorkflowResponse:
    """根据动作类型构建统一响应；激活接口命中处理中消息时立即返回 processing。AI by zb"""
    if result.action in ACTIVATION_ACTIONS and result.status == "processing":
        return WorkflowResponse(
            request_id=job.request_id,
            action=result.action,
            success=True,
            status="processing",
            message=result.message,
            raw_message=result.raw_message,
            balance=result.balance,
            queue_position=job.queue_position,
            queued_at=job.queued_at.isoformat(),
        )

    return WorkflowResponse(
        request_id=job.request_id,
        action=result.action,
        success=result.success,
        status=result.status,
        message=result.message,
        raw_message=result.raw_message,
        balance=result.balance,
        queue_position=job.queue_position,
        queued_at=job.queued_at.isoformat(),
    )


def _build_request_status_response(job) -> RequestStatusResponse:
    """把队列中的任务对象转换为可直接返回给调用方的状态模型。AI by zb"""
    result = job.result if isinstance(job.result, WorkflowResult) else None
    if result is None and isinstance(job.response_result, WorkflowResult):
        result = job.response_result
    is_terminal_state = str(job.state or "").strip().lower() in {"completed", "failed", "cancelled"}
    return RequestStatusResponse(
        request_id=job.request_id,
        action=job.action,
        state=job.state,
        queue_position=job.queue_position,
        queued_at=job.queued_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        success=result.success if result and is_terminal_state else None,
        status=result.status if result else None,
        message=result.message if result else None,
        raw_message=result.raw_message if result else None,
        balance=result.balance if result else None,
        error_message=job.error_message,
        error_type=job.error_type,
    )


async def _restore_activation_menu_if_needed(request: Request, job: QueueJob) -> None:
    """当激活任务进入终态且调用方查询状态时，按需触发一次菜单复原。AI by zb"""
    normalized_state = str(job.state or "").strip().lower()
    if job.action not in ACTIVATION_ACTIONS:
        return
    if normalized_state not in {"completed", "failed", "cancelled"}:
        return

    job_queue: WorkflowJobQueue = request.app.state.job_queue
    claimed = await job_queue.claim_menu_restore(job.request_id)
    if not claimed:
        return

    back_text = str(request.app.state.config["workflow"]["back_text"])
    delay_seconds = float(request.app.state.config["workflow"]["return_delay_seconds"])
    sent = False
    try:
        await request.app.state.telegram_service.safe_send_back(
            back_text=back_text,
            delay_seconds=delay_seconds,
        )
        sent = True
        LOGGER.info("request_status 触发菜单复原成功: action=%s request_id=%s", job.action, job.request_id)
    finally:
        await job_queue.finish_menu_restore(job.request_id, sent=sent)
