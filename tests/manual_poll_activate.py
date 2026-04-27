from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import Any

import requests

# BASE_URL = "https://bot.joini.cloud"
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "lxMzdyRKcSjTzC4jMVC7bP_ORLRv1jIyLAW7NFjfSdk"
ACTION = "plus"
ACCOUNT_FILE_PATH = Path(r"d:\work\python\gpt-bot\tests\sub2api-account-20260418223743.json")
POLL_INTERVAL_SECONDS = 15
REQUEST_TIMEOUT_SECONDS = 30
MAX_ACTIVATE_ATTEMPTS = 240
MAX_RESULT_POLLS = 240
MAX_SUBMISSION_ROUNDS = 50

ACTIVATE_PATHS = {
    "plus": "/api/v1/activate/plus",
    "team": "/api/v1/activate/team",
}

ACCEPTED_STATUSES = {"queued", "already_queued", "success", "processing"}
RETRYABLE_STATUSES = {"queue_full"}
FINAL_REQUEST_STATES = {"completed", "failed", "cancelled"}


def _headers() -> dict[str, str]:
    """构造联测请求所需的统一请求头。AI by zb"""
    return {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }


def _print_response(title: str, payload: Any) -> None:
    """统一打印接口返回，便于联测时直接观察结果。AI by zb"""
    print(f"\n===== {title} =====")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _load_random_access_token() -> str:
    """从账号导出文件中随机取一个 access_token 作为本轮提交凭证。AI by zb"""
    payload = json.loads(ACCOUNT_FILE_PATH.read_text(encoding="utf-8"))
    accounts = payload.get("accounts") or []
    if not isinstance(accounts, list) or not accounts:
        raise ValueError(f"账号文件中没有可用 accounts：{ACCOUNT_FILE_PATH}")

    candidates = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        credentials = account.get("credentials") or {}
        if not isinstance(credentials, dict):
            continue
        access_token = str(credentials.get("access_token") or "").strip()
        if access_token:
            candidates.append(access_token)

    if not candidates:
        raise ValueError(f"账号文件中没有可用 access_token：{ACCOUNT_FILE_PATH}")

    return random.choice(candidates)


def _extract_plus_queue_size(payload: dict[str, Any]) -> int | None:
    """从接口返回文本中提取 Plus 队列人数，用于动态调整重试间隔。AI by zb"""
    raw_message = str(payload.get("rawMessage") or payload.get("raw_message") or payload.get("message") or "")
    match = re.search(r"Plus(?:直充)?队列[：:：]\s*(\d+)\s*人", raw_message)
    if match:
        return int(match.group(1))

    match = re.search(r"Plus直充队列已满（(\d+)人）", raw_message)
    if match:
        return int(match.group(1))

    return None


def _get_retry_interval_seconds(queue_size: int | None) -> int:
    """根据当前队列人数返回下一次提交前的等待秒数。AI by zb"""
    if queue_size is None:
        return POLL_INTERVAL_SECONDS
    if queue_size > 60:
        return 60
    if 55 <= queue_size <= 60:
        return 40
    if 51 <= queue_size <= 54:
        return 30
    if queue_size <= 50:
        return 5
    return POLL_INTERVAL_SECONDS


def _should_retry_immediately(request_result: dict[str, Any]) -> bool:
    """判断当前失败是否属于可立即重提的额度退回场景。AI by zb"""
    status = str(request_result.get("status", "")).strip()
    raw_message = str(request_result.get("rawMessage") or request_result.get("raw_message") or request_result.get("message") or "")
    if status != "invalid_access_token":
        return False
    return "直充失败" in raw_message or "额度已退回" in raw_message


def _activate_once(access_token: str) -> dict[str, Any]:
    """发送一次激活请求并返回 JSON 结果。AI by zb"""
    response = requests.post(
        f"{BASE_URL}{ACTIVATE_PATHS[ACTION]}",
        headers=_headers(),
        json={"accessToken": access_token},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _query_request(request_id: str) -> dict[str, Any]:
    """按 requestId 查询任务状态，直到拿到最终结果。AI by zb"""
    response = requests.get(
        f"{BASE_URL}/api/v1/requests/{request_id}",
        headers=_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    """执行联测轮询：抢占可提交窗口，接单后继续轮询最终结果。AI by zb"""
    if ACTION not in ACTIVATE_PATHS:
        raise ValueError(f"不支持的 ACTION: {ACTION}")

    if "替换成" in API_KEY:
        raise ValueError("请先把脚本顶部的 API_KEY 改成真实值。")

    if not ACCOUNT_FILE_PATH.exists():
        raise FileNotFoundError(f"账号文件不存在：{ACCOUNT_FILE_PATH}")

    for submission_round in range(1, MAX_SUBMISSION_ROUNDS + 1):
        print(f"\n================ 第 {submission_round} 轮提交流程开始 ================")
        access_token = _load_random_access_token()
        print(f"本轮随机选取 access_token，长度={len(access_token)}")
        request_id = ""

        for attempt in range(1, MAX_ACTIVATE_ATTEMPTS + 1):
            print(f"\n>>> 第 {attempt} 次尝试提交激活请求")
            activate_result = _activate_once(access_token=access_token)
            _print_response("激活接口返回", activate_result)

            status = str(activate_result.get("status", "")).strip()
            request_id = str(activate_result.get("requestId", "")).strip()

            if status in RETRYABLE_STATUSES:
                queue_size = _extract_plus_queue_size(activate_result) if ACTION == "plus" else None
                retry_interval = _get_retry_interval_seconds(queue_size)
                print(
                    f"当前状态={status}，Plus 队列={queue_size if queue_size is not None else '未知'}，"
                    f"{retry_interval} 秒后重试。"
                )
                time.sleep(retry_interval)
                continue

            if status == "queued":
                print("当前状态=queued，表示已入队排队中，停止重复提交并转入任务轮询。")
                break

            if status == "processing":
                print("当前状态=processing，表示已开始处理当前请求，停止重复提交并转入任务轮询。")
                break

            if status == "already_queued":
                print("当前状态=already_queued，表示已有任务在队列中，停止重复提交并转入任务轮询。")
                break

            if status == "success":
                print("激活接口已直接返回 success，流程结束。")
                return

            if request_id:
                print(f"收到 requestId={request_id}，即使状态未命中预设，也转入任务轮询。")
                break

            raise RuntimeError(f"未识别的激活返回，且没有 requestId：{activate_result}")
        else:
            raise TimeoutError("达到最大激活尝试次数，仍未等到可接单窗口。")

        if not request_id:
            raise RuntimeError("激活接口未返回 requestId，无法继续轮询任务状态。")

        for poll_index in range(1, MAX_RESULT_POLLS + 1):
            print(f"\n>>> 第 {poll_index} 次轮询任务状态 requestId={request_id}")
            request_result = _query_request(request_id)
            _print_response("任务状态接口返回", request_result)

            state = str(request_result.get("state", "")).strip()
            status = str(request_result.get("status", "")).strip()
            if state not in FINAL_REQUEST_STATES:
                print(f"当前 state={state}，任务未结束，{POLL_INTERVAL_SECONDS} 秒后继续查询。")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            if state == "completed" and status == "success":
                print("任务已成功完成，脚本结束。")
                return

            if _should_retry_immediately(request_result):
                print("检测到“直充失败，额度已退回”场景，立即开始下一轮重新提交。")
                break

            print(f"任务已结束，最终 state={state}，status={status}，脚本结束。")
            return
    else:
        raise TimeoutError("达到最大提交流程轮数，仍未完成成功激活。")


if __name__ == "__main__":
    main()
