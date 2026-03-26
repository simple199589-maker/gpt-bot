from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "history_limit": 20,
    "proxy": {
        "enabled": False,
        "proxy_type": "socks5",
        "addr": "127.0.0.1",
        "port": 7890,
        "username": "",
        "password": "",
        "rdns": True,
    },
    "api": {
        "host": "127.0.0.1",
        "port": 8000,
        "api_key": "",
        "queue_max_size": 10,
    },
    "workflow": {
        "prompt_timeout_seconds": 60,
        "result_timeout_seconds": 180,
        "return_delay_seconds": 1,
        "back_text": "⬅️ 返回",
        "buttons": {
            "activate_plus": "⚡️ 激活plus母号",
            "activate_team": "👥 激活team母号",
            "balance": "💰 查余额",
            "redeem": "🎟 兑换卡密",
        },
        "prompts": {
            "access_token": [
                "请发送 accessToken",
                "请发送 accessToken 或付款链接",
            ],
            "redeem_code": [
                "请发送卡密",
            ],
        },
        "result_keywords": {
            "activation_progress": [
                "已收到请求",
                "正在生成",
                "生成支付链接",
                "正在处理",
                "处理中",
                "当前状态",
                "次查询",
                "请稍候",
                "请等待",
            ],
            "activation_cancelled": [
                "已取消",
            ],
            "activation_success": [
                "升级成功",
                "激活成功",
            ],
            "activation_failure": [
                "Token 无效或已过期",
                "Token 无效",
                "额度已退回",
                "重新获取后再试",
                "激活失败",
            ],
            "balance": [
                "余额：",
                "余额:",
            ],
            "redeem_progress": [
                "已收到请求",
                "正在处理",
                "处理中",
                "当前状态",
                "次查询",
                "请稍候",
                "请等待",
            ],
            "redeem_cancelled": [
                "已取消",
            ],
            "redeem_success": [
                "充值成功",
            ],
            "redeem_failure": [
                "你当前余额不少于 3 次",
                "暂不符合公共卡密领取条件",
                "充值码无效",
            ],
        },
    },
    "daemon": {
        "pid_file": ".runtime/gpt-bot.pid",
        "log_file": ".runtime/gpt-bot.log",
    },
}


def _merge_defaults(target: dict[str, Any], defaults: dict[str, Any]) -> None:
    """递归填充默认配置，避免遗漏新增配置项。AI by zb"""
    for key, value in defaults.items():
        if key not in target:
            target[key] = value
            continue

        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_defaults(target[key], value)


def resolve_local_path(base_dir: Path, raw_path: str) -> Path:
    """将相对路径解析为相对于配置文件目录的绝对路径。AI by zb"""
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_config(config_path: Path) -> dict[str, Any]:
    """读取配置文件并补齐当前版本所需的默认项。AI by zb"""
    if not config_path.exists():
        raise FileNotFoundError(f"未找到配置文件: {config_path}")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    required_fields = ["api_id", "api_hash", "phone", "bot_username"]
    missing_fields = [field for field in required_fields if not config.get(field)]
    if missing_fields:
        missing_text = ", ".join(missing_fields)
        raise ValueError(f"配置缺少必要字段: {missing_text}")

    _merge_defaults(config, DEFAULT_CONFIG)

    env_api_key = os.environ.get("GPT_BOT_API_KEY", "").strip()
    if env_api_key and not str(config["api"].get("api_key", "")).strip():
        config["api"]["api_key"] = env_api_key

    return config


def validate_api_runtime_config(config: dict[str, Any]) -> None:
    """校验 API 服务运行所需的关键配置，缺失时直接报错。AI by zb"""
    api_config = config.get("api", {})
    api_key = str(api_config.get("api_key", "")).strip()
    if not api_key or api_key == "replace_with_your_api_key":
        raise ValueError("请先在 config.json 的 api.api_key 中填写 API Key，或设置 GPT_BOT_API_KEY 环境变量。")

    queue_max_size = int(api_config.get("queue_max_size", 0))
    if queue_max_size <= 0:
        raise ValueError("api.queue_max_size 必须大于 0。")

    port = int(api_config.get("port", 0))
    if port <= 0 or port > 65535:
        raise ValueError("api.port 必须是有效端口号。")


def get_daemon_paths(config: dict[str, Any], config_path: Path) -> tuple[Path, Path]:
    """根据配置解析后台服务使用的 PID 与日志文件路径。AI by zb"""
    daemon_config = config.get("daemon", {})
    base_dir = config_path.parent
    pid_file = resolve_local_path(base_dir, str(daemon_config.get("pid_file", ".runtime/gpt-bot.pid")))
    log_file = resolve_local_path(base_dir, str(daemon_config.get("log_file", ".runtime/gpt-bot.log")))
    return pid_file, log_file


def build_proxy_config(config: dict[str, Any]) -> dict[str, Any] | None:
    """将配置文件中的代理项转换为 Telethon 可识别的格式。AI by zb"""
    proxy = config.get("proxy")
    if not isinstance(proxy, dict) or not proxy.get("enabled"):
        return None

    proxy_type = str(proxy.get("proxy_type", "")).strip().lower()
    addr = str(proxy.get("addr", "")).strip()
    port = proxy.get("port")

    if not proxy_type or not addr or not port:
        raise ValueError("启用代理时，proxy_type、addr、port 都必须填写。")

    proxy_config: dict[str, Any] = {
        "proxy_type": proxy_type,
        "addr": addr,
        "port": int(port),
    }

    username = str(proxy.get("username", "")).strip()
    password = str(proxy.get("password", "")).strip()
    if username:
        proxy_config["username"] = username
    if password:
        proxy_config["password"] = password
    if "rdns" in proxy:
        proxy_config["rdns"] = bool(proxy.get("rdns"))

    return proxy_config


def ensure_proxy_dependencies(proxy: dict[str, Any] | None) -> None:
    """在启用代理时提前校验代理依赖，避免底层抛出难读错误。AI by zb"""
    if not proxy:
        return

    has_python_socks = importlib.util.find_spec("python_socks") is not None
    has_pysocks = importlib.util.find_spec("socks") is not None
    if not has_python_socks and not has_pysocks:
        raise ModuleNotFoundError(
            "已启用代理，但当前环境缺少代理依赖。请先执行 `uv sync`，"
            "确保 `python-socks` / `PySocks` 已安装，然后重新运行脚本。"
        )


def normalize_text(text: str) -> str:
    """统一文本匹配格式，减少大小写和首尾空白带来的干扰。AI by zb"""
    return text.replace("\ufe0f", "").replace("\u200d", "").casefold().strip()


def match_keywords(message_text: str, keywords: list[str]) -> bool:
    """判断消息文本是否命中任意一个关键词。AI by zb"""
    normalized_text = normalize_text(message_text)
    return any(normalize_text(keyword) in normalized_text for keyword in keywords if keyword)
