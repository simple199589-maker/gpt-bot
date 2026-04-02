from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app_config import match_keywords
from telegram_service import TelegramBotService


LOGGER = logging.getLogger("telegram_button_automation.workflow")


class WorkflowError(Exception):
    """表示工作流执行过程中出现的业务级异常。AI by zb"""

    status_code = 500


class WorkflowTimeoutError(WorkflowError):
    """表示机器人在预期时间内没有给出下一步反馈。AI by zb"""

    status_code = 504


@dataclass(slots=True)
class WorkflowResult:
    """承载单次工作流执行结果，供 API 层统一返回。AI by zb"""

    action: str
    success: bool
    status: str
    message: str
    raw_message: str
    balance: int | None = None


class BotWorkflowService:
    """将 Telegram 机器人菜单动作封装为可复用的业务工作流。AI by zb"""

    def __init__(self, telegram_service: TelegramBotService, config: dict[str, Any]) -> None:
        """初始化工作流配置，准备激活、查询余额与兑换卡密逻辑。AI by zb"""
        self._telegram_service = telegram_service
        self._config = config
        self._workflow_config = config["workflow"]
        self._buttons = self._workflow_config["buttons"]
        self._prompts = self._workflow_config["prompts"]
        self._result_keywords = self._workflow_config["result_keywords"]

    async def activate_plus(
        self,
        access_token: str,
        progress_callback: Callable[[WorkflowResult], Awaitable[None]] | None = None,
    ) -> WorkflowResult:
        """执行 plus 母号激活流程，并返回机器人最终反馈。AI by zb"""
        return await self._run_access_token_workflow(
            action="activate_plus",
            button_text=str(self._buttons["activate_plus"]),
            access_token=access_token,
            progress_callback=progress_callback,
        )

    async def activate_team(
        self,
        access_token: str,
        progress_callback: Callable[[WorkflowResult], Awaitable[None]] | None = None,
    ) -> WorkflowResult:
        """执行 team 母号激活流程，并返回机器人最终反馈。AI by zb"""
        return await self._run_access_token_workflow(
            action="activate_team",
            button_text=str(self._buttons["activate_team"]),
            access_token=access_token,
            progress_callback=progress_callback,
        )

    async def query_balance(self) -> WorkflowResult:
        """执行余额查询流程，并尽量解析返回文本中的余额次数。AI by zb"""
        before_event_cursor = await self._telegram_service.get_latest_event_cursor()
        await self._telegram_service.click_button_or_send_text(str(self._buttons["balance"]))
        result_message = await self._wait_for_keywords(
            keywords=list(self._result_keywords["balance"]),
            after_event_cursor=before_event_cursor,
            description="等待余额结果",
            timeout_seconds=float(self._workflow_config["result_timeout_seconds"]),
        )
        raw_message = (result_message.raw_text or "").strip()
        balance = self._extract_balance(raw_message)
        return WorkflowResult(
            action="query_balance",
            success=True,
            status="success",
            message=raw_message,
            raw_message=raw_message,
            balance=balance,
        )

    async def redeem(self, card_code: str) -> WorkflowResult:
        """执行兑换卡密流程，并在结束后尝试返回主菜单。AI by zb"""
        prompt_event_cursor = await self._telegram_service.get_latest_event_cursor()
        await self._telegram_service.click_button_or_send_text(str(self._buttons["redeem"]))
        prompt_message = await self._wait_for_keywords(
            keywords=list(self._prompts["redeem_code"]),
            after_event_cursor=prompt_event_cursor,
            description="等待卡密输入提示",
            timeout_seconds=float(self._workflow_config["prompt_timeout_seconds"]),
        )

        try:
            result_event_cursor = await self._telegram_service.get_latest_event_cursor()
            await self._telegram_service.send_text(card_code, reply_to_message_id=int(prompt_message.id))
            return await self._wait_for_terminal_message(
                action="redeem",
                after_event_cursor=result_event_cursor,
                description="等待兑换结果",
                timeout_seconds=float(self._workflow_config["result_timeout_seconds"]),
                classifier=self._classify_redeem_message,
            )
        finally:
            await self._telegram_service.safe_send_back(
                back_text=str(self._workflow_config["back_text"]),
                delay_seconds=float(self._workflow_config["return_delay_seconds"]),
            )

    @property
    def _activation_terminal_keywords(self) -> list[str]:
        """返回激活流程完成时允许命中的全部终态关键词。AI by zb"""
        return (
            list(self._result_keywords["activation_success"])
            + list(self._result_keywords["activation_failure"])
            + list(self._result_keywords.get("activation_cancelled", []))
        )

    @property
    def _activation_progress_keywords(self) -> list[str]:
        """返回激活流程中间态关键词，用于识别处理中提示。AI by zb"""
        return list(self._result_keywords.get("activation_progress", []))

    @property
    def _redeem_progress_keywords(self) -> list[str]:
        """返回兑换流程中间态关键词，用于识别处理中提示。AI by zb"""
        return list(self._result_keywords.get("redeem_progress", []))

    async def _run_access_token_workflow(
        self,
        action: str,
        button_text: str,
        access_token: str,
        progress_callback: Callable[[WorkflowResult], Awaitable[None]] | None = None,
    ) -> WorkflowResult:
        """执行 accessToken 型流程，适用于 plus 与 team 激活。AI by zb"""
        prompt_event_cursor = await self._telegram_service.get_latest_event_cursor()
        await self._telegram_service.click_button_or_send_text(button_text)
        prompt_message = await self._wait_for_keywords(
            keywords=list(self._prompts["access_token"]),
            after_event_cursor=prompt_event_cursor,
            description="等待 accessToken 输入提示",
            timeout_seconds=float(self._workflow_config["prompt_timeout_seconds"]),
        )
        LOGGER.info("%s 已收到输入提示，准备发送 accessToken。", action)

        result_event_cursor = await self._telegram_service.get_latest_event_cursor()
        await self._telegram_service.send_text(access_token, reply_to_message_id=int(prompt_message.id))
        result = await self._wait_for_terminal_message(
            action=action,
            after_event_cursor=result_event_cursor,
            description="等待激活结果",
            timeout_seconds=float(self._workflow_config["result_timeout_seconds"]),
            classifier=self._classify_activation_message,
            progress_callback=progress_callback,
        )
        LOGGER.info("%s 已收到结果消息。", action)
        return result

    async def _wait_for_keywords(
        self,
        keywords: list[str],
        after_event_cursor: int,
        description: str,
        timeout_seconds: float,
    ):
        """统一包装消息等待逻辑，并把超时转换为工作流级异常。AI by zb"""
        try:
            return await self._telegram_service.wait_for_keywords(
                keywords=keywords,
                after_event_cursor=after_event_cursor,
                timeout_seconds=timeout_seconds,
                description=description,
            )
        except TimeoutError as exc:
            raise WorkflowTimeoutError(str(exc)) from exc

    async def _wait_for_terminal_message(
        self,
        action: str,
        after_event_cursor: int,
        description: str,
        timeout_seconds: float,
        classifier,
        progress_callback: Callable[[WorkflowResult], Awaitable[None]] | None = None,
    ) -> WorkflowResult:
        """持续消费新消息，忽略中间态提示，直到识别出最终结果。AI by zb"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        cursor = after_event_cursor
        last_message = ""

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                detail = f"{description} 超时"
                if last_message:
                    detail = f"{detail}，最近一条消息：{last_message}"
                raise WorkflowTimeoutError(detail)

            try:
                event = await self._telegram_service.wait_for_next_message(
                    after_event_cursor=cursor,
                    timeout_seconds=remaining,
                    description=description,
                )
            except TimeoutError as exc:
                detail = str(exc)
                if last_message:
                    detail = f"{detail} 最近一条消息：{last_message}"
                raise WorkflowTimeoutError(detail) from exc

            cursor = event.cursor
            message = event.message
            raw_message = (message.raw_text or "").strip()
            if not raw_message:
                continue

            last_message = raw_message
            result = classifier(action=action, raw_message=raw_message)
            if isinstance(result, WorkflowResult):
                return result

            if result == "progress":
                LOGGER.info("%s 收到中间态消息: %s", action, raw_message.replace("\n", " | "))
                if progress_callback is not None:
                    await progress_callback(
                        self._build_progress_result(
                            action=action,
                            raw_message=raw_message,
                        )
                    )
                continue

            LOGGER.info("%s 收到未识别消息，继续等待: %s", action, raw_message.replace("\n", " | "))

    def _build_activation_result(self, action: str, raw_message: str) -> WorkflowResult:
        """根据机器人返回文本构建激活流程的结构化结果。AI by zb"""
        if self._is_activation_success_message(raw_message):
            return WorkflowResult(
                action=action,
                success=True,
                status="success",
                message=raw_message,
                raw_message=raw_message,
            )

        if match_keywords(raw_message, list(self._result_keywords.get("activation_cancelled", []))):
            return WorkflowResult(
                action=action,
                success=False,
                status="cancelled",
                message=raw_message,
                raw_message=raw_message,
            )

        if self._is_activation_failure_message(raw_message):
            return WorkflowResult(
                action=action,
                success=False,
                status="invalid_access_token",
                message=raw_message,
                raw_message=raw_message,
            )

        return WorkflowResult(
            action=action,
            success=False,
            status="unknown",
            message=raw_message,
            raw_message=raw_message,
        )

    def _is_activation_success_message(self, raw_message: str) -> bool:
        """判断激活结果是否属于明确成功终态。AI by zb"""
        if match_keywords(raw_message, list(self._result_keywords["activation_success"])):
            return True

        return bool(re.search(r"(成功|已升级|升级完成)", raw_message) and "请求" not in raw_message)

    def _is_activation_failure_message(self, raw_message: str) -> bool:
        """判断激活结果是否属于明确失败终态。AI by zb"""
        if match_keywords(raw_message, list(self._result_keywords["activation_failure"])):
            return True

        return bool(re.search(r"(无效|过期|退回|失败|重试|重新获取)", raw_message))

    def _build_progress_result(self, action: str, raw_message: str) -> WorkflowResult:
        """根据处理中提示构建可立即返回给调用方的中间态结果。AI by zb"""
        return WorkflowResult(
            action=action,
            success=True,
            status="processing",
            message=raw_message,
            raw_message=raw_message,
        )

    def _classify_activation_message(self, action: str, raw_message: str) -> WorkflowResult | str | None:
        """将激活流程中的任意新消息分类为中间态、成功或失败。AI by zb"""
        if match_keywords(raw_message, self._activation_progress_keywords):
            return "progress"

        if re.search(r"当前状态[：:]", raw_message) or re.search(r"第\s*\d+\s*次查询", raw_message):
            return "progress"

        if match_keywords(raw_message, self._activation_terminal_keywords):
            return self._build_activation_result(action=action, raw_message=raw_message)

        if self._is_activation_success_message(raw_message):
            return self._build_activation_result(action=action, raw_message=raw_message)

        if self._is_activation_failure_message(raw_message):
            return self._build_activation_result(action=action, raw_message=raw_message)

        return self._build_activation_result(action=action, raw_message=raw_message)

    def _build_redeem_result(self, raw_message: str) -> WorkflowResult:
        """根据机器人返回文本构建兑换流程的结构化结果。AI by zb"""
        if self._is_redeem_success_message(raw_message):
            return WorkflowResult(
                action="redeem",
                success=True,
                status="success",
                message=raw_message,
                raw_message=raw_message,
            )

        return WorkflowResult(
            action="redeem",
            success=False,
            status="failed",
            message=raw_message,
            raw_message=raw_message,
        )

    def _is_redeem_success_message(self, raw_message: str) -> bool:
        """判断兑换结果是否属于明确成功终态。AI by zb"""
        if match_keywords(raw_message, list(self._result_keywords["redeem_success"])):
            return True

        return bool(re.search(r"(充值成功|充值完成|已?增加\s*\d+\s*次)", raw_message))

    def _classify_redeem_message(self, action: str, raw_message: str) -> WorkflowResult | str | None:
        """将兑换流程中的任意新消息分类为中间态、成功或失败。AI by zb"""
        _ = action
        if match_keywords(raw_message, self._redeem_progress_keywords):
            return "progress"

        if re.search(r"当前状态[：:]", raw_message) or re.search(r"第\s*\d+\s*次查询", raw_message):
            return "progress"

        return self._build_redeem_result(raw_message)

    def _extract_balance(self, raw_message: str) -> int | None:
        """尝试从余额结果文本中提取可直接使用的次数值。AI by zb"""
        match = re.search(r"余额[：:]\s*(\d+)", raw_message)
        if not match:
            return None
        return int(match.group(1))
