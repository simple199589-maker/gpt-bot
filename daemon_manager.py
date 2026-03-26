from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app_config import get_daemon_paths, load_config, validate_api_runtime_config


def start_daemon(config_path: Path, script_path: Path, host: str | None = None, port: int | None = None) -> dict[str, Any]:
    """启动后台服务进程，并将日志与 PID 写入配置指定的位置。AI by zb"""
    config = load_config(config_path)
    validate_api_runtime_config(config)

    pid_file, log_file = get_daemon_paths(config=config, config_path=config_path)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    current_status = get_daemon_status(config_path)
    if current_status["running"]:
        raise RuntimeError(f"后台服务已在运行，PID: {current_status['pid']}")

    if pid_file.exists():
        pid_file.unlink()

    command = [
        sys.executable,
        str(script_path),
        "serve",
        "--config",
        str(config_path),
        "--non-interactive",
    ]
    if host:
        command.extend(["--host", host])
    if port:
        command.extend(["--port", str(port)])

    process = _spawn_detached_process(command=command, workdir=config_path.parent, log_file=log_file)
    time.sleep(2)
    if process.poll() is not None:
        raise RuntimeError(f"后台服务启动失败，请查看日志: {log_file}")

    pid_file.write_text(str(process.pid), encoding="utf-8")
    return {
        "pid": process.pid,
        "pid_file": str(pid_file),
        "log_file": str(log_file),
    }


def stop_daemon(config_path: Path) -> dict[str, Any]:
    """停止后台服务进程，并清理已写入的 PID 文件。AI by zb"""
    status = get_daemon_status(config_path)
    if not status["running"]:
        return {
            "running": False,
            "message": "后台服务未运行。",
        }

    pid = int(status["pid"])
    _terminate_process(pid)
    for _ in range(20):
        if not _is_process_running(pid):
            break
        time.sleep(0.2)

    pid_file = Path(status["pid_file"])
    if pid_file.exists():
        pid_file.unlink()

    return {
        "running": False,
        "message": f"后台服务已停止，PID: {pid}",
    }


def get_daemon_status(config_path: Path) -> dict[str, Any]:
    """读取后台服务 PID 文件并判断目标进程当前是否仍然存活。AI by zb"""
    config = load_config(config_path)
    pid_file, log_file = get_daemon_paths(config=config, config_path=config_path)
    pid = _read_pid(pid_file)
    running = pid is not None and _is_process_running(pid)

    if not running and pid_file.exists():
        pid_file.unlink()

    return {
        "running": running,
        "pid": pid,
        "pid_file": str(pid_file),
        "log_file": str(log_file),
    }


def _spawn_detached_process(command: list[str], workdir: Path, log_file: Path) -> subprocess.Popen[str]:
    """以脱离终端的方式启动后台进程，并把标准输出重定向到日志文件。AI by zb"""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    log_handle = log_file.open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "cwd": str(workdir),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "text": True,
    }

    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **kwargs)
    log_handle.close()
    return process


def _read_pid(pid_file: Path) -> int | None:
    """读取 PID 文件中的进程号，文件损坏时返回 None。AI by zb"""
    if not pid_file.exists():
        return None

    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _is_process_running(pid: int) -> bool:
    """通过平台兼容的方式判断目标进程是否仍然存活。AI by zb"""
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_process(pid: int) -> None:
    """按平台选择更稳妥的方式结束后台服务及其子进程。AI by zb"""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return

    os.kill(pid, signal.SIGTERM)
