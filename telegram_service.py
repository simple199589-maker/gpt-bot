from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from telethon import TelegramClient, events
from telethon.tl.custom.message import Message
from telethon.tl.types import KeyboardButton

from app_config import build_proxy_config, ensure_proxy_dependencies, match_keywords


LOGGER = logging.getLogger("telegram_button_automation.telegram")


@dataclass(slots=True)
class MessageEvent:
    """表示一条按时间顺序记录的 Telegram 消息事件，支持新消息与编辑消息。AI by zb"""

    cursor: int
    message: Message


class TelegramBotService:
    """封装 Telegram 会话生命周期、收发消息与按钮点击能力。AI by zb"""

    def __init__(self, config: dict[str, Any], config_path: Path) -> None:
        """基于当前配置构建 Telethon 客户端并初始化消息缓存。AI by zb"""
        self._config = config
        self._config_path = config_path
        self._proxy = build_proxy_config(config)
        ensure_proxy_dependencies(self._proxy)

        session_path = config_path.parent / str(config["session_name"])
        self._client = TelegramClient(
            str(session_path),
            int(config["api_id"]),
            str(config["api_hash"]),
            proxy=self._proxy,
        )
        self._bot_entity: object | None = None
        self._handler_registered = False
        self._message_events: deque[MessageEvent] = deque(maxlen=max(400, int(config["history_limit"]) * 40))
        self._message_condition = asyncio.Condition()
        self._event_cursor = 0

    @property
    def is_connected(self) -> bool:
        """返回当前 Telethon 客户端是否已建立连接。AI by zb"""
        return self._client.is_connected()

    async def interactive_login(self) -> None:
        """首次登录时通过交互式方式完成授权并保存本地会话。AI by zb"""
        await self._connect_internal(allow_interactive_auth=True)
        LOGGER.info("登录成功，会话已保存到本地。")
        await self.disconnect()

    async def connect(self, allow_interactive_auth: bool = False) -> None:
        """建立 Telegram 连接，并在需要时校验已有会话是否已授权。AI by zb"""
        await self._connect_internal(allow_interactive_auth=allow_interactive_auth)

    async def disconnect(self) -> None:
        """断开 Telegram 连接并释放已注册的事件处理器。AI by zb"""
        if self._handler_registered:
            self._client.remove_event_handler(self._handle_message_event)
            self._handler_registered = False

        if self._client.is_connected():
            await self._client.disconnect()

    async def get_latest_event_cursor(self) -> int:
        """返回当前最新的消息事件游标，用于等待后续新增或编辑消息。AI by zb"""
        async with self._message_condition:
            return self._event_cursor

    async def get_latest_message_id(self) -> int:
        """获取当前机器人会话的最近一条消息 ID，用于界定新消息范围。AI by zb"""
        self._ensure_bot_ready()
        async for message in self._client.iter_messages(self._bot_entity, limit=1):
            return int(message.id)
        return 0

    async def click_button_or_send_text(self, text: str) -> None:
        """优先点击最近消息中的按钮，找不到时回退为发送同名文本。AI by zb"""
        self._ensure_bot_ready()
        history_limit = int(self._config["history_limit"])
        clicked = await self._click_button_from_recent_messages(text=text, history_limit=history_limit)
        if clicked:
            return

        LOGGER.info("未找到按钮，回退为发送同名文本: %s", text)
        await self.send_text(text)

    async def send_text(self, text: str, reply_to_message_id: int | None = None) -> Message:
        """向目标机器人发送一条文本消息，可选回复指定消息。AI by zb"""
        self._ensure_bot_ready()
        message = await self._client.send_message(self._bot_entity, text, reply_to=reply_to_message_id)
        LOGGER.info("已发送消息: %s", text)
        return message

    async def send_back(self, back_text: str) -> None:
        """立即向机器人发送返回消息，供外部取消接口直接调用。AI by zb"""
        await self.click_button_or_send_text(back_text)

    async def wait_for_keywords(
        self,
        keywords: Iterable[str],
        after_event_cursor: int,
        timeout_seconds: float,
        description: str,
    ) -> Message:
        """等待指定关键词命中的新消息，用于串联多步机器人交互。AI by zb"""
        keyword_list = [keyword for keyword in keywords if keyword]
        if not keyword_list:
            raise ValueError("等待消息时必须提供至少一个关键词。")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        async with self._message_condition:
            while True:
                matched_message = self._find_event_match(
                    keywords=keyword_list,
                    after_event_cursor=after_event_cursor,
                )
                if matched_message is not None:
                    return matched_message

                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError(f"{description} 超时，未收到期望消息。")

                await asyncio.wait_for(self._message_condition.wait(), timeout=remaining)

    async def wait_for_next_message(
        self,
        after_event_cursor: int,
        timeout_seconds: float,
        description: str,
    ) -> MessageEvent:
        """等待下一条新消息，用于上层工作流自行判断中间态和终态。AI by zb"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        async with self._message_condition:
            while True:
                next_message = self._find_next_event_message(after_event_cursor=after_event_cursor)
                if next_message is not None:
                    return next_message

                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError(f"{description} 超时，未收到新消息。")

                await asyncio.wait_for(self._message_condition.wait(), timeout=remaining)

    async def safe_send_back(self, back_text: str, delay_seconds: float = 0) -> None:
        """在流程结束后尝试发送返回消息，不让清理动作影响主流程结果。AI by zb"""
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            await self.send_back(back_text)
        except Exception as exc:  # pragma: no cover - 清理路径只做日志兜底
            LOGGER.warning("发送返回消息失败: %s", exc)

    async def _connect_internal(self, allow_interactive_auth: bool) -> None:
        """内部连接实现，统一处理授权方式、实体解析和事件注册。AI by zb"""
        if self._proxy:
            LOGGER.info(
                "已启用代理: %s://%s:%s",
                self._proxy["proxy_type"],
                self._proxy["addr"],
                self._proxy["port"],
            )

        if allow_interactive_auth:
            await self._client.start(phone=str(self._config["phone"]))
        else:
            await self._client.connect()
            if not await self._client.is_user_authorized():
                await self._client.disconnect()
                raise RuntimeError("当前会话未授权，请先运行 `uv run .\\main.py login` 完成首次登录。")

        self._bot_entity = await self._client.get_entity(str(self._config["bot_username"]))
        LOGGER.info(
            "已解析 bot 实体: id=%s username=%s class=%s",
            getattr(self._bot_entity, "id", None),
            getattr(self._bot_entity, "username", None),
            type(self._bot_entity).__name__,
        )
        if not self._handler_registered:
            self._client.add_event_handler(
                self._handle_message_event,
                events.NewMessage(incoming=True),
            )
            self._client.add_event_handler(
                self._handle_message_event,
                events.MessageEdited(incoming=True),
            )
            self._handler_registered = True

    async def _handle_message_event(self, event: events.common.EventCommon) -> None:
        """缓存机器人发来的新消息或编辑消息，供后续工作流按条件等待匹配。AI by zb"""
        message = event.message
        async with self._message_condition:
            self._event_cursor += 1
            self._message_events.append(MessageEvent(cursor=self._event_cursor, message=message))
            self._message_condition.notify_all()

        log_prefix = "收到编辑消息" if bool(getattr(message, "edit_date", None)) else "收到消息"
        LOGGER.info("%s: %s", log_prefix, (message.raw_text or "").replace("\n", " | "))

    async def _click_button_from_recent_messages(self, text: str, history_limit: int) -> bool:
        """从最近消息中查找并点击指定按钮，成功时返回 True。AI by zb"""
        async for message in self._client.iter_messages(self._bot_entity, limit=history_limit):
            if not message.buttons:
                continue

            for row in message.buttons:
                for button in row:
                    button_text = getattr(button, "text", "")
                    if not match_keywords(button_text, [text]) or not match_keywords(text, [button_text]):
                        continue

                    raw_button = getattr(button, "button", None)
                    if isinstance(raw_button, KeyboardButton):
                        await self.send_text(button_text)
                        LOGGER.info("检测到 Reply Keyboard，改为发送同名文本: %s", button_text)
                        return True

                    try:
                        await message.click(text=button_text)
                        LOGGER.info("已点击按钮: %s", button_text)
                        return True
                    except Exception:
                        continue

        return False

    def _ensure_bot_ready(self) -> None:
        """确保机器人实体已初始化，避免在未连接时执行消息操作。AI by zb"""
        if self._bot_entity is None:
            raise RuntimeError("Telegram 服务尚未完成初始化。")

    def _find_event_match(self, keywords: list[str], after_event_cursor: int) -> Message | None:
        """在已缓存的消息事件中查找符合条件的目标消息。AI by zb"""
        for item in self._message_events:
            if item.cursor <= after_event_cursor:
                continue

            message_text = item.message.raw_text or ""
            if match_keywords(message_text, keywords):
                return item.message

        return None

    def _find_next_event_message(self, after_event_cursor: int) -> MessageEvent | None:
        """在已缓存的消息事件中找到指定游标之后的第一条消息。AI by zb"""
        for item in self._message_events:
            if item.cursor > after_event_cursor:
                return item

        return None
