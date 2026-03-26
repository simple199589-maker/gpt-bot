from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ActivateRequest(BaseModel):
    """定义激活接口的请求体，统一接收 accessToken 参数。AI by zb"""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    access_token: str = Field(..., alias="accessToken", min_length=1)


class RedeemRequest(BaseModel):
    """定义兑换接口的请求体，统一接收卡密参数。AI by zb"""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    card_code: str = Field(..., alias="cardCode", min_length=1)


class WorkflowResponse(BaseModel):
    """定义统一的工作流响应结构，便于外部系统稳定消费。AI by zb"""

    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(..., alias="requestId")
    action: str
    success: bool
    status: str
    message: str
    raw_message: str = Field(..., alias="rawMessage")
    balance: int | None = None
    queue_position: int = Field(..., alias="queuePosition")
    queued_at: str = Field(..., alias="queuedAt")


class ServiceStatusResponse(BaseModel):
    """定义服务状态接口的返回结构，暴露连接状态与排队情况。AI by zb"""

    model_config = ConfigDict(populate_by_name=True)

    connected_to_telegram: bool = Field(..., alias="connectedToTelegram")
    queue_size: int = Field(..., alias="queueSize")
    queue_limit: int = Field(..., alias="queueLimit")
    active_action: str | None = Field(default=None, alias="activeAction")
    active_request_id: str | None = Field(default=None, alias="activeRequestId")


class RequestStatusResponse(BaseModel):
    """定义按 requestId 查询任务状态时的统一返回结构。AI by zb"""

    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(..., alias="requestId")
    action: str
    state: str
    queue_position: int | None = Field(default=None, alias="queuePosition")
    queued_at: str = Field(..., alias="queuedAt")
    started_at: str | None = Field(default=None, alias="startedAt")
    finished_at: str | None = Field(default=None, alias="finishedAt")
    success: bool | None = None
    status: str | None = None
    message: str | None = None
    raw_message: str | None = Field(default=None, alias="rawMessage")
    balance: int | None = None
    error_message: str | None = Field(default=None, alias="errorMessage")
    error_type: str | None = Field(default=None, alias="errorType")


class HealthResponse(BaseModel):
    """定义轻量健康检查返回结构，便于外部探活。AI by zb"""

    status: str
