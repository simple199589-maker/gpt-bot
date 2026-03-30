# API 简洁文档

本文档基于项目 `README.md` 整理，并已对照线上 `OpenAPI` 入口 `https://bot.joini.cloud/openapi.json` 校验。

## 基础信息

- Host：`https://bot.joini.cloud`
- 内容类型：`application/json`
- 鉴权方式：
  - `X-API-Key: your_api_key`
  - `Authorization: Bearer your_api_key`
- 免鉴权接口：
  - `GET /healthz`

## 通用说明

- 业务接口会进入串行队列执行，避免 Telegram 会话串台。
- 当等待队列已满时，服务会返回 `429`。
- 如果客户端请求超时或断开，可继续通过任务状态接口轮询最终结果。

## 通用响应结构

### WorkflowResponse

适用于：

- `POST /api/v1/activate/plus`
- `POST /api/v1/activate/team`
- `GET /api/v1/balance`
- `POST /api/v1/redeem`

核心字段：

- `requestId`：请求 ID
- `action`：动作名称
- `success`：是否成功
- `status`：结果状态
- `message`：摘要消息
- `rawMessage`：原始返回文本
- `balance`：余额，部分接口可能返回
- `queuePosition`：进入队列时的位置
- `queuedAt`：排队时间

### RequestStatusResponse

适用于：

- `GET /api/v1/requests/{request_id}`

核心字段：

- `requestId`：请求 ID
- `action`：动作名称
- `state`：任务状态，常见值为 `queued`、`running`、`completed`、`failed`、`cancelled`
- `queuePosition`：当前排队位置
- `queuedAt`：入队时间
- `startedAt`：开始时间
- `finishedAt`：结束时间
- `success`：是否成功
- `status`：结果状态
- `message`：摘要消息
- `rawMessage`：原始返回文本
- `balance`：余额
- `errorMessage`：错误消息
- `errorType`：错误类型

### ServiceStatusResponse

适用于：

- `GET /api/v1/status`

核心字段：

- `connectedToTelegram`：是否已连接 Telegram
- `queueSize`：当前队列长度
- `queueLimit`：队列上限
- `activeAction`：当前执行中的动作
- `activeRequestId`：当前执行中的请求 ID

### CancelResponse

适用于：

- `POST /api/v1/cancel`

核心字段：

- `action`：固定为 `cancel`
- `success`：是否发送成功
- `message`：摘要消息
- `sentText`：实际发送给机器人的文本

## 接口列表

### 1. 激活 Plus 母号

- 方法：`POST`
- 路径：`/api/v1/activate/plus`
- 鉴权：需要

请求体：

```json
{
  "accessToken": "your_access_token"
}
```

说明：

- 触发 Telegram 菜单：`⚡️ 激活plus母号`
- 返回结构：`WorkflowResponse`

### 2. 激活 Team 母号

- 方法：`POST`
- 路径：`/api/v1/activate/team`
- 鉴权：需要

请求体：

```json
{
  "accessToken": "your_access_token"
}
```

说明：

- 触发 Telegram 菜单：`👥 激活team母号`
- 返回结构：`WorkflowResponse`

### 3. 查询余额

- 方法：`GET`
- 路径：`/api/v1/balance`
- 鉴权：需要

说明：

- 触发 Telegram 菜单：`💰 查余额`
- 返回结构：`WorkflowResponse`

### 4. 兑换卡密

- 方法：`POST`
- 路径：`/api/v1/redeem`
- 鉴权：需要

请求体：

```json
{
  "cardCode": "your_card_code"
}
```

说明：

- 触发 Telegram 菜单：`🎟 兑换卡密`
- 返回结构：`WorkflowResponse`
- 若机器人返回“充值成功”、“充值完成”或“已增加 x 次 / 增加 x 次”这类字样，接口会返回成功结果，`status` 为 `success`
- 除处理中提示外，其余兑换返回一律按失败处理，`status` 为 `failed`

### 5. 取消当前菜单

- 方法：`POST`
- 路径：`/api/v1/cancel`
- 鉴权：需要

说明：

- 直接向 Telegram bot 发送 `⬅️ 返回`
- 不进入工作流队列
- 不等待 bot 返回结果
- 返回结构：`CancelResponse`

### 6. 服务状态

- 方法：`GET`
- 路径：`/api/v1/status`
- 鉴权：需要

说明：

- 用于查看 Telegram 连接状态与队列状态
- 返回结构：`ServiceStatusResponse`

### 7. 查询任务状态

- 方法：`GET`
- 路径：`/api/v1/requests/{request_id}`
- 鉴权：需要

路径参数：

- `request_id`：任务请求 ID

说明：

- 用于轮询异步任务执行状态和最终结果
- 返回结构：`RequestStatusResponse`

### 8. 健康检查

- 方法：`GET`
- 路径：`/healthz`
- 鉴权：不需要

响应体：

```json
{
  "status": "ok"
}
```

## 最小调用示例

### 激活 Plus

```bash
curl -X POST "https://bot.joini.cloud/api/v1/activate/plus" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d "{\"accessToken\":\"your_access_token\"}"
```

### 查询余额

```bash
curl "https://bot.joini.cloud/api/v1/balance" \
  -H "X-API-Key: your_api_key"
```

### 查询任务状态

```bash
curl "https://bot.joini.cloud/api/v1/requests/your_request_id" \
  -H "X-API-Key: your_api_key"
```

### 发送取消

```bash
curl -X POST "https://bot.joini.cloud/api/v1/cancel" \
  -H "X-API-Key: your_api_key"
```

### 健康检查

```bash
curl "https://bot.joini.cloud/healthz"
```

## 备注

- README 中“按 requestId 查询任务状态”是说明性写法，线上实际 OpenAPI 路径参数名为 `request_id`。
- 若需要完整字段定义，可直接查看 `https://bot.joini.cloud/openapi.json`。
- 服务端现已支持通过 `scheduled_redeem` 配置在每日指定时刻自动执行一次与 `POST /api/v1/redeem` 等价的兑换工作流，例如 `00:00`、`00:05` 自动提交固定 `cardCode`。
