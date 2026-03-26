from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable
from pathlib import Path

import uvicorn

from api_server import create_app
from app_config import load_config, validate_api_runtime_config
from daemon_manager import get_daemon_status, start_daemon, stop_daemon
from telegram_service import TelegramBotService


LOGGER = logging.getLogger("telegram_button_automation")


def setup_logging() -> None:
    """初始化统一日志格式，便于观察服务运行与工作流执行情况。AI by zb"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        force=True,
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数，支持登录、前台服务与后台服务管理。AI by zb"""
    parser = argparse.ArgumentParser(description="Telegram 按钮自动化 API 服务")
    parser.add_argument("command", nargs="?", choices=["serve", "login", "daemon"], default="serve")
    parser.add_argument("daemon_action", nargs="?", choices=["start", "stop", "status"])
    parser.add_argument("--config", default="config.json", help="配置文件路径，默认读取当前目录下的 config.json")
    parser.add_argument("--host", help="覆盖配置文件中的 API 监听地址")
    parser.add_argument("--port", type=int, help="覆盖配置文件中的 API 监听端口")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="启动服务时禁止交互式登录，适合后台运行",
    )
    args = parser.parse_args()
    if args.command == "daemon" and not args.daemon_action:
        parser.error("daemon 命令必须指定 start、stop 或 status。")
    return args


async def run_login(config_path: Path) -> None:
    """执行一次交互式登录，并把授权后的 Telegram 会话保存在本地。AI by zb"""
    config = load_config(config_path)
    service = TelegramBotService(config=config, config_path=config_path)
    await service.interactive_login()


async def run_serve(config_path: Path, host: str | None, port: int | None, non_interactive: bool) -> None:
    """启动前台 API 服务，并在生命周期内保持 Telegram 会话在线。AI by zb"""
    config = load_config(config_path)
    validate_api_runtime_config(config)

    api_config = config["api"]
    app = create_app(
        config=config,
        config_path=config_path,
        allow_interactive_auth=not non_interactive,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app=app,
            host=host or str(api_config["host"]),
            port=port or int(api_config["port"]),
            log_level="info",
            timeout_graceful_shutdown=3,
        )
    )
    await server.serve()


def run_async_entrypoint(awaitable: Awaitable[None], action_name: str) -> None:
    """统一运行异步入口，并在用户主动中断时以日志方式优雅退出。AI by zb"""
    try:
        asyncio.run(awaitable)
    except KeyboardInterrupt:
        LOGGER.info("已收到 Ctrl+C，%s已停止。", action_name)


def main() -> None:
    """程序主入口，负责分发 CLI 命令并协调不同运行模式。AI by zb"""
    setup_logging()
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()

    if args.command == "login":
        run_async_entrypoint(run_login(config_path), action_name="登录流程")
        return

    if args.command == "daemon":
        if args.daemon_action == "start":
            result = start_daemon(
                config_path=config_path,
                script_path=Path(__file__).resolve(),
                host=args.host,
                port=args.port,
            )
            LOGGER.info("后台服务已启动，PID: %s，日志: %s", result["pid"], result["log_file"])
            return

        if args.daemon_action == "stop":
            result = stop_daemon(config_path=config_path)
            LOGGER.info(result["message"])
            return

        status = get_daemon_status(config_path=config_path)
        if status["running"]:
            LOGGER.info("后台服务运行中，PID: %s，日志: %s", status["pid"], status["log_file"])
        else:
            LOGGER.info("后台服务未运行，日志文件: %s", status["log_file"])
        return

    run_async_entrypoint(
        run_serve(
            config_path=config_path,
            host=args.host,
            port=args.port,
            non_interactive=args.non_interactive,
        ),
        action_name="前台服务",
    )


if __name__ == "__main__":
    main()
